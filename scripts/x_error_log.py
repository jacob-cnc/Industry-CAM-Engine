"""Read-only X position-error logger (no realtime components, halcmd reads only).

Samples X commanded vs scale position and the PID state at about 20 Hz and
writes a CSV, then prints a summary in DIAMETER units (the part tolerance):
standstill error, error while moving, and the encoder-count histogram.

usage:  python3 scripts/x_error_log.py SECONDS out.csv
Run only with the owner present; it does not command the machine.
"""
import csv, subprocess, sys, time
from collections import Counter

PINS = ["joint.0.motor-pos-cmd", "joint.0.motor-pos-fb", "pid.x.error",
        "pid.x.output", "joint.0.vel-cmd"]
COUNT_R = 1.0 / 5080.0        # one X scale count, radius inches


def read():
    out = subprocess.run(["halcmd", "-s", "show", "pin"], capture_output=True, text=True).stdout
    vals = {}
    for line in out.splitlines():
        f = line.split()
        if len(f) >= 5 and f[4] in PINS:
            vals[f[4]] = float(f[3])
    return vals


def main(seconds, path):
    rows, t0 = [], time.monotonic()
    while time.monotonic() - t0 < seconds:
        v = read()
        if len(v) == len(PINS):
            rows.append([round(time.monotonic() - t0, 3)] + [v[p] for p in PINS])
        time.sleep(0.05)
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["t"] + PINS)
        w.writerows(rows)
    still = [r for r in rows if abs(r[5]) < 1e-6]
    moving = [r for r in rows if abs(r[5]) >= 1e-6]

    def stats(rs, label):
        if not rs:
            print(f"{label}: no samples")
            return
        err_dia = [2.0 * (r[1] - r[2]) for r in rs]       # cmd - fb, diameter
        print(f"{label}: n={len(rs)}  err dia min {min(err_dia):+.5f} max {max(err_dia):+.5f}  "
              f"span {max(err_dia) - min(err_dia):.5f}  mean {sum(err_dia) / len(err_dia):+.5f}")
        counts = Counter(round((r[1] - r[2]) / COUNT_R) for r in rs)
        print(f"   error in scale counts (1 = .0004 dia): {dict(sorted(counts.items()))}")
    stats(still, "standstill")
    stats(moving, "moving")


if __name__ == "__main__":
    main(float(sys.argv[1]), sys.argv[2])
