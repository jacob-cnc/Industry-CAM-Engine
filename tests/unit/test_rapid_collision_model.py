"""validation/rapid_collision.material_at_start: what is there before a block runs.

Z0 is the faced surface; Z start is a cushion that may be stock or air (owner
2026-11-11). Stock in front of Z0 is modelled only across the band the block
faces (owner 2026-11-12, GCH bores: "the Z0 datum is the true face of the
stock"): no face passes -> nothing in front of Z0.
"""
from types import SimpleNamespace

import pytest

from validation.rapid_collision import material_at_start


def _pr(face_passes, x_start, pilot=0.0):
    st = SimpleNamespace(pilot_hole_dia=pilot, diameter=4.0, z_start=0.05, z_end=-0.5,
                         x_start=x_start, face_at_z0=False)
    return SimpleNamespace(stock=st, face_passes=face_passes)


def test_no_face_passes_nothing_in_front_of_z0():
    g = material_at_start(_pr([], 2.95, pilot=2.87), True)
    assert g.bounds[3] == pytest.approx(0.0)


def test_id_face_band_is_pilot_to_x_start_only():
    g = material_at_start(_pr(["face"], 2.95, pilot=2.87), True)
    front = g.intersection(__import__("shapely.geometry", fromlist=["box"]).box(0, 0.0001, 10, 1))
    x0, _, x1, z1 = front.bounds
    assert (2 * x0, 2 * x1, z1) == pytest.approx((2.87, 2.95, 0.05))


def test_od_face_band_is_x_start_to_stock_od():
    g = material_at_start(_pr(["face"], 0.0), False)
    front = g.intersection(__import__("shapely.geometry", fromlist=["box"]).box(0, 0.0001, 10, 1))
    x0, _, x1, _ = front.bounds
    assert (2 * x0, 2 * x1) == pytest.approx((0.0, 4.0))
