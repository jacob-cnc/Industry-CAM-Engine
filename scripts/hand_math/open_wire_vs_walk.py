#!/usr/bin/env python3
"""Finish-contour edges two ways, compared (basic understanding tool).

Today FinishPlanner._extract_profile_edges WALKS the closed finished-part
outline (profile + the engine's closure to the centreline / stock OD) and
searches it for the profile's first and last points. When the profile itself
runs along the closure line (a back shoulder at the operation end), the outline
folds onto itself, the walk fails, and the finish pass silently falls back to
hand-math arcs (2026-11-12, "Hemisphere Test").

The alternative asks the kernel for the profile's OPEN wire directly (the same
corner-break-aware coords, no closure, no search) and converts it with the same
ZoneQueryAPI._edge_data_from_wire.

For every program this regenerates through the GUI's Generate, captures the
(zone_query, profile) the finish planner receives, and prints whether the two
ways agree edge by edge (type, start, end, centre, radius, direction).

usage: open_wire_vs_walk.py --tool-table TBL prog.json [...]   (from the repo root)
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import sys

REPO = os.getcwd()
sys.path.insert(0, REPO)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
TOL = 1e-7


def open_wire_edges(profile):
    """Prototype: EdgeData of the profile's open wire, in profile (cutting) order."""
    from geometry.zone_builder import _build_face_from_coords, profile_to_radius_coords
    from geometry.zone_query import ZoneQueryAPI
    from build123d import Wire
    coords = profile_to_radius_coords(profile)
    curve = _build_face_from_coords(coords, profile, closed=False)
    wire = Wire(curve.edges())
    return ZoneQueryAPI._edge_data_from_wire(wire.wrapped)


def _key(e):
    c = tuple(e.center) if getattr(e, "center", None) is not None else None
    return (e.edge_type, tuple(e.start), tuple(e.end), c, round(getattr(e, "radius", 0.0) or 0.0, 9),
            getattr(e, "direction", None), round(getattr(e, "sweep", 0.0) or 0.0, 9))


def _same(a, b):
    # direction only means something for an ARC; a LINE's is a default the walk's
    # reversed() flips ("cw" <-> "ccw") without any geometric meaning.
    if a[0] != b[0] or (a[0] == "ARC" and a[5] != b[5]):
        return False
    for i in (1, 2):
        if max(abs(x - y) for x, y in zip(a[i], b[i])) > TOL:
            return False
    if (a[3] is None) != (b[3] is None):
        return False
    if a[3] is not None and max(abs(x - y) for x, y in zip(a[3], b[3])) > TOL:
        return False
    return abs(a[4] - b[4]) <= TOL and abs(a[6] - b[6]) <= 1e-6


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tool-table", required=True)
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--query", action="store_true",
                    help="compare against ZoneQueryAPI.profile_offset_edges(profile, 0) instead of the prototype")
    ap.add_argument("programs", nargs="+")
    a = ap.parse_args()
    spec = importlib.util.spec_from_file_location("regen", os.path.join(REPO, "scripts/regression/regen.py"))
    regen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(regen)
    regen._refuse_if_linuxcnc_up()
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])           # noqa: F841
    regen._record_dialogs()
    from planners.finish_planner import FinishPlanner
    captured = []
    orig = FinishPlanner._extract_profile_edges

    def spy(self, zq, profile):
        r = orig(self, zq, profile)
        captured.append((zq, profile, r))
        return r
    FinishPlanner._extract_profile_edges = spy
    import tempfile
    out = tempfile.mkdtemp(prefix="open_wire_")
    resolver = regen._tool_resolver(os.path.abspath(a.tool_table))
    for p in a.programs:
        captured.clear()
        regen.regenerate(os.path.abspath(p), resolver, out)
        name = os.path.basename(p)[:50]
        if not captured:
            print(f"--         {name}: finish planner not reached")
            continue
        for zq, profile, walk in captured:
            try:
                # the kernel's existing open-contour query (used today for intermediate finish passes)
                opn = zq.profile_offset_edges(profile, 0.0) if a.query else open_wire_edges(profile)
            except Exception as exc:
                print(f"OPEN-FAIL  {name}: {type(exc).__name__}: {exc}")
                continue
            if walk is None:
                print(f"WALK-NONE  {name}: walk failed (hand-math fallback today); open wire gives "
                      f"{len(opn)} edges")
                if a.verbose:
                    for e in opn:
                        print("             ", _key(e))
                continue
            wk = [_key(e) for e in walk]
            ok_ = [_key(e) for e in opn]
            agree = len(wk) == len(ok_) and all(_same(x, y) for x, y in zip(wk, ok_))
            print(f"{'SAME' if agree else 'DIFFERENT':10s} {name}: walk {len(wk)} edges, open wire {len(ok_)}")
            if not agree or a.verbose:
                for i in range(max(len(wk), len(ok_))):
                    x = wk[i] if i < len(wk) else None
                    y = ok_[i] if i < len(ok_) else None
                    flag = "  " if (x and y and _same(x, y)) else "!!"
                    print(f"    {flag} walk {x}\n       open {y}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
