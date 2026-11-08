# 2026-11-08 — Cycle start / pause pushbuttons

## Measured (lathe, GPIO change logger)
GREEN = hm2_7i96s.0.gpio.009.in (TB3 P10), RED = gpio.010.in (TB3 P11); both
normally open, TRUE while pressed, ~150 ms presses, no bounce seen.

## What was there
Since 19ce3e6 (2026-05-27): green -> halui.program.run AND halui.program.resume,
red -> halui.program.stop (abort). Green while paused or mid-cut could restart
from line 1 (LinuxCNC reports interp IDLE mid-cut once the file is read) — the
"cycle start brought the program backwards" symptom. Red aborted, not paused.

## Owner requirement
Green: start when nothing running/queued; resume (not line 1) when paused.
Red: pause. Pushbuttons primary; GUI buttons kept as backup.

## Implementation
- industry-cam.hal sec. 10: red (debounced) -> halui.program.pause;
  green AND halui.program.is-paused -> halui.program.resume (and2.cycle-resume).
  GUI-independent.
- GUI: compound-slide.cycle-start netted to cycle-go-btn; main window polls at
  20 ms, on a rising edge with nothing queued (program_busy/paused false) it
  switches to the Run tab and calls RunTab.cycle_start(): machine-on and
  program-loaded checks, tool-table check prompt, then start at line 1.
- On-screen Cycle Start uses the same cycle_start(): resumes when paused.
- MachineState.paused (stat.paused) added.

## Verification
- Headless 2.9.6 sim with halui + the same nets: green idle -> nothing (HAL);
  green running -> ignored; red -> paused, 0.0000 movement over 1.5 s; green ->
  resumed on the same line from the same Z.
- 7 GUI tests (mock): idle start, held = one press, paused/running ignored by
  GUI, no-program and machine-off messages, screen resume.
Machine verification pending.

## Machine evidence (owner bench test, 15:24-15:25)
Owner: "Everything appears to be working." Log: 15:24:38 green -> program started
at line 1; 15:24:55-59 green while paused -> resumed by HAL (GUI logs "paused -
handled in HAL", it samples before halui applies the resume); 15:25:01-06 green
while running -> ignored. No LinuxCNC errors. MACHINE-VERIFIED.
