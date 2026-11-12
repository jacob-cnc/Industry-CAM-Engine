#!/usr/bin/env python3
"""List every rapid that touches remaining material, per program (basic tool).

Regenerates each program through the GUI's Generate (scripts/regression/regen.py)
and runs validation/rapid_collision.check_rapids on each profile block's G-code,
printing the colliding rapids: section, from -> to (X dia, Z), material area hit
and its bounding box.

usage: /usr/bin/python3 scripts/hand_math/rapid_report.py --tool-table TBL prog.json [...]
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import tempfile

REPO = os.getcwd()
sys.path.insert(0, REPO)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tool-table", required=True)
    ap.add_argument("--all", action="store_true", help="list every rapid, not only collisions")
    ap.add_argument("programs", nargs="+")
    a = ap.parse_args()
    spec = importlib.util.spec_from_file_location("regen", os.path.join(REPO, "scripts/regression/regen.py"))
    regen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(regen)
    regen._refuse_if_linuxcnc_up()
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])          # noqa: F841
    regen._record_dialogs()
    from validation.rapid_collision import check_rapids
    captured = []
    import gui.program_tab as pt
    resolver = regen._tool_resolver(os.path.abspath(a.tool_table))
    out = tempfile.mkdtemp(prefix="rapids_")
    orig_sections = regen._sections

    def grab(inputs):
        captured.extend(inputs)
        return orig_sections(inputs)
    regen._sections = grab
    for p in a.programs:
        captured.clear()
        regen.regenerate(os.path.abspath(p), resolver, out)
        print(f"== {os.path.basename(p)}")
        for gcode, plan, _o in captured:
            for r in check_rapids(gcode, plan):
                if r.collides or a.all:
                    tag = "HIT " if r.collides else "    "
                    extra = (f" depth {r.hit_depth:.4f} area {r.hit_area:.2e} in X{r.hit_bounds[0]:.4f}-{r.hit_bounds[1]:.4f} "
                             f"Z{r.hit_bounds[2]:.4f}-{r.hit_bounds[3]:.4f}" if r.collides
                             else f" clear {r.clearance:.4f}")
                    print(f"  {tag}{r.section:8s} X{r.start[0]:.4f} Z{r.start[1]:.4f} -> "
                          f"X{r.end[0]:.4f} Z{r.end[1]:.4f}{extra}")
    del pt
    return 0


if __name__ == "__main__":
    sys.exit(main())
