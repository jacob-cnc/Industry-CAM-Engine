#!/usr/bin/env python3
"""Compare two regen.py runs program by program, like a machinist would.

For each program in BASE and NEW:

1. Both generated?
2. G-code text, normalised (N-numbers and the "Generation time" comment
   dropped): identical, comments only, or motion lines changed.
3. What the tool actually does to the metal (cut sections from LinuxCNC's own
   interpreter, see regen.py):
     - finished part as cut: area of the symmetric difference and the largest
       local deviation (Hausdorff distance), in inches, radius space;
     - GOUGE (finished part removed) and NOT REMOVED (material that should go
       but stays): did either grow?
     - each band (face / rough / cleanup / finish): area change - material
       moved between operations even when the finished part is the same.

Verdict per program:
    SAME            normalised text identical
    COMMENTS        only comments changed, every motion line identical
    MOTION/PART-OK  motion changed; finished part within TOL, no new gouge or
                    left material  -> read the motion diff (it is shown)
    PART-CHANGED    the finished part, gouge or left material changed -> stop
                    and look at it like a machinist before accepting
    BOTH-REFUSE     neither side generated, with the same dialog (e.g. a tool
                    that no longer suits the block) - consistent, not an error
    MISSING/FAILED  one side has no program, or they refuse differently

usage: compare.py BASE_DIR NEW_DIR [--tol 1e-5] [--show 40]
exit 1 if any program is PART-CHANGED or MISSING/FAILED.
"""
from __future__ import annotations

import argparse
import difflib
import glob
import json
import os
import re
import sys

_N = re.compile(r"^N\d+\s+")


def _norm(code: str):
    out = []
    for line in code.splitlines():
        if "Generation time" in line:
            continue
        out.append(_N.sub("", line).rstrip())
    return out


def _motion(line: str) -> str:
    """The executable part of a line (comments removed), '' if none."""
    line = re.sub(r"\([^)]*\)", "", line)
    return line.split(";")[0].strip()


def _load(d, name):
    ngc = os.path.join(d, name + ".ngc")
    res = os.path.join(d, name + ".result.json")
    if not (os.path.exists(ngc) and os.path.exists(res)):
        return None, None
    return open(ngc).read(), json.load(open(res))


def _geom(res, key):
    from shapely import wkt
    w = (res.get("wkt") or {}).get(key)
    return wkt.loads(w) if w else None


def _part_diff(b, n):
    """(symmetric-difference area, Hausdorff distance) of two geometries."""
    if b is None and n is None:
        return 0.0, 0.0
    if b is None or n is None:
        return float("inf"), float("inf")
    if b.is_empty and n.is_empty:
        return 0.0, 0.0
    if b.is_empty or n.is_empty:
        return float("inf"), float("inf")
    return b.symmetric_difference(n).area, b.hausdorff_distance(n)


def compare(base_dir, new_dir, tol, show):
    names = sorted({os.path.basename(p)[:-4] for d in (base_dir, new_dir)
                    for p in glob.glob(os.path.join(d, "*.ngc"))})
    worst = 0
    for name in names:
        bc, br = _load(base_dir, name)
        nc, nr = _load(new_dir, name)
        if (bc is not None and nc is not None and not br.get("generated") and not nr.get("generated")
                and br.get("dialogs") == nr.get("dialogs")):
            print(f"BOTH-REFUSE     {name}: same refusal on both sides: {(br.get('dialogs') or ['?'])[0][:160]}")
            continue
        if bc is None or nc is None or not br.get("generated") or not nr.get("generated"):
            print(f"MISSING/FAILED  {name}: base={bool(bc and br.get('generated'))} "
                  f"new={bool(nc and nr.get('generated'))}")
            worst = 2
            continue
        bl, nl = _norm(bc), _norm(nc)
        if bl == nl:
            print(f"SAME            {name}")
            continue
        bm = [m for m in map(_motion, bl) if m]
        nm = [m for m in map(_motion, nl) if m]
        # what the metal sees
        sym, haus = _part_diff(_geom(br, "finished"), _geom(nr, "finished"))
        gb, gn = (br["areas"].get("gouge") or 0.0), (nr["areas"].get("gouge") or 0.0)
        lb, ln = (br["areas"].get("not_removed") or 0.0), (nr["areas"].get("not_removed") or 0.0)
        bands = {k: (nr["areas"].get(k) or 0.0) - (br["areas"].get(k) or 0.0)
                 for k in ("face", "rough", "cleanup", "finish")}
        part_ok = haus <= tol and gn <= gb + 1e-9 and ln <= lb + 1e-9
        if bm == nm:
            verdict = "COMMENTS" if part_ok else "PART-CHANGED"
        else:
            verdict = "MOTION/PART-OK" if part_ok else "PART-CHANGED"
        if verdict == "PART-CHANGED":
            worst = max(worst, 2)
        print(f"{verdict:15s} {name}: motion lines {len(bm)} -> {len(nm)}; finished part "
              f"diff area {sym:.2e} in^2, max deviation {haus:.6f} in (radius); "
              f"gouge {gb:.2e} -> {gn:.2e}; left {lb:.2e} -> {ln:.2e}; "
              f"band change " + ", ".join(f"{k} {v:+.2e}" for k, v in bands.items() if abs(v) > 1e-9))
        if bm != nm and show:
            diff = [l for l in difflib.unified_diff(bm, nm, "base", "new", n=1, lineterm="")
                    if not l.startswith(("---", "+++"))]
            for l in diff[:show]:
                print("      " + l)
            if len(diff) > show:
                print(f"      ... {len(diff) - show} more diff lines")
    return worst


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("base")
    ap.add_argument("new")
    ap.add_argument("--tol", type=float, default=1e-5, help="finished-part deviation allowed (in, radius)")
    ap.add_argument("--show", type=int, default=40, help="motion diff lines to print per program")
    a = ap.parse_args()
    return 1 if compare(a.base, a.new, a.tol, a.show) else 0


if __name__ == "__main__":
    sys.exit(main())
