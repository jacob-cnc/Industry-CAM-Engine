# X Axis PID Tuning Session — 2026-05-25

## Starting State
- X (JOINT_0): P=50, D=.0001, DEADBAND=.0001", FERROR=.500", MIN_FERROR=.100"
- MAX_VEL=1.7 in/s, MAX_ACCEL=10.0, STEPGEN_MAXVEL=1.8, STEPGEN_MAXACCEL=12.5
- Minimum jog increment: .0001" (below encoder resolution)

## Phase 1 — Velocity Ceiling

Tested MPG fast jog at MAX_VEL=1.0 in/s (conservative starting point):
- Peak f-error: .0051" at ~.78 in/s — no FERROR trip, tracking clean

Raised MAX_VEL to 1.5 in/s: immediate FERROR trip on fast jog, motor stalled.
Motor velocity ceiling is between 1.0 and 1.5 in/s on X.

**Decision:** Keep MAX_VEL=1.7 in/s (committed value), STEPGEN_MAXVEL=1.8.
Operator stays below ceiling via normal use. FERROR=.020" / MIN_FERROR=.005"
will catch any real stall during operation.

**Lesson:** JOINT_0 MAX_ACCEL and STEPGEN_MAXACCEL must stay matched to AXIS_X
MAX_ACCELERATION (10.0 in/s²). Lowering JOINT_0 MAX_ACCEL to 5 without updating
AXIS_X caused direction-reversal FERROR — the trajectory planner commanded at
10 in/s² while stepgen headroom was only 6.25. Reverted to committed values.

## Phase 2 — PID Tuning (Slow Jog Priority)

Monitored f-error during .001"/click MPG jog:
- At rest: f-error = 0, no hunting
- During slow jog: peak f-error .00031", mean .00005"
- PID output small (max ~.044 in/s) — FF1=1.0 handling velocity, P trimming

**Result: P=125, D=.001, FF1=1.0 validated for slow jog use case.**

## Phase 3 — FERROR Tightening

Tightened from commissioning values:
- FERROR: .500" → .020" (~4× headroom over worst observed .0051")
- MIN_FERROR: .100" → .005"

First attempt (.010"/.003") tripped on fast direction change due to f-error
peaking at deceleration through zero velocity when limit dropped to MIN_FERROR.
.020"/.005" is stable across all jog speeds and directions.

## Phase 4 — Deadband and Position Accuracy

Used .0001" indicator (≈.00003" resolution with graduation interpolation)
to evaluate static accuracy.

**Hunting at rest:** DEADBAND=.00005" was below encoder resolution (.0002"/count).
PID chasing sub-count noise caused hunting. Raised to DEADBAND=.0002" (one encoder
count) — hunting stopped completely.

**Position accuracy at .001"/click:** 10 cycles of 10 clicks fwd/back accurate
to within .0002" — acceptable.

**Position accuracy at .0002"/click (dia):** Each click = .0001" radius = half
an encoder count. Motor executes move correctly (indicator confirms .0001" radius
per click), but DRO can only resolve full counts (.0002" radius = .0004" dia).
Accepted as the encoder resolution floor — physical motion is accurate, DRO
display is quantized.

## Bug Fix — Minimum Jog Increment Mismatch

Changed minimum jog increment from .0001" to .0002" (diameter) to match encoder
resolution. However, the mux4.jogscale-x.in0 HAL value was not updated to match:

- GUI label: .0002" dia per detent
- mux4.jogscale-x.in0 was: .0000125" radius
- Actual motion: .0000125 × 4 counts/detent = .00005" radius = .0001" dia ← wrong

Fix: mux4.jogscale-x.in0 .0000125 → .000025" radius
     (.000025 × 4 counts/detent = .0001" radius = .0002" dia ✓)

Note: 100 PPR MPG × 4 quadrature = 400 counts/rev ÷ 100 detents = 4 counts/detent.
All other mux4 scale values were already correctly set for this factor.

## Final X Axis State

| Parameter | Value |
|---|---|
| P | 125 |
| I | 0 |
| D | .001 |
| FF1 | 1.0 |
| DEADBAND | .0002" |
| MAX_OUTPUT | 2.5 in/s |
| FERROR | .020" |
| MIN_FERROR | .005" |
| MAX_VEL | 1.7 in/s |
| MAX_ACCEL | 10.0 in/s² |
| STEPGEN_MAXVEL | 1.8 in/s |
| STEPGEN_MAXACCEL | 12.5 in/s² |

## Next Session
- Z axis: apply same PID tuning + FERROR tightening methodology
- Home/limit switches still unwired
- Jog buttons, cycle start/stop still unwired
