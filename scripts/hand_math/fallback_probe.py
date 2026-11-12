#!/usr/bin/env python3
"""Which fallback / hand-math paths do real programs actually take? (basic probe)

Wraps the engine's known fallback points, regenerates each program through
the GUI's own Generate (scripts/regression/regen.py), and counts per program
how often each path ran:

  finish.kernel_edges_none   FinishPlanner._extract_profile_edges returned None
                             (kernel edge walk failed or found no profile start)
  finish.segments_fallback   FinishPlanner._moves_from_segments ran (hand-math
                             arc centres with the X-bounds centre swap)
  finish.find_arc_center     FinishPlanner._find_arc_center calls
  finish.centre_swapped      ...of which picked the OTHER centre than the plain
                             cross-product rule (the validator's rule)
  cleanup.offset_profile_empty  CleanupPlanner._compute_offset_profile returned []
                             ("triggers fallback to zone boundary")
  offset.rounded_fallback    kernel_offset fell back from sharp to rounded joins

History (2026-11-12): the finish segments fallback (with _find_arc_center) and
the cleanup offset route were removed on the hand-math branch; the probe then
reports them as "no longer in the code".

usage: fallback_probe.py --tool-table TBL prog.json [...]   (from the repo root)
"""
from __future__ import annotations

import argparse
import importlib.util
import logging
import os
import sys
from collections import Counter

REPO = os.getcwd()
sys.path.insert(0, REPO)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
COUNTS: Counter = Counter()
REMOVED: list = []


def _install_spies():
    from planners.finish_planner import FinishPlanner
    from planners.cleanup_planner import CleanupPlanner
    from validation.pre_planning_validator import _compute_arc_center

    def wrap(cls, name, on_result):
        if not hasattr(cls, name):                 # path removed since the probe was written
            REMOVED.append(f"{cls.__name__}.{name}")
            return
        orig = getattr(cls, name)

        def spy(self, *a, **k):
            r = orig(self, *a, **k)
            on_result(r, a, k)
            return r
        setattr(cls, name, spy)

    wrap(FinishPlanner, "_extract_profile_edges",
         lambda r, a, k: COUNTS.update(["finish.kernel_edges_none"]) if not r else None)
    wrap(FinishPlanner, "_moves_from_segments", lambda r, a, k: COUNTS.update(["finish.segments_fallback"]))

    def on_centre(r, a, k):
        COUNTS.update(["finish.find_arc_center"])
        x1, z1, x2, z2, radius, is_cw = a[:6]
        plain = _compute_arc_center(x1, z1, x2, z2, radius, is_cw)
        if r and plain and (abs(r[0] - plain[0]) > 1e-9 or abs(r[1] - plain[1]) > 1e-9):
            COUNTS.update(["finish.centre_swapped"])
    wrap(FinishPlanner, "_find_arc_center", on_centre)
    wrap(CleanupPlanner, "_compute_offset_profile",
         lambda r, a, k: COUNTS.update(["cleanup.offset_profile_empty"]) if not r else None)

    class _H(logging.Handler):
        def emit(self, rec):
            if "used rounded joins" in rec.getMessage():
                COUNTS.update(["offset.rounded_fallback"])
    logging.getLogger("geometry.kernel_offset").addHandler(_H())


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
    app = QApplication.instance() or QApplication([])           # noqa: F841
    regen._record_dialogs()
    _install_spies()
    if REMOVED:
        print("paths no longer in the code (nothing to probe):", ", ".join(REMOVED))
    resolver = regen._tool_resolver(os.path.abspath(a.tool_table))
    import tempfile
    out = tempfile.mkdtemp(prefix="fallback_probe_")          # regen's .ngc/.result.json, not needed
    for p in a.programs:
        COUNTS.clear()
        r = regen.regenerate(os.path.abspath(p), resolver, out)
        status = "OK " if r["generated"] else "REF"
        print(f"{status} {os.path.basename(p)[:52]:52s} {dict(sorted(COUNTS.items())) or '-'}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
