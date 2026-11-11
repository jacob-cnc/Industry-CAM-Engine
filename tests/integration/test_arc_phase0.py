"""Arc Phase 0: one arc identity from the kernel, canonical <= 90 deg pieces.

docs/handoffs/2026-11-10-arc-segment-strategy.md (branch claude/arc-proto).
Fixtures (tests/fixtures/arc_testbed): the owner's NX corner-break parts with
every fillet re-entered as an ARC segment, and two-quadrant OD/ID cases
(180 deg bead and groove, 120 deg crest), each entered as two <= 90 deg arcs.
"""

import json
import math
import os
import re
import shutil
import subprocess

import pytest
from PyQt5.QtWidgets import QApplication

from geometry.arc_math import (
    Arc, arc_from_kernel, merge_co_circular, short_sweep, split_at_quadrants,
)
from models.moves import MoveType
from models.tool import ToolDef, ToolDirection, ToolOrientation, ToolType
from outputs.gcode_writer import GCodeWriter
from pipeline.model_builder import build_from_fields
from pipeline.pipeline import execute

_app = QApplication.instance() or QApplication([])
HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "..", "fixtures", "arc_testbed")
REPO = os.path.dirname(os.path.dirname(HERE))
RS274 = shutil.which("rs274")

CNMG = ToolDef(tool_number=4, nose_radius=0.016, tip_angle=80.0, edge_length=0.375,
               orientation=ToolOrientation(2), direction=ToolDirection.RIGHT,
               tool_type=ToolType.TURNING, description="CNMG")
BAR = ToolDef(tool_number=1, nose_radius=0.0157, tip_angle=80.0, edge_length=0.375,
              orientation=ToolOrientation(3), direction=ToolDirection.RIGHT,
              tool_type=ToolType.BORING, description="CCMT bar")


# ----------------------------------------------------------------------
# arc_math
# ----------------------------------------------------------------------

def _pt(c, r, deg):
    return (c[0] + r * math.cos(math.radians(deg)), c[1] + r * math.sin(math.radians(deg)))


def test_sweep_from_three_points_handles_180_and_beyond():
    c, r = (0.3, -0.4), 0.1
    assert math.degrees(arc_from_kernel(_pt(c, r, 0), _pt(c, r, 90), _pt(c, r, 180), c, r).sweep) \
        == pytest.approx(180.0)
    assert math.degrees(arc_from_kernel(_pt(c, r, 3), _pt(c, r, -90), _pt(c, r, 177), c, r).sweep) \
        == pytest.approx(-186.0)


@pytest.mark.parametrize("a0,mid,a1", [(3, -90, 177), (0, 90, 180), (90, 45, 0), (10, 50, 80),
                                       (170, 200, 260)])
def test_split_pieces_are_quadrant_bounded_and_merge_back(a0, mid, a1):
    c, r = (0.3, -0.4), 0.1
    arc = arc_from_kernel(_pt(c, r, a0), _pt(c, r, mid), _pt(c, r, a1), c, r)
    pieces = split_at_quadrants(arc)
    assert sum(p.sweep for p in pieces) == pytest.approx(arc.sweep, abs=1e-9)
    for p in pieces:
        assert abs(p.sweep) <= math.pi / 2 + 1e-9
        assert short_sweep(p.start, p.end, c) == pytest.approx(p.sweep, abs=1e-9)
    merged = merge_co_circular(pieces)
    assert len(merged) == 1 and merged[0].sweep == pytest.approx(arc.sweep, abs=1e-9)


# ----------------------------------------------------------------------
# Pipeline on the test bed
# ----------------------------------------------------------------------

def _plan(name):
    d = json.load(open(os.path.join(FIX, name + ".json")))
    st, ro, fi = d["stock"], d["roughing"], d["finishing"]
    mode = st.get("mode", "od")
    tool = CNMG if mode == "od" else BAR
    p, s, r, f = build_from_fields(
        segments=d["segments"], stock_dia=st["diameter"], x_start=st.get("x_start", 0.0),
        z_start=st.get("z_start", 0.05), z_end=st["z_end"], stock_back_z=None, mode=mode,
        pilot_hole_dia=st.get("pilot_hole_dia", 0.0), doc_dia=ro["doc_dia"], feed=ro["feed"],
        strategy=ro.get("strategy", "staircase"), fin_allowance=ro["fin_allowance"],
        peck_enabled=False, peck_length=None, spindle_rpm=ro.get("spindle_rpm", 1000.0),
        finish_passes=fi.get("passes", 1), finish_doc_dia=fi.get("doc_dia", 0.002),
        finish_feed=fi.get("feed", 0.003), finish_spring_pass=False, tool_def=tool,
        x_park=st.get("x_park", 2.0), z_park=st.get("z_park", 1.0),
        corner_breaks=d.get("corner_breaks", []))
    return execute(p, s, tool, r, f)


def _arc_moves(passes):
    out = []
    for tp in passes:
        pos = None
        for m in tp.moves:
            if m.move_type in (MoveType.ARC_CW, MoveType.ARC_CCW) and pos is not None:
                out.append((pos, m))
            pos = (m.x, m.z)
    return out


def _through(pos, m, x_dia):
    """Does this arc move pass through diameter x_dia (radius space check)?"""
    c = (pos[0] / 2 + m.center_i / 2, pos[1] + m.center_k)
    rad = math.hypot(pos[0] / 2 - c[0], pos[1] - c[1])
    sw = short_sweep((pos[0] / 2, pos[1]), (m.x / 2, m.z), c)
    pts = [Arc((pos[0] / 2, pos[1]), (m.x / 2, m.z), c, rad, sw).point_at(t / 20) for t in range(21)]
    return any(abs(2 * p[0] - x_dia) < 0.003 for p in pts)


def test_od_groove_cleanup_goes_into_the_groove():
    """Was: the 186 deg offset arc was cut the short way, over the top."""
    res = _plan("OD_groove_2x90")
    assert res.plan_result is not None
    cleanup = _arc_moves(res.plan_result.cleanup_passes)
    assert cleanup
    assert any(_through(pos, m, 0.41) for pos, m in cleanup)        # groove bottom + allowance
    assert not any(_through(pos, m, 0.79) for pos, m in cleanup)    # never over the top


def test_id_bead_rapid_through_the_part_is_caught():
    """Was: the validator drew the 180 deg arc on the wrong side and passed a
    rapid that runs .007 inside the bead."""
    res = _plan("ID_bead_2x90")
    assert res.plan_result is None
    assert any("GOUGE" in v.message for v in res.validations)


@pytest.mark.parametrize("name", ["OD_NX_arcs_noV1", "ID_NX_arcs_no_undercut",
                                  "OD_groove_2x90", "ID_groove_2x90", "OD_crest120_2x60",
                                  "OD_bead_2x90"])
def test_testbed_generates_with_canonical_arcs(name):
    res = _plan(name)
    assert res.plan_result is not None, [v.message for v in res.validations
                                         if v.severity.value == "error"]
    pr = res.plan_result
    for pos, m in _arc_moves(pr.finish_passes + pr.cleanup_passes):
        c = (pos[0] / 2 + m.center_i / 2, pos[1] + m.center_k)
        sw = short_sweep((pos[0] / 2, pos[1]), (m.x / 2, m.z), c)
        # <= 90 deg plus a merged kernel-tolerance sliver (split_at_quadrants)
        assert abs(sw) <= math.pi / 2 + math.radians(0.1)
        assert (sw < 0) == (m.move_type == MoveType.ARC_CW)


@pytest.mark.skipif(RS274 is None, reason="LinuxCNC rs274 not installed")
@pytest.mark.parametrize("name", ["OD_NX_arcs_noV1", "ID_NX_arcs_no_undercut",
                                  "OD_groove_2x90", "ID_groove_2x90", "OD_crest120_2x60"])
def test_linuxcnc_runs_testbed_without_long_way_arcs(tmp_path, name):
    import sys
    sys.path.insert(0, os.path.join(REPO, "scripts", "arc_testbed"))
    from sweep_audit import audit
    code = GCodeWriter().write(_plan(name).plan_result)
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
