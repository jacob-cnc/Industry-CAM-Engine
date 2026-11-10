"""Arcs the engine writes must run in LinuxCNC exactly as the preview draws them.

Found on the lathe 2026-11-10 (air cut of the GCH bore with an ID fillet):
the writer emitted I as a DIAMETER offset and mirrored G02/G03, so LinuxCNC
rejected every arc program ("radius to end of arc differs", cutter-comp gouge
errors). outputs/gcode_dialect.py now owns the mapping; these tests pin it.

The rs274 tests run the generated program through LinuxCNC's own standalone
interpreter (no realtime, no machine) and are skipped where rs274 is not
installed (dev PCs).
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
from outputs.gcode_dialect import (
    arc_type_for_gcode, center_i_from_i_word, gcode_for_arc, i_word_from_center_i,
)
from outputs.gcode_parser import parse
from outputs.gcode_writer import GCodeWriter
from pipeline.model_builder import build_from_fields
from pipeline.pipeline import execute

_app = QApplication.instance() or QApplication([])

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RS274 = shutil.which("rs274")

CNMG = ToolDef(tool_number=4, nose_radius=0.016, tip_angle=80.0, edge_length=0.375,
               orientation=ToolOrientation(2), direction=ToolDirection.RIGHT,
               tool_type=ToolType.TURNING, description="CNMG")
BAR = ToolDef(tool_number=1, nose_radius=0.0157, tip_angle=80.0, edge_length=0.375,
              orientation=ToolOrientation(3), direction=ToolDirection.RIGHT,
              tool_type=ToolType.BORING, description="CCMT bar")


def _fields(segments, corner_breaks, mode, stock_dia, z_end, pilot=0.0, x_start=0.0,
            **over):
    f = dict(segments=segments, stock_dia=stock_dia, x_start=x_start, z_start=0.05,
             z_end=z_end, stock_back_z=None, mode=mode, pilot_hole_dia=pilot,
             doc_dia=0.04, feed=0.006, strategy="staircase", fin_allowance=0.01,
             peck_enabled=False, peck_length=None, spindle_rpm=1000.0, finish_passes=1,
             finish_doc_dia=0.002, finish_feed=0.003, finish_spring_pass=False,
             tool_def=CNMG if mode == "od" else BAR, x_park=2.0, z_park=1.0,
             corner_breaks=corner_breaks)
    f.update(over)
    return f


def _seg(x, z):
    return {"type": "line", "x": x, "z": z, "radius": 0.0}


def _mm(v):
    return v / 25.4


def _od_nx_part():
    """Owner's NX reference part (inch), V1 sharp: convex + concave fillets,
    chamfers, the V9 cut-short fillet and the V10 R3 concave fillet."""
    pts = [(6, 0), (6, -6), (12, -6), (12, -12), (6, -12), (6, -18), (15, -18),
           (15, -21), (12, -21), (12, -27), (18, -27), (18, -33)]
    c = lambda s: {"type": "chamfer", "size": _mm(s), "angle": 45.0, "radius": 0.0}
    r = lambda s: {"type": "fillet", "size": 0.0, "angle": 45.0, "radius": _mm(s)}
    breaks = [None, c(1), r(1), r(1), r(1), r(1), c(1), c(1), r(1), r(3), None]
    return _fields([_seg(_mm(d), _mm(z)) for d, z in pts], breaks, "od", 0.75, -1.3)


def _id_gch_fillet():
    """GCH ring bore with the owner's R.010 fillet at the chamfer-to-bore corner."""
    segs = [_seg(3.127, 0.0), _seg(3.099, -0.014), _seg(3.099, -0.56), _seg(2.95, -0.56)]
    breaks = [None, {"type": "fillet", "radius": 0.01, "size": 0.0, "angle": 45.0}, None]
    # Parameters as saved by the owner ("GCH Boring Test Ring Bore NEW.json").
    return _fields(segs, breaks, "id", 4.0, -0.56, pilot=2.95, x_start=2.95,
                   z_start=0.1, stock_back_z=-1.0, doc_dia=0.035, feed=0.01,
                   fin_allowance=0.003, spindle_rpm=64.0, finish_passes=2,
                   finish_doc_dia=0.0015, finish_feed=0.008, x_park=2.5)


CASES = {"od_nx_part": _od_nx_part, "id_gch_fillet": _id_gch_fillet}


def _generate(fields):
    tool = fields["tool_def"]
    p, s, r, f = build_from_fields(**fields)
    res = execute(p, s, tool, r, f)
    assert res.plan_result is not None, [v.message for v in res.validations]
    return res.plan_result, GCodeWriter().write(res.plan_result)


def _internal_arcs(plan):
    moves = []
    for group in (plan.roughing_passes, plan.cleanup_passes, plan.finish_passes):
        for p in group or []:
            moves.extend(m for m in p.moves
                         if m.move_type in (MoveType.ARC_CW, MoveType.ARC_CCW))
    return moves


# ----------------------------------------------------------------------
# The mapping itself
# ----------------------------------------------------------------------

def test_dialect_mapping_is_its_own_inverse():
    for mt in (MoveType.ARC_CW, MoveType.ARC_CCW):
        g = gcode_for_arc(mt)
        assert arc_type_for_gcode(int(g[1:])) is mt
    assert gcode_for_arc(MoveType.ARC_CW) == "G03"     # see gcode_dialect.py
    assert i_word_from_center_i(0.25) == pytest.approx(0.125)
    assert center_i_from_i_word(0.125) == pytest.approx(0.25)


@pytest.mark.parametrize("case", sorted(CASES))
def test_parser_reads_back_exactly_what_the_writer_meant(case):
    """Writer -> text -> parser gives the internal arcs back (type and centre),
    so the Program/Run graphs draw the arcs the planner produced."""
    plan, code = _generate(CASES[case]())
    wanted = _internal_arcs(plan)
    got = [m for m in parse(code) if m.move_type in (MoveType.ARC_CW, MoveType.ARC_CCW)]
    assert wanted and len(got) == len(wanted)
    for w, g in zip(wanted, got):
        assert g.move_type is w.move_type
        assert g.x == pytest.approx(w.x, abs=1e-4) and g.z == pytest.approx(w.z, abs=1e-4)
        assert g.center_i == pytest.approx(w.center_i, abs=2e-4)   # I has 4 decimals
        assert g.center_k == pytest.approx(w.center_k, abs=1e-4)


def test_preview_parser_matches_move_parser():
    from gui.components.sim_viewer import parse_gcode_for_sim
    _, code = _generate(_od_nx_part())
    sim = [m for m in parse_gcode_for_sim(code) if m.move_type.startswith("arc")]
    mv = [m for m in parse(code) if m.move_type in (MoveType.ARC_CW, MoveType.ARC_CCW)]
    assert len(sim) == len(mv) > 0
    for s, m in zip(sim, mv):
        assert s.move_type == m.move_type.value
        assert s.center_i == pytest.approx(m.center_i, abs=1e-9)


# ----------------------------------------------------------------------
# LinuxCNC's own interpreter
# ----------------------------------------------------------------------

def _rs274(tmp_path, code):
    """Run code through rs274 with copies of the machine ini/tool table/var."""
    for name in ("industry-cam.ini", "tool.tbl"):
        shutil.copy(os.path.join(REPO, name), tmp_path / name)
    var = os.path.join(REPO, "industry-cam.var")
    if os.path.exists(var):
        shutil.copy(var, tmp_path / "industry-cam.var")
    else:
        (tmp_path / "industry-cam.var").write_text("5220\t1.000000\n")
    (tmp_path / "prog.ngc").write_text(code)
    proc = subprocess.run(
        [RS274, "-i", "industry-cam.ini", "-t", "tool.tbl", "-v", "industry-cam.var",
         "prog.ngc", "canon.txt"],
        cwd=tmp_path, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)
    canon = (tmp_path / "canon.txt").read_text() if (tmp_path / "canon.txt").exists() else ""
    return proc.stdout + proc.stderr, canon


@pytest.mark.skipif(RS274 is None, reason="LinuxCNC rs274 not installed")
@pytest.mark.parametrize("case", sorted(CASES))
def test_linuxcnc_runs_every_arc(tmp_path, case):
    _, code = _generate(CASES[case]())
    out, canon = _rs274(tmp_path, code)
    assert "PROGRAM_END" in canon, out[-600:]
    assert canon.count("ARC_FEED") >= len(re.findall(r"^N\d+ G0[23] ", code, re.M))


@pytest.mark.skipif(RS274 is None, reason="LinuxCNC rs274 not installed")
def test_linuxcnc_arc_matches_internal_geometry(tmp_path):
    """Without cutter comp, every ARC_FEED must have the planner's centre and
    sweep the same way (minor arc, same end) as the internal move."""
    plan, code = _generate(_od_nx_part())
    # Strip comp so canon ARC_FEEDs are the programmed arcs one-to-one.
    code = re.sub(r"\bG4[12]\b", "G40", code)
    out, canon = _rs274(tmp_path, code)
    assert "PROGRAM_END" in canon, out[-600:]
    feeds = re.findall(r"ARC_FEED\(([^)]*)\)", canon)
    arcs = []
    prev = None
    for line in code.splitlines():
        m = re.match(r"N\d+ (G0[0-3]) X(-?[\d.]+) Z(-?[\d.]+)(?: I(-?[\d.]+) K(-?[\d.]+))?", line)
        if not m:
            continue
        x, z = float(m.group(2)), float(m.group(3))
        if m.group(1) in ("G02", "G03"):
            arcs.append((prev, (x, z), m.group(1), float(m.group(4)), float(m.group(5))))
        prev = (x, z)
    assert len(feeds) == len(arcs) > 0
    for f, (start, end, g, i_word, k_word) in zip(feeds, arcs):
        # G18 canon: ARC_FEED(first_end=Z, second_end=X, first_axis=Zc, second_axis=Xc, rot, ...)
        ze, xe, zc, xc, rot = (float(v) for v in f.split(",")[:5])
        # canon X is the axis value (radius; G7 halves X words)
        assert xe == pytest.approx(end[0] / 2.0, abs=2e-4)
        assert ze == pytest.approx(end[1], abs=1e-4)
        assert xc == pytest.approx(start[0] / 2.0 + i_word, abs=2e-4)
        assert zc == pytest.approx(start[1] + k_word, abs=1e-4)
        # Sweep must be the short way round (all profile arcs here are < 180 deg).
        a0 = math.atan2(start[0] / 2.0 - xc, start[1] - zc)
        a1 = math.atan2(xe - xc, ze - zc)
        d = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi     # signed minor sweep, Z->X positive
        assert (d > 0) == (rot > 0), (g, rot, math.degrees(d))


# ----------------------------------------------------------------------
# Concave fillets not larger than the nose radius (owner decision 2026-11-10)
# ----------------------------------------------------------------------

def _od_step_with_concave_fillet(radius):
    """OD step-up: Ø.500 to Z-.5, face up to Ø1.000. The corner at
    (Ø.500, Z-.5) is concave (inside corner) for the turning tool."""
    segs = [_seg(0.5, 0.0), _seg(0.5, -0.5), _seg(1.0, -0.5), _seg(1.0, -1.0)]
    breaks = [None, {"type": "fillet", "radius": radius, "size": 0.0, "angle": 45.0}, None]
    return _fields(segs, breaks, "od", 1.1, -1.0)


def _finish_and_cleanup_arcs(code):
    tail = code.split("; === CLEANUP")[-1] if "; === CLEANUP" in code else code
    return re.findall(r"^N\d+ G0[23] .*$", tail, re.M)


def test_concave_fillet_below_nose_radius_is_cut_sharp_with_a_note():
    plan, _ = _generate(_od_step_with_concave_fillet(0.010))    # CNMG TNR .016
    w = GCodeWriter()
    code = w.write(plan)
    assert not _finish_and_cleanup_arcs(code), _finish_and_cleanup_arcs(code)
    assert w.notes and all("sharp corner" in n for n in w.notes)
    assert "; NOTE:" in code
    # The comp contour now meets the sharp vertex (Ø.500, Z-.5) exactly.
    assert re.search(r"^N\d+ G01 X0\.5000 Z-0\.5000\b", code, re.M), code


def test_concave_fillet_larger_than_nose_radius_keeps_its_arc():
    plan, _ = _generate(_od_step_with_concave_fillet(0.030))
    w = GCodeWriter()
    code = w.write(plan)
    assert _finish_and_cleanup_arcs(code)
    assert not w.notes


@pytest.mark.skipif(RS274 is None, reason="LinuxCNC rs274 not installed")
@pytest.mark.parametrize("radius", [0.010, 0.016, 0.030])
def test_linuxcnc_runs_concave_fillet_around_nose_radius(tmp_path, radius):
    _, code = _generate(_od_step_with_concave_fillet(radius))
    out, canon = _rs274(tmp_path, code)
    assert "PROGRAM_END" in canon, out[-600:]
