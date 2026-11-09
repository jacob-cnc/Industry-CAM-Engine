# Session plan: X position-loop deadband tuning

## Workstream

Branch: none yet (INI change only after the bench step passes)
Environment: lathe PC, LinuxCNC 2.9.6, Mesa 7i96s, X step/dir + linear scale
Change classification: Machine-control (position loop gain)
Status: **Planned — owner-present bench session required.** Nothing changed yet.

## Why

Owner touched off X with Set X = 2.9583 after a measured test cut; the DRO then
read 2.9576.

- **Observed (2026-11-08, read-only HAL):** `x-pos-cmd` 2.127125, `x-pos-fb`
  2.126772 (radius). Difference .000353 r = .0007 dia = the DRO discrepancy.
- **Verified (config):** `[JOINT_0] DEADBAND = .0005`, `I = 0`.
  `G10 L20` registers from the *commanded* position; the DRO shows the
  *encoder* position. The PID ignores any error inside ±.0005 r (±.0010 dia),
  so X can park anywhere in that window, and sizes vary by the same amount.
- **Verified (config):** X scale 5080 counts/in → one count = .000197 r
  (.0004 dia). X step scale 54186.667 steps/in ≈ 10.7 steps per count.
- Z already runs `DEADBAND = 0.0002` (≈1 count) — X is the outlier.
- The drives are UIM8696PM closed-loop steppers with their own internal motor
  encoder loop. LinuxCNC's loop sits on top via the linear scale, so watch for
  the two loops fighting (drive correcting while PID nudges) as well as plain
  dithering.

Owner decided: do NOT use a wear offset to hide this; tune the loop instead.

## Goal and Acceptance Criteria

- Goal: X standstill error ≤ about 1.3 encoder counts.
- Accept the new deadband only if ALL hold:
  1. Standstill |cmd − fb| ≤ new deadband at every test position, approached
     from both directions.
  2. No hunting at rest for 60 s: fb does not toggle counts, no step-motor
     buzz/tick, `pid.x.output` stays 0.
  3. Jogs (MPG ×1/×10/×100) and an MDI rapid end-to-end finish without
     following-error faults, with no visible overshoot ringing.
  4. A skim cut measured after the change agrees with the DRO within .0004 dia
     (one count).

## What we will NOT change

- **I gain stays 0.** LinuxCNC's `pid` zeroes the error inside the deadband
  before integrating, so I cannot remove an error that is inside the band; it
  would only add windup/overshoot risk outside it.
- P, D, FF1, MAX_OUTPUT, FERROR, stepgen limits: unchanged.
- No realtime latency tests and no test suite runs while LinuxCNC is up
  (see 2026-11-08 PC freeze).

## Procedure (owner at the machine, Claude reading HAL)

Preconditions: LinuxCNC up, homed at the gage block (Machine Coords X should
read +8.5000), machine on, spindle off, no program running, tool clear of work.

1. **Baseline at .0005.** Jog X with the MPG to ~4 positions across the travel,
   arriving at each from + and from −. At each stop wait 5 s and record
   `x-pos-cmd`, `x-pos-fb`, `joint.0.f-error`, `pid.x.output`
   (Claude reads these with `halcmd getp`, read-only, one-shot).
2. **Step the deadband down live** (Commissioning → Tuning, X axis, Deadband
   field → **Apply Live**; this is `halcmd setp pid.x.deadband`, no restart):
   `.0004` → `.0003` → `.00025`. At each value:
   - leave X at rest 60 s, listen at the motor, Claude samples fb/output a few
     times (no continuous logging loop);
   - repeat two of the step-1 positions from both directions.
   - **Stop at the first sign of hunting** and go back one value.
3. **Do not go below .00025** (≈1.27 counts). At or below one count
   (.000197) the loop dithers between adjacent counts.
4. **Motion check** at the chosen value: MPG jogs at all scales, then an MDI
   rapid across most of the X travel and back. Watch for f-error faults or
   ringing at the stop.
5. **Persist:** Tuning tab **Save to INI** (or edit `[JOINT_0] DEADBAND`),
   commit on a `claude/x-deadband` branch with the measured numbers, merge to
   main after the owner confirms.
6. **Verify on a part:** restart LinuxCNC, home at the gage block, skim cut,
   measure, Set X to the measured diameter, check the DRO now agrees within
   one count. Then a second skim at a programmed diameter and measure — this is
   the real acceptance check.

## Rollback

- Live: Tuning tab Deadband `.0005` → Apply Live (immediate).
- Persistent: revert the INI commit, restart LinuxCNC.

## After this session

- Re-check the G54 X touch-off (it was registered against commanded position
  with up to .0005 r of loop slack).
- If X hunts even at .0003, the next suspects are mechanical (gib, scale mount,
  backlash vs. step resolution), not more PID tuning — record and stop.
