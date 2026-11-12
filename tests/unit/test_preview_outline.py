"""The Program-tab preview draws the ENGINE's outline (2026-11-12).

ProgramTab._outline_rows samples the very kernel edges the zone builder
machines (geometry/zone_builder.sample_outline over the corner solver's
coords), so the preview cannot disagree with the cut. These tests check the
preview points, per row, against the geometry definitions:

  * quadrant rows: inside the box of their end points and on the quarter
    circle (were: tests of the old preview-only _quadrant_arc_kernel_points);
  * same-X quadrants: drawn as the two quadrants they are cut as, OD and ID;
  * corner breaks next to arcs: the operator's arc and a tangent fillet;
  * every preview point lies on the finished part's profile wire;
  * a row being typed (radius too small for its chord) does not break the
    rest of the preview: that element is a straight guide.
"""
import math
import types

import pytest

from geometry.arc_entry import quadrant_centre
from gui.program_tab import ProgramTab

TOL = 1e-6


def _tab(mode="od"):
    """Just enough of a ProgramTab for the outline helpers."""
    stub = types.SimpleNamespace(_get_machining_mode=lambda: mode)
    stub._od_corner_result = lambda s=None, b=None: ProgramTab._od_corner_result(stub, s, b)
    return stub


def _rows(segments, breaks=None, mode="od"):
    breaks = breaks if breaks is not None else [None] * (len(segments) - 1)
    return ProgramTab._outline_rows(_tab(mode), segments, breaks)


def _row_points(rows, row):
    return [p for r, pts in rows if r == row for p in pts]


QUADRANT_CASES = [  # (x_start_r, z_start, x_end_r, z_end): every direction, equal legs
    (0.375, -0.75, 0.625, -1.0),
    (0.375, -0.75, 0.625, -0.5),
    (0.625, -0.75, 0.375, -1.0),
    (0.625, -0.75, 0.375, -0.5),
    (0.5, -0.1, 1.5, -1.1),
]


@pytest.mark.parametrize("sign", [1, -1])
@pytest.mark.parametrize("x0,z0,x1,z1", QUADRANT_CASES)
def test_quadrant_row_in_box_and_on_the_circle(x0, z0, x1, z1, sign):
    segs = [{"type": "line", "x": 2 * x0, "z": 0.0},
            {"type": "line", "x": 2 * x0, "z": z0},
            {"type": "arc", "x": 2 * x1, "z": z1, "radius": "Q" if sign > 0 else "-Q"},
            {"type": "line", "x": 2 * x1, "z": z1 - 0.5}]
    pts = _row_points(_rows(segs), 2)
    assert math.dist(pts[0], (x0, z0)) < 1e-12 and math.dist(pts[-1], (x1, z1)) < 1e-12
    c = quadrant_centre((x0, z0), (x1, z1), sign)
    R = abs(x1 - x0)
    assert len(pts) > 8
    for px, pz in pts:
        assert min(x0, x1) - TOL <= px <= max(x0, x1) + TOL
        assert min(z0, z1) - TOL <= pz <= max(z0, z1) + TOL
        assert math.hypot(px - c[0], pz - c[1]) == pytest.approx(R, abs=1e-9)


@pytest.mark.parametrize("sign,mode,apex_r", [(1, "od", 0.75), (-1, "od", 0.25),
                                              (1, "id", 0.25), (-1, "id", 0.75)])
def test_same_x_quadrant_is_drawn_as_two_quadrants(sign, mode, apex_r):
    segs = [{"type": "line", "x": 1.0, "z": 0.0},
            {"type": "arc", "x": 1.0, "z": -0.5, "radius": "Q" if sign > 0 else "-Q"},
            {"type": "line", "x": 1.0, "z": -1.0}]
    rows = _rows(segs, mode=mode)
    pts = _row_points(rows, 1)
    far = max(pts, key=lambda p: abs(p[0] - 0.5))
    assert far[0] == pytest.approx(apex_r, abs=1e-9) and far[1] == pytest.approx(-0.25, abs=1e-9)
    for px, pz in pts:
        assert math.hypot(px - 0.5, pz + 0.25) == pytest.approx(0.25, abs=1e-9)
    assert {r for r, _ in rows} == {0, 1, 2}        # the split point stays on row 1


def _arc_profile():
    return [{"type": "line", "x": 1.0, "z": 0.0},
            {"type": "line", "x": 1.0, "z": -0.5},
            {"type": "arc", "x": 1.5, "z": -1.0, "radius": 0.4},
            {"type": "line", "x": 1.5, "z": -1.5}]


def test_fillet_next_to_arc_preview_is_the_engines():
    """The break row's points lie on the kernel's fillet circle; the arc row's
    points on the operator's circle (the old preview recomputed the break with
    the chord method)."""
    from geometry.corner_breaks_od import build_od_corner_coords
    from pipeline.model_builder import profile_from_fields
    segs = _arc_profile()
    breaks = [None, {"type": "fillet", "radius": 0.05}, None]
    res = build_od_corner_coords(profile_from_fields(segs, "od", breaks))
    g = res.geometry[1]
    rows = _rows(segs, breaks)
    on_fillet = [p for p in _row_points(rows, 2)
                 if abs(math.dist(p, g.center) - g.radius) < 1e-9]
    assert len(on_fillet) >= 16                      # the fillet is drawn, sampled
    # operator arc: same circle as without the break
    plain = _row_points(_rows(segs), 2)
    from geometry.arc_math import radius_arc_centre
    c = radius_arc_centre((0.5, -0.5), (0.75, -1.0), 0.4)
    assert all(abs(math.dist(p, c) - 0.4) < 1e-9 for p in plain)
    tail = [p for p in _row_points(rows, 2) if abs(math.dist(p, g.center) - g.radius) > 1e-9]
    assert tail and all(abs(math.dist(p, c) - 0.4) < 1e-9 for p in tail)


def test_every_preview_point_is_on_the_machined_profile():
    from build123d import Vector
    from geometry.zone_builder import _build_face_from_coords, profile_to_radius_coords
    from pipeline.model_builder import profile_from_fields
    segs = [{"type": "line", "x": 0.6, "z": 0.0}, {"type": "line", "x": 0.6, "z": -0.3},
            {"type": "line", "x": 1.0, "z": -0.3}, {"type": "arc", "x": 1.4, "z": -0.5, "radius": "Q"},
            {"type": "line", "x": 1.4, "z": -0.9}, {"type": "arc", "x": 1.0, "z": -1.2, "radius": -0.3},
            {"type": "line", "x": 1.0, "z": -1.6}]
    breaks = [{"type": "chamfer", "size": 0.03}, {"type": "fillet", "radius": 0.04}, None,
              {"type": "fillet", "radius": 0.05}, {"type": "chamfer", "size": 0.02}, None]
    profile = profile_from_fields(segs, "od", breaks)
    wire = _build_face_from_coords(profile_to_radius_coords(profile), profile, closed=False)
    for _, pts in _rows(segs, breaks):
        for p in pts:
            assert wire.distance_to(Vector(p[0], p[1], 0)) < 1e-7


def test_half_typed_radius_is_a_guide_and_the_rest_stays_exact():
    segs = _arc_profile()
    segs[2] = dict(segs[2], radius=0.1)              # chord .559: radius too small
    rows = _rows(segs)
    arc = _row_points(rows, 2)
    assert arc == [(0.5, -0.5), (0.75, -1.0)]        # straight guide
    assert _row_points(rows, 3)[-1] == (0.75, -1.5)


def test_unparseable_row_falls_back_to_straight_lines():
    segs = _arc_profile()
    segs[1] = dict(segs[1], z="")
    rows = _rows(segs)
    assert rows and all(len(pts) <= 2 for _, pts in rows)
