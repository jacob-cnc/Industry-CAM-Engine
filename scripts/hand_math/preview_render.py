#!/usr/bin/env python3
"""Render the Program-tab profile preview offscreen (basic look-and-compare tool).

Loads each saved program into a real ProgramTab (Qt offscreen, like
scripts/regression/regen.py), draws the editing preview (BUILDING state) and
writes, per program:
  <out>/<name>.png          what the operator sees (graph widget grab)
  <out>/<name>.preview.json the active block's drawn profile points (r, z)

Run it on two checkouts (--repo) and compare: the JSON gives the largest
distance between the two previews' profile lines; the PNGs are for the eye.

usage: /usr/bin/python3 scripts/hand_math/preview_render.py [--repo DIR] --out DIR prog.json [...]
       /usr/bin/python3 scripts/hand_math/preview_render.py --compare DIR_A DIR_B
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def render(repo, out, programs):
    sys.path.insert(0, repo)
    os.chdir(repo)
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])          # noqa: F841
    import importlib.util
    spec = importlib.util.spec_from_file_location("regen", os.path.join(repo, "scripts/regression/regen.py"))
    regen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(regen)
    regen._refuse_if_linuxcnc_up()
    regen._record_dialogs()
    from gui.program_tab import ProgramTab, ProgramState
    os.makedirs(out, exist_ok=True)
    for path in programs:
        name = os.path.splitext(os.path.basename(path))[0]
        tab = ProgramTab()
        tab.resize(1400, 900)
        with open(path) as f:
            tab._load_program_data(json.load(f))
        tab.set_state(ProgramState.BUILDING)
        tab.show()
        app.processEvents()
        tab._update_preview()
        app.processEvents()
        tab._graph_widget.grab().save(os.path.join(out, name + ".png"))
        pts = [list(zip(xs, zs)) for zs, xs in getattr(tab, "_profile_contour_segments", [])]
        with open(os.path.join(out, name + ".preview.json"), "w") as f:
            json.dump(pts, f)
        tab.close()
        print(f"rendered {name}: {sum(len(p) for p in pts)} points", flush=True)


def _seg_dist(p, a, b):
    ax, az = a
    bx, bz = b
    dx, dz = bx - ax, bz - az
    L2 = dx * dx + dz * dz
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - az) * dz) / L2))
    return math.hypot(p[0] - (ax + t * dx), p[1] - (az + t * dz))


def _poly_dist(p, poly):
    return min(_seg_dist(p, a, b) for a, b in zip(poly, poly[1:])) if len(poly) > 1 else math.dist(p, poly[0])


def compare(a_dir, b_dir):
    """Largest distance from either preview's points to the other's line."""
    for fn in sorted(os.listdir(a_dir)):
        if not fn.endswith(".preview.json") or not os.path.exists(os.path.join(b_dir, fn)):
            continue
        A = [p for poly in json.load(open(os.path.join(a_dir, fn))) for p in poly]
        B = [p for poly in json.load(open(os.path.join(b_dir, fn))) for p in poly]
        if not A or not B:
            print(f"{fn[:-13]:50s} empty preview ({len(A)} / {len(B)} points)")
            continue
        ab = max(_poly_dist(p, B) for p in A)
        ba = max(_poly_dist(p, A) for p in B)
        print(f"{fn[:-13]:50s} max distance {max(ab, ba):.6f} in (radius)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=os.getcwd())
    ap.add_argument("--out")
    ap.add_argument("--compare", nargs=2)
    ap.add_argument("programs", nargs="*")
    a = ap.parse_args()
    if a.compare:
        compare(*a.compare)
    else:
        render(os.path.abspath(a.repo), os.path.abspath(a.out), [os.path.abspath(p) for p in a.programs])
