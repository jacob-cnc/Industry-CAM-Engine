"""Per-pass cutter comp entry/exit, G40 roughing, and tool-table checks.

Simulator evidence (headless LinuxCNC 2.9.6, 2026-11-08): the old GCH program
failed with 'Straight feed in concave corner ...'; the new structure ran end to
end with walls exactly at 3.1150 / 3.1160 / 3.1170 and shoulder Z -0.5680, and
a mismatched tool table paused at the tool check.
"""
import re
from types import SimpleNamespace

import pytest
from PyQt5.QtWidgets import QApplication

from models.tool import ToolDef, ToolOrientation, ToolDirection, ToolType
from outputs.gcode_writer import GCodeWriter
from pipeline.model_builder import build_from_fields
from pipeline.pipeline import execute
from tests.integration.test_operation_depth import bore_fields

_app = QApplication.instance() or QApplication([])

BAR = ToolDef(tool_number=1, nose_radius=0.0157, tip_angle=80.0, edge_length=0.375,
              orientation=ToolOrientation(3), direction=ToolDirection.RIGHT,
              tool_type=ToolType.BORING, description="CCMT bar")


def _gch_code():
    fields = bore_fields(segments=[dict(x=3.117, z=0), dict(x=3.117, z=-.568),
                                   dict(x=2.995, z=-.568)], finish_passes=2)
    fields["tool_def"] = BAR
    p, s, r, f = build_from_fields(**fields)
    return GCodeWriter().write(execute(p, s, BAR, r, f).plan_result)


def _blocks(code):
    return [l.split(";")[0].strip() for l in code.splitlines() if l.startswith("N")]


def test_roughing_is_uncompensated():
    code = _gch_code()
    rough = code.split("; === CLEANUP")[0]
    assert not re.search(r"\bG4[12]\b", rough.split("; === ROUGHING")[1].split(";")[0] + "".join(
        l for l in rough.split("; === ROUGHING")[1].splitlines() if l.startswith("N")))
    assert any("G40" in b for b in _blocks(rough))


def test_each_contour_pass_has_entry_in_air_and_exit():
    blocks = _blocks(_gch_code())
    ons = [i for i, b in enumerate(blocks) if re.search(r"\bG41\b", b)]
    assert len(ons) == 3                        # cleanup + 2 finish passes
    for i in ons:
        entry = blocks[i + 1]
        m = re.match(r"N\d+ G01 X([\d.]+) Z(-?[\d.]+)", entry)
        assert m, entry
        z_entry_end = float(m.group(2))
        # G00 (rise at the entry X) or, since 2026-11-11, the G01 .020 dia X feed-in
        prev = re.match(r"N\d+ G0[01] X([\d.]+) Z(-?[\d.]+)", blocks[i - 1])
        assert prev and prev.group(1) == m.group(1)          # straight down the wall line
        assert float(prev.group(2)) - z_entry_end > 2 * 0.0157  # entry longer than 2 x TNR
        assert z_entry_end >= 0.0                              # comp switches on in air
        nxt = blocks[i + 2:]
        off = next(j for j, b in enumerate(nxt) if re.search(r"\bG40\b", b))
        assert not any(re.search(r"\bG4[12]\b", b) for b in nxt[:off])


def test_id_pass_drops_face_lead_moves():
    code = _gch_code()
    cleanup = code.split("; === CLEANUP")[1].split("; === FINISH")[0]
    feeds = [b for b in _blocks(cleanup) if b.startswith("N") and " G01 " in f" {b} "]
    # first feed after G41 is the vertical entry, no radial feed along the face
    assert all(not re.search(r"Z0\.00[0-9]{2}$", f) or "X3.115" in f for f in feeds[:2])


def test_tool_check_after_every_tool_change():
    code = _gch_code()
    assert "o9001 if [[#5400 NE 1] OR [ABS[#5410 - 0.031400] GT 0.000050] OR [#5413 NE 3]]" in code
    assert code.count("o9001 endif") == 1
    i = code.index("T1 M6"); j = code.index("o9001 if")
    assert i < j < code.index("G40  ; Cutter comp off - roughing")


@pytest.mark.parametrize("direction,is_id,code", [
    (ToolDirection.RIGHT, True, "G41"), (ToolDirection.RIGHT, False, "G42")])
def test_comp_side_still_correct(direction, is_id, code):
    assert GCodeWriter._get_comp_code(direction, is_id) == code


class _FakeBackend:
    def __init__(self, table): self.table = table
    def get_tool_entry(self, n): return self.table.get(n)


@pytest.mark.parametrize("table,expect", [
    ({1: (0.0314, 3)}, []),
    ({1: (0.0320, 8)}, ["T1: program expects D0.0314 Q3, LinuxCNC has D0.0320 Q8."]),
    ({}, ["T1 is not in LinuxCNC's tool table."]),
])
def test_run_tab_tool_table_problems(table, expect):
    from gui.run_tab import RunTab
    tab = RunTab()
    try:
        tab._backend = _FakeBackend(table)
        tab._gcode_text = _gch_code()
        assert tab.tool_table_problems() == expect
    finally:                      # left to GC, a top-level tab can crash a later teardown
        tab.close()
        tab.deleteLater()


@pytest.fixture
def tab():
    """A Program tab that is closed and deleted afterwards (left to the garbage
    collector, a top-level tab can be freed with Qt events still queued for it,
    and a later test's teardown segfaults)."""
    from gui.program_tab import ProgramTab
    w = ProgramTab()
    yield w
    w.close()
    w.deleteLater()


def test_program_tab_missing_tool_is_an_error(tab):
    tab.set_tool_resolver(lambda n: None)
    block = SimpleNamespace(display_label="ID bore")
    with pytest.raises(ValueError, match="T7 .* not in the tool table"):
        tab._require_tool(7, block, "roughing")


# --- end-of-contour lead-out (sim: without it the nose ran to Z-0.6156 for
#     a wall ending at Z-0.6; with it, exactly Z-0.6000) ---------------------

def _lead(prev, end, comp, stock, part, moves_z):
    w = GCodeWriter(); w._x, w._z = end; w._conv, w._fmt, w._n, w._feed = 1.0, ".4f", 10, None
    pr = SimpleNamespace(stock_boundary=stock, finished_part_boundary=part)
    moves = [SimpleNamespace(z=z) for z in moves_z]
    tool = SimpleNamespace(nose_radius=0.016)
    return w._comp_lead_out(prev, end, tool, comp, moves, pr)


def test_lead_out_when_material_beyond_od_wall_end():
    stock = [(0.0, 0.1), (1.0, 0.1), (1.0, -1.0), (0.0, -1.0)]       # bar continues to -1.0
    part = [(0.5, 0.0), (0.0, 0.0), (0.0, -0.6), (0.8, -0.6), (0.8, -0.3), (0.5, -0.3)]
    out = _lead((0.8, -0.3), (0.8, -0.6), "G42", stock, part, [0.0, -0.3, -0.6])
    assert len(out) == 1 and "X0.8840 Z-0.6000" in out[0]           # +X (air side), 2R+0.010


def test_no_lead_out_into_pilot_hole_air():
    stock = [(2.995, 0.05), (4.0, 0.05), (4.0, -1.0), (2.995, -1.0)]
    part = [(3.117, 0.0), (3.117, -0.568), (2.995, -0.568), (2.995, -1.0), (4.0, -1.0), (4.0, 0.0)]
    assert _lead((3.117, -0.568), (2.995, -0.568), "G41", stock, part, [0.0, -0.568]) == []


def test_no_lead_out_past_end_of_bar():
    stock = [(0.0, 0.1), (1.0, 0.1), (1.0, -0.8), (0.0, -0.8)]       # bar ends at -0.8
    part = [(0.5, 0.0), (0.0, 0.0), (0.0, -0.8), (0.8, -0.8), (0.8, -0.3), (0.5, -0.3)]
    assert _lead((0.8, -0.3), (0.8, -0.8), "G42", stock, part, [0.0, -0.3, -0.8]) == []


# --- tool type vs OD/ID (owner slip 2026-11-09: boring bar on an OD block) ---

@pytest.mark.parametrize("mode,q,ttype,ok", [
    ("od", 2, ToolType.TURNING, True),
    ("od", 3, ToolType.BORING, False),
    ("od", 8, ToolType.TURNING, False),
    ("id", 3, ToolType.BORING, True),
    ("id", 2, ToolType.TURNING, False),
    ("id", 7, ToolType.TURNING, True),      # along-Z orientations not checked
])
def test_program_tab_tool_must_suit_mode(tab, mode, q, ttype, ok):
    td = ToolDef(tool_number=1, nose_radius=0.016, tip_angle=80.0, edge_length=0.375,
                 orientation=ToolOrientation(q), direction=ToolDirection.RIGHT,
                 tool_type=ttype, description="t")
    block = SimpleNamespace(display_label="blk")
    if ok:
        tab._check_tool_suits_mode(td, mode, block, "roughing")
    else:
        with pytest.raises(ValueError, match="T1"):
            tab._check_tool_suits_mode(td, mode, block, "roughing")


# --- contour approach: never at face level; OD face entry one radius before ---

def _od_face_code():
    from tests.integration.test_od_step_to_stock import _run
    face = [dict(x=0.0, z=0), dict(x=0.5, z=0), dict(x=0.5, z=-0.3), dict(x=0.8, z=-0.3),
            dict(x=0.8, z=-0.6), dict(x=1.0, z=-0.6)]
    return GCodeWriter().write(_run(face).plan_result)


def test_contour_approach_rapids_stay_at_clearance():
    code = _od_face_code()
    for section in ("; === CLEANUP", "; === FINISH"):
        body = code.split(section)[1].split("; ===")[0]
        rapids = [b for b in _blocks(body) if " G00 " in f" {b} "]
        # every rapid before comp-on that is inside the bar (X < 1.0) is at clearance Z
        before_comp = body.split("G42")[0]
        for b in _blocks(before_comp):
            m = re.match(r"N\d+ G00 X(-?[\d.]+) Z(-?[\d.]+)", b)
            if m and float(m.group(1)) < 1.0:
                assert float(m.group(2)) >= 0.1 - 1e-9, b


def test_od_face_entry_one_nose_radius_before_centre():
    """Owner 2026-11-11: at the centre the nose goes nose radius + .002 past the
    centreline so no nib is left (was exactly one nose radius: X-.0320)."""
    code = _od_face_code()
    fin = code.split("; === FINISH")[1]
    b = _blocks(fin)
    i = next(j for j, x in enumerate(b) if re.search(r"\bG42\b", x))
    assert re.match(r"N\d+ G01 X-0\.0360 Z0\.0000", b[i + 1]), b[i + 1]
    assert re.match(r"N\d+ G01 X0\.0000 Z0\.0000", b[i + 2]), b[i + 2]
