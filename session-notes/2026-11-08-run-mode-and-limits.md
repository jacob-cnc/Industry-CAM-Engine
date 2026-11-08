# 2026-11-08 — Program would not start; stuck in AUTO; soft limits relaxed

## Symptoms (owner, lathe)
Cycle start on the regenerated GCH bore program did nothing; afterwards the
controller stayed in AUTO (MPGs dead) even when switching tabs.

## Causes (from /tmp/lcnc_gui.log and the .ngc)
1. Program rejected at line 51 `N40 G00 X2.5000 Z2.0000` (park):
   "Linear move on line 51 would exceed X's negative limit". G54 X = -1.5000
   radius (Set X to 3.000 dia at the power-up position), so X2.5 dia = -0.25
   machine radius < MIN_LIMIT -0.01. Unhomed machine 0 is the power-up position;
   LinuxCNC relaxes jog limits when unhomed but always checks program moves.
2. RunTab.load -> LiveBackend.program_open switched to AUTO; nothing returned to
   MANUAL; LinuxCNC ignores MPG jog counts outside MANUAL.

## Changes (owner-approved)
- INI: X MIN_LIMIT -0.01 -> -0.05 (JOINT_0, AXIS_X); Z limits +/-3.0 -> +/-5.0
  (JOINT_1, AXIS_Z). Owner powers up at a known reference so machine 0 is
  meaningful. NOTE: unhomed, machine X 0 = power-up position, so X can only go
  0.05 radius INWARD of it; if powering up at full X retract, press Home (sets
  X = 4.25 there via home-in-place) before running programs.
- program_open no longer changes mode (matches AXIS open_file_guts); refuses
  while the interpreter is busy; task_plan_synch before open. _ensure_mode now
  waits for the mode change like AXIS ensure_mode.
- MainWindow: AUTO + interpreter IDLE for 2 consecutive polls -> MANUAL
  (covers finish, stop, and cycle-start rejection; PAUSED/WAITING untouched).
- Run tab shows the last LinuxCNC error (cleared at next start).
- Ribbon mode chip is clickable: returns to MANUAL only when the interpreter
  is idle; otherwise shows "Program active - stop it before leaving AUTO".
- backend.touch_off (Manual tab touch-off) sends G7 with X like Set X.

## Verification
Mock offscreen (system Python 3.11): AUTO+idle -> MANUAL after 2 polls; stays
AUTO while READING; chip click refused while running, works when idle; Run tab
error shown. Machine verification pending.

## Spindle at-speed (program held after N80)

- Cause: near-spindle compared encoder velocity (rev/s) with speed-out-abs (RPM);
  at-speed never TRUE with the spindle running, so motion held the first G01 after
  M3 (interp WAITING; extra cycle starts rejected "in auto mode with the interpreter
  waiting"). Unchanged since 2026-05-18; earlier successful runs likely had no M3.
- A false "encoder dead" reading at 12:22 was a Mesa power drop at 12:17 under a
  running LinuxCNC (stale hm2 inputs); after restart the encoder read normally.
- Measured: gearbox "64" position = 80.3 RPM (8.395 rev / 6.27 s), + in M3.
- MIN_FORWARD_VELOCITY 100 -> 50 (S64 had been clamped to 100 commanded).
- Fix (owner choice): in1 = speed-out-rps, in2 = encoder rev/s, scale 2.0
  (0.5x..2x, same direction). scripts/check_spindle_at_speed.sh: 10/10 PASS.
- Machine-verified: M3 S64 + spindle at 64 gear -> at-speed TRUE (cmd 1.067 rps,
  meas 1.30-1.42 rps); spindle stopped with M3 active -> FALSE.

## Program held before N90 until the spindle was switched off (and 0 RPM ribbon)

- Simulator (headless LinuxCNC 2.9.6 sim lathe, scratchpad) measured task states:
  at-speed hold = interp WAITING; single-block between steps = PAUSED/WAITING;
  MANUAL requested while waiting -> refused by LinuxCNC ("Can't switch mode while
  mode is AUTO and interpreter is not IDLE"). So the AUTO->MANUAL auto-return did
  not interfere with the run.
- Cause: program order `S64 M3` (N30) then `T1 M6` (N50). LinuxCNC stops the
  commanded spindle on M6 unless [EMCIO] TOOL_CHANGE_WITH_SPINDLE_ON = 1 (manual:
  "Useful for lathes"). Commanded 0 vs physically running manual spindle ->
  at-speed FALSE -> held; spindle off -> 0 vs 0 -> TRUE -> released; G95 then fed
  from the encoder with LinuxCNC believing the spindle was OFF. Ribbon showed the
  commanded (0) speed.
- Sim proof: after M6 commanded speed 64 -> 0 without the option, stays 64 with it.
- Fixes: INI TOOL_CHANGE_WITH_SPINDLE_ON = 1; ribbon RPM / direction / at-speed
  now from HAL (encoder rev/s via spindle-vel, spindle-at-speed) instead of stat.
- Proposed to Codex/owner (CAM): emit S/M3 after T M6 as defence in depth.
