#!/usr/bin/env python3
"""Fit the X vernier calibration from a sweep capture.

Input: a capture from scripts/xvernier/capture.sh (or the bench's --sweep), one
servo sample per line:  step_fb scale_counts motor_pos_cmd pos_est residual enable
Run scripts/xvernier/x_calibration_sweep.ngc while capturing.

Every single-count scale edge crossed while the motor was moving slowly is an
exact measurement of b = step_fb - true position at that instant. The fit is

    b = b0 + SLOPE*s + HARM_COS*cos(2 pi s/LEAD) + HARM_SIN*sin(2 pi s/LEAD)
           + H*dir + LAG_TIME*v

(dir = +1 moving +X, -1 moving -X; v = step velocity). LEAD is found by a grid
search. Prints the [XVERNIER] INI lines and how good the fit is, in DIAMETER
(X, the default) or in LENGTH (--units length, for Z).

usage: fit_calibration.py CAPTURE [--scale -5080] [--dt 0.002] [--span-max 0.0001]
                          [--lead-min 0.02 --lead-max 0.5] [--plot out.png]
  Z:   fit_calibration.py CAPTURE --scale 5080 --units length --steps-per-unit 27093.333
"""
import argparse
import math
import sys

import numpy as np


def load(path):
    rows = []
    with open(path) as fh:
        for line in fh:
            if not line.strip() or line.startswith("#"):
                continue
            f = line.split()
            if len(f) < 2:
                continue
            rows.append((float(f[0]), int(float(f[1])), int(float(f[5])) if len(f) > 5 else 1))
    a = np.array(rows, dtype=float)
    return a[:, 0], a[:, 1].astype(np.int64), a[:, 2]


def edges(s, counts, en, scale, dt, span_max):
    """Motor-driven single-count edges, same rules as the component."""
    out = []
    last_edge = None
    for k in range(1, len(s)):
        dc = counts[k] - counts[k - 1]
        if dc not in (1, -1) or not en[k] or not en[k - 1]:
            if dc != 0:
                last_edge = None
            continue
        ds = s[k] - s[k - 1]
        p0, p1 = counts[k - 1] / scale, counts[k] / scale
        td = 1 if p1 > p0 else -1
        eid = min(counts[k], counts[k - 1])
        driven = ds * td > 1e-9 and eid != last_edge
        last_edge = eid
        if not driven or abs(ds) > span_max:
            continue
        s_mid = 0.5 * (s[k] + s[k - 1])
        out.append((k * dt, s_mid, td, ds / dt, s_mid - 0.5 * (p0 + p1)))
    return np.array(out)


def design(e, lead):
    t, s, td, v, b = e.T
    cols = [np.ones_like(s), s, td, v]
    if lead:
        ph = 2 * math.pi * s / lead
        cols += [np.cos(ph), np.sin(ph)]
    return np.column_stack(cols), b


def fit(e, lead):
    A, b = design(e, lead)
    x, *_ = np.linalg.lstsq(A, b, rcond=None)
    r = b - A @ x
    return x, r


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("capture")
    ap.add_argument("--scale", type=float, default=-5080.0, help="ENCODER_SCALE (counts per unit, signed)")
    ap.add_argument("--dt", type=float, default=0.002, help="servo period, s")
    ap.add_argument("--span-max", type=float, default=0.0001)
    ap.add_argument("--lead-min", type=float, default=0.02)
    ap.add_argument("--lead-max", type=float, default=0.5)
    ap.add_argument("--units", choices=("dia", "length"), default="dia",
                    help="report X errors on diameter (default) or Z errors as length")
    ap.add_argument("--steps-per-unit", type=float, default=54186.667, help="|STEP_SCALE| (Z: 27093.333)")
    ap.add_argument("--plot", help="write a residual plot (needs matplotlib)")
    ap.add_argument("--json", action="store_true", help="print the result as JSON (for tests)")
    a = ap.parse_args(argv)

    s, counts, en = load(a.capture)
    u, un = (2.0, "dia") if a.units == "dia" else (1.0, "length")
    e = edges(s, counts, en, a.scale, a.dt, a.span_max)
    c = 1.0 / abs(a.scale)
    if len(e) < 200:
        print(f"only {len(e)} usable edges: run the full sweep program while capturing", file=sys.stderr)
        return 1
    span = s.max() - s.min()

    x0, r0 = fit(e, 0.0)
    best = (float(np.sqrt(np.mean(r0 ** 2))), 0.0, x0, r0)
    # grid search the screw lead; need >= 2 periods in the sweep
    lo, hi = a.lead_min, min(a.lead_max, span / 2)
    if hi > lo:
        for lead in np.geomspace(lo, hi, 3000):
            x, r = fit(e, lead)
            rms = float(np.sqrt(np.mean(r ** 2)))
            if rms < best[0]:
                best = (rms, float(lead), x, r)
        if best[1]:     # refine around the best
            for lead in np.linspace(best[1] * 0.995, best[1] * 1.005, 401):
                x, r = fit(e, lead)
                rms = float(np.sqrt(np.mean(r ** 2)))
                if rms < best[0]:
                    best = (rms, float(lead), x, r)
    rms_noharm = float(np.sqrt(np.mean(r0 ** 2)))
    rms, lead, x, r = best
    amp = math.hypot(x[4], x[5]) if lead else 0.0
    # keep the harmonic only if it explains something real (> 20% rms and > 5 microinch)
    if lead and not (rms < 0.8 * rms_noharm and amp > 5e-6):
        lead, x, r, rms = 0.0, x0, r0, rms_noharm
        amp = 0.0
    b0, slope, h, lag = x[0], x[1], x[2], x[3]
    hc, hs = (x[4], x[5]) if lead else (0.0, 0.0)

    # quality: residual per edge, and the drift of b0 across the capture (thermal)
    t = e[:, 0]
    k = max(1, len(t) // 5)
    drift = [float(np.mean(r[i:i + k])) for i in range(0, len(t) - k + 1, k)]
    up, dn = e[:, 2] > 0, e[:, 2] < 0
    res = {
        "edges": int(len(e)), "edges_up": int(up.sum()), "edges_down": int(dn.sum()),
        "speeds_in_s": sorted({round(abs(v), 4) for v in e[:, 3]})[:1] + sorted({round(abs(v), 4) for v in e[:, 3]})[-1:],
        "H_INIT": float(max(h, 0.0)), "LEAD": lead, "HARM_COS": float(hc), "HARM_SIN": float(hs),
        "SLOPE": float(slope), "LAG_TIME": float(max(lag, 0.0)), "b0": float(b0),
        "harm_amp": amp, "resid_rms": rms, "resid_rms_no_harm": rms_noharm,
        "resid_max": float(np.max(np.abs(r))), "drift_chunks": drift,
        "lead_steps": lead * a.steps_per_unit if lead else 0.0,
    }
    if a.json:
        import json
        print(json.dumps(res))
        return 0

    print(f"capture: {len(s)} samples, travel {span:.4f} r, {len(e)} usable edges "
          f"({res['edges_up']} up / {res['edges_down']} down)")
    print(f"fit residual rms {u*rms:.6f} {un} (max {u*res['resid_max']:.6f} {un}); "
          f"one scale count = {u*c:.6f} {un}")
    if lead:
        print(f"screw harmonic: lead {lead:.5f} in (= {res['lead_steps']:.0f} motor steps), "
              f"amplitude {u*amp:.6f} {un}; residual without it {u*rms_noharm:.6f} {un}")
    else:
        print("screw harmonic: none found (LEAD = 0)")
    print(f"backlash: half {h:+.6f}  -> total {2*h:.6f} axis = {2*u*h:.6f} {un} "
          + ("(negative: check the capture; using 0)" if h < 0 else ""))
    print(f"drive lag: {lag*1000:+.3f} ms " + ("(negative: using 0)" if lag < 0 else ""))
    print(f"step-vs-scale slope: {slope:+.3e}  ({slope*1e6:+.1f} microinch per inch of travel)")
    print(f"b0 drift over the capture (5 chunks, {un}): " + " ".join(f"{u*d:+.6f}" for d in drift))
    if u * rms > 0.0001:
        print(f"WARNING: residual > .0001 {un} - something the model doesn't cover "
              "(vibration, loose gib, scale mounting?). Look before closing the loop.")
    print()
    print("[XVERNIER] values:" if a.units == "dia" else "[ZVERNIER] values (for the Z phase):")
    print(f"H_INIT = {res['H_INIT']:.7f}")
    print(f"LEAD = {lead:.6f}")
    print(f"HARM_COS = {hc:.7f}")
    print(f"HARM_SIN = {hs:.7f}")
    print(f"SLOPE = {slope:.4e}")
    print(f"LAG_TIME = {res['LAG_TIME']:.5f}")
    print(f"FAULT_LIMIT = {max(0.0005, 4 * res['H_INIT'] + 0.0004):.5f}")

    if a.plot:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(2, 1, figsize=(10, 7))
        ax[0].plot(e[up, 1], u * 1e4 * (e[up, 4] - b0), ".", ms=2, label="up edges")
        ax[0].plot(e[dn, 1], u * 1e4 * (e[dn, 4] - b0), ".", ms=2, label="down edges")
        ax[0].set_xlabel("step position (r in)"); ax[0].set_ylabel(f"b - b0 ({un}, .0001)")
        ax[0].legend()
        ax[1].plot(e[:, 0], u * 1e4 * r, ".", ms=2)
        ax[1].set_xlabel("time (s)"); ax[1].set_ylabel(f"fit residual ({un}, .0001)")
        fig.tight_layout(); fig.savefig(a.plot)
        print(f"plot: {a.plot}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
