#!/usr/bin/env python3
"""Corner breaks three ways: NX, the engine's solver, the kernel (basic tool).

Question: can OCCT's own 2D fillet / chamfer (build123d Face.fillet_2d /
chamfer_2d) replace the hand vector algebra in geometry/corner_breaks_od.py?

For the owner's NX reference part (tests/fixtures/nx_corner_break, line-line
corners V1..V10, V9 the deliberate "doesn't fit" case) this:
  1. builds the SHARP finished-part face with the engine (no breaks),
  2. applies each break with the kernel, vertex by vertex in V order,
  3. compares the result element by element with NX's broken part and with
     the engine's own corner-break outline.
Then (part 2) arc-adjacent vertices, where the engine still uses its legacy
chord construction: measures the direction change (kink) at every joint of
the engine's outline and of the kernel's, and how far apart they are.

Read-only. usage: /usr/bin/python3 scripts/hand_math/corner_break_probe.py  (repo root)
"""
from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.getcwd())

from tests.unit.test_corner_breaks_od_nx import (  # noqa: E402  (probe reuses the NX test's readers)
    FIX, NX_BREAKS, _match, _profile_from_points, engine_elements, nx_elements, sharp_points,
)


def _face(profile):
    from geometry.zone_builder import _build_face_from_coords, _compute_closure_coords, profile_to_radius_coords
    from models.stock import StockDef
    stock = StockDef(diameter=20.0, x_start=20.0, z_start=0.5, z_end=-33.0)
    coords = profile_to_radius_coords(profile)
    sk = _build_face_from_coords(coords + _compute_closure_coords(profile, stock, coords), profile)
    return sk.faces()[0]


def _elements_of(face):
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GeomAbs import GeomAbs_Circle
    out = []
    for e in face.edges():
        s, t = e.start_point(), e.end_point()
        if abs(s.X) < 1e-9 and abs(t.X) < 1e-9:
            continue
        ends = sorted([(round(s.Y, 6), round(abs(s.X), 6)), (round(t.Y, 6), round(abs(t.X), 6))])
        ad = BRepAdaptor_Curve(e.wrapped)
        if ad.GetType() == GeomAbs_Circle:
            c = ad.Circle()
            out.append(("arc", ends, (c.Location().Y(), c.Location().X(), c.Radius())))
        else:
            out.append(("line", ends, None))
    return out


def kernel_broken_face(points_dia_z, breaks, log):
    """Sharp face, then each break with the kernel in V order."""
    from build123d import Vector
    from models.profile import CornerBreakType
    face = _face(_profile_from_points(points_dia_z, [None] * len(breaks)))
    for i, cb in enumerate(breaks):
        if cb is None or cb.break_type == CornerBreakType.NONE:
            continue
        target = Vector(points_dia_z[i][0] / 2.0, points_dia_z[i][1], 0)
        v = min(face.vertices(), key=lambda q: (Vector(q) - target).length)
        miss = (Vector(v) - target).length
        if miss > 1e-6:
            log.append(f"V{i+1}: sharp corner no longer exists (nearest vertex {miss:.4f} away) "
                       f"- consumed by an earlier break")
            continue
        try:
            if cb.break_type == CornerBreakType.FILLET:
                face = face.fillet_2d(cb.radius, [v])
            else:
                face = face.chamfer_2d(cb.size, cb.size, [v])
            log.append(f"V{i+1}: kernel {cb.break_type.name.lower()} OK")
        except Exception as exc:
            log.append(f"V{i+1}: kernel {cb.break_type.name.lower()} FAILED: {type(exc).__name__}: {exc}")
    return face


def part1():
    print("== Part 1: owner's NX part, line-line corners ==")
    sharp = sharp_points(os.path.join(FIX, "sharp.stp"))
    nx = nx_elements(os.path.join(FIX, "broken.stp"))
    eng = engine_elements(_profile_from_points(sharp, NX_BREAKS))
    log = []
    ker = _elements_of(kernel_broken_face(sharp, NX_BREAKS, log))
    for line in log:
        print("  ", line)
    for name, els in (("engine", eng), ("kernel", ker)):
        missing = [el for el in nx if _match(el, els) is None]
        extra = [el for el in els if _match(el, nx) is None]
        print(f"  {name}: {len(els)} elements vs NX {len(nx)}; NX elements not reproduced: "
              f"{len(missing)}; elements NX does not have: {len(extra)}")
        for el in missing:
            print(f"      NX has      {el}")
        for el in extra:
            print(f"      {name} has  {el}")


def _vertex_kinks(face):
    """{(r, z): direction change in degrees} at every vertex of the face's
    outline (0 = tangent joint)."""
    out = {}
    for v in face.vertices():
        p = (v.X, v.Y)
        dirs = []
        for e in face.edges():
            if (e.start_point() - v.center()).length < 1e-7:
                dirs.append(e.tangent_at(0))
            elif (e.end_point() - v.center()).length < 1e-7:
                dirs.append(e.tangent_at(1) * -1)
        if len(dirs) == 2:
            cosang = max(-1.0, min(1.0, dirs[0].dot(dirs[1])))
            out[p] = 180.0 - math.degrees(math.acos(cosang))
    return out


def _near(kinks, corner, reach):
    return {p: k for p, k in kinks.items() if math.hypot(p[0] - corner[0], p[1] - corner[1]) <= reach}


def _arc_cases():
    from models.profile import ClosedProfile, CornerBreak, CornerBreakType, MachiningMode, ProfileMove, SegmentType
    L, A = SegmentType.LINE, SegmentType.ARC
    F = lambda r: CornerBreak(CornerBreakType.FILLET, radius=r)
    C = lambda s: CornerBreak(CornerBreakType.CHAMFER, size=s)
    cases = []
    for sign in (+1, -1):
        bulge = "R+" if sign > 0 else "R-"
        segs = [ProfileMove(L, 1.0, 0.0), ProfileMove(L, 1.0, -0.5),
                ProfileMove(A, 1.5, -1.0, radius=sign * 0.4), ProfileMove(L, 1.5, -1.5),
                ProfileMove(L, 2.0, -1.5), ProfileMove(L, 2.0, -2.0)]
        for vi, where in ((1, "line->arc"), (2, "arc->line")):
            for br, bname in ((F(0.05), "fillet .05"), (C(0.05), "chamfer .05")):
                breaks = [None] * (len(segs) - 1)
                breaks[vi] = br
                cases.append((f"{where} ({bulge} .4) {bname}", segs, vi, breaks))
    # arc -> arc (S-curve) with a corner between the two arcs
    segs = [ProfileMove(L, 1.0, 0.0), ProfileMove(A, 1.4, -0.5, radius=0.5),
            ProfileMove(A, 1.4, -1.0, radius=0.5), ProfileMove(L, 1.4, -1.5)]
    for br, bname in ((F(0.05), "fillet .05"), (C(0.05), "chamfer .05")):
        breaks = [None] * 3
        breaks[1] = br
        cases.append((f"arc->arc {bname}", segs, 1, breaks))
    return cases


def part2():
    from models.profile import ClosedProfile, MachiningMode
    print("\n== Part 2: corners next to arcs (engine: legacy chord method) ==")
    print("   kink = direction change left at a joint of the break region (0 = tangent)")
    for name, segs, vi, breaks in _arc_cases():
        prof = ClosedProfile(segments=segs, corner_breaks=breaks, mode=MachiningMode.OD, z_end=segs[-1].z)
        corner = (segs[vi].x / 2.0, segs[vi].z)
        reach = 0.2
        try:
            eng = _near(_vertex_kinks(_face(prof)), corner, reach)
        except Exception as exc:
            eng = f"FAILED {type(exc).__name__}: {exc}"
        log = []
        try:
            pts = [(s_.x, s_.z) for s_ in segs]
            kf = _kernel_on_profile(segs, breaks, log)
            ker = _near(_vertex_kinks(kf), corner, reach)
        except Exception as exc:
            ker = f"FAILED {type(exc).__name__}: {exc}"
        fmt = lambda d: d if isinstance(d, str) else ", ".join(
            f"({p[0]*2:.4f}, {p[1]:.4f}) {k:.2f}deg" for p, k in sorted(d.items(), key=lambda t: -t[0][1]))
        print(f"  {name}")
        print(f"     engine: {fmt(eng)}")
        print(f"     kernel: {fmt(ker)}  {' '.join(log)}")


def _kernel_on_profile(segs, breaks, log):
    from build123d import Vector
    from models.profile import ClosedProfile, CornerBreakType, MachiningMode
    face = _face(ClosedProfile(segments=segs, corner_breaks=[None] * len(breaks),
                               mode=MachiningMode.OD, z_end=segs[-1].z))
    for i, cb in enumerate(breaks):
        if cb is None:
            continue
        target = Vector(segs[i].x / 2.0, segs[i].z, 0)
        v = min(face.vertices(), key=lambda q: (Vector(q) - target).length)
        try:
            face = (face.fillet_2d(cb.radius, [v]) if cb.break_type == CornerBreakType.FILLET
                    else face.chamfer_2d(cb.size, cb.size, [v]))
        except Exception as exc:
            log.append(f"V{i+1} FAILED: {type(exc).__name__}: {exc}")
    return face


if __name__ == "__main__":
    part1()
    part2()
