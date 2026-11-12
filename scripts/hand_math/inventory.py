#!/usr/bin/env python3
"""Inventory of hand-written geometry math, per function (basic, by design).

Scans the engine packages (not gui/, tests/, scripts/) with the AST and lists
every function that does trig / roots / distance-like arithmetic:

    trig      sin cos tan asin acos atan atan2 radians degrees (math or numpy)
    root      sqrt hypot, x ** 0.5
    sq        x ** 2 / x*x terms (distance and circle formulas)
    pi        uses of pi

It does NOT decide what is wrong - that is the point of the inquiry
(docs/handoffs/2026-11-12-hand-math-inquiry.md). It answers: where is the
math, how much of it, and which functions does the architecture checker
already flag.

usage: inventory.py [--min N] [--tsv]    (run from the repo root)
"""
from __future__ import annotations

import argparse
import ast
import os
import sys
from collections import Counter
from pathlib import Path

PACKAGES = ["geometry", "planners", "transitions", "validation", "outputs",
            "pipeline", "tools", "intervals", "models"]
TRIG = {"sin", "cos", "tan", "asin", "acos", "atan", "atan2", "radians", "degrees"}
ROOT = {"sqrt", "hypot"}


def _call_name(node):
    f = node.func
    if isinstance(f, ast.Attribute):
        return f.attr
    if isinstance(f, ast.Name):
        return f.id
    return None


class _Scan(ast.NodeVisitor):
    def __init__(self):
        self.stack, self.found = [], {}

    def _fn(self, node):
        self.stack.append(node.name)
        key = ".".join(self.stack)
        self.found.setdefault(key, [node.lineno, Counter()])
        self.generic_visit(node)
        self.stack.pop()

    visit_FunctionDef = visit_AsyncFunctionDef = _fn

    def visit_ClassDef(self, node):
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def _count(self, kind):
        if not self.stack:
            key = "<module>"
            self.found.setdefault(key, [0, Counter()])
        else:
            key = ".".join(self.stack)
        self.found[key][1][kind] += 1

    def visit_Call(self, node):
        name = _call_name(node)
        if name in TRIG:
            self._count("trig")
        elif name in ROOT:
            self._count("root")
        self.generic_visit(node)

    def visit_BinOp(self, node):
        if isinstance(node.op, ast.Pow) and isinstance(node.right, ast.Constant):
            if node.right.value == 2:
                self._count("sq")
            elif node.right.value == 0.5:
                self._count("root")
        self.generic_visit(node)

    def visit_Attribute(self, node):
        if node.attr == "pi":
            self._count("pi")
        self.generic_visit(node)


def scan(root: Path):
    rows = []
    for pkg in PACKAGES:
        for f in sorted((root / pkg).rglob("*.py")):
            tree = ast.parse(f.read_text())
            s = _Scan()
            s.visit(tree)
            for fn, (line, c) in s.found.items():
                if c:
                    rows.append((str(f.relative_to(root)), line, fn, c))
    return rows


def flagged(root: Path):
    sys.path.insert(0, str(root))
    from validation.architecture_check import check_hand_math
    out = set()
    for v in check_hand_math(root):
        import re
        m = re.search(r"Function '([^']+)'", v.message)
        if m:
            out.add((v.file_path, m.group(1)))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--min", type=int, default=1, help="only functions with at least N math operations")
    ap.add_argument("--tsv", action="store_true")
    a = ap.parse_args()
    root = Path.cwd()
    rows = scan(root)
    fl = flagged(root)
    total = Counter()
    by_pkg = Counter()
    shown = 0
    for path, line, fn, c in rows:
        n = sum(c.values())
        total.update(c)
        by_pkg[path.split("/")[0]] += n
        if n < a.min:
            continue
        shown += 1
        mark = "FLAGGED" if (path, fn.split(".")[-1]) in fl else ""
        ops = " ".join(f"{k}={v}" for k, v in sorted(c.items()))
        if a.tsv:
            print(f"{path}\t{line}\t{fn}\t{n}\t{ops}\t{mark}")
        else:
            print(f"{path}:{line:<5} {fn:55s} {n:3d}  {ops:32s} {mark}")
    print(f"\n{shown} functions shown; totals {dict(total)}; per package {dict(by_pkg)}; "
          f"checker flags {len(fl)} functions", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
