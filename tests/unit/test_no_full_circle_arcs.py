"""No arc may end where it starts at output precision (2026-11-12).

LinuxCNC runs a G2/G3 whose end point equals its start point as a FULL circle.
Kernel offsets left sub-.0001 arc slivers in offset-contour roughing passes;
printed at 4 decimals they became e.g. 'G02 X0.9531 Z-0.5321 I-0.2426 K0.0212'
from X0.9531 Z-0.5321 - a full R.2435 circle through the part (Corner Break
Test on main 517fe43..5e12c13). Three layers now prevent it:
  pipeline._no_degenerate_arcs   planned slivers become straight feeds
  GCodeWriter._arc               refuses to print one
  cut_regions.parse_canon        reads a same-point ARC_FEED as LinuxCNC does
"""
import math

import pytest

from models.moves import MoveType, PassType, ToolMove
from models.results import TurningPass
from outputs.gcode_writer import GCodeWriter
from pipeline.pipeline import _no_degenerate_arcs
from validation.cut_regions import parse_canon


def test_pipeline_turns_a_sliver_arc_into_a_feed():
    sliver = ToolMove(MoveType.ARC_CCW, 0.95315, -0.53212, feed=0.01, center_i=-0.4852, center_k=0.0212)
    keep = ToolMove(MoveType.ARC_CW, 0.95, -0.6, feed=0.01, center_i=-0.2, center_k=-0.03)
    p = TurningPass(x_level=0.9531, z_start=-0.5321, z_end=-0.6, pass_index=0,
                    pass_type=PassType.ROUGH, moves=[sliver, keep])
    out = _no_degenerate_arcs([p])[0].moves
    assert out[0].move_type == MoveType.FEED and (out[0].x, out[0].z) == (0.95315, -0.53212)
    assert out[1] is keep


def test_writer_refuses_an_arc_ending_at_its_start():
    w = GCodeWriter()
    w._x, w._z, w._conv, w._fmt, w._n, w._feed = 0.9531, -0.5321, 1.0, "z.4f", 10, None
    arc = ToolMove(MoveType.ARC_CCW, 0.95312, -0.53213, feed=0.01, center_i=-0.4852, center_k=0.0212)
    with pytest.raises(ValueError, match="FULL circle"):
        w._arc(arc, "Rough pass 1 cut")


def test_checker_reads_a_same_point_arc_as_a_full_circle():
    canon = ("STRAIGHT_FEED(0.4765, 0.0000, -0.5321, 0, 0, 0)\n"
             "ARC_FEED(-0.5321, 0.4765, -0.5109, 0.2339, -1, 0, 0, 0, 0)\n")
    arc = [m for m in parse_canon(canon) if not m.rapid][-1]
    zs = [p[1] for p in arc.pts]
    rs = [p[0] for p in arc.pts]
    R = math.hypot(0.4765 - 0.2339, -0.5321 + 0.5109)
    assert max(zs) - min(zs) == pytest.approx(2 * R, rel=0.01)
    assert max(rs) - min(rs) == pytest.approx(2 * R, rel=0.01)
