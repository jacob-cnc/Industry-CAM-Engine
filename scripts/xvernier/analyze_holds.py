#!/usr/bin/env python3
"""Parking error per hold from a capture (x_positioning_test.ngc / x_wear_staircase.ngc).

A hold = motor_pos_cmd unchanged for >= --min-hold seconds. For each hold the
last --tail seconds are averaged and reported in DIAMETER:
  est-cmd    vernier estimate minus command: the real parking error
             (shadow mode: what today's loop actually does; closed: the new loop)
  scale-cmd  raw scale minus command (what the DRO showed before)
  resid      vernier vs scale at rest, in counts (must stay within +-0.6)
The approach direction is taken from the command before the hold.

usage: analyze_holds.py CAPTURE [--scale -5080] [--dt 0.002] [--min-hold 1.5] [--tail 0.5]
"""
import argparse
import sys

import numpy as np


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("capture")
    ap.add_argument("--scale", type=float, default=-5080.0)
    ap.add_argument("--dt", type=float, default=0.002)
    ap.add_argument("--min-hold", type=float, default=1.5)
    ap.add_argument("--tail", type=float, default=0.5)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    d = np.loadtxt(a.capture, comments="#")
    s, counts, cmd, est, resid, en = d.T
    p = counts / a.scale
    n_min, n_tail = int(a.min_hold / a.dt), int(a.tail / a.dt)

    holds, i, N = [], 1, len(cmd)
    while i < N:
        j = i
        while j + 1 < N and cmd[j + 1] == cmd[i]:
            j += 1
        if j - i + 1 >= n_min and en[i:j + 1].all():
            k0 = max(i, j - n_tail + 1)
            before = cmd[max(0, i - 50):i]
            came = "up" if len(before) and before.mean() < cmd[i] else "down"
            holds.append({
                "t": i * a.dt, "cmd_dia": 2 * cmd[i], "from": came,
                "est_err": 2 * float(np.mean(est[k0:j + 1]) - cmd[i]),
                "scale_err": 2 * float(np.mean(p[k0:j + 1]) - cmd[i]),
                "resid_max": float(np.max(np.abs(resid[k0:j + 1]))),
                "est_wander": 2 * float(np.ptp(est[k0:j + 1])),
            })
        i = j + 1

    if a.json:
        import json
        print(json.dumps(holds))
        return 0
    if not holds:
        print("no holds found (is the capture from a test program?)")
        return 1
    print(f"{'t s':>7} {'cmd dia':>9} {'from':>5} {'est-cmd':>9} {'scale-cmd':>10} {'resid':>6} {'wander':>8}")
    for h in holds:
        print(f"{h['t']:7.1f} {h['cmd_dia']:9.4f} {h['from']:>5} {h['est_err']:+9.5f} "
              f"{h['scale_err']:+10.5f} {h['resid_max']:6.2f} {h['est_wander']:8.5f}")
    e = np.array([h["est_err"] for h in holds])
    print(f"\n{len(holds)} holds   parking error (est-cmd, dia): max |{np.max(np.abs(e)):.5f}|  "
          f"rms {np.sqrt(np.mean(e**2)):.5f}  mean {np.mean(e):+.5f}  spread {np.ptp(e):.5f}")
    for came in ("up", "down"):
        ee = np.array([h["est_err"] for h in holds if h["from"] == came])
        if len(ee):
            print(f"  from {came:>4}: n={len(ee):3d} mean {np.mean(ee):+.5f} spread {np.ptp(ee):.5f}")
    bad = [h for h in holds if h["resid_max"] > 0.6]
    if bad:
        print(f"WARNING: {len(bad)} holds where the vernier disagreed with the scale by > 0.6 count")
    return 0


if __name__ == "__main__":
    sys.exit(main())
