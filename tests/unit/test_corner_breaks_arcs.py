"""Corner breaks next to arcs come from the geometry kernel (C1, 2026-11-12).

Until 2026-11-12 a break at a vertex with an arc neighbour used a chord
construction: the break's end point was placed along the CHORD direction, off
the arc, and the operator's arc was then redrawn through it with the same
radius - on a shifted centre (.008 in for a .05 fillet, .034 in for a .05
chamfer, scripts/hand_math/corner_break_probe.py), with a 29-43 deg kink where
a fillet should be tangent. Now OCCT's 2D fillet / chamfer builds them:

  * the operator's arc keeps its centre and radius (only its end moves);
  * a fillet is tangent to both neighbours;
  * a chamfer's ends lie on the neighbours, `size` from the sharp corner;
  * a break that does not fit next to an arc is NOT applied (reported), never
    approximated.
"""
import math

import pytest

from models.profile import (
    ClosedProfile, CornerBreak, CornerBreakType, MachiningMode, ProfileMove, SegmentType,
)

L, A = SegmentType.LINE, SegmentType.ARC
F = lambda r: CornerBreak(CornerBreakType.FILLET, radius=r)          # noqa: E731
C = lambda s: CornerBreak(CornerBreakType.CHAMFER, size=s)           # noqa: E731


def _line_arc_profile(sign, mode=MachiningMode.OD):
    return [ProfileMove(L, 1.0, 0.0), ProfileMove(L, 1.0, -0.5),
            ProfileMove(A, 1.5, -1.0, radius=sign * 0.4), ProfileMove(L, 1.5, -1.5),
            ProfileMove(L, 2.0, -1.5), ProfileMove(L, 2.0, -2.0)]


def _profile(segs, breaks, mode=MachiningMode.OD):
    b = [None] * (len(segs) - 1)
    for i, cb in breaks.items():
        b[i] = cb
    return ClosedProfile(segments=segs, corner_breaks=b, mode=mode, z_end=segs[-1].z)


def _open_edges(profile):
    from geometry.zone_builder import _build_face_from_coords, profile_to_radius_coords
    return _build_face_from_coords(profile_to_radius_coords(profile), profile, closed=False).edges()


def _circles(edges):
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GeomAbs import GeomAbs_Circle
    out = []
    for e in edges:
        ad = BRepAdaptor_Curve(e.wrapped)
        if ad.GetType() == GeomAbs_Circle:
            c = ad.Circle()
            out.append(((c.Location().X(), c.Location().Y()), c.Radius()))
    return out


def _operator_circle(segs, i):
    """Centre and radius of segment i's arc, built with no breaks at all."""
    prof = _profile(segs, {})
    circ = [c for c in _circles(_open_edges(prof)) if abs(c[1] - abs(segs[i].radius)) < 1e-12]
    assert len(circ) == 1
    return circ[0]


def _max_kink_deg(edges):
    """Largest direction change between consecutive edges of the open profile."""
    worst = 0.0
    for a, b in zip(edges, edges[1:]):
        ta, tb = a.tangent_at(1), b.tangent_at(0)
        # Orientation-robust: compare as travel directions at the shared point.
        if (a.end_point() - b.start_point()).length > 1e-7:
            continue
        worst = max(worst, math.degrees(math.acos(max(-1.0, min(1.0, ta.dot(tb))))))
    return worst


@pytest.mark.parametrize("sign", [+1, -1])
@pytest.mark.parametrize("vertex", [1, 2])           # line->arc, arc->line
def test_fillet_next_to_arc_keeps_the_arc_and_is_tangent(sign, vertex):
    segs = _line_arc_profile(sign)
    centre, radius = _operator_circle(segs, 2)
    prof = _profile(segs, {vertex: F(0.05)})
    circles = _circles(_open_edges(prof))
    same = [c for c in circles if abs(c[1] - radius) < 1e-9]
    assert same, "operator arc lost"
    assert math.dist(same[0][0], centre) < 1e-9, "operator arc centre moved"
    fillets = [c for c in circles if abs(c[1] - 0.05) < 1e-9]
    assert len(fillets) == 1
    # tangent at both fillet joints (and everywhere else the profile was smooth)
    corner = (segs[vertex].x / 2.0, segs[vertex].z)
    edges = _open_edges(prof)
    near = [e for e in edges if min((e.start_point() - _v(corner)).length,
                                    (e.end_point() - _v(corner)).length) < 0.2]
    assert _max_kink_deg(_ordered(near)) < 1e-6


@pytest.mark.parametrize("sign", [+1, -1])
@pytest.mark.parametrize("vertex", [1, 2])
def test_chamfer_next_to_arc_keeps_the_arc_and_ends_on_it(sign, vertex):
    segs = _line_arc_profile(sign)
    centre, radius = _operator_circle(segs, 2)
    from geometry.corner_breaks_od import build_od_corner_coords
    res = build_od_corner_coords(_profile(segs, {vertex: C(0.05)}))
    g = res.geometry[vertex]
    corner = (segs[vertex].x / 2.0, segs[vertex].z)
    for p in (g.t_in, g.t_out):
        assert math.dist(p, corner) == pytest.approx(0.05, abs=1e-4)
    arc_end = g.t_out if vertex == 1 else g.t_in
    assert abs(math.dist(arc_end, centre) - radius) < 1e-9, "chamfer end is off the arc"
    circles = _circles(_open_edges(_profile(segs, {vertex: C(0.05)})))
    same = [c for c in circles if abs(c[1] - radius) < 1e-9]
    assert same and math.dist(same[0][0], centre) < 1e-9


def test_arc_adjacent_reports_are_ok_with_true_corner_kind():
    from geometry.corner_breaks_od import build_od_corner_coords
    segs = _line_arc_profile(+1)
    res = build_od_corner_coords(_profile(segs, {1: F(0.05), 2: F(0.05)}))
    by_v = {r.vertex: r for r in res.reports}
    assert by_v[2].status == "ok" and by_v[3].status == "ok"
    assert by_v[2].corner in ("convex", "concave") and by_v[3].corner in ("convex", "concave")
    assert set(res.geometry) == {1, 2}


def test_fillet_that_does_not_fit_next_to_an_arc_is_not_applied():
    from geometry.corner_breaks_od import build_od_corner_coords
    segs = _line_arc_profile(+1)
    res = build_od_corner_coords(_profile(segs, {1: F(2.0)}))
    rep = res.reports[0]
    assert rep.status == "skipped" and "V2" in rep.message
    assert 1 not in res.geometry
    centre, radius = _operator_circle(segs, 2)
    circles = _circles(_open_edges(_profile(segs, {1: F(2.0)})))
    assert any(abs(c[1] - radius) < 1e-9 and math.dist(c[0], centre) < 1e-9 for c in circles)


def test_quadrant_neighbour_stays_on_its_quarter_circle():
    segs = [ProfileMove(L, 1.0, 0.0), ProfileMove(L, 1.0, -0.5),
            ProfileMove(A, 1.5, -0.75, quadrant=True, quadrant_sign=1),
            ProfileMove(L, 1.5, -1.5)]
    plain = _circles(_open_edges(_profile(segs, {})))
    assert len(plain) == 1
    centre, radius = plain[0]
    broken = _circles(_open_edges(_profile(segs, {1: F(0.03), 2: F(0.03)})))
    quarter = [c for c in broken if abs(c[1] - radius) < 1e-9]
    assert quarter and math.dist(quarter[0][0], centre) < 1e-9


def test_arc_to_arc_fillet_is_tangent_and_keeps_both_arcs():
    segs = [ProfileMove(L, 1.0, 0.0), ProfileMove(A, 1.4, -0.5, radius=0.5),
            ProfileMove(A, 1.4, -1.0, radius=0.5), ProfileMove(L, 1.4, -1.5)]
    plain = _circles(_open_edges(_profile(segs, {})))
    broken = _circles(_open_edges(_profile(segs, {1: F(0.05)})))
    for centre, radius in plain:
        assert any(abs(c[1] - radius) < 1e-9 and math.dist(c[0], centre) < 1e-9 for c in broken)
    assert sum(1 for c in broken if abs(c[1] - 0.05) < 1e-9) == 1


def _v(p):
    from build123d import Vector
    return Vector(p[0], p[1], 0)


def _ordered(edges):
    """Edges chained end-to-start (each oriented along the chain)."""
    edges = list(edges)
    if not edges:
        return []
    chain = [edges.pop(0)]
    while edges:
        tail = chain[-1].end_point()
        nxt = next((e for e in edges if (e.start_point() - tail).length < 1e-7), None)
        if nxt is None:
            break
        edges.remove(nxt)
        chain.append(nxt)
    return chain
