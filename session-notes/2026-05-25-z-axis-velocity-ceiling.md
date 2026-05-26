# Z Axis Velocity Ceiling Investigation — 2026-05-25

## Starting State
- Z (JOINT_1): P=100, D=.0001, DEADBAND=.0001", FERROR=.500", MIN_FERROR=.100"
- MAX_VEL=2.0 in/s, MAX_ACCEL=10.0, STEPGEN_MAXVEL=2.4, STEPGEN_MAXACCEL=12.5

## Phase 1 — Accuracy Check at Slow Jog

100 MPG clicks (.0005" dia per click on GUI selector): DRO read .0049", indicator read .0051".
Error ~.0002" — borderline. Stepper hunted continuously at rest.

**Fix:** DEADBAND .0001" → .0002" (one encoder count, same fix as X axis). Hunting stopped.

Tested .001"/click accuracy: broadly consistent but ~.001" cumulative error over 100 clicks.
Observed .101" indicator vs .100" DRO on a 100-click move — approximately 1% scale error.
Decision: defer ENCODER_SCALE calibration (from 5080 to ~5030) until velocity issue resolved.

## Phase 2 — Velocity Ceiling Discovery

Fast MPG jog at MAX_VEL=2.0 in/s: immediate FERROR trip. Motor stalling on any fast jog.

Captured data with `monitor_z_vel.sh`:

```
Peak f-error: 0.2730" at t=Xs
Feedback velocity capped at ~0.25 in/s while cmd reached 0.35+ in/s
```

Motor velocity ceiling confirmed at approximately **0.25 in/s**. This is extremely low —
same UIM8696PM motor as X but Z ceiling is ~4× lower. Z leadscrew pitch is ~6mm
(27093 steps/in) vs X ~3mm (54186 steps/in); at 0.25 in/s Z motor is only ~63 RPM.
This strongly suggests a UIM8696PM internal parameter (speed limit or current profile)
needs investigation separately.

## Phase 3 — PID Correction Headroom Investigation

Identified two config errors making recovery impossible during velocity events:

**Error 1 — MAX_OUTPUT=0.35 in/s too low:**
PID can only command .15 in/s above cruise speed (.20 in/s), not enough to recover
from a velocity-induced lag. Raised MAX_OUTPUT .35 → 2.5 in/s (same as X axis).

**Error 2 — MAX_ERROR=.001" too tight:**
PID correction authority = P × MAX_ERROR = 100 × .001 = .1 in/s — starved.
Raised MAX_ERROR .001" → .010" → correction authority now 100 × .010 = 1.0 in/s.

**Error 3 — STEPGEN_MAXVEL=2.4 insufficient without headroom:**
With MAX_OUTPUT=0.35 and motor ceiling at 0.25, stepgen headroom was meaningless.
After fixing MAX_OUTPUT, lowered STEPGEN_MAXVEL to 1.0 (still 5× MAX_VEL headroom).

## Final Decision — Conservative MAX_VEL

Set MAX_VEL=0.20 in/s (safely below .25 ceiling). This allows reliable operation
while the motor ceiling is investigated. Raised when root cause is understood.

## Result

Fast MPG jogging stable. FERROR no longer trips during normal use.
Operator stays below velocity ceiling via normal use; FERROR=.500"/.100" catches stalls.

## Z Axis State After This Session

| Parameter | Value |
|---|---|
| P | 100 |
| I | 0 |
| D | .0001 |
| FF1 | 1.0 |
| DEADBAND | .0002" |
| MAX_OUTPUT | 2.5 in/s |
| MAX_ERROR | .010" |
| FERROR | .500" |
| MIN_FERROR | .100" |
| MAX_VEL | .20 in/s |
| MAX_ACCEL | 10.0 in/s² |
| STEPGEN_MAXVEL | 1.0 in/s |
| STEPGEN_MAXACCEL | 12.5 in/s² |

## Pending (Next Sessions)

- **Motor ceiling investigation:** UIM8696PM internal speed parameters — why is Z ceiling .25 in/s?
  At 27093 steps/in × 0.25 in/s = 6773 steps/s = ~100 Hz step rate. Should be far below limit.
  Check UIM8696PM serial config (max RPM, acceleration limit, current settings) via USB tool.
- **ENCODER_SCALE calibration:** Observed ~1% scale error (.101" indicator vs .100" DRO).
  ENCODER_SCALE 5080 → ~5030 once velocity is resolved and slow-jog is reliable.
- **PID tuning (slow jog):** P/D/FERROR tightening using same methodology as X axis.
- **mux4.jogscale-z.in0:** Currently .000025 (gives .0001"/click). Should be .00005 to
  match .0002" minimum GUI label (Z is linear, not diameter — same factor as X but without 2×).
- Home/limit switches still unwired.
- Jog buttons, cycle start/stop still unwired.
