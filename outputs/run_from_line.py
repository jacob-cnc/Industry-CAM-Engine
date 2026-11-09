"""Run-from-line program builder for Industry CAM Engine.

LinuxCNC's own "run from line" (AUTO_RUN with a start line) reads the earlier
lines but discards their canonical commands, so the tool change, G43 offset,
spindle start and feed rate never reach the machine while the interpreter
believes they did. Instead we build a *resume program*:

    %                        (only if the source uses % delimiters)
    <preamble>               every modal group restored explicitly
    <start line .. end>      unchanged source text (N words kept)

and run that from its first line. Lines before the start line are scanned
for modal state only; nothing in them executes.

Starting points that cannot be restored safely are refused with
``RunFromError`` (cutter comp active, inside an O-word block or threading,
G91/G92/G10/parameter expressions before the start, ...).

Pure module: no Qt/LinuxCNC imports. Imports from: standard library only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


class RunFromError(ValueError):
    """The requested start line cannot be resumed safely."""


# --------------------------------------------------------------------------
# Modal groups (LinuxCNC 2.9 G-code reference, "Modal Groups")
# --------------------------------------------------------------------------

_MOTION = {0.0, 1.0, 2.0, 3.0, 33.0, 33.1, 38.2, 38.3, 38.4, 38.5, 73.0, 76.0,
           80.0, 81.0, 82.0, 83.0, 84.0, 85.0, 86.0, 87.0, 88.0, 89.0}
_GROUPS: Dict[str, set] = {
    "plane": {17.0, 18.0, 19.0, 17.1, 18.1, 19.1},
    "distance": {90.0, 91.0},
    "arc_distance": {90.1, 91.1},
    "feed_mode": {93.0, 94.0, 95.0},
    "units": {20.0, 21.0},
    "cutter_comp": {40.0, 41.0, 42.0, 41.1, 42.1},
    "tool_length": {43.0, 43.1, 43.2, 49.0},
    "canned_return": {98.0, 99.0},
    "wcs": {54.0, 55.0, 56.0, 57.0, 58.0, 59.0, 59.1, 59.2, 59.3},
    "path": {61.0, 61.1, 64.0},
    "spindle_mode": {96.0, 97.0},
    "lathe": {7.0, 8.0},
}
_STARTUP: Dict[str, float] = {
    "units": 20.0, "lathe": 7.0, "plane": 18.0, "distance": 90.0,
    "arc_distance": 91.1, "feed_mode": 94.0, "canned_return": 98.0,
    "wcs": 54.0, "path": 64.0, "spindle_mode": 97.0, "tool_length": 49.0,
}
# Non-modal codes that change persistent state we cannot reproduce.
_REFUSED_BEFORE = {10.0: "G10 (offset/table write)", 92.0: "G92 offsets",
                   92.1: "G92.1", 92.2: "G92.2", 92.3: "G92.3",
                   52.0: "G52 local offset", 43.1: "G43.1 dynamic tool offset",
                   43.2: "G43.2 additional tool offset", 91.0: "G91 incremental mode"}
_NO_START_MOTION = {33.0: "G33 spindle-synchronised motion",
                    33.1: "G33.1 rigid tapping", 76.0: "G76 threading cycle"}

_COMMENT_RE = re.compile(r"\([^)]*\)")
_WORD_RE = re.compile(r"([A-Z])\s*([-+]?(?:\d+\.?\d*|\.\d+))")
_N_RE = re.compile(r"^\s*N\s*(\d+)", re.I)
_O_RE = re.compile(r"^\s*O\s*(<[^>]*>|\d+)\s*([A-Z]+)", re.I)


def _strip(line: str) -> str:
    """Remove (...) and ;... comments, uppercase, trim."""
    line = line.split(";", 1)[0]
    line = _COMMENT_RE.sub(" ", line)
    return line.strip().upper()


def _fmt(v: float) -> str:
    s = f"{v:.6f}".rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"


def _gname(v: float) -> str:
    return f"G{_fmt(v)}"


@dataclass
class ModalState:
    """Modal state the interpreter holds before a given line."""
    motion: Optional[float] = None
    groups: Dict[str, float] = field(default_factory=dict)
    feed: Optional[float] = None
    speed: Optional[float] = None
    spindle: Optional[int] = None        # 3, 4 or 5
    css_max: Optional[float] = None      # D word with G96
    coolant: set = field(default_factory=set)  # {7, 8}; cleared by M9
    tool: Optional[int] = None           # tool loaded by the last M6
    prepped: Optional[int] = None        # last T word
    tool_length_h: Optional[int] = None
    path_pq: Tuple[Optional[float], Optional[float]] = (None, None)
    x: Optional[float] = None            # last programmed X (program units)
    z: Optional[float] = None


@dataclass
class ResumePlan:
    """Everything the GUI needs to run from ``start_index``."""
    program_text: str
    start_index: int            # 0-based line index in the SOURCE text
    resume_start_index: int     # 0-based index of that line in program_text
    preamble: List[str]
    state: ModalState
    first_line: str             # start line as it will run (motion code added)
    notes: List[str]

    def source_line(self, resume_line_1based: int) -> int:
        """Map a 1-based LinuxCNC line in program_text to the source (1-based).

        Returns 0 for preamble lines.
        """
        idx = resume_line_1based - 1
        if idx < self.resume_start_index:
            return 0
        return idx - self.resume_start_index + self.start_index + 1


# --------------------------------------------------------------------------
# Public helpers
# --------------------------------------------------------------------------

def has_n_numbers(text: str) -> bool:
    """True if the program numbers its blocks with N words."""
    return any(_N_RE.match(l) for l in text.splitlines())


def find_n_line(text: str, n: int) -> Optional[int]:
    """0-based index of the first line whose block number is N``n``."""
    for i, line in enumerate(text.splitlines()):
        m = _N_RE.match(line)
        if m and int(m.group(1)) == n:
            return i
    return None


def scan_modal_state(lines: List[str], stop: int) -> Tuple[ModalState, List[str]]:
    """Scan ``lines[:stop]`` and return the modal state before ``stop``.

    Also returns the most recent tool-check O-block (verbatim lines) that
    follows the last M6, so the resume program can repeat that check.
    Raises RunFromError for constructs we cannot restore.
    """
    st = ModalState()
    o_stack: List[str] = []
    block: List[str] = []           # current o-if block being captured
    last_check: List[str] = []
    for i in range(stop):
        raw = lines[i]
        text = _strip(raw)
        if not text or text == "%":
            if o_stack and raw.strip():
                block.append(raw)    # keep (DEBUG, ...) messages of a check
            continue
        om = _O_RE.match(text)
        if om:
            kw = om.group(2)
            if kw == "IF":
                o_stack.append(om.group(1))
                block = [raw]
            elif kw == "ENDIF":
                if not o_stack:
                    raise RunFromError(f"Line {i + 1}: endif without if.")
                o_stack.pop()
                block.append(raw)
                if not o_stack:
                    last_check = block
                    block = []
            elif kw in ("ELSE", "ELSEIF"):
                raise RunFromError(
                    f"Line {i + 1}: if/else branches before the start line - "
                    "modal state depends on run-time values.")
            else:
                raise RunFromError(
                    f"Line {i + 1}: O-word '{kw.lower()}' (subroutine/loop) before "
                    "the start line - state cannot be restored by scanning.")
            continue
        if o_stack:
            block.append(raw)
            words = _WORD_RE.findall(text)
            if any(l in "GTSF" or (l == "M" and float(v) not in (0.0, 1.0))
                   for l, v in words):
                raise RunFromError(
                    f"Line {i + 1}: modal codes inside a conditional block - "
                    "state depends on run-time values.")
            continue
        if "#" in text or "[" in text:
            raise RunFromError(
                f"Line {i + 1}: parameters/expressions before the start line "
                "cannot be evaluated by the restore scan.")
        if text.startswith("/"):
            raise RunFromError(f"Line {i + 1}: block delete ('/') before the start line.")
        _apply_line(st, text, i)
        if any(l == "M" and float(v) == 6.0 for l, v in _WORD_RE.findall(text)):
            last_check = []          # a check only counts after the latest M6
    if o_stack:
        raise RunFromError("The start line is inside an O-word block.")
    return st, last_check


def build_resume_program(text: str, start_index: int,
                         tool_in_spindle: Optional[int] = None) -> ResumePlan:
    """Build the resume program that starts at source line ``start_index``.

    ``tool_in_spindle``: LinuxCNC's current tool; when it already matches the
    program's tool the preamble skips M6 (still applies G43).
    """
    lines = text.splitlines()
    if not 0 < start_index < len(lines):
        raise RunFromError("Start line is outside the program.")
    start_text = _strip(lines[start_index])
    if not start_text or start_text == "%":
        raise RunFromError("The start line is blank or a comment - choose a line with a block.")
    if _O_RE.match(start_text):
        raise RunFromError("Start on a G-code block, not an O-word line.")

    st, tool_check = scan_modal_state(lines, start_index)
    notes: List[str] = []

    # --- refusals that depend on the state at the start line ---------------
    comp = st.groups.get("cutter_comp", 40.0)
    start_cancels_comp = any(l == "G" and float(v) == 40.0
                             for l, v in _WORD_RE.findall(_strip(lines[start_index])))
    if comp != 40.0 and not start_cancels_comp:
        raise RunFromError(
            f"Cutter comp ({_gname(comp)}) is active at this line - the comp "
            "entry move cannot be reproduced. Start at or before the line that "
            "turns comp on, or after its G40.")
    if st.motion in _NO_START_MOTION:
        raise RunFromError(
            f"{_NO_START_MOTION[st.motion]} is the active motion mode - start "
            "before the threading/synchronised block.")
    if st.motion is not None and (80.0 < st.motion <= 89.0 or st.motion == 73.0):
        raise RunFromError("A canned cycle is active at this line - start at its first block.")

    start_words = _WORD_RE.findall(start_text)
    start_g = [float(v) for l, v in start_words if l == "G"]
    for g in start_g:
        if g in _NO_START_MOTION:
            raise RunFromError(
                f"The start line is a {_NO_START_MOTION[g]} - it starts from the "
                "current position, so begin at the positioning move before it.")

    # --- preamble ------------------------------------------------------------
    # Groups never set by the program fall back to this machine's startup
    # state (industry-cam.ini: LINEAR_UNITS inch, RS274NGC_STARTUP_CODE G7 G18)
    # and LinuxCNC's power-on defaults for the rest - not to whatever an
    # earlier MDI session left active.
    g = {**_STARTUP, **st.groups}
    pre: List[str] = []
    first = [_gname(g["units"]), _gname(g["lathe"]),
             _gname(g["plane"]), _gname(g["distance"]),
             _gname(g["arc_distance"]), _gname(g["feed_mode"]),
             "G40", "G80", _gname(g["canned_return"])]
    pre.append(" ".join(first) + "  (restore units/diameter/plane/distance/feed mode)")
    pre.append(f"{_gname(g['wcs'])}  (work coordinate system)")
    path = g["path"]
    p, q = st.path_pq
    path_words = _gname(path) + (f" P{_fmt(p)}" if path == 64.0 and p is not None else "") \
        + (f" Q{_fmt(q)}" if path == 64.0 and q is not None else "")
    pre.append(f"{path_words}  (path control)")

    if st.prepped is not None and st.tool is None:
        notes.append(f"T{st.prepped} was selected but never loaded with M6 before this line.")
    if st.tool is not None:
        if tool_in_spindle != st.tool:
            pre.append(f"T{st.tool} M6  (load tool used at this line)")
        else:
            notes.append(f"T{st.tool} already in spindle - no tool change.")
    if st.prepped is not None and st.prepped != st.tool:
        pre.append(f"T{st.prepped}  (re-select prepared tool)")
    tl = g["tool_length"]
    if tl == 43.0:
        pre.append("G43" + (f" H{st.tool_length_h}" if st.tool_length_h is not None else "")
                   + "  (tool length offset)")
    else:
        pre.append("G49  (no tool length offset)")
    pre.extend(tool_check)

    sm = g["spindle_mode"]
    sp = st.spindle if st.spindle is not None else 5
    sword = f" S{_fmt(st.speed)}" if st.speed is not None else ""
    if sm == 96.0:
        if st.speed is None:
            raise RunFromError("G96 is active but no S value was found before the start line.")
        d = f" D{_fmt(st.css_max)}" if st.css_max is not None else ""
        pre.append(f"G96{d}{sword} M{sp}  (constant surface speed, spindle)")
    else:
        pre.append(f"G97{sword} M{sp}  (spindle speed and direction)")
    pre.append("M9" if not st.coolant else " ".join(f"M{c}" for c in sorted(st.coolant)))
    if st.feed is not None:
        pre.append(f"F{_fmt(st.feed)}  (feed rate)")
    elif g["feed_mode"] != 93.0:
        notes.append("No feed rate before this line - the program must set F before feeding.")

    # --- start line: make the motion mode explicit ---------------------------
    first_line = lines[start_index]
    has_axis = any(l in "XZ" for l, _ in start_words)
    if has_axis and not any(v in _MOTION for v in start_g):
        if st.motion is None:
            raise RunFromError("The start line moves an axis but no motion mode (G0/G1/...) was set before it.")
        m = _N_RE.match(first_line)
        if m:   # keep the N word first: "N210 G1 X..."
            first_line = f"{first_line[:m.end()]} {_gname(st.motion)} {first_line[m.end():].lstrip()}"
        else:
            first_line = f"{_gname(st.motion)} {first_line.lstrip()}"
        notes.append(f"Added the active motion mode {_gname(st.motion)} to the start line.")

    # --- assemble --------------------------------------------------------------
    percent = next((_strip(l) for l in lines if _strip(l)), "") == "%"
    out: List[str] = []
    if percent:
        out.append("%")
    out.append(f"; Run-from resume program - source line {start_index + 1}"
               + (f" ({_N_RE.match(lines[start_index]).group(0).strip()})"
                  if _N_RE.match(lines[start_index]) else ""))
    out.append("; Preamble restores the modal state the program had at that line.")
    out.extend(pre)
    resume_start = len(out)
    out.append(first_line)
    out.extend(lines[start_index + 1:])
    return ResumePlan(program_text="\n".join(out) + "\n", start_index=start_index,
                      resume_start_index=resume_start, preamble=pre, state=st,
                      first_line=first_line, notes=notes)


# --------------------------------------------------------------------------
# Internals
# --------------------------------------------------------------------------

def _apply_line(st: ModalState, text: str, idx: int) -> None:
    words = _WORD_RE.findall(text)
    gs = [float(v) for l, v in words if l == "G"]
    vals: Dict[str, float] = {}
    for l, v in words:
        if l not in ("G", "M"):
            vals[l] = float(v)
    for gv in gs:
        if gv in _REFUSED_BEFORE:
            raise RunFromError(
                f"Line {idx + 1}: {_REFUSED_BEFORE[gv]} before the start line - "
                "cannot be restored safely.")
    non_modal_move = any(gv in (28.0, 30.0, 53.0, 28.1, 30.1) for gv in gs)
    for gv in gs:
        if gv in _MOTION:
            st.motion = gv
            continue
        for name, members in _GROUPS.items():
            if gv in members:
                st.groups[name] = gv
                break
    if 43.0 in gs and "H" in vals:
        st.tool_length_h = int(vals["H"])
    if 64.0 in gs:
        st.path_pq = (vals.get("P"), vals.get("Q"))
    if 96.0 in gs and "D" in vals:
        st.css_max = vals["D"]
    if "F" in vals:
        st.feed = vals["F"]
    if "S" in vals:
        st.speed = vals["S"]
    if "T" in vals:
        st.prepped = int(vals["T"])
    for l, v in words:
        if l != "M":
            continue
        mv = float(v)
        if mv in (3.0, 4.0, 5.0):
            st.spindle = int(mv)
        elif mv in (7.0, 8.0):
            st.coolant.add(int(mv))
        elif mv == 9.0:
            st.coolant.clear()
        elif mv == 6.0:
            if st.prepped is None:
                raise RunFromError(f"Line {idx + 1}: M6 without a T word.")
            st.tool = st.prepped
        elif mv in (2.0, 30.0):
            raise RunFromError(f"Line {idx + 1}: program end (M{int(mv)}) before the start line.")
    if non_modal_move:
        st.x = st.z = None           # position known only in machine terms
    else:
        if "X" in vals:
            st.x = vals["X"]
        if "Z" in vals:
            st.z = vals["Z"]
