"""OD corner-break invariants on line-line profiles (any valid output).

Complements the NX reference test with geometric properties that must hold
for every profile: the broken outline is continuous, untrimmed fillets are
tangent to both neighbours with the requested radius, untrimmed chamfers
have equal legs of the requested size, a cut-short fillet stays tangent on
the side with room and keeps its radius, and every trim is reported.
"""

import math
import random

import pytest

from geometry.corner_breaks_od import build_od_corner_coords
from models.profile import (
    ClosedProfile, CornerBreak, CornerBreakType, MachiningMode, ProfileMove,
    SegmentType,
)

ANG_TOL = 1e-7      # rad
LEN_TOL = 1e-9


def _profile(points_dia_z, breaks):
    return ClosedProfile([ProfileMove(SegmentType.LINE, x=d, z=z) for d, z in points_dia_z],
                         breaks, MachiningMode.OD, z_end=points_dia_z[-1][1])


def _walk(points_dia_z, result):
    """Outline as a list of (kind, start, end, radius) in (r, z), starting
    at the implied face start (r=0, z of first point)."""
    start = (0.0, points_dia_z[0][1])
    out, cur = [], start
    for c in result.coords:
        nxt = (c["x_radius"], c["z"])
        if math.dist(cur, nxt) > 1e-12:
            kind = "arc" if c["type"] == SegmentType.ARC and c["radius"] else "line"
            out.append((kind, cur, nxt, c["radius"]))
        cur = nxt
    return out


def _arc_center(s, e, signed_r):
    """Centre of a minor arc s->e per Build123d RadiusArc (+R: centre right
    of travel, -R: left)."""
    r = abs(signed_r)
    mx, mz = (s[0] + e[0]) / 2, (s[1] + e[1]) / 2
    dx, dz = e[0] - s[0], e[1] - s[1]
    half = math.hypot(dx, dz) / 2
    h = math.sqrt(max(0.0, r * r - half * half))
    ux, uz = dx / (2 * half), dz / (2 * half)
    left = (-uz, ux)
    k = -h if signed_r > 0 else h
    return (mx + left[0] * k, mz + left[1] * k)


def _tangent_dir(el, at_start):
    kind, s, e, r = el
    if kind == "line":
        d = (e[0] - s[0], e[1] - s[1])
    else:
        c = _arc_center(s, e, r)
        p = s if at_start else e
        rad = (p[0] - c[0], p[1] - c[1])
        d = (-rad[1], rad[0])
        chord = (e[0] - s[0], e[1] - s[1])
        if d[0] * chord[0] + d[1] * chord[1] < 0:
            d = (-d[0], -d[1])
    n = math.hypot(*d)
    return (d[0] / n, d[1] / n)


def _angle(u, v):
    return math.acos(max(-1.0, min(1.0, u[0] * v[0] + u[1] * v[1])))


def _random_step_profile(rng, n=8):
    """Random OD staircase/taper profile with segments long enough that a
    fraction of them conflict once breaks are applied."""
    pts, d, z = [], rng.uniform(0.5, 1.0), 0.0
    pts.append((d, z))
    for k in range(n):
        if k % 2 == 0:
            z -= rng.uniform(0.15, 0.6)                    # along Z (maybe a taper)
            d += rng.choice([0.0, 0.0, rng.uniform(-0.2, 0.2)])
        else:
            d = max(0.2, d + rng.choice([-1, 1]) * rng.uniform(0.1, 0.5))
        pts.append((round(d, 4), round(z, 4)))
    return pts


@pytest.mark.parametrize("seed", range(300))
def test_invariants_random_line_profiles(seed):
    rng = random.Random(seed)
    pts = _random_step_profile(rng)
    breaks = []
    for _ in range(len(pts) - 1):
        r = rng.random()
        if r < 0.35:
            breaks.append(CornerBreak(CornerBreakType.FILLET, radius=rng.uniform(0.01, 0.12)))
        elif r < 0.7:
            breaks.append(CornerBreak(CornerBreakType.CHAMFER, size=rng.uniform(0.01, 0.12)))
        else:
            breaks.append(None)
    result = build_od_corner_coords(_profile(pts, breaks))
    els = _walk(pts, result)

    # Continuous: each element starts where the previous ended (by construction
    # of the walk) and no arc is degenerate.
    for kind, s, e, r in els:
        if kind == "arc":
            assert abs(r) >= math.dist(s, e) / 2 - 1e-9
    reports = {rep.vertex: rep for rep in result.reports}

    # Every requested break is reported; trims carry a message.
    for i, cb in enumerate(breaks):
        if cb is not None:
            assert (i + 1) in reports
    for rep in result.reports:
        if rep.status == "trimmed":
            assert rep.message.startswith(f"V{rep.vertex}:")

    # Fillets, in vertex order, are the outline's arcs in walk order. Each is
    # checked against ITS corner's two original segment directions (the next
    # element may be a following break that starts right at the fillet end).
    fillet_reps = [rp for rp in result.reports
                   if rp.break_type == "fillet" and rp.status in ("ok", "trimmed")]
    arcs = [el for el in els if el[0] == "arc"]
    assert len(arcs) == len(fillet_reps)
    sharp_rz = [(0.0, pts[0][1])] + [(d / 2.0, z) for d, z in pts]

    def unit(a, b):
        d = (b[0] - a[0], b[1] - a[1])
        n = math.hypot(*d)
        return (d[0] / n, d[1] / n)

    for rep, arc in zip(fillet_reps, arcs):
        k = rep.vertex                          # corner at sharp_rz[k]
        u_in = unit(sharp_rz[k - 1], sharp_rz[k])
        u_out = unit(sharp_rz[k], sharp_rz[k + 1])
        a_in = _angle(u_in, _tangent_dir(arc, True))
        a_out = _angle(_tangent_dir(arc, False), u_out)
        if rep.status == "ok":
            assert abs(abs(arc[3]) - rep.requested) < LEN_TOL      # radius kept
            assert a_in < ANG_TOL and a_out < ANG_TOL               # both tangent
        else:
            # Cut short: tangent on at least one side; radius kept unless the
            # report says it was reduced (neither side had room).
            assert min(a_in, a_out) < ANG_TOL
            if "reduced" not in rep.message:
                assert abs(abs(arc[3]) - rep.requested) < LEN_TOL


@pytest.mark.parametrize("size", [0.01, 0.05, 0.1, 0.2])
@pytest.mark.parametrize("kind", ["chamfer", "fillet"])
def test_exact_breaks_at_90_degree_corners(size, kind):
    """Convex + concave 90° corners with room: exact equal legs / radius."""
    pts = [(1.0, 0.0), (1.0, -1.0), (2.0, -1.0), (2.0, -2.0)]   # V1 conv, V2 conc, V3 conv
    cb = (CornerBreak(CornerBreakType.CHAMFER, size=size) if kind == "chamfer"
          else CornerBreak(CornerBreakType.FILLET, radius=size))
    result = build_od_corner_coords(_profile(pts, [cb, cb, cb]))
    assert [r.status for r in result.reports] == ["ok", "ok", "ok"]
    assert [r.corner for r in result.reports] == ["convex", "concave", "convex"]
    els = _walk(pts, result)
    breaks = [e for e in els if (e[0] == "arc") == (kind == "fillet")
              and not (kind == "chamfer" and (e[1][0] == e[2][0] or e[1][1] == e[2][1]))]
    assert len(breaks) == 3
    for kind_, s, e, r in breaks:
        if kind == "chamfer":
            assert math.dist(s, e) == pytest.approx(size * math.sqrt(2), abs=LEN_TOL)
        else:
            assert abs(r) == pytest.approx(size, abs=LEN_TOL)


def test_conflict_on_shared_segment_is_trimmed_and_reported():
    """Two breaks wanting more than a short segment: earlier one wins."""
    pts = [(1.0, 0.0), (1.0, -1.0), (1.3, -1.0), (1.3, -2.0)]   # 0.15 radial step
    fil = CornerBreak(CornerBreakType.FILLET, radius=0.1)
    result = build_od_corner_coords(_profile(pts, [None, fil, fil]))
    v2, v3 = result.reports
    assert v2.status == "ok"
    assert v3.status == "trimmed" and "V2" in v3.message
    assert v3.kink_deg > 0


@pytest.mark.parametrize("size", [0.05, 0.1, 0.2])
def test_chamfers_run_through_full_pipeline(size):
    """Regression: legacy chamfers >= 0.05 at 90° corners crashed the cleanup
    offset. Must now plan and write G-code."""
    from models.stock import StockDef
    from models.tool import ToolDef, ToolOrientation, ToolDirection
    from models.params import RoughingParams, FinishingParams, RoughingStrategy
    from pipeline.pipeline import execute
    from outputs.gcode_writer import GCodeWriter
    pts = [(1.0, 0.0), (1.0, -1.0), (2.0, -1.0), (2.0, -2.0)]
    ch = CornerBreak(CornerBreakType.CHAMFER, size=size)
    profile = _profile(pts, [ch, ch, ch])
    stock = StockDef(diameter=2.2, x_start=2.2, z_start=0.05, z_end=-2.0)
    tool = ToolDef(tool_number=1, nose_radius=0.016, tip_angle=55.0, edge_length=0.5,
                   orientation=ToolOrientation.OD_FRONT_RIGHT, direction=ToolDirection.RIGHT)
    res = execute(profile, stock, tool,
                  RoughingParams(doc_dia=0.05, feed=0.008, strategy=RoughingStrategy.STAIRCASE,
                                 fin_allowance=0.01, spindle_rpm=1200.0),
                  FinishingParams(passes=1, doc_dia=0.002, feed=0.003))
    assert res.plan_result is not None, [v.message for v in res.validations]
    assert "G0" in GCodeWriter().write(res.plan_result, unit_mode="inch")


# ----------------------------------------------------------------------
# Smooth trim (roll onto the earlier neighbour)
# ----------------------------------------------------------------------

def _joint_kinks(els):
    return [math.degrees(_angle(_tangent_dir(a, False), _tangent_dir(b, True)))
            for a, b in zip(els, els[1:])]


def test_smooth_rolls_fillet_onto_fillet_tangentially():
    """Owner's snapshot: V2 R.0625 concave + V3 R.25 convex on a 0.25 step."""
    pts = [(0.5, 0.0), (0.5, -0.5), (1.0, -0.5), (1.0, -1.0)]
    for trim, expect_kink in (("nx", True), ("smooth", False)):
        breaks = [None, CornerBreak(CornerBreakType.FILLET, radius=0.0625),
                  CornerBreak(CornerBreakType.FILLET, radius=0.25, trim=trim)]
        res = build_od_corner_coords(_profile(pts, breaks))
        els = _walk(pts, res)
        arcs = [e for e in els if e[0] == "arc"]
        assert sorted(round(abs(a[3]), 9) for a in arcs) == [0.0625, 0.25]   # radii kept
        i = els.index(arcs[0])
        kink = _joint_kinks(els)[i]                       # V2 arc -> V3 arc
        assert (kink > 1.0) == expect_kink
        if trim == "smooth":
            assert kink < 1e-4
            assert [r.status for r in res.reports] == ["smoothed", "smoothed"]


def test_smooth_extends_chamfer_on_nx_part_v9():
    pts = [(6, 0), (6, -6), (12, -6), (12, -12), (6, -12), (6, -18), (15, -18),
           (15, -21), (12, -21), (12, -27), (18, -27), (18, -33)]
    C1 = CornerBreak(CornerBreakType.CHAMFER, size=1.0)
    R = lambda r, t="nx": CornerBreak(CornerBreakType.FILLET, radius=r, trim=t)
    res = build_od_corner_coords(_profile(pts, [C1, C1, R(1), R(1), R(1), R(1), C1, C1,
                                                R(1, "smooth"), R(3), None]))
    g8, g9 = res.geometry[7], res.geometry[8]
    # Hand result: R1 tangent to the chamfer line r = z + 13.75 (radius units:
    # chamfer from (r 7.5, z -20) at 45°) and to r = 6 -> centre (r 7, z -21.9142).
    assert g9.radius == pytest.approx(1.0)
    assert g9.center == pytest.approx((7.0, -20.5 - math.sqrt(2)), abs=1e-9)
    assert math.dist(g8.t_out, g9.t_in) < 1e-12               # chamfer meets fillet
    by_v = {r.vertex: r for r in res.reports}
    assert by_v[8].status == by_v[9].status == "smoothed"
    assert "lengthened" in by_v[8].message


@pytest.mark.parametrize("seed", range(150))
def test_smooth_random_profiles_have_no_kink_where_smoothed(seed):
    """Every smoothed fillet keeps its radius and joins its neighbour
    tangentially; where smoothing is impossible it falls back to NX style
    and says so."""
    rng = random.Random(1000 + seed)
    pts = _random_step_profile(rng)
    breaks = []
    for _ in range(len(pts) - 1):
        r = rng.random()
        if r < 0.45:
            breaks.append(CornerBreak(CornerBreakType.FILLET, radius=rng.uniform(0.02, 0.15),
                                      trim="smooth"))
        elif r < 0.75:
            breaks.append(CornerBreak(CornerBreakType.CHAMFER, size=rng.uniform(0.02, 0.12)))
        else:
            breaks.append(None)
    res = build_od_corner_coords(_profile(pts, breaks))
    els = _walk(pts, res)
    kinks = _joint_kinks(els)
    for rep in res.reports:
        g = res.geometry.get(rep.vertex - 1)
        if rep.status == "smoothed" and rep.break_type == "fillet" and g is not None:
            assert g.radius == pytest.approx(rep.requested, abs=1e-9)
            idx = next(k for k, e in enumerate(els)
                       if e[0] == "arc" and math.dist(e[1], g.t_in) < 1e-9)
            assert kinks[idx - 1] < 1e-3                   # tangent to the neighbour
        if rep.status == "trimmed" and rep.break_type == "fillet" and rep.kink_deg > 0:
            assert "Smoothing" in rep.message or "after the V" not in rep.message
