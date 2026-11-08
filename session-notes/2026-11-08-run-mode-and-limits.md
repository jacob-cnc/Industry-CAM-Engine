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
