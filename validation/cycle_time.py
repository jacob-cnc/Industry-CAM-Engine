"""Cycle-time estimate from the G-code as LinuxCNC runs it (owner 2026-11-12).

The program goes through LinuxCNC's own interpreter (rs274, as the cut-section
and rapid checks do) with the machine's INI and tool table. Its canonical
moves are timed:

  rapid   at the lowest of [TRAJ] MAX_LINEAR_VELOCITY and each axis's
          MAX_VELOCITY for the move's direction, with a trapezoidal accel /
          decel (same caps on acceleration) - every rapid starts and stops
  feed    feed per rev x programmed spindle speed (G95), or the programmed
          units/min (G94); threading (START_SPEED_FEED_SYNCH) at pitch x RPM;
          capped by the same velocity limits; blended (no accel penalty)
  dwell   as programmed

Not timed, counted: manual stops (tool changes, M0, optional M1) - the
operator decides how long they take. The spindle is manual on this lathe, so
the estimate assumes the PROGRAMMED speed.

Before interpreting, the runtime tool checks (o-word if/endif) and M0 / M1 are
taken out (standalone rs274 ends at a stop); they are counted instead.

Also gives, per program line, the time left after it - for the Run tab.
X in the canonical output is a radius (lathe); velocities / accelerations from
the INI are in machine units (radius for X).
"""
from __future__ import annotations

import configparser
import math
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Dict, List, Optional

_STOP = re.compile(r"\bM0?([01])\b(?!\d)", re.I)


@dataclass
class CycleEstimate:
    total_s: float = 0.0
    cutting_s: float = 0.0        # feed moves incl. threading
    rapid_s: float = 0.0
    dwell_s: float = 0.0
    tool_changes: int = 0
    program_stops: int = 0        # M0 (incl. the tool-change stops)
    optional_stops: int = 0       # M1
    # 0-based source line -> estimated seconds still to run AFTER that line
    remaining_after_line: Dict[int, float] = field(default_factory=dict)
    complete: bool = True
    problem: str = ""             # why the estimate stopped early, if it did

    def text(self) -> str:
        t = fmt_duration(self.total_s)
        stops = []
        if self.tool_changes:
            stops.append(f"{self.tool_changes} tool change{'s' if self.tool_changes > 1 else ''}")
        m0 = self.program_stops - self.tool_changes
        if m0 > 0:
            stops.append(f"{m0} stop{'s' if m0 > 1 else ''}")
        if self.optional_stops:
            stops.append(f"{self.optional_stops} optional stop{'s' if self.optional_stops > 1 else ''}")
        s = f"~{t}" + (f" + {', '.join(stops)}" if stops else "")
        if not self.complete:
            s += " (incomplete)"
        return s


def fmt_duration(seconds: float) -> str:
    s = int(round(seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


@dataclass
class _Limits:
    traj_v: float
    traj_a: float
    vx: float
    ax: float
    vz: float
    az: float


def _limits(ini_path: str) -> _Limits:
    cp = configparser.ConfigParser(strict=False, inline_comment_prefixes=("#", ";"))
    cp.optionxform = str
    with open(ini_path) as fh:
        cp.read_string(fh.read())

    def num(sec, key, default):
        try:
            return float(cp.get(sec, key))
        except Exception:
            return default
    tv = num("TRAJ", "MAX_LINEAR_VELOCITY", 1e9)
    ta = num("TRAJ", "MAX_LINEAR_ACCELERATION", 1e9)
    return _Limits(tv, ta, num("AXIS_X", "MAX_VELOCITY", tv), num("AXIS_X", "MAX_ACCELERATION", ta),
                   num("AXIS_Z", "MAX_VELOCITY", tv), num("AXIS_Z", "MAX_ACCELERATION", ta))


def _cap(dr: float, dz: float, vmax: float, ax_lim: float, az_lim: float) -> float:
    """Largest vector value along (dr, dz) that keeps each axis within its limit."""
    L = math.hypot(dr, dz)
    if L < 1e-12:
        return vmax
    caps = [vmax]
    if abs(dr) > 1e-12:
        caps.append(ax_lim * L / abs(dr))
    if abs(dz) > 1e-12:
        caps.append(az_lim * L / abs(dz))
    return min(caps)


def _trapezoid(d: float, v: float, a: float) -> float:
    """Time to travel d from rest to rest at max speed v, acceleration a."""
    if d <= 0:
        return 0.0
    if d >= v * v / a:
        return d / v + v / a
    return 2.0 * math.sqrt(d / a)


def prepare(gcode: str):
    """(program for the interpreter, tool changes, M0 count, M1 count): runtime
    tool checks (o-word if .. endif) and M0 / M1 taken out, counted. Line count
    is kept (removed text becomes an empty line) so line numbers still match."""
    out, skip = [], None
    m0 = m1 = tc = 0
    for line in gcode.splitlines():
        code = line.split(";")[0]
        m = re.match(r"\s*(o\d+)\s+if\b", code, re.I)
        if skip is None and m:
            skip = m.group(1).lower()
            out.append("")
            continue
        if skip:
            if re.match(rf"\s*{skip}\s+endif\b", code, re.I):
                skip = None
            out.append("")
            continue
        if re.search(r"\bM0?6\b(?!\d)", code, re.I):
            tc += 1
        stop = _STOP.search(code)
        if stop:
            if stop.group(1) == "0":
                m0 += 1
            else:
                m1 += 1
            line = _STOP.sub("", code) + ((";" + line.split(";", 1)[1]) if ";" in line else "")
        out.append(line)
    return "\n".join(out) + "\n", tc, m0, m1


def _canon(program: str, ini_path: str, tool_table: str) -> tuple:
    exe = shutil.which("rs274")
    if exe is None:
        return "", "LinuxCNC's rs274 interpreter is not installed"
    with tempfile.TemporaryDirectory() as d:
        prog = os.path.join(d, "p.ngc")
        with open(prog, "w") as fh:
            fh.write(program)
        var = os.path.join(d, "v.var")
        with open(var, "w") as fh:
            fh.write("5220\t1.000000\n")
        tbl = os.path.join(d, "tool.tbl")
        shutil.copyfile(tool_table, tbl)
        out = os.path.join(d, "canon.txt")
        p = subprocess.run([exe, "-i", ini_path, "-t", tbl, "-v", var, prog, out],
                           stdin=subprocess.DEVNULL, capture_output=True, text=True,
                           timeout=60, cwd=d)
        canon = open(out).read() if os.path.exists(out) else ""
    problem = ""
    if "PROGRAM_END" not in canon:
        msgs = [l for l in (p.stdout + p.stderr).splitlines()
                if l.strip() and not re.match(r"\s*(\d+ =|enter choice)", l)]
        problem = msgs[-1].strip() if msgs else "the interpreter stopped early"
    return canon, problem


def _arc_length(start, end, centre, rot) -> float:
    from validation.cut_regions import _canon_arc_points
    pts = _canon_arc_points(start, end, centre, rot)
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


def estimate(gcode: str, ini_path: str, tool_table: str) -> CycleEstimate:
    """Cycle-time estimate of a whole program (see module doc)."""
    ini_path, tool_table = os.path.abspath(ini_path), os.path.abspath(tool_table)
    program, tc, m0, m1 = prepare(gcode)
    est = CycleEstimate(tool_changes=tc, program_stops=m0, optional_stops=m1)
    lim = _limits(ini_path)
    canon, problem = _canon(program, ini_path, tool_table)
    if problem:
        est.complete, est.problem = False, problem
    per_rev, feed, rpm, sync_pitch = False, 0.0, 0.0, None
    pos = None
    t = 0.0
    time_at_line: Dict[int, float] = {}
    # Source lines by N word, walked forward: N numbers restart in every block,
    # but the interpreter's output is in program order.
    numbered = [(i, m.group(1)) for i, l in enumerate(gcode.splitlines())
                for m in [re.match(r"\s*N(\d+)\b", l)] if m]
    cursor = 0
    for raw in canon.splitlines():
        parts = raw.split(None, 2)
        if len(parts) < 3:
            continue
        line_no = None
        if parts[1].startswith("N"):
            n = parts[1][1:]
            for k in range(cursor, len(numbered)):
                if numbered[k][1] == n:
                    cursor, line_no = k, numbered[k][0]
                    break
            body = parts[2]
        else:
            body = parts[1] + " " + parts[2]
        m = re.match(r"(\w+)\((.*)\)", body.strip())
        if not m:
            continue
        name, args = m.group(1), [a.strip() for a in m.group(2).split(",")] if m.group(2) else []
        try:
            vals = [float(a) for a in args]
        except ValueError:
            vals = []
        if name == "SET_FEED_MODE" and len(vals) >= 2:
            per_rev = vals[1] == 1
        elif name == "SET_FEED_RATE" and vals:
            feed = vals[0]
        elif name == "SET_SPINDLE_SPEED" and len(vals) >= 2:
            rpm = vals[1]
        elif name == "START_SPEED_FEED_SYNCH" and len(vals) >= 2:
            sync_pitch = vals[1]
        elif name == "STOP_SPEED_FEED_SYNCH":
            sync_pitch = None
        elif name == "DWELL" and vals:
            t += vals[0]
            est.dwell_s += vals[0]
        elif name in ("STRAIGHT_TRAVERSE", "STRAIGHT_FEED") and len(vals) >= 3:
            new = (vals[0], vals[2])
            if pos is not None:
                dr, dz = new[0] - pos[0], new[1] - pos[1]
                d = math.hypot(dr, dz)
                if d > 1e-9:
                    vcap = _cap(dr, dz, lim.traj_v, lim.vx, lim.vz)
                    if name == "STRAIGHT_TRAVERSE":
                        dt = _trapezoid(d, vcap, _cap(dr, dz, lim.traj_a, lim.ax, lim.az))
                        est.rapid_s += dt
                    else:
                        dt = d / _feed_speed(per_rev, feed, rpm, sync_pitch, vcap)
                        est.cutting_s += dt
                    t += dt
            pos = new
        elif name == "ARC_FEED" and len(vals) >= 5 and pos is not None:
            ze, xe, zc, xc, rot = vals[:5]
            d = _arc_length(pos, (xe, ze), (xc, zc), rot)
            dt = d / _feed_speed(per_rev, feed, rpm, sync_pitch, lim.traj_v)
            est.cutting_s += dt
            t += dt
            pos = (xe, ze)
        if line_no is not None:
            time_at_line[line_no] = t
    est.total_s = t
    # time left after each source line (lines with no canonical output inherit)
    last = 0.0
    n_lines = gcode.count("\n") + 1
    for i in range(n_lines):
        if i in time_at_line:
            last = time_at_line[i]
        est.remaining_after_line[i] = max(0.0, t - last)
    return est


def _feed_speed(per_rev, feed, rpm, sync_pitch, vcap) -> float:
    """Feed move speed, inches / second."""
    if sync_pitch is not None:
        v = sync_pitch * rpm / 60.0
    elif per_rev:
        v = feed * rpm / 60.0
    else:
        v = feed / 60.0
    v = min(v, vcap)
    return v if v > 1e-9 else 1e-9


def estimate_for_machine(gcode: str) -> CycleEstimate:
    """estimate() with this config's INI and tool table (the repo IS the
    LinuxCNC config directory on the lathe)."""
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return estimate(gcode, os.path.join(repo, "industry-cam.ini"), os.path.join(repo, "tool.tbl"))


def details(est: CycleEstimate) -> str:
    """Tooltip wording: the breakdown and what the estimate assumes."""
    lines = [f"Estimated cycle time {fmt_duration(est.total_s)}: cutting {fmt_duration(est.cutting_s)}, "
             f"rapids {fmt_duration(est.rapid_s)}"
             + (f", dwells {fmt_duration(est.dwell_s)}" if est.dwell_s else "") + ".",
             "Not included: tool changes, M0 stops and optional (M1) stops - they take as long as "
             "the operator does.",
             "Assumes the programmed spindle speed (manual spindle) and 100% feed / rapid override."]
    if not est.complete:
        lines.append(f"Incomplete: LinuxCNC's interpreter stopped at: {est.problem}")
    return "\n".join(lines)

