"""Circular quadrant arcs (Q / -Q) stay inside the box of their end points.

Since 2026-11-11 a quadrant arc is a TRUE quarter circle (owner: ellipses are
retired; geometry/arc_entry.py). With equal legs the quarter circle about the
bounding-box corner is exactly inscribed in that box, so every preview point
(_quadrant_arc_kernel_points) lies inside it and on the circle. A same-X
"quadrant" is two quadrants and bulges out of its (zero-width) box by design.
"""

import math

import pytest

from geometry.arc_entry import quadrant_centre
from gui.program_tab import _quadrant_arc_kernel_points

TOL = 1e-6
CASES = [  # (x_start_r, z_start, x_end_r, z_end): every direction, equal legs
    (0.375, -0.75, 0.625, -1.0),
    (0.375, -0.75, 0.625, -0.5),
    (0.625, -0.75, 0.375, -1.0),
    (0.625, -0.75, 0.375, -0.5),
    (0.25, 0.0, 0.2501, -0.0001),   # tiny
    (0.5, -0.1, 1.5, -1.1),         # large
]


@pytest.mark.parametrize("sign", [1, -1])
@pytest.mark.parametrize("x0,z0,x1,z1", CASES)
def test_points_in_box_and_on_the_circle(x0, z0, x1, z1, sign):
    pts = _quadrant_arc_kernel_points(x0, z0, x1, z1, sign)
    assert pts[0] == (x0, z0) and pts[-1] == (x1, z1)
    c = quadrant_centre((x0, z0), (x1, z1), sign)
    R = abs(x1 - x0)
    for px, pz in pts:
        assert min(x0, x1) - TOL <= px <= max(x0, x1) + TOL
        assert min(z0, z1) - TOL <= pz <= max(z0, z1) + TOL
        assert math.hypot(px - c[0], pz - c[1]) == pytest.approx(R, abs=1e-9)


@pytest.mark.parametrize("sign,mode_od,apex_r", [(1, True, 0.75), (-1, True, 0.25),
                                                 (1, False, 0.25), (-1, False, 0.75)])
def test_same_x_is_drawn_as_two_quadrants(sign, mode_od, apex_r):
    pts = _quadrant_arc_kernel_points(0.5, 0.0, 0.5, -0.5, sign, 48, mode_od=mode_od)
    assert pts[0] == (0.5, 0.0) and pts[-1] == (0.5, -0.5)
    far = max(pts, key=lambda p: abs(p[0] - 0.5))
    assert far[0] == pytest.approx(apex_r, abs=1e-9) and far[1] == pytest.approx(-0.25, abs=1e-9)
    for px, pz in pts:
        assert math.hypot(px - 0.5, pz + 0.25) == pytest.approx(0.25, abs=1e-9)
