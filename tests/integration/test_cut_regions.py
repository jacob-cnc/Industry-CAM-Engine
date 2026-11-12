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


def _envelope_ok(code, pr):
    """Every programmed X/Z stays in a sane envelope: centre overshoot up to
    2*(TNR + .002) below X0, nothing beyond the stock / park position. (An entry
    to X18.2 was caught this way, 2026-11-11.)"""
    import re
    tnr = max(pr.tool.nose_radius, getattr(getattr(pr, "finish_tool", None), "nose_radius", 0.0) or 0.0)
    x_hi = max(pr.stock.diameter, pr.stock.x_park) + 0.25
    z_hi = max(pr.stock.z_start, pr.stock.z_park) + 0.25
    z_lo = pr.stock.z_end - 0.25
    for line in code.splitlines():
        if line.lstrip().startswith(";") or not re.search(r"\bG0?[0123]\b", line.split(";")[0]):
            continue
        body = line.split(";")[0]
        for w, v in re.findall(r"\b([XZ])(-?\d+\.?\d*)", body):
            v = float(v)
            if w == "X":
                assert -2 * (tnr + 0.002) - 1e-4 <= v <= x_hi, line
            else:
                assert z_lo <= v <= z_hi, line


def _sections(res, gcode=None):
    pr = res.plan_result
    outl = [v.outline for v in res.validations if v.category == "tool_reach" and v.outline]
    code = gcode or GCodeWriter().write(pr)
    if gcode is None:
        _envelope_ok(code, pr)
    return compute_sections(code, pr, outl)


FACED = dict(x_start=0.0)       # face to the centre so nothing is left in front of Z0


def _run(rows, tool, **kw):
    from pipeline.model_builder import build_from_fields
    from pipeline.pipeline import execute
    p, s, r, f = build_from_fields(
        segments=rows, stock_dia=kw.get("stock_dia", 1.4), x_start=kw.get("x_start", 0.0),
        z_start=kw.get("z_start", 0.05), z_end=min(x["z"] for x in rows), stock_back_z=None,
        mode=kw.get("mode", "od"),
        pilot_hole_dia=kw.get("pilot", 0.0), doc_dia=0.08, feed=0.008, strategy="staircase",
        fin_allowance=kw.get("fin", 0.02), peck_enabled=False, peck_length=None, spindle_rpm=1000.0,
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
        if m.section in ("cleanup", "finish") and not m.rapid:
            c = [(r + off[0], z + off[1]) for r, z in m.pts]
            mid = ((c[0][0] + c[-1][0]) / 2, (c[0][1] + c[-1][1]) / 2)
            if chamfer.distance(Point(mid)) < 0.03 and abs(abs(c[-1][0] - c[0][0]) - abs(c[-1][1] - c[0][1])) < 1e-6:
                d.append(chamfer.distance(Point(mid)))
    assert d and min(abs(x - pr.tool.nose_radius) for x in d) < 2e-5


def test_cleanup_is_tagged_as_the_band_not_roughing():
    tagged = tag_sections("; === CLEANUP PASS (semi-finish, roughing boundary contour) ===\n"
                          "; === ROUGHING PASSES (3 passes) ===\n; === FACE PASSES (1 passes) ===\n")
    assert [l for l in tagged.splitlines() if l.startswith("(")] == [
        "(ICAM_SECTION cleanup)", "(ICAM_SECTION rough)", "(ICAM_SECTION face)"]


# ----------------------------------------------------------------------
# The sections
# ----------------------------------------------------------------------

def _partition_ok(s):
    names = ("face", "rough", "cleanup", "finish", "finished", "uncut")
    total = sum(getattr(s, n).area for n in names)
    assert total == pytest.approx(s.stock.area, abs=1e-7)
    for a, b in itertools.combinations(names, 2):
        assert getattr(s, a).intersection(getattr(s, b)).area < 1e-8, (a, b)   # grid noise


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
    assert not s.cleanup.is_empty and not s.finish.is_empty
    assert not s.rough.is_empty and not s.face.is_empty


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


@pytest.mark.parametrize("strategy", ["staircase", "offset_contour"])
@pytest.mark.parametrize("name", ["OD_crest120_2x60", "OD_groove_2x90"])
def test_roughing_beside_a_falling_flank_does_not_gouge(name, strategy):
    """Defect found by this check (2026-11-11), now fixed: roughing runs
    uncompensated, so LinuxCNC drives the imaginary tip and the nose sits behind
    and above it (Q2). Beside a contour falling toward the chuck - reachable with
    a VNMG - the nose went .0125 into a 60 deg flank against a .005 allowance.
    Staircase passes are now trimmed against a nose-aware keep zone and contour
    passes offset for the nose centre; nothing is left for cleanup to miss."""
    import test_arc_phase0 as P
    orig = json.load

    def with_strategy(fh, *a, **k):
        d = orig(fh, *a, **k)
        if isinstance(d, dict) and "roughing" in d:
            d["roughing"]["strategy"] = strategy
        return d
    json.load = with_strategy
    try:
        res = _plan_with(name, VNMG)
    finally:
        json.load = orig
    assert res.plan_result.roughing_params.strategy.value == strategy
    s = _sections(res)
    assert s.ok, s.notes


def test_id_mouth_chamfer_is_finished_to_the_top():
    """Defect found by this check (2026-11-11), now fixed: an ID contour starting
    with a bore-mouth chamfer. The finish entered along Z0 across the mouth and
    turned back down the chamfer; comp treated the in-air lead as a wall and the
    nose never reached the top of the chamfer (up to .005 left). The lead is now
    dropped as air and the pass enters in line with the chamfer."""
    res = _plan_with("ID_NX_arcs_no_undercut", BAR)
    s = _sections(res)
    assert s.ok, s.notes
    code = GCodeWriter().write(res.plan_result)
    fin = code[code.index("=== FINISH PASS"):]
    assert "in line with the first cut" in fin


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


def test_tool_without_nose_or_angles_is_not_guessed():
    """A sharp tool with no edge angles (e.g. the QCTP master tool, T99 D0 I0 J0)
    sweeps no area we can model: say so instead of painting it all as an error."""
    from outputs.cut_regions import CutRegionsUnavailable
    bare = replace(CNMG, nose_radius=0.0, front_angle=0.0, back_angle=0.0)
    res = _run(STEPPED, bare)
    with pytest.raises(CutRegionsUnavailable, match="no nose radius or edge angles"):
        _sections(res)


_REF = os.path.join(os.path.dirname(__file__), "..", "..", "reference", "CAD Reference", "Engine Output")


def _reference_blocks():
    import glob
    out = []
    for f in sorted(glob.glob(os.path.join(_REF, "**", "*.json"), recursive=True)):
        d = json.load(open(f))
        for b in d.get("blocks", [d]):
            pdata = b.get("params_data", b)
            bt = b.get("block_type", "")
            if ("rofile" in bt or "profile" in bt) and "stock" in pdata:
                out.append(pytest.param(f, b, id=os.path.basename(f)))
    return out


@pytest.mark.parametrize("path,block", _reference_blocks())
def test_owner_reference_programs_check_clean(path, block):
    """Every saved reference program, with the repo's tool table: generates,
    runs in LinuxCNC's interpreter, sections partition the stock, no gouge and
    nothing left that should go (or, for a tool with no nose radius or angles,
    an honest 'can't tell')."""
    from outputs.cut_regions import CutRegionsUnavailable
    from pipeline.model_builder import build_from_fields
    from pipeline.pipeline import execute
    from pipeline.tool_card_data import tool_card_to_tool_def
    from pipeline.tool_table_io import load_tool_table
    repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    tools = {c.tool_number: tool_card_to_tool_def(c) for c in load_tool_table(os.path.join(repo, "tool.tbl"))}
    pdata = block.get("params_data", block)
    bt = block.get("block_type", "")
    mode = "id" if ("ID" in bt or "id_" in bt) else "od"
    st, ro, fi = pdata["stock"], pdata["roughing"], pdata.get("finishing", {})
    tool = tools.get(ro.get("tool_number") or block.get("tool_number") or (1 if mode == "id" else 4), tools[4])
    if mode == "od" and tool.tool_type.value == "boring":
        tool = tools[4]
    p, s, r, f = build_from_fields(
        segments=pdata["segments"], stock_dia=st["diameter"], x_start=st.get("x_start", 0),
        z_start=st.get("z_start", 0.05), z_end=st["z_end"], stock_back_z=None, mode=mode,
        pilot_hole_dia=st.get("pilot_hole_dia", 0), doc_dia=ro.get("doc_dia", 0.05),
        feed=ro.get("feed", 0.008), strategy=ro.get("strategy", "staircase"),
        fin_allowance=ro.get("fin_allowance", 0.01), peck_enabled=False, peck_length=None,
        spindle_rpm=ro.get("spindle_rpm", 1000), finish_passes=fi.get("passes", 1),
        finish_doc_dia=fi.get("doc_dia", .002), finish_feed=fi.get("feed", .003),
        finish_spring_pass=False, tool_def=tool, x_park=st.get("x_park", 3.0),
        z_park=st.get("z_park", 1.0), corner_breaks=pdata.get("corner_breaks", []))
    res = execute(p, s, tool, r, f)
    assert res.plan_result is not None, [v.message for v in res.validations if v.severity.value == "error"]
    try:
        sec = _sections(res)
    except CutRegionsUnavailable as exc:
        assert "no nose radius or edge angles" in str(exc)
        return
    _partition_ok(sec)
    assert sec.ok, sec.notes


@pytest.mark.parametrize("label,rows,x_start", [
    ("flat face from X0", _rows(0.0, (0.6, 0.0), (0.8, -0.1), (0.8, -0.5), (1.2, -0.5), (1.2, -1.0)), 0.0),
    # .005 allowance: at .020 this dome's cleanup is refused by LinuxCNC - item 4, open
    ("dome from X0", _rows(0.0, (0.5, -0.25, 0.25), (0.5, -0.6), (1.2, -0.6), (1.2, -1.0)), 0.0),
    ("X start 0, profile starts at X.4", _rows(0.4, (0.4, -0.3), (1.2, -0.3), (1.2, -1.0)), 0.0),
])
def test_no_centre_nib_and_a_flat_face(label, rows, x_start):
    """Owner 2026-11-11: with X start 0 or segment 1 at X0 the nose goes nose
    radius + .002 past the centreline - no nib - and the face is cut flat at Z0
    (it was a .001 cone from the Z0+.001 lead), flowing straight into the profile."""
    from shapely.geometry import box
    res = _run(rows, CNMG, x_start=x_start, fin=0.005 if label.startswith("dome") else 0.02)
    s = _sections(res)
    assert s.ok, s.notes
    front = s.finished.union(s.uncut).intersection(box(-5, 1e-5, 5, 5))
    assert front.area < 1e-8, (label, front.bounds)
    code = GCodeWriter().write(res.plan_result)
    fin = code[code.index("=== FINISH PASS"):]
    assert "X-0.0360 Z0.0000" in fin          # 2 x (TNR .016 + .002) past centre, at Z0


def test_facing_off_leaves_the_face_alone():
    """X start at the stock OD = no facing: nothing in front of Z0 inside the
    first point is cut (owner: users often don't want the part faced). (Stock in
    front of Z0 with facing off is the open item-3 discussion.)"""
    from shapely.geometry import box, LineString
    res = _run(_rows(1.0, (1.0, -0.4), (1.2, -0.4), (1.2, -1.0)), CNMG, x_start=1.4)
    s = _sections(res)
    front = s.finished.intersection(box(-5, 1e-5, 5, 5))
    assert LineString([(0.0, 0.0), (0.0, 1.0)]).intersection(front).length == pytest.approx(0.05, abs=1e-4)


@pytest.mark.parametrize("label,rows,kw", [
    ("chamfer first, faced to centre", _rows(0.6, (0.8, -0.1), (0.8, -0.5), (1.2, -0.5), (1.2, -1.0)), {}),
    ("rounded edge first, faced", _rows(0.6, (0.8, -0.1, 0.1), (0.8, -0.5), (1.2, -0.5), (1.2, -1.0)), {}),
    ("chamfer first, facing off, face at Z0", _rows(0.6, (0.8, -0.1), (0.8, -0.5), (1.2, -0.5), (1.2, -1.0)),
     dict(x_start=1.4, z_start=0.0)),
    ("chamfer first, fin .005", _rows(0.6, (0.8, -0.1), (0.8, -0.5), (1.2, -0.5), (1.2, -1.0)), dict(fin=0.005)),
])
def test_face_chamfer_profiles_generate_and_cut_in_one_motion(label, rows, kw):
    """1a (owner 2026-11-11): a profile starting with a chamfer / rounded edge at
    the face used to be refused - the cleanup stepped straight down .0007-.0029 to
    the chamfer's offset, an inside corner LinuxCNC comp can't make. The cleanup
    now runs its first cut back along its own line to the face level: along the
    face and straight down the chamfer in one motion. With the face already at Z0
    and facing off, the inward lead over the face is air and is dropped, so the
    passes enter in line with the chamfer instead of reversing onto it."""
    res = _run(rows, CNMG, **kw)
    assert res.plan_result is not None, [v.message for v in res.validations if v.severity.value == "error"]
    s = _sections(res)                    # writes the G-code: raises if refused
    assert s.ok, s.notes


def test_face_already_at_z0_shows_no_stock_in_front():
    """Z start 0 = the face is already at Z0. The model raises z_start to
    allowance + .050 for approach clearance only; the graph must not show that
    as stock (it did: a phantom .055 stub)."""
    from shapely.geometry import box
    res = _run(_rows(1.0, (1.0, -0.4), (1.2, -0.4), (1.2, -1.0)), CNMG, x_start=1.4, z_start=0.0)
    assert res.plan_result.stock.face_at_z0
    s = _sections(res)
    assert s.stock.bounds[3] == 0.0
    assert s.finished.intersection(box(-5, 1e-6, 5, 5)).is_empty
