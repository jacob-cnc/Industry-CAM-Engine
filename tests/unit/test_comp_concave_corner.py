"""Comp entry merge and LinuxCNC concave-corner reachability (owner 2026-11-09).

The GCH ID chamfer job failed on the machine with "straight feed in concave
corner cannot be reached by the tool without gouging": the cleanup comp entry
stopped at Z0+fin (Z.0015) and left a .0006" cleanup move before the concave
chamfer corner, which needs R*tan(turn/2) = .0055".
"""

import math

import pytest
from PyQt5.QtWidgets import QApplication

from outputs.gcode_writer import GCodeWriter
from pipeline.model_builder import build_from_fields
from pipeline.pipeline import execute
from tests.integration.test_operation_depth import bore_fields
from tests.unit.test_comp_entry_and_tool_checks import BAR

_app = QApplication.instance() or QApplication([])


def _chamfer_bore_code():
    fields = bore_fields(
        segments=[dict(x=3.115, z=0), dict(x=3.099, z=-0.01),
                  dict(x=3.099, z=-0.56), dict(x=2.95, z=-0.56)],
        stock_dia=4, x_start=2.95, z_start=0.1, pilot_hole_dia=2.95,
        doc_dia=0.045, feed=0.01, fin_allowance=0.003, spindle_rpm=64,
        finish_passes=2, finish_doc_dia=0.0015, finish_feed=0.008)
    fields["tool_def"] = BAR
    p, s, r, f = build_from_fields(**fields)
    result = execute(p, s, BAR, r, f)
    assert result.plan_result is not None, result.validations
    return GCodeWriter().write(result.plan_result)


def _comp_runs(code):
    """Yield (X, Z) polylines of each G41/G42 ... G40 run (X diameter)."""
    runs, cur, x, z = [], None, None, None
    for line in code.splitlines():
        blk = line.split(";")[0].split("(")[0]
        if not blk.startswith("N"):
            continue
        words = dict((w[0], w[1:]) for w in blk.split()[1:] if w[0] in "GXZ")
        if "X" in words:
            x = float(words["X"])
        if "Z" in words:
            z = float(words["Z"])
        g = words.get("G")
        if g in ("41", "42"):
            cur = [(x, z)]
            runs.append(cur)
        elif g == "40":
            cur = None
        elif cur is not None and ("X" in words or "Z" in words):
            cur.append((x, z))
    return runs


def test_owner_chamfer_bore_has_no_unreachable_concave_corner():
    code = _chamfer_bore_code()
    r = BAR.nose_radius
    runs = _comp_runs(code)
    assert len(runs) >= 3                      # cleanup + 2 finish passes
    for run in runs:
        for a, b, c in zip(run, run[1:], run[2:]):
            d1 = (b[1] - a[1], (b[0] - a[0]) / 2)
            d2 = (c[1] - b[1], (c[0] - b[0]) / 2)
            l1, l2 = math.hypot(*d1), math.hypot(*d2)
            if l1 < 1e-9 or l2 < 1e-9:
                continue
            cross = (d1[0] * d2[1] - d1[1] * d2[0]) / (l1 * l2)
            dot = (d1[0] * d2[0] + d1[1] * d2[1]) / (l1 * l2)
            if cross > 1e-9:                   # G41: left turn is concave
                need = r * math.tan(math.atan2(cross, dot) / 2)
                assert l1 >= need, (a, b, c, l1, need)


def test_cleanup_entry_ends_in_air_high_enough_for_the_corner():
    code = _chamfer_bore_code()
    lines = [l for l in code.splitlines() if l.startswith("N")]
    e = next(i for i, l in enumerate(lines) if "Comp entry move" in l)
    entry, first = lines[e], lines[e + 1]
    assert "Cleanup move 1" in first and "Z0.0009" in first   # plan move kept
    entry_z = float(entry.split("Z")[1].split()[0])
    # entry ends above the face (air), far enough above the contour start
    assert entry_z > 0.0 and entry_z - 0.0009 >= 2 * BAR.nose_radius


def test_check_rejects_short_line_before_concave_corner():
    path = [(3.1127, 0.1), (3.1127, 0.0015), (3.1127, 0.0009), (3.0960, -0.0095)]
    with pytest.raises(ValueError, match="concave corner"):
        GCodeWriter._check_concave_corners(path, 0.0157, "G41", "Cleanup move")
    # same geometry is convex for G42 -> no error; arcs (None) are skipped
    GCodeWriter._check_concave_corners(path, 0.0157, "G42", "x")
    GCodeWriter._check_concave_corners([path[0], path[1], None, path[3]], 0.0157, "G41", "x")
