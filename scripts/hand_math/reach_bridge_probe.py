#!/usr/bin/env python3
"""Tool-reach bridge lines: polyline construction vs exact kernel (basic probe).

geometry/tool_reach.make_reachable replaces a stretch the insert can't follow
by a straight line at the insert's limit angle, built on a polyline of the
contour (arcs every 0.5 deg): start = first polyline vertex past where the
contour gets steeper than the limit, end = where the ray meets the polyline.

The exact construction asks the kernel: on an arc, the point where its
tangent reaches the limit direction (build123d Edge.find_tangent); at a line,
its start; end = the ray's first intersection with the contour edges.

For each program (regenerated through the GUI's Generate) this captures every
make_reachable call (OD, right-hand, 'fall' regions) and prints both lines.

usage: /usr/bin/python3 scripts/hand_math/reach_bridge_probe.py --tool-table TBL prog.json [...]
"""
from __future__ import annotations

import argparse
import importlib.util
import math
import os
import sys
import tempfile

REPO = os.getcwd()
sys.path.insert(0, REPO)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def kernel_fall_bridges(profile, tool, tol_deg=1.0):
    """Exact bridges for an OD right-hand tool's falling stretches:
    [(P, Q)] in (r, z)."""
    from build123d import Line, Vector
    from geometry.arc_entry import normalize_profile
    from geometry.zone_builder import edge_from_coords, profile_to_radius_coords
    coords = profile_to_radius_coords(normalize_profile(profile))
    edges = [e for e in (edge_from_coords(a, b) for a, b in zip(coords, coords[1:])) if e is not None]
    L = 180.0 - tool.back_angle
    th = math.radians(L)
    u = (-math.sin(th), -math.cos(th))

    def phi(e, t):
        d = e.tangent_at(t)
        return math.degrees(math.atan2(d.X, -d.Y))

    out, k = [], 0
    while k < len(edges):
        e = edges[k]
        start_steep = phi(e, 0.0) < -(L + tol_deg)
        P = None
        if start_steep:
            P = e.position_at(0.0)
        elif e.geom_type.name == "CIRCLE" and phi(e, 1.0) < -(L + tol_deg):
            theta = math.degrees(math.atan2(u[1], u[0]))
            ts = [t for t in e.find_tangent(theta) if 0.0 <= t <= 1.0]
            ts = [t for t in ts if abs(phi(e, t) + L) < 1e-6] or ts
            P = e.position_at(min(ts)) if ts else None
        if P is None:
            k += 1
            continue
        ray = Line((P.X, P.Y), (P.X + 10 * u[0], P.Y + 10 * u[1]))
        best = None
        for j in range(k, len(edges)):
            for q in edges[j].find_intersection_points(ray):
                d = math.hypot(q.X - P.X, q.Y - P.Y)
                if d > 1e-7 and (best is None or d < best[0]):
                    best = (d, j, (q.X, q.Y))
        if best is None:
            out.append(((P.X, P.Y), None))
            break
        out.append(((P.X, P.Y), best[2]))
        k = best[1] + 1
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tool-table", required=True)
    ap.add_argument("programs", nargs="+")
    a = ap.parse_args()
    spec = importlib.util.spec_from_file_location("regen", os.path.join(REPO, "scripts/regression/regen.py"))
    regen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(regen)
    regen._refuse_if_linuxcnc_up()
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])          # noqa: F841
    regen._record_dialogs()
    import geometry.tool_reach as tr
    calls = []
    orig = tr.make_reachable

    def spy(profile, tool, *args, **kw):
        res = orig(profile, tool, *args, **kw)
        if res[1]:
            calls.append((profile, tool, res[1]))
        return res
    tr.make_reachable = spy
    resolver = regen._tool_resolver(os.path.abspath(a.tool_table))
    out = tempfile.mkdtemp(prefix="reach_")
    for p in a.programs:
        calls.clear()
        regen.regenerate(os.path.abspath(p), resolver, out)
        print(f"== {os.path.basename(p)}")
        seen = set()
        for profile, tool, regions in calls:
            key = id(profile)
            if key in seen:
                continue
            seen.add(key)
            exact = kernel_fall_bridges(profile, tool)
            for reg in regions:
                P = (reg.line_from[0] / 2.0, reg.line_from[1])
                Q = (reg.line_to[0] / 2.0, reg.line_to[1])
                m = min(exact, key=lambda b: math.dist(b[0], P)) if exact else None
                if m is None:
                    print(f"  {reg.kind}: hand P{P} Q{Q}  kernel: none")
                    continue
                dq = math.dist(m[1], Q) if m[1] is not None else float('nan')
                print(f"  {reg.kind}: start off by {math.dist(m[0], P):.6f}, end off by {dq:.6f} in (radius)"
                      f"   hand P=({2*P[0]:.5f}, {P[1]:.5f}) kernel P=({2*m[0][0]:.5f}, {m[0][1]:.5f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
