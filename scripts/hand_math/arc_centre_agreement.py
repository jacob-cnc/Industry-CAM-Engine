#!/usr/bin/env python3
"""Do the engine's arc-centre implementations agree with the kernel? (basic tool)

Question: "centre of the arc from P0 to P1 with signed radius R" (ProfileMove
convention, radius space: +R = clockwise in (r, z) = ARC_CW). The kernel's
answer is build123d's RadiusArc(P0, P1, R).arc_center - the same call the zone
builder uses to draw profile arcs (zone_builder: "pass target['radius']
directly", the signs align). Each hand implementation is compared with it on
random arcs, both signs, short and near-semicircle chords.

usage: arc_centre_agreement.py [--n 2000] [--seed 1]   (from the repo root)
"""
from __future__ import annotations

import argparse
import math
import random
import sys

sys.path.insert(0, ".")


def kernel_centre(p0, p1, r):
    from build123d import RadiusArc
    c = RadiusArc(p0, p1, r).arc_center
    return (c.X, c.Y)


def implementations():
    from validation.pre_planning_validator import _compute_arc_center
    from geometry.arc_helpers import _select_center
    from geometry.arc_entry import radius_arc_centre
    return {
        "validation.pre_planning_validator._compute_arc_center":
            lambda p0, p1, r: _compute_arc_center(p0[0], p0[1], p1[0], p1[1], abs(r), r > 0),
        "geometry.arc_helpers._select_center":
            lambda p0, p1, r: _select_center(p0[0], p0[1], p1[0], p1[1], abs(r), r > 0),
        "geometry.arc_entry.radius_arc_centre":
            lambda p0, p1, r: radius_arc_centre(p0, p1, r),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    rnd = random.Random(a.seed)
    impls = implementations()
    worst = {k: 0.0 for k in impls}
    bad = {k: 0 for k in impls}
    example = {}
    n = 0
    for _ in range(a.n):
        p0 = (rnd.uniform(0.05, 1.5), rnd.uniform(-2.0, 0.0))
        ang = rnd.uniform(0, 2 * math.pi)
        chord = rnd.uniform(0.01, 0.8)
        p1 = (p0[0] + chord * math.cos(ang), p0[1] + chord * math.sin(ang))
        # radius from just over half the chord (near semicircle) to long and flat
        R = chord / 2.0 * rnd.choice([1.0001, 1.01, 1.2, 2.0, 5.0, 20.0])
        for r in (R, -R):
            try:
                k = kernel_centre(p0, p1, r)
            except Exception:
                continue
            n += 1
            for name, f in impls.items():
                c = f(p0, p1, r)
                d = math.inf if c is None else math.hypot(c[0] - k[0], c[1] - k[1])
                worst[name] = max(worst[name], d)
                if d > 1e-9:
                    bad[name] += 1
                    example.setdefault(name, (p0, p1, r, c, k))
    print(f"{n} arcs compared with the kernel (RadiusArc.arc_center)")
    for name in impls:
        print(f"  {name:55s} disagree {bad[name]:5d}   worst {worst[name]:.3g} in")
        if name in example:
            p0, p1, r, c, k = example[name]
            print(f"      e.g. P0={p0} P1={p1} R={r:+.5f}: impl {c} vs kernel {k}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
