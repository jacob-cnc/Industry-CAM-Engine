"""Tool reach (arc strategy Phase 1, Principle D; geometry/tool_reach.py).

The insert is the wedge between its front and back edges (tool table I / J,
in the tool's own frame: from its feed direction round toward the air). It
must fit on the air side of every tangent of the finished contour:
    rise <= front angle,   fall <= 180 - back angle.
OD and ID are the same check mirrored in X; a left-hand tool mirrors Z.
CNMG in a 95 deg holder (95/175): square shoulders yes, falling only 5 deg.
VNMG neutral (72.5/107.5): falls up to 72.5, rises up to 72.5.
"""

import math
import os
import json
from dataclasses import replace

import pytest
from PyQt5.QtWidgets import QApplication

from geometry.tool_reach import reach_messages, reach_problems
from models.tool import ToolDef, ToolDirection, ToolOrientation, ToolType
from models.validation import PipelineStatus
from pipeline.model_builder import build_from_fields, profile_from_fields
from pipeline.pipeline import execute

_app = QApplication.instance() or QApplication([])
FIX = os.path.join(os.path.dirname(__file__), "..", "fixtures", "arc_testbed")

CNMG = ToolDef(4, 0.016, 80.0, 0.375, ToolOrientation(2), ToolDirection.RIGHT,
               ToolType.TURNING, description="CNMG", front_angle=95.0, back_angle=175.0)
VNMG = replace(CNMG, tip_angle=35.0, front_angle=72.5, back_angle=107.5, description="VNMG")
CNMG_LH = replace(CNMG, direction=ToolDirection.LEFT, description="CNMG LH")
BAR = ToolDef(1, 0.0157, 80.0, 0.375, ToolOrientation(3), ToolDirection.RIGHT,
              ToolType.BORING, description="CCMT bar", front_angle=95.0, back_angle=175.0)


def _rows(*pts):
    out = [{"type": "line", "x": pts[0], "z": 0.0, "radius": 0.0}]
    for p in pts[1:]:
        out.append({"type": "arc" if len(p) > 2 else "line", "x": p[0], "z": p[1],
                    "radius": p[2] if len(p) > 2 else 0.0})
    return out


def _od(*pts):
    return profile_from_fields(_rows(*pts), "od")


def _id(*pts):
    return profile_from_fields(_rows(*pts), "id")


def _taper_down(deg):
    """OD: X1.0 to Z-.5, then falls toward the chuck at `deg`, then on."""
    dz = 0.2
    dx = 2 * dz * math.tan(math.radians(deg))
    return _od(1.0, (1.0, -0.5), (1.0 - dx, -0.5 - dz), (1.0 - dx, -1.0))


# ----------------------------------------------------------------------
# OD
# ----------------------------------------------------------------------

def test_od_turning_shoulders_and_rising_chamfers_are_fine_for_cnmg():
    prof = _od(0.5, (0.6, -0.05), (0.6, -0.5), (1.0, -0.5), (1.0, -1.0),
               (1.2, -1.0, 0.0), (1.2, -1.5))
    assert reach_problems(prof, CNMG) == []


@pytest.mark.parametrize("deg,ok", [(3.0, True), (5.5, True), (7.0, False), (30.0, False),
                                    (90.0, False)])
def test_od_falling_contour_limited_by_cnmg_back_clearance(deg, ok):
    assert (reach_problems(_taper_down(deg), CNMG) == []) is ok


@pytest.mark.parametrize("deg,ok", [(30.0, True), (72.0, True), (80.0, False)])
def test_od_falling_contour_with_vnmg(deg, ok):
    assert (reach_problems(_taper_down(deg), VNMG) == []) is ok


def test_od_square_shoulder_too_steep_for_a_neutral_vnmg():
    probs = reach_problems(_od(0.5, (0.5, -0.5), (1.0, -0.5), (1.0, -1.0)), VNMG)
    assert probs and probs[0].kind == "rise" and probs[0].phi == pytest.approx(90.0)


def test_od_left_hand_tool_is_the_mirror():
    # falls toward the chuck at 45: fine for a LH tool (it feeds toward the tailstock)
    assert reach_problems(_taper_down(45.0), CNMG_LH) == []
    # a square shoulder climbing toward the chuck is a back face for a LH tool
    assert reach_problems(_od(0.5, (0.5, -0.5), (1.0, -0.5), (1.0, -1.0)), CNMG_LH)


@pytest.mark.parametrize("name,cnmg,vnmg", [
    ("OD_groove_2x90", False, False),     # walls: fall 90 (CNMG, VNMG) and rise 90 (VNMG)
    ("OD_bead_2x90", False, False),       # back of the bead falls 90
    ("OD_crest120_2x60", False, True),    # falls 60: VNMG yes, CNMG no
    ("OD_NX_arcs_noV1", False, False),    # the NX part has a neck (back face) and shoulders
])
def test_od_testbed_parts(name, cnmg, vnmg):
    d = json.load(open(os.path.join(FIX, name + ".json")))
    prof = profile_from_fields(d["segments"], "od", d.get("corner_breaks"))
    assert (reach_problems(prof, CNMG) == []) is cnmg
    assert (reach_problems(prof, VNMG) == []) is vnmg


def test_od_arcs_checked_at_their_steepest_tangent():
    # convex R .25 quarter from a face onto a diameter: rises to 90 at its start
    up = _od(0.5, (0.5, -0.2), (1.0, -0.45, "Q"), (1.0, -1.0))
    assert reach_problems(up, CNMG) == []
    # same-X bead: the far half falls to 90 toward the chuck
    bead = _od(1.0, (1.0, -0.2), (1.0, -0.6, "Q"), (1.0, -1.0))
    assert any(p.kind == "fall" for p in reach_problems(bead, CNMG))


# ----------------------------------------------------------------------
# ID (boring bar)
# ----------------------------------------------------------------------

def test_id_bore_with_steps_in_and_mouth_chamfer_is_fine_for_the_bar():
    # mouth chamfer X1.2 -> X1.0, bore, step in to X.8 (a shoulder deeper in), bore
    prof = _id(1.2, (1.0, -0.1), (1.0, -0.6), (0.8, -0.6), (0.8, -1.0))
    assert reach_problems(prof, BAR) == []


@pytest.mark.parametrize("deg,ok", [(4.0, True), (10.0, False), (90.0, False)])
def test_id_bore_opening_up_deeper_is_limited_by_back_clearance(deg, ok):
    dz = 0.2
    dx = 2 * dz * math.tan(math.radians(deg))
    prof = _id(1.0, (1.0, -0.5), (1.0 + dx, -0.5 - dz), (1.0 + dx, -1.0))
    assert (reach_problems(prof, BAR) == []) is ok


@pytest.mark.parametrize("name,ok", [("ID_NX_arcs_no_undercut", True),
                                     ("ID_groove_2x90", False), ("ID_bead_2x90", False)])
def test_id_testbed_parts(name, ok):
    d = json.load(open(os.path.join(FIX, name + ".json")))
    prof = profile_from_fields(d["segments"], "id", d.get("corner_breaks"))
    assert (reach_problems(prof, BAR) == []) is ok


# ----------------------------------------------------------------------
# When it applies, and the pipeline
# ----------------------------------------------------------------------

def test_skipped_without_edge_angles_or_for_other_tool_types():
    prof = _taper_down(45.0)
    assert reach_problems(prof, replace(CNMG, front_angle=0.0, back_angle=0.0)) == []
    assert reach_problems(prof, replace(CNMG, tool_type=ToolType.THREADING)) == []


def test_tool_table_angles_reach_the_tool_def():
    from tools.tool_card_data import tool_card_to_tool_def, tool_def_to_tool_card
    card = tool_def_to_tool_card(CNMG)
    assert (card.front_angle, card.back_angle) == (95.0, 175.0)
    back = tool_card_to_tool_def(card)
    assert (back.front_angle, back.back_angle) == (95.0, 175.0)


def _execute(rows, tool, finish_tool=None, mode="od"):
    p, s, r, f = build_from_fields(
        segments=rows, stock_dia=2.0, x_start=2.0, z_start=0.05,
        z_end=min(x["z"] for x in rows), stock_back_z=None, mode=mode, pilot_hole_dia=0.0,
        doc_dia=0.05, feed=0.008, strategy="staircase", fin_allowance=0.01,
        peck_enabled=False, peck_length=None, spindle_rpm=1000.0, finish_passes=1,
        finish_doc_dia=0.002, finish_feed=0.003, finish_spring_pass=False, tool_def=tool,
        x_park=3.0, z_park=1.0, corner_breaks=[])
    return execute(p, s, tool, r, f, finish_tool=finish_tool)


NECK = _rows(1.0, (1.0, -0.4), (0.7, -0.4), (0.7, -0.8), (1.2, -0.8), (1.2, -1.2))


def _finish_points(res):
    """Sampled tool-path points of the finish passes, (X dia, Z)."""
    from models.moves import MoveType
    out = []
    for fp in res.plan_result.finish_passes:
        pos = None
        for m in fp.moves:
            if pos is not None and m.move_type in (MoveType.FEED, MoveType.ARC_CW, MoveType.ARC_CCW):
                for k in range(11):
                    out.append((pos[0] + (m.x - pos[0]) * k / 10, pos[1] + (m.z - pos[1]) * k / 10))
            pos = (m.x, m.z)
    return out


def test_pipeline_leaves_the_neck_uncut_and_says_where():
    res = _execute(NECK, CNMG)
    assert res.status == PipelineStatus.SUCCESS_WITH_WARNINGS, [
        v.message for v in res.validations if v.severity.value == "error"]
    warn = [v.message for v in res.validations if v.category == "tool_reach"]
    assert len(warn) == 1
    assert warn[0].startswith("Left uncut: X0.7000-X1.0000, Z-0.4000 to Z-0.8000")
    assert "grooving" in warn[0]
    # the finish pass follows the 5 deg line X1.0 Z-.4 -> X.93 Z-.8, never into the neck
    for x, z in _finish_points(res):
        if -0.79 < z < -0.41:
            line_x = 1.0 - (0.07 * (-0.4 - z) / 0.4)
            assert x >= line_x - 0.002, (x, z)
    from outputs.gcode_writer import GCodeWriter
    code = GCodeWriter().write(res.plan_result)
    assert "UNCUT: THIS TOOL CAN'T REACH" in code


def test_pipeline_checks_the_finish_tool_too():
    ok = _rows(1.0, (1.0, -0.4), (1.2, -0.4), (1.2, -1.2))          # shoulder up only
    res = _execute(ok, CNMG)
    assert res.status == PipelineStatus.SUCCESS
    res = _execute(ok, CNMG, finish_tool=VNMG)                       # VNMG can't climb 90
    assert res.plan_result is not None
    warn = [v.message for v in res.validations if v.category == "tool_reach"]
    assert warn and "VNMG" in warn[0] and "climbs" in warn[0]


def test_pipeline_unchanged_for_tools_without_angles():
    res = _execute(NECK, replace(CNMG, front_angle=0.0, back_angle=0.0))
    assert not any(v.category == "tool_reach" for v in res.validations)


# ----------------------------------------------------------------------
# make_reachable: the contour the tool can follow, and the report
# ----------------------------------------------------------------------

from geometry.tool_reach import make_reachable  # noqa: E402


def test_reachable_contour_unchanged_when_nothing_is_out_of_reach():
    prof = _od(0.5, (0.5, -0.5), (1.0, -0.5), (1.0, -1.0))
    assert make_reachable(prof, CNMG) == (prof, [])


def test_neck_bridged_at_the_back_clearance_angle():
    newp, regs = make_reachable(profile_from_fields(NECK, "od"), CNMG)
    pts = [(round(m.x, 4), round(m.z, 4)) for m in newp.segments]
    assert pts == [(1.0, 0.0), (1.0, -0.4), (0.93, -0.8), (1.2, -0.8), (1.2, -1.2)]
    assert len(regs) == 1 and regs[0].kind == "fall" and regs[0].depth == pytest.approx(0.1494, abs=1e-3)
    assert reach_problems(newp, CNMG) == []


@pytest.mark.parametrize("name,tool,mode,n,hint", [
    ("OD_NX_arcs_noV1", CNMG, "od", 2, "VNMG"),     # neck: grooving; 60 deg chamfer: VNMG/DNMG/TNMG
    ("OD_bead_2x90", CNMG, "od", 1, "left-hand"),   # back of the bead: a left-hand 95 deg tool
    ("OD_groove_2x90", VNMG, "od", 2, "CNMG"),      # walls: a 95 deg tool of each hand
    ("ID_groove_2x90", BAR, "id", 1, "grooving"),
    ("ID_bead_2x90", BAR, "id", 1, "left-hand"),
])
def test_testbed_parts_become_cuttable_with_the_regions_reported(name, tool, mode, n, hint):
    d = json.load(open(os.path.join(FIX, name + ".json")))
    prof = profile_from_fields(d["segments"], mode, d.get("corner_breaks"))
    newp, regs = make_reachable(prof, tool)
    assert reach_problems(newp, tool) == []
    assert len(regs) == n
    assert any(hint in r.message for r in regs), [r.message for r in regs]
    for r in regs:
        assert r.message.startswith("Left uncut: X") and r.depth > 0


def test_nx_part_60_deg_chamfer_suggests_the_right_inserts():
    d = json.load(open(os.path.join(FIX, "OD_NX_arcs_noV1.json")))
    _, regs = make_reachable(profile_from_fields(d["segments"], "od"), CNMG)
    chamfer = next(r for r in regs if 55 < r.worst_deg < 65)
    for code in ("VNMG", "DNMG", "TNMG"):
        assert code in chamfer.message
    assert "CNMG" not in chamfer.message.split("Cut it")[1]


def test_neck_program_runs_in_linuxcnc(tmp_path):
    import shutil
    rs274 = shutil.which("rs274")
    if rs274 is None:
        pytest.skip("LinuxCNC rs274 not installed")
    import sys
    repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sys.path.insert(0, os.path.join(repo, "scripts", "arc_testbed"))
    from sweep_audit import audit
    from outputs.gcode_writer import GCodeWriter
    code = GCodeWriter().write(_execute(NECK, CNMG).plan_result)
    assert max(len(line) for line in code.splitlines()) <= 255     # LinuxCNC line limit
    for f in ("industry-cam.ini", "tool.tbl"):
        shutil.copy(os.path.join(repo, f), tmp_path / f)
    var = os.path.join(repo, "industry-cam.var")
    if os.path.exists(var):
        shutil.copy(var, tmp_path / "industry-cam.var")
    else:
        (tmp_path / "industry-cam.var").write_text("5220\t1.000000\n")
    (tmp_path / "p.ngc").write_text(code)
    ended, n, bad, err = audit(str(tmp_path / "industry-cam.ini"), str(tmp_path / "tool.tbl"),
                               str(tmp_path / "industry-cam.var"), str(tmp_path / "p.ngc"))
    assert ended, err
    assert not bad, bad
