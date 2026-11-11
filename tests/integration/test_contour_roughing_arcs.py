"""Offset-contour roughing arcs: right side of the chord, right direction.

Found 2026-11-10 (lathe): ContourRoughingPlanner built its own part face with
RadiusArc(-radius) (every arc bulged the wrong way: gouges on concave
fillets) and labelled arcs with the negation of the rule every other planner
uses. After the G-code dialect fix LinuxCNC ran those arcs the long way
round (GUI Conv Test: 27 roughing arcs of -350..-359 deg).
"""

import math
import os
import re
import shutil
import subprocess

import pytest
from PyQt5.QtWidgets import QApplication

from models.moves import MoveType
from models.tool import ToolDef, ToolDirection, ToolOrientation, ToolType
from outputs.gcode_writer import GCodeWriter
from pipeline.model_builder import build_from_fields
from pipeline.pipeline import execute

_app = QApplication.instance() or QApplication([])
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RS274 = shutil.which("rs274")
CNMG = ToolDef(tool_number=4, nose_radius=0.016, tip_angle=80.0, edge_length=0.375,
               orientation=ToolOrientation(2), direction=ToolDirection.RIGHT,
               tool_type=ToolType.TURNING, description="CNMG")


def _step_with_concave_fillet(radius):
    """OD step-up Ø.5 -> Ø1.5 at Z-1 with a concave fillet in the corner."""
    segs = [{"type": "line", "x": x, "z": z, "radius": 0.0}
            for x, z in [(0.5, 0.0), (0.5, -1.0), (1.5, -1.0), (1.5, -1.5)]]
    return dict(segments=segs, stock_dia=1.6, x_start=0.0, z_start=0.05, z_end=-1.5,
                stock_back_z=None, mode="od", pilot_hole_dia=0.0, doc_dia=0.04, feed=0.006,
                strategy="offset_contour", fin_allowance=0.01, peck_enabled=False,
                peck_length=None, spindle_rpm=1000.0, finish_passes=1, finish_doc_dia=0.002,
                finish_feed=0.003, finish_spring_pass=False, tool_def=CNMG, x_park=2.0,
                z_park=1.0,
                corner_breaks=[None, {"type": "fillet", "radius": radius, "size": 0.0,
                                      "angle": 45.0}, None])


def _plan(fields):
    p, s, r, f = build_from_fields(**fields)
    res = execute(p, s, CNMG, r, f)
    assert res.plan_result is not None, [v.message for v in res.validations
                                         if v.severity.value == "error"]
    return res.plan_result


@pytest.mark.parametrize("radius", [0.08, 0.12, 0.16])
def test_concave_fillet_roughs_without_gouge(radius):
    """Was blocked as GOUGE for R >= .12 (rough passes followed a mirrored arc)."""
    _plan(_step_with_concave_fillet(radius))


@pytest.mark.parametrize("radius", [0.08, 0.16])
def test_rough_arcs_are_canonical_short_pieces(radius):
    """Every roughing arc is a <= 90 deg piece whose label matches its short sweep."""
    from geometry.arc_math import short_sweep
    pr = _plan(_step_with_concave_fillet(radius))
    n = 0
    for p in pr.roughing_passes:
        pos = None
        for m in p.moves:
            if m.move_type in (MoveType.ARC_CW, MoveType.ARC_CCW) and pos is not None:
                c = (pos[0] / 2.0 + m.center_i / 2.0, pos[1] + m.center_k)
                sw = short_sweep((pos[0] / 2.0, pos[1]), (m.x / 2.0, m.z), c)
                assert abs(sw) <= math.pi / 2 + 1e-6
                assert (sw < 0) == (m.move_type == MoveType.ARC_CW)
                n += 1
            pos = (m.x, m.z)
    assert n > 0


@pytest.mark.skipif(RS274 is None, reason="LinuxCNC rs274 not installed")
def test_linuxcnc_never_runs_a_long_way_round_rough_arc(tmp_path):
    code = GCodeWriter().write(_plan(_step_with_concave_fillet(0.12)))
    for name in ("industry-cam.ini", "tool.tbl"):
        shutil.copy(os.path.join(REPO, name), tmp_path / name)
    var = os.path.join(REPO, "industry-cam.var")
    if os.path.exists(var):
        shutil.copy(var, tmp_path / "industry-cam.var")
    else:
        (tmp_path / "industry-cam.var").write_text("5220\t1.000000\n")
    (tmp_path / "p.ngc").write_text(code)
    subprocess.run([RS274, "-i", "industry-cam.ini", "-t", "tool.tbl", "-v",
                    "industry-cam.var", "p.ngc", "c.txt"], cwd=tmp_path,
                   stdin=subprocess.DEVNULL, capture_output=True, timeout=60)
    canon = (tmp_path / "c.txt").read_text()
    assert "PROGRAM_END" in canon
    pos, worst = None, 0.0
    for line in canon.splitlines():
        m = re.search(r"(STRAIGHT_FEED|STRAIGHT_TRAVERSE)\(([^)]*)\)", line)
        if m:
            v = [float(x) for x in m.group(2).split(",")]
            pos = (v[0], v[2])
            continue
        m = re.search(r"ARC_FEED\(([^)]*)\)", line)
        if m and pos:
            ze, xe, zc, xc, rot = [float(x) for x in m.group(1).split(",")][:5]
            ccw = (math.atan2(xe - xc, ze - zc) - math.atan2(pos[0] - xc, pos[1] - zc)) % (2 * math.pi)
            sweep = ccw if rot > 0 else ccw - 2 * math.pi
            worst = max(worst, abs(math.degrees(sweep)) if ccw else 0.0)
            pos = (xe, ze)
    assert worst <= 190.0, f"LinuxCNC would run an arc of {worst:.1f} deg"
