"""OD corner breaks validated against an NX reference part.

Fixtures (owner-made in NX, mm, turning axis = model X, front face at X0):
  tests/fixtures/nx_corner_break/sharp.stp   - the sharp profile
  tests/fixtures/nx_corner_break/broken.stp  - same part after NX chamfer /
                                               fillet tools at V1..V10

The sharp profile is read from sharp.stp, entered into the engine exactly as
an operator would (segment end points, Ø and Z), the ten breaks are applied,
and the engine's finished-part outline is compared element by element with
the profile NX produced (broken.stp): same element types, end points, arc
centres and radii. V9 is the deliberate conflict case: the V8 chamfer leaves
only 0.5 of the Z-21 face for an R1 fillet; NX cuts the fillet short and the
engine must reproduce that (owner's trim rule).
"""

import math
import os

import pytest

from models.profile import (
    ClosedProfile, CornerBreak, CornerBreakType, MachiningMode, ProfileMove,
    SegmentType,
)

FIX = os.path.join(os.path.dirname(__file__), "..", "fixtures", "nx_corner_break")
TOL = 1e-3            # mm; NX STEP values are exact to ~1e-6

C1 = CornerBreak(CornerBreakType.CHAMFER, size=1.0)
R1 = CornerBreak(CornerBreakType.FILLET, radius=1.0)
R3 = CornerBreak(CornerBreakType.FILLET, radius=3.0)
# V1..V11 at profile points 0..10 (the owner's model; V11 stays sharp).
NX_BREAKS = [C1, C1, R1, R1, R1, R1, C1, C1, R1, R3, None]


# ----------------------------------------------------------------------
# Reading NX faces as (r, z) profile elements
# ----------------------------------------------------------------------

def _circle_edges(face):
    """Boundary circles of a face of revolution about model X:
    [(z, r)] with z = model X, r = circle radius."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GeomAbs import GeomAbs_Circle
    out = []
    for e in face.edges():
        ad = BRepAdaptor_Curve(e.wrapped)
        if ad.GetType() == GeomAbs_Circle:
            circ = ad.Circle()
            out.append((round(circ.Location().X(), 6), round(circ.Radius(), 6)))
    return sorted(set(out))


def nx_elements(path):
    """Profile elements of a turned NX part: ('line'|'arc', end points, extra).

    Each face of revolution contributes the element that generates it: its
    two boundary circles are the element's end points (a disc face at the
    axis gets r = 0 for its centre end)."""
    from build123d import import_step
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Torus
    part = import_step(path)
    elements = []
    for fc in part.faces():
        circles = _circle_edges(fc)
        ends = circles if len(circles) == 2 else sorted([circles[0], (circles[0][0], 0.0)])
        ad = BRepAdaptor_Surface(fc.wrapped)
        if ad.GetType() == GeomAbs_Torus:
            t = ad.Torus()
            extra = (t.Location().X(), t.MajorRadius(), t.MinorRadius())
            elements.append(("arc", ends, extra))
        else:
            elements.append(("line", ends, None))
    return elements


def sharp_points(path):
    """Ordered sharp profile points (Ø, Z) from the sharp part, front face
    outward: every corner circle, ordered along the outline."""
    els = nx_elements(path)
    # Build the outline graph from element end points and walk it from the
    # front-face rim (largest z, r > 0), skipping the axis.
    adj = {}
    for _, (a, b), _ in els:
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    front_z = max(z for z, _ in adj)
    start = max((p for p in adj if p[0] == front_z and p[1] > 0), key=lambda p: p[1])
    prev, cur = (front_z, 0.0), start
    order = [cur]
    while True:
        nxt = [p for p in adj[cur] if p != prev]
        if not nxt or nxt[0][1] == 0.0:
            break
        prev, cur = cur, nxt[0]
        order.append(cur)
    return [(2.0 * r, z) for z, r in order]


# ----------------------------------------------------------------------
# Engine outline as the same kind of elements
# ----------------------------------------------------------------------

def engine_elements(profile):
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GeomAbs import GeomAbs_Circle
    from geometry.zone_builder import (
        _build_face_from_coords, _compute_closure_coords, _profile_to_radius_coords,
    )
    from models.stock import StockDef
    stock = StockDef(diameter=20.0, x_start=20.0, z_start=0.5, z_end=-33.0)
    coords = _profile_to_radius_coords(profile)
    face = _build_face_from_coords(coords + _compute_closure_coords(profile, stock, coords),
                                   profile)
    out = []
    for e in face.edges():
        s, t = e.start_point(), e.end_point()
        ends = sorted([(round(s.Y, 6), round(abs(s.X), 6)), (round(t.Y, 6), round(abs(t.X), 6))])
        if abs(s.X) < 1e-9 and abs(t.X) < 1e-9:
            continue                                   # centreline, not a face
        ad = BRepAdaptor_Curve(e.wrapped)
        if ad.GetType() == GeomAbs_Circle:
            c = ad.Circle()
            out.append(("arc", ends, (c.Location().Y(), c.Location().X(), c.Radius())))
        else:
            out.append(("line", ends, None))
    return out


def _close(a, b):
    return all(abs(x - y) <= TOL for x, y in zip(a, b))


def _match(el, others):
    kind, ends, extra = el
    for o in others:
        if o[0] != kind:
            continue
        if not (_close(ends[0], o[1][0]) and _close(ends[1], o[1][1])):
            continue
        if kind == "arc" and not _close(extra, o[2]):
            continue
        return o
    return None


def _profile_from_points(points, breaks):
    segs = [ProfileMove(SegmentType.LINE, x=d, z=z) for d, z in points]
    return ClosedProfile(segments=segs, corner_breaks=breaks, mode=MachiningMode.OD,
                         z_end=points[-1][1])


# ----------------------------------------------------------------------
# Tests
# ----------------------------------------------------------------------

@pytest.fixture(scope="module")
def sharp():
    return sharp_points(os.path.join(FIX, "sharp.stp"))


def test_sharp_profile_read_as_entered(sharp):
    """The sharp part is the profile the owner described (Ø, Z)."""
    assert sharp == [(6, 0), (6, -6), (12, -6), (12, -12), (6, -12), (6, -18),
                     (15, -18), (15, -21), (12, -21), (12, -27), (18, -27), (18, -33)]
    assert len(NX_BREAKS) == len(sharp) - 1


def test_engine_without_breaks_matches_sharp_part(sharp):
    profile = _profile_from_points(sharp, [None] * (len(sharp) - 1))
    nx = nx_elements(os.path.join(FIX, "sharp.stp"))
    eng = engine_elements(profile)
    assert len(eng) == len(nx)
    for el in nx:
        assert _match(el, eng) is not None, f"NX element not built by engine: {el}"


def test_engine_breaks_match_nx_element_by_element(sharp):
    profile = _profile_from_points(sharp, NX_BREAKS)
    nx = nx_elements(os.path.join(FIX, "broken.stp"))
    eng = engine_elements(profile)
    missing = [el for el in nx if _match(el, eng) is None]
    extra = [el for el in eng if _match(el, nx) is None]
    assert not missing, f"NX elements the engine did not reproduce: {missing}"
    assert not extra, f"engine elements NX does not have: {extra}"
    assert len(eng) == len(nx)


def test_reports_flag_only_v9_trim(sharp):
    from geometry.corner_breaks_od import build_od_corner_coords
    profile = _profile_from_points(sharp, NX_BREAKS)
    result = build_od_corner_coords(profile)
    by_v = {r.vertex: r for r in result.reports}
    assert sorted(by_v) == list(range(1, 11))          # V11 has no break
    assert [r.vertex for r in result.trims] == [9]
    v9 = by_v[9]
    assert "V8" in v9.message and "0.5" in v9.message
    assert v9.kink_deg == pytest.approx(15.0, abs=0.05)   # 60° arc vs 45° chamfer
    assert all(r.status == "ok" for v, r in by_v.items() if v != 9)
    # OD convex / concave classification of the owner's corners.
    convex = {1, 3, 4, 7, 8}
    for v, r in by_v.items():
        assert r.corner == ("convex" if v in convex else "concave"), v
