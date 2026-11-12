"""The architecture check may only get better (ratchet).

`python -m validation.architecture_check` fails on main: the layering and
hand-math rules were broken by earlier work and are being paid down. This test
pins the ERROR count per category to validation/architecture_baseline.json:

- more errors than the baseline -> a change broke the layering: fix the change;
- fewer errors than the baseline -> good: lower the number in the baseline in
  the same commit, so the improvement can't silently be lost again.

Warnings (dead code, dual implementations) are not pinned: the checker's
heuristics for those have false positives (e.g. `from __future__ import
annotations` counts as an unused import).
"""
import json
import os
from collections import Counter
from pathlib import Path

from validation.architecture_check import run_all_checks

REPO = Path(__file__).resolve().parents[2]
BASELINE = REPO / "validation" / "architecture_baseline.json"


def test_architecture_errors_only_go_down():
    baseline = json.loads(BASELINE.read_text())["errors"]
    found = Counter(v.category for v in run_all_checks(REPO) if v.severity == "error")
    worse = {k: (found.get(k, 0), n) for k, n in baseline.items() if found.get(k, 0) > n}
    new_kinds = {k: c for k, c in found.items() if k not in baseline}
    better = {k: (found.get(k, 0), n) for k, n in baseline.items() if found.get(k, 0) < n}
    assert not worse and not new_kinds, (
        f"architecture errors went UP (found, baseline): {worse} new categories: {new_kinds}. "
        f"Run `python -m validation.architecture_check` and fix the layering.")
    assert not better, (
        f"architecture errors went DOWN (found, baseline): {better}. "
        f"Lower the numbers in {BASELINE.relative_to(REPO)} to lock the improvement in.")
