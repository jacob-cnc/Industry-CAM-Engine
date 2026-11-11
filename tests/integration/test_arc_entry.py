"""Arc entry rules (owner decisions 2026-11-11; geometry/arc_entry.py).

* Q / -Q is a true quarter circle (ellipses retired).
* An arc that begins and ends at the same X is two quadrants, e.g. the owner's
  X1 Z0 -> X1 Z-1 is cut as +Q to the apex then -Q back. X is a DIAMETER, so a
  .5 radius bead peaks at X2.0.
* A radius arc that passes its own X extreme is split there (same circle,
  same direction) instead of being refused.
The split happens in the model (profile_from_fields / execute) and, in the
Program tab, on the rows when the operator leaves the row.
"""

import math
import os
import shutil
import sys

import pytest
from PyQt5.QtWidgets import QApplication

from geometry.arc_entry import (
    normalize_profile, quadrant_problem, radius_arc_x_extreme, split_rows,
)
from models.moves import MoveType
from models.tool import ToolDef, ToolDirection, ToolOrientation, ToolType
from outputs.gcode_writer import GCodeWriter
from pipeline.model_builder import build_from_fields, profile_from_fields
from pipeline.pipeline import execute

_app = QApplication.instance() or QApplication([])
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RS274 = shutil.which("rs274")
CNMG = ToolDef(tool_number=4, nose_radius=0.016, tip_angle=80.0, edge_length=0.375,
               orientation=ToolOrientation(3), direction=ToolDirection.RIGHT,
               tool_type=ToolType.TURNING, description="CNMG")
# A 35 deg VNMG reaches the back flank of a bead (the CNMG's 80 deg would rub it).
# T4 because rs274 needs a number that is in the machine tool table.
VNMG = ToolDef(tool_number=4, nose_radius=0.016, tip_angle=35.0, edge_length=0.5,
               orientation=ToolOrientation(3), direction=ToolDirection.RIGHT,
               tool_type=ToolType.TURNING, description="VNMG")


def _rows(*pts):
    out = [{"type": "line", "x": pts[0][0], "z": 0.0, "radius": 0.0}]
    for p in pts[1:]:
        out.append({"type": "arc" if len(p) > 2 else "line", "x": p[0], "z": p[1],
                    "radius": p[2] if len(p) > 2 else 0.0})
    return out


def _execute(rows, tool, stock_dia=2.5):
    p, s, r, f = build_from_fields(
        segments=rows, stock_dia=stock_dia, x_start=stock_dia, z_start=0.05,
        z_end=min(x["z"] for x in rows), stock_back_z=None, mode="od", pilot_hole_dia=0.0,
        doc_dia=0.05, feed=0.008, strategy="staircase", fin_allowance=0.01,
        peck_enabled=False, peck_length=None, spindle_rpm=1000.0, finish_passes=1,
        finish_doc_dia=0.002, finish_feed=0.003, finish_spring_pass=False, tool_def=tool,
        x_park=3.0, z_park=1.0, corner_breaks=[])
    return execute(p, s, tool, r, f)


# ----------------------------------------------------------------------
# The rules
# ----------------------------------------------------------------------

def test_owner_example_same_x_quadrant_is_two_quadrants():
    segs, breaks, notes = split_rows(_rows((1.0,), (1.0, -1.0, "Q"), (1.0, -1.5)),
                                     [None, {"type": "chamfer", "size": 0.01}], "od")
    assert [(s["x"], s["z"], s["radius"]) for s in segs[1:3]] == [(2.0, -0.5, "Q"), (1.0, -1.0, "-Q")]
    # the new apex vertex has no break; the chamfer stays on the arc's far end
    assert breaks == [None, None, {"type": "chamfer", "size": 0.01}]
    assert "X2.0000 Z-0.5000" in notes[0]


def test_same_x_radius_arc_splits_at_its_apex_with_the_same_radius():
    segs, _, notes = split_rows(_rows((1.0,), (1.0, -1.0, 0.6)), [None], "od")
    h = math.sqrt(0.6 ** 2 - 0.5 ** 2)
    assert segs[1]["x"] == pytest.approx(1.0 + 2 * (0.6 - h)) and segs[1]["z"] == pytest.approx(-0.5)
    assert segs[1]["radius"] == segs[2]["radius"] == 0.6 and len(notes) == 1
    # -R bulges the other way (a groove)
    segs, _, _ = split_rows(_rows((1.0,), (1.0, -1.0, -0.6)), [None], "od")
    assert segs[1]["x"] == pytest.approx(1.0 - 2 * (0.6 - h))


def test_arc_inside_its_end_diameters_is_left_alone():
    rows = _rows((1.0,), (1.2, -0.1, 0.1), (1.2, -0.5))        # an NX-style fillet
    assert split_rows(rows, [None, None], "od")[2] == []
    assert radius_arc_x_extreme((0.5, 0.0), (0.6, -0.1), 0.1) is None


def test_arc_past_its_end_diameter_is_split_not_refused():
    """X1.0 -> X1.2 over Z .4 with R .25: bulges past X1.2 (was 'exceeds X bounds')."""
    segs, _, notes = split_rows(_rows((1.0,), (1.2, -0.4, 0.25)), [None], "od")
    assert len(segs) == 3 and segs[1]["x"] > 1.2 + 1e-3 and notes
    again, _, more = split_rows(segs, [None, None], "od")      # stable once split
    assert more == [] and again == segs


def test_split_survives_four_decimal_rounding_in_the_segment_list():
    segs, _, _ = split_rows(_rows((1.0,), (1.2, -0.4, 0.25)), [None], "od")
    shown = [dict(s, x=round(s["x"], 4), z=round(s["z"], 4)) for s in segs]
    assert split_rows(shown, [None, None], "od")[2] == []


def test_quadrant_legs_must_match():
    assert quadrant_problem(1.0, 0.0, 1.5, -0.25) is None
    assert quadrant_problem(1.0, 0.0, 1.5, -0.2501) is None     # within .0002 on the radius
    assert "X1.5000 Z-0.2500" in quadrant_problem(1.0, 0.0, 1.5, -0.5)


def test_profile_from_fields_splits_and_is_idempotent():
    prof = profile_from_fields(_rows((1.0,), (1.0, -1.0, "Q"), (1.0, -1.5)), "od")
    assert len(prof.segments) == 4 and prof.segments[1].quadrant and prof.segments[1].x == 2.0
    assert normalize_profile(prof) is prof


# ----------------------------------------------------------------------
# End to end
# ----------------------------------------------------------------------

def _finish_reach(res):
    """Largest diameter on the finish pass arcs (radius space sampling)."""
    best = 0.0
    for fp in res.plan_result.finish_passes:
        pos = None
        for m in fp.moves:
            if m.move_type in (MoveType.ARC_CW, MoveType.ARC_CCW) and pos is not None:
                c = (pos[0] / 2 + m.center_i / 2, pos[1] + m.center_k)
                rad = math.hypot(pos[0] / 2 - c[0], pos[1] - c[1])
                a0 = math.atan2(pos[1] - c[1], pos[0] / 2 - c[0])
                a1 = math.atan2(m.z - c[1], m.x / 2 - c[0])
                sw = math.atan2(math.sin(a1 - a0), math.cos(a1 - a0))
                for k in range(21):
                    best = max(best, 2 * (c[0] + rad * math.cos(a0 + sw * k / 20)))
            pos = (m.x, m.z)
    return best


# The owner's bead (X1 -> X1 over 1.0 of Z, peaking at X2.0) with a step up after
# it, as on a real part.
BEAD = _rows((1.0,), (1.0, -0.4), (1.0, -1.4, "Q"), (1.0, -1.6), (2.2, -1.6), (2.2, -2.0))


def test_owner_bead_generates_and_peaks_at_x2():
    res = _execute(BEAD, VNMG)
    assert res.plan_result is not None, [v.message for v in res.validations
                                         if v.severity.value == "error"]
    assert _finish_reach(res) == pytest.approx(2.0, abs=2e-3)


@pytest.mark.skipif(RS274 is None, reason="LinuxCNC rs274 not installed")
def test_owner_bead_runs_in_linuxcnc_without_long_way_arcs(tmp_path):
    sys.path.insert(0, os.path.join(REPO, "scripts", "arc_testbed"))
    from sweep_audit import audit
    res = _execute(BEAD, VNMG)
    code = GCodeWriter().write(res.plan_result)
    for f in ("industry-cam.ini", "tool.tbl"):
        shutil.copy(os.path.join(REPO, f), tmp_path / f)
    var = os.path.join(REPO, "industry-cam.var")
    if os.path.exists(var):
        shutil.copy(var, tmp_path / "industry-cam.var")
    else:
        (tmp_path / "industry-cam.var").write_text("5220\t1.000000\n")
    (tmp_path / "p.ngc").write_text(code)
    ended, n, bad, err = audit(str(tmp_path / "industry-cam.ini"), str(tmp_path / "tool.tbl"),
                               str(tmp_path / "industry-cam.var"), str(tmp_path / "p.ngc"))
    assert ended, err
    assert n > 0 and not bad, bad


def test_radius_bulge_past_end_diameter_now_generates():
    res = _execute(_rows((1.0,), (1.0, -0.3), (1.2, -0.7, 0.25), (1.2, -1.2)), VNMG)
    assert res.plan_result is not None, [v.message for v in res.validations
                                         if v.severity.value == "error"]


def test_bead_at_the_end_of_the_part_is_blocked_not_gouged():
    """Ending BEHIND a bead (smaller than its peak, nothing after it): the closing
    rapid back to the start would run through the bead. Rapid routing around
    bumps is arc strategy Phase 2; until then the post-planning check must
    block it (it does)."""
    res = _execute(_rows((1.0,), (1.0, -0.4), (1.0, -1.4, "Q"), (1.0, -2.0)), VNMG)
    assert res.plan_result is None
    assert any("GOUGE" in v.message for v in res.validations)
