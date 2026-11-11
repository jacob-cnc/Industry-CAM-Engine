"""Audit what LinuxCNC will ACTUALLY do with every arc in a program.

Runs the program through LinuxCNC's standalone interpreter (rs274, no
realtime, no machine) and measures each ARC_FEED's real sweep. Flags arcs
above a limit (default 190 deg): profile arcs in this engine are <= 180 deg
and a concave 180 deg arc offset for cleanup is ~186 deg, so anything larger
means a mirrored G02/G03 (the 2026-11-10 contour-roughing bug ran -359 deg
arcs).

usage: sweep_audit.py INI TOOL_TBL VAR_FILE prog.ngc [...]   (copies are fine)
exit 1 if any program fails to reach PROGRAM_END or has a flagged arc.
"""
import math, os, re, subprocess, sys, tempfile

LIMIT = float(os.environ.get("SWEEP_LIMIT_DEG", "190"))


def audit(ini, tbl, var, ngc):
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "canon.txt")
        p = subprocess.run(["rs274", "-i", ini, "-t", tbl, "-v", var, ngc, out],
                           stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120)
        canon = open(out).read() if os.path.exists(out) else ""
    ended = "PROGRAM_END" in canon
    pos, bad, n = None, [], 0
    for line in canon.splitlines():
        m = re.search(r"(STRAIGHT_FEED|STRAIGHT_TRAVERSE)\(([^)]*)\)", line)
        if m:
            v = [float(x) for x in m.group(2).split(",")]
            pos = (v[0], v[2])                       # (x, z)
            continue
        m = re.search(r"N(\S+)\s+ARC_FEED\(([^)]*)\)", line)
        if m and pos is not None:
            v = [float(x) for x in m.group(2).split(",")]
            ze, xe, zc, xc, rot = v[:5]              # G18: first axis Z, second X
            a0 = math.atan2(pos[0] - xc, pos[1] - zc)
            a1 = math.atan2(xe - xc, ze - zc)
            ccw = (a1 - a0) % (2 * math.pi)          # Z->X positive amount
            sweep = ccw if rot > 0 else ccw - 2 * math.pi
            if ccw == 0.0:
                sweep = 0.0
            n += 1
            if abs(math.degrees(sweep)) > LIMIT:
                bad.append((m.group(1), round(math.degrees(sweep), 1)))
            pos = (xe, ze)
    err = "" if ended else (p.stdout + p.stderr).strip().splitlines()[-1:]
    return ended, n, bad, err


if __name__ == "__main__":
    ini, tbl, var, *files = sys.argv[1:]
    failed = False
    for f in files:
        ended, n, bad, err = audit(ini, tbl, var, f)
        ok = ended and not bad
        failed |= not ok
        print(f"{'OK ' if ok else 'BAD'} {os.path.basename(f)}: end={ended} arcs={n}"
              + (f" OVER {LIMIT:.0f} deg: {bad[:6]}{' ...' if len(bad) > 6 else ''}" if bad else "")
              + (f" err={err}" if err else ""))
    sys.exit(1 if failed else 0)
