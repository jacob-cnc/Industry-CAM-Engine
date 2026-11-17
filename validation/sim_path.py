"""The sim path from LinuxCNC's own interpreter (tool-graphic plan 2026-11-13, T4).

The program goes through rs274 (as the cycle time and cut sections do) with the
machine's INI and tool table. Its canonical moves are what the machine will
run: cutter compensation (G41 / G42) already applied, G76 / G33 threading as
LinuxCNC expands it, each tool change where the T word / M6 puts it. Every
position is the CONTROLLED POINT in program (work) coordinates - the imaginary
tip for Q1-Q8, the nose centre for Q9 - which is the same point the live
graphic places at the DRO position. X is a radius.

Source lines: each program line is given its line number as an N word before
interpreting (rs274 prints the N of the block that made each canonical call),
so every move knows the line it came from - no matching back by coordinates.

Under cutter compensation rs274 holds each move until it has read the next
motion block (to find the corner), so it prints it under THAT block's N. Those
moves are given back to the motion block before it (owner(N) = the last line
before N with an X / Z / I / K word), so the highlighted line is the block that
made the move.

Precision: rs274 prints 4 decimals (inches), so positions are within .00005.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np
import shapely
from shapely.geometry import LineString

from validation.cut_regions import _canon_arc_points
from validation.cycle_time import _canon, prepare

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MM = 25.4

Point = Tuple[float, float]            # (r, z)


@dataclass(frozen=True)
class SimSegment:
    """One canonical move: kind rapid | feed | arc | thread."""
    kind: str
    tool: int                          # tool in the spindle (0 = none changed in yet)
    tool_offset: Optional[Tuple[float, float]]   # active (x radius, z) offset, None = none applied
    line_idx: int                      # 0-based source line, -1 unknown
    pts: Tuple[Point, ...]             # controlled-point path, start included

    def resampled(self, per_inch: float, minimum: int = 3) -> List[Point]:
        """Evenly spaced points along the path (start and end included)."""
        line = LineString(self.pts)
        n = max(minimum, int(line.length * per_inch))
        at = shapely.line_interpolate_point(line, np.linspace(0.0, 1.0, n), normalized=True)
        return [tuple(p) for p in shapely.get_coordinates(at).tolist()]


@dataclass
class SimPath:
    segments: List[SimSegment] = field(default_factory=list)
    problem: str = ""                  # why the interpreter stopped early ("" = ran to the end)


_LEAD_N = re.compile(r"^\s*N\d+\s*", re.I)


def number_lines(program: str) -> str:
    """Each code line gets N<line number> (1-based). Existing N words are
    replaced; o-word and % lines are left alone (rs274 rejects N there)."""
    out = []
    for i, line in enumerate(program.splitlines()):
        body = _LEAD_N.sub("", line)
        s = body.strip()
        if not s or s.startswith("%") or s[0] in "oO":
            out.append(body)
        else:
            out.append(f"N{i + 1} {body}")
    return "\n".join(out) + "\n"


_CALL = re.compile(r"^\s*\d+\s+N(\S+)\s+(\w+)\((.*)\)\s*$")


def _floats(args: str) -> List[float]:
    return [float(a) for a in re.split(r"[,\s]+", args.strip()) if a]


_MOTION_WORD = re.compile(r"[XZIK]\s*[-+.\d]", re.I)


def _motion_lines(program: str) -> List[int]:
    """0-based lines with an axis or arc-centre word (comments removed)."""
    out = []
    for i, line in enumerate(program.splitlines()):
        code = re.sub(r"\([^)]*\)", "", line.split(";")[0])
        if _MOTION_WORD.search(code):
            out.append(i)
    return out


def parse_sim_canon(canon: str, program: str = "") -> List[SimSegment]:
    """Segments from rs274 canonical output of a number_lines() program.
    program: the source, to give comp-delayed moves back to their block."""
    import bisect
    motion = _motion_lines(program)
    comp = False
    segs: List[SimSegment] = []
    pos: Optional[Point] = None
    scale = 1.0
    selected = tool = 0
    offset: Optional[Tuple[float, float]] = None
    synced = False
    for raw in canon.splitlines():
        m = _CALL.match(raw)
        if not m:
            continue
        n, name, args = m.groups()
        line_idx = int(n) - 1 if n.isdigit() else -1
        if comp and line_idx >= 0 and name in ("STRAIGHT_FEED", "STRAIGHT_TRAVERSE", "ARC_FEED"):
            k = bisect.bisect_left(motion, line_idx) - 1
            line_idx = motion[k] if k >= 0 else line_idx
        if name == "COMMENT" and "cutter radius compensation" in args:
            comp = "compensation on" in args
        elif name == "USE_LENGTH_UNITS":
            scale = 1.0 / MM if "MM" in args else 1.0
        elif name == "SELECT_TOOL":
            selected = int(args)
        elif name == "CHANGE_TOOL":
            tool, offset = selected, None
        elif name == "USE_TOOL_LENGTH_OFFSET":
            v = _floats(args.split(",")[0])
            offset = (v[0] * scale, v[2] * scale)
        elif name.startswith("START_SPEED_FEED_SYNC"):
            synced = True
        elif name.startswith("STOP_SPEED_FEED_SYNC"):
            synced = False
        elif name in ("STRAIGHT_TRAVERSE", "STRAIGHT_FEED"):
            v = _floats(args)
            new = (v[0] * scale, v[2] * scale)
            if pos is not None and new != pos:
                kind = "rapid" if name == "STRAIGHT_TRAVERSE" else ("thread" if synced else "feed")
                segs.append(SimSegment(kind, tool, offset, line_idx, (pos, new)))
            pos = new
        elif name == "ARC_FEED" and pos is not None:
            ze, xe, zc, xc, rot = _floats(args)[:5]       # G18: first axis Z, second X
            end, centre = (xe * scale, ze * scale), (xc * scale, zc * scale)
            pts = tuple(_canon_arc_points(pos, end, centre, rot))
            segs.append(SimSegment("arc", tool, offset, line_idx, pts))
            pos = end
    return segs


def sim_path(gcode: str, ini_path: str, tool_table: str) -> SimPath:
    """The program's path as LinuxCNC will run it. If the interpreter stops
    early (an error the machine would also stop at) the path up to there is
    returned with the reason in .problem."""
    program, _tc, _m0, _m1 = prepare(gcode)
    canon, problem = _canon(number_lines(program), os.path.abspath(ini_path),
                            os.path.abspath(tool_table))
    return SimPath(parse_sim_canon(canon, program), problem)


def interpreter_available() -> bool:
    import shutil
    return shutil.which("rs274") is not None
