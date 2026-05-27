# Z-Axis PID Tuning, Motor Stall Diagnosis, MPG Scale Calibration
**Date:** 2026-05-26  
**Branch:** main

---

## Summary

This session resolved Z-axis following errors, drive stalls during fast MPG jogging,
and a systematic Z position-mode jog accuracy error (2:1). The machine is now stable
for manual operation. Threading validation is the next milestone.

---

## Key Findings

### FF1 > 1.0 on Z causes endpoint overshoot in G-code
FF1=1.4 (and later 1.05) was masking a friction/load problem by overcorrecting velocity.
It reduced following error during fast jogging but would cause position overshoot at the
end of G-code moves and during fine-feed incremental jogging. Root cause of growing
following error at FF1=1.0 is carriage friction, not FF1 deficiency. FF1 returned to 1.00.
The correct tool for friction-induced drift is small I gain — tested at I=0.002 but
reverted; user set I=0 and adjusted P/D instead.

### Z motor stall is a torque/speed limit, not a PID issue
The "grrrr" + stall pattern during fast velocity-mode MPG jogging is the UIM8696PM
internal loop losing lock at high speed + abrupt acceleration demand. The following error
ramp (encoder runs ahead of command) is a symptom of motor slip, not a tuning problem.
Fixes applied:
- AXIS_Z MAX_VELOCITY: 1.0 → **0.75 in/s** (caps teleop jog, does NOT affect threading)
- Z fast MPG jog scale reduced 25%: 0.000351563 → **0.000263672**
- JOINT_1 MAX_VELOCITY remains 1.5 in/s for threading (smooth G-code profile tolerated)

### AXIS_Z vs JOINT_1 MAX_VELOCITY: different limits for different modes
- `AXIS_Z MAX_VELOCITY` = teleop/jogging cap only (MPG, jog buttons)
- `JOINT_1 MAX_VELOCITY` = G-code / threading cap
Reducing AXIS_Z to 0.75 protects the motor during jogging while leaving threading
velocity at 1.5 in/s. At 1.5 in/s: 8 TPI → max 720 RPM, 10 TPI → max 900 RPM.

### Z position-mode MPG jog was reading half the commanded distance
Symptom: .001" mode moved Z only .0005" per click.  
Root cause: LinuxCNC lathe G7 (diameter) mode doubles the apparent X jog distance
(axis.x.jog-counts × scale is in radius, DRO shows diameter = 2× that). Z has no
diameter mode — its jog counts are in actual inches — so the mux8 scales calibrated
on the assumption of 8 counts/click (50-detent MPG) were producing only 4 counts/click
(100-detent MPG) × 0.000125 = 0.0005" per click. X appeared correct because the
diameter/radius doubling coincidentally compensated.  
Fix: doubled Z position-mode jog scales only:
- `mux8.jogscale-z.in0`: 0.000025 → **0.000050** (0.0002" per click)
- `mux8.jogscale-z.in1`: 0.000125 → **0.000250** (0.001" per click)

### STEPGEN_MAXVEL was exceeding hardware ceiling on X
X hardware max: 100kHz / 54186.667 steps/in = **1.845 in/s**  
Old STEPGEN_MAXVEL was 2.04 (above ceiling → startup clipping warning).  
Fixed: X → 1.8, Z → 2.0 (satisfies JOINT_MAX_VEL × 1.25 headroom rule).

---

## Final INI Values (settled, committed)

### JOINT_1 (Z axis)
```
MAX_VELOCITY    = 1.5       # G-code / threading
MAX_ACCELERATION = 5
STEPGEN_MAXVEL  = 2.0
P = 60  I = 0  D = 0.005
FF1 = 1.00
DEADBAND = 0.0002
FERROR = 0.200
MIN_FERROR = 0.100          # raise if direction-reversal faults appear
```

### AXIS_Z (teleop / jogging cap)
```
MAX_VELOCITY = 0.75
```

### JOINT_0 (X axis) — unchanged and stable
```
MAX_VELOCITY    = 1.7
STEPGEN_MAXVEL  = 1.8       # near hardware ceiling 1.845 — do not raise
P = 125  I = 0  D = 0.002
FF1 = 1.00
DEADBAND = 0.0005
FERROR = 0.100
MIN_FERROR = 0.050
```

---

## HAL Changes (industry-cam.hal)

### Z position-mode jog scales doubled
```
mux8.jogscale-z.in0  = 0.000050   # 0.0002" per click
mux8.jogscale-z.in1  = 0.000250   # 0.001"  per click
mux8.jogscale-z.in2  = 0.00003125 # Vel Slow (unchanged)
mux8.jogscale-z.in3  = 0.0001875  # Vel Med  (unchanged)
mux8.jogscale-z.in4-7 = 0.000263672 # Vel Fast (capped at AXIS_Z=0.75)
```

### X jog scales unchanged
X position-mode scales are correct as-is — diameter mode makes them coincidentally right.

---

## GUI Changes

### status_bar.py — error ribbon
- Added `_error_label` QLabel to status bar ribbon
- 8-second auto-dismiss timer
- Polls NML error channel at 5 Hz via `_poll_status_bar_inner()`
- Shows "E-STOP" on first ESTOP transition

### live_backend.py — error channel robustness
- Wrapped NML error channel drain in try/except to prevent poll() crash

### tuning_tab.py — AXIS-level velocity fields
- Added "Axis Jog Limits (teleop cap)" section with axis_max_vel / axis_max_accel
- Reads/writes [AXIS_X] / [AXIS_Z] sections separately from joint sections
- Added backlash field (displays BACKLASH=0 correctly for linear encoder systems)
- Updated MIN_FERROR tooltip to explain backlash relationship

---

## Known Remaining Items

- **Z backlash unmeasured**: MIN_FERROR=0.100" is safe but loose. Measure with dial
  indicator (jog to contact, reverse, measure lag) and tighten to backlash + 0.010".
- **BACKLASH=0 orphan lines**: lines 136 and 190 in INI sit outside their section headers
  but parse into the correct preceding section with value 0.0 — functionally correct,
  cosmetically confusing. User's editor keeps restoring them.
- **X STEPGEN_MAXVEL headroom tight**: 1.8 / 1.7 = 1.06× (hardware-constrained).
  If X shows startup clipping warning, lower JOINT_0 MAX_VELOCITY to 1.6.
- **Threading not yet validated**: first test should be a light pass at 200–300 RPM.
  Start at 16 TPI or finer before attempting 8 TPI.
- **Z velocity modes**: fast mode capped by AXIS_Z=0.75. If motor proves stable at
  higher jogging speeds, raise AXIS_Z before touching fast jog scale.
