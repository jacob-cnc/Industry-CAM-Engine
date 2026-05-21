# Axis Convention Triple-Flip — X and Z

## Date: 2026-05-20

## Summary
Both X and Z axes had inverted lathe-convention sign mapping: positive joint command physically drove the carriage in the **wrong** direction relative to convention (X+ should be away from spindle center, Z+ toward tailstock). Initial attempts to "fix" by flipping ENCODER_SCALE alone broke the closed loop (cmd/fb sign disagreement → FERROR runaway). The correct fix is a coordinated three-sign flip per axis.

## Root Cause
For a closed-loop stepper + linear-encoder axis, **three independent sign choices** must be self-consistent:

1. `STEP_SCALE` — relates joint cmd direction to physical motor/carriage direction.
2. `ENCODER_SCALE` — relates physical motion direction to position-fb (DRO) direction.
3. `jogscale` (MPG) — relates MPG rotation to joint cmd direction.

Loop stability requires `sign(STEP_SCALE)` and `sign(ENCODER_SCALE)` to be consistent with the encoder's physical count direction — otherwise the PID gets positive feedback and the motor runs away. **Flipping ENCODER_SCALE alone always breaks stability.** Flipping STEP_SCALE alone reverses physical motion. Flipping jogscale alone reverses MPG direction.

To rotate an axis 180° in software (correct convention without changing motor wiring), all three signs must flip together.

## The Triple-Flip Pattern

| Concern | Sign change required |
|---|---|
| Physical motion direction relative to joint cmd | `STEP_SCALE` |
| Loop stability (cmd and fb agree) | `ENCODER_SCALE` |
| MPG rotational direction preserved | `jogscale` |

After the triple flip:
- Positive joint cmd = lathe-convention positive direction (X+ away from center, Z+ toward tailstock)
- DRO position-fb increments in the convention-positive direction
- Closed loop stable (cmd and fb track)
- MPG direction unchanged (CW → X− toward center, CW → Z+ toward tailstock per user preference)

## Diagnostic Pattern

**Symptom A — instant FERROR trip on first jog click**: sign mismatch between STEP_SCALE and ENCODER_SCALE. Loop is positive-feedback unstable. (We hit this on X when we tried flipping just ENCODER_SCALE.)

**Symptom B — FERROR drifts in over distance, physical motion correct, DRO direction wrong**: loop sign-stable but axis convention inverted. (Z's symptom before the fix.) The cmd/fb may briefly disagree at edges; FF1=1.0 carries physical motion while PID accumulates error.

**Symptom C — physical direction wrong on MPG, otherwise OK**: jogscale sign issue only.

If DRO direction is wrong on a closed-loop stepper + linear-encoder, **never flip ENCODER_SCALE alone**. Either:
- Hardware fix: swap motor wires (then ENCODER_SCALE alone flips), or
- Software fix: triple flip (STEP_SCALE + ENCODER_SCALE + jogscale).

## Changes This Session

### `industry-cam.ini`

**`[JOINT_0]` X axis:**
- `STEP_SCALE` `54186.667` → `-54186.667`
- `ENCODER_SCALE` `-5080` → was already negative (no change vs prior-day state, but paired with negated STEP_SCALE now)

**`[JOINT_1]` Z axis:**
- `STEP_SCALE` `27093.333` → `-27093.333`
- `ENCODER_SCALE` `5080` → ... → `5080` (briefly flipped to `-5080` while diagnosing; final value is positive, paired with negated STEP_SCALE)

### `industry-cam.hal`

- `mux4.jogscale-x.in0..in3` all positive (`+0.0000125 / +0.000125 / +0.00125 / +0.0125`).
  Magnitudes intentionally halved vs Z (X is in diameter mode — half-click radial gives same numeric DRO step as Z).
- `mux4.jogscale-z.in0..in3` all positive (`+0.000025 / +0.00025 / +0.0025 / +0.025`).

## Verification

**X axis** (CW MPG click):
- Carriage moves toward center (X−) ✓
- DRO decrements ✓
- Loop stable (no FERROR) ✓

**Z axis** (CW MPG click):
- Carriage moves toward tailstock (Z+) ✓
- DRO increments ✓
- Loop stable (no FERROR) ✓

Both directions verified on single-click jog before larger moves committed.

## Live HAL Snapshot Used During Diagnosis

Reading `hm2_7i96s.0.encoder.00.rawcounts` before/after a known motion proved that Z encoder rawcounts **increase** as the carriage moves toward the tailstock. Combined with the empirical loop-stability behavior (loop stable with `ENCODER_SCALE = -5080`, unstable with `+5080` *at the time of testing with the old STEP_SCALE sign*), this confirmed the axis was internally consistent but inverted in convention — not a simple encoder polarity issue.

The same diagnostic approach should be used in future commissioning: rather than guessing scale signs, monitor `encoder.NN.rawcounts` and the corresponding `joint.N.motor-pos-cmd` and `motor-pos-fb` during slow MPG motion.

## Open Items
- PID tuning not yet started (X: P=150 D=.0001 — placeholder; Z: P=500 D=0 — original). Need to step through gain tuning with actual loads.
- Following error remains loose (`FERROR = 0.500"`) — tighten once PID is dialed.
- STEP_SCALE accuracy not yet verified against a measured 1.0" move.
- Home switches, limit switches, jog buttons, cycle start/stop still NOT wired.
