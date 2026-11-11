"""Shaded sections from the G-code as LinuxCNC runs it (outputs/cut_regions.py;
docs/handoffs/2026-11-11-zone-shading-plan.md). The graph must be trustworthy:
sections partition the stock exactly, their edges are where the tool cuts, and
a program that leaves material or cuts into the part shows it."""
import itertools
import json
import math
import os
import shutil
from dataclasses import replace

import pytest
from PyQt5.QtWidgets import QApplication
from shapely.geometry import LineString, Point

from outputs.cut_regions import (
    compute_sections, nose_offset, parse_canon, part_polygon, run_rs274, tag_sections,
)
from outputs.gcode_writer import GCodeWriter

pytestmark = pytest.mark.skipif(shutil.which("rs274") is None, reason="LinuxCNC rs274 not installed")
_app = QApplication.instance() or QApplication([])
FIX = os.path.join(os.path.dirname(__file__), "..", "fixtures", "arc_testbed")

import sys  # noqa: E402
sys.path.insert(0, os.path.dirname(__file__))
from test_tool_reach import BAR, CNMG, NECK, VNMG, _execute, _rows  # noqa: E402


def _sections(res, gcode=None):
    pr = res.plan_result
    outl = [v.outline for v in res.validations if v.category == "tool_reach" and v.outline]
    return compute_sections(gcode or GCodeWriter().write(pr), pr, outl)


FACED = dict(x_start=0.0)       # face to the centre so nothing is left in front of Z0


def _run(rows, tool, **kw):
    from pipeline.model_builder import build_from_fields
    from pipeline.pipeline import execute
    p, s, r, f = build_from_fields(
        segments=rows, stock_dia=kw.get("stock_dia", 1.4), x_start=kw.get("x_start", 0.0),
        z_start=0.05, z_end=min(x["z"] for x in rows), stock_back_z=None, mode=kw.get("mode", "od"),
        pilot_hole_dia=kw.get("pilot", 0.0), doc_dia=0.08, feed=0.008, strategy="staircase",
        fin_allowance=0.02, peck_enabled=False, peck_length=None, spindle_rpm=1000.0,
        finish_passes=1, finish_doc_dia=0.002, finish_feed=0.003, finish_spring_pass=False,
        tool_def=tool, x_park=kw.get("x_park", 3.0), z_park=1.0, corner_breaks=[])
    return execute(p, s, tool, r, f)


STEPPED = _rows(0.6, (0.6, -0.1), (0.8, -0.2), (0.8, -0.5), (1.0, -0.5), (1.2, -0.7), (1.2, -1.2))


# ----------------------------------------------------------------------
# What rs274 reports
# ----------------------------------------------------------------------

def test_rs274_reports_the_imaginary_tip_even_under_comp():
    """A G42 finish along a 45 deg chamfer: the nose centre (tip minus Q offset)
    sits exactly TNR from the drawn chamfer."""
    res = _run(STEPPED, CNMG)
    pr = res.plan_result
    moves = parse_canon(run_rs274(GCodeWriter().write(pr), [pr.tool]))
    off = nose_offset(pr.tool)
    chamfer = LineString([(0.3, -0.1), (0.4, -0.2)])                # X.6 Z-.1 -> X.8 Z-.2, radius
    d = []
    for m in moves:
        if m.section == "band" and not m.rapid:
            c = [(r + off[0], z + off[1]) for r, z in m.pts]
            mid = ((c[0][0] + c[-1][0]) / 2, (c[0][1] + c[-1][1]) / 2)
            if chamfer.distance(Point(mid)) < 0.03 and abs(abs(c[-1][0] - c[0][0]) - abs(c[-1][1] - c[0][1])) < 1e-6:
                d.append(chamfer.distance(Point(mid)))
    assert d and min(abs(x - pr.tool.nose_radius) for x in d) < 2e-5


def test_cleanup_is_tagged_as_the_band_not_roughing():
    tagged = tag_sections("; === CLEANUP PASS (semi-finish, roughing boundary contour) ===\n"
                          "; === ROUGHING PASSES (3 passes) ===\n; === FACE PASSES (1 passes) ===\n")
    assert [l for l in tagged.splitlines() if l.startswith("(")] == [
        "(ICAM_SECTION band)", "(ICAM_SECTION rough)", "(ICAM_SECTION face)"]


# ----------------------------------------------------------------------
# The sections
# ----------------------------------------------------------------------

def _partition_ok(s):
    names = ("face", "rough", "band", "finished", "uncut")
    total = sum(getattr(s, n).area for n in names)
    assert total == pytest.approx(s.stock.area, abs=1e-7)
    for a, b in itertools.combinations(names, 2):
        assert getattr(s, a).intersection(getattr(s, b)).area < 1e-9, (a, b)


@pytest.mark.parametrize("rows,tool", [(STEPPED, CNMG), (NECK, CNMG)])
def test_sections_partition_the_stock_and_match_the_part(rows, tool):
    res = _run(rows, tool)
    s = _sections(res)
    _partition_ok(s)
    assert s.ok, s.notes
    pr = res.plan_result
    from shapely.geometry import box
    behind = box(-1, -5, 5, 0)          # in front of Z0: the face pass's allowance is left
    part = part_polygon(pr.profile, pr.stock, False).intersection(s.stock).intersection(behind)
    left = s.finished.union(s.uncut).intersection(behind)
    # what's left = the intended part, except nose-radius fillets in concave corners
    assert left.symmetric_difference(part).area < 2e-4
    assert not s.band.is_empty and not s.rough.is_empty and not s.face.is_empty


def test_neck_uncut_section_is_the_reported_region():
    res = _run(NECK, CNMG)
    s = _sections(res)
    assert s.uncut.area == pytest.approx(0.053, abs=2e-3)
    b = s.uncut.bounds                                              # (r, z)
    assert 2 * b[0] == pytest.approx(0.7, abs=1e-3) and b[3] == pytest.approx(-0.4, abs=1e-3)


def _plan_with(name, tool):
    import test_arc_phase0 as P
    old = (P.CNMG, P.BAR)
    try:
        P.CNMG, P.BAR = tool, tool
        return P._plan(name)
    finally:
        P.CNMG, P.BAR = old


@pytest.mark.parametrize("name,tool,mode", [
    ("OD_NX_arcs_noV1", CNMG, "od"), ("OD_groove_2x90", CNMG, "od"),
    ("OD_bead_2x90", CNMG, "od"), ("ID_groove_2x90", BAR, "id"),
])
def test_testbed_parts_run_in_linuxcnc_and_check_clean(name, tool, mode):
    """Includes parts whose contour is bridged for reach - those once produced
    cleanup passes LinuxCNC refused (short arc after the bridge's concave corner)."""
    res = _plan_with(name, tool)
    assert res.plan_result is not None, [v.message for v in res.validations if v.severity.value == "error"]
    s = _sections(res)                       # raises if rs274 doesn't reach the end
    _partition_ok(s)
    assert s.gouge.is_empty


@pytest.mark.parametrize("name", ["OD_crest120_2x60", "OD_groove_2x90"])
def test_roughing_beside_a_falling_flank_gouge_is_found(name):
    """A real defect the check found (2026-11-11): roughing runs uncompensated,
    so LinuxCNC drives the imaginary tip and the nose sits behind/above it (Q2).
    A roughing plunge beside a contour falling toward the chuck - reachable with a
    VNMG - puts the nose into the flank: .0125 deep on the 60 deg crest against a
    .005 allowance. The post-planning check looks at the tip path and misses it;
    the graph must show it. Planner fix pending."""
    res = _plan_with(name, VNMG)
    s = _sections(res)
    assert not s.gouge.is_empty and any("cuts into the finished part" in n for n in s.notes)


def test_id_mouth_chamfer_left_proud_is_found():
    """A real defect the check found (2026-11-11): an ID contour that starts with
    a bore-mouth chamfer. The finish pass enters along Z0 across the mouth and
    turns back down the chamfer; LinuxCNC's comp treats the in-air entry line as a
    surface, so the nose never reaches the top of the chamfer (up to .005 left).
    The graph must show it. Writer fix pending (strategy doc / zone plan)."""
    import test_arc_phase0 as P
    old = P.BAR
    try:
        P.BAR = BAR
        res = P._plan("ID_NX_arcs_no_undercut")
    finally:
        P.BAR = old
    s = _sections(res)
    assert not s.not_removed.is_empty
    r0, z0, r1, z1 = s.not_removed.bounds
    assert 0.59 < r0 < r1 < 0.63 and -0.04 < z0 < z1 < 0.0
    assert any("should remove" in n for n in s.notes)


# ----------------------------------------------------------------------
# A broken program must show
# ----------------------------------------------------------------------

def _drop_section(gcode, header):
    out, skip = [], False
    for line in gcode.splitlines():
        if line.startswith("; ==="):
            skip = header in line
        if not skip or line.startswith("; ==="):
            out.append(line)
    return "\n".join(out) + "\n"


def test_program_without_its_finish_pass_shows_material_left():
    res = _run(STEPPED, CNMG)
    code = _drop_section(GCodeWriter().write(res.plan_result), "FINISH PASS")
    s = _sections(res, code)
    assert not s.not_removed.is_empty and any("should remove" in n for n in s.notes)
    _partition_ok(s)


def test_program_cutting_into_the_part_shows_a_gouge():
    import re
    res = _run(STEPPED, CNMG)
    code = GCodeWriter().write(res.plan_result)
    # move one finish cut .010 deeper on the diameter (X.8 -> X.79 at the Z-.5 shoulder run)
    i = code.index("=== FINISH PASS")
    fin = code[i:]
    fin2 = re.sub(r"G01 X0\.8000 Z-0\.5000", "G01 X0.7800 Z-0.5000", fin, count=1)
    assert fin2 != fin
    s = _sections(res, code[:i] + fin2)
    assert not s.gouge.is_empty and any("cuts into the finished part" in n for n in s.notes)
