# X axis: holding a .0004" diameter tolerance band (2026-11-10)

Owner goal: parts with a **total** tolerance band of .0004" (diameter), so the
actual-vs-commanded X position must hold *tighter* than that. Tonight's parts
were made to size, but only by chasing X wear by hand.

## Evidence

- **Tonight's wear chase** (tool.tbl backups, T1 X wear, 16:51-20:03):
  -.0005, -.00075, -.0015, -.0010, -.00125, -.00115, -.00105, -.0010, -.00095,
  -.000975, -.00095 — 11 corrections in about 3 hours, wandering over a .001"
  window before settling near -.0010.
- **Loop configuration** (`industry-cam.ini [JOINT_0]`, `industry-cam.hal`):
  the position loop closes on the X linear scale (`encoder.01` → `pid.x` →
  `stepgen.01` velocity mode), `P = 125`, `I = 0`, `D = .002`, `FF1 = 1`,
  **`DEADBAND = .0005`** (radius) → the PID ignores errors up to ±.0005 r =
  **±.0010 dia**. That window matches the wear wander above.
- **Measured 2026-11-08** (read-only HAL): X parked .000353 r (.0007 dia) off
  command.
- **Scale resolution:** `ENCODER_SCALE = 5080` counts/in → 1 count =
  .000197 r = **.0004 dia — the whole tolerance band.**
- **Step resolution:** `STEP_SCALE = 54186.667` steps/in → .0000185 r
  (.000037 dia) per step, about 11 steps per scale count. The motor can move
  far finer than the scale can see.

## What this means

A position loop cannot hold a target tighter than about ±1 count of its own
feedback. With this scale that is ±.0004 dia (±.0002 at best, with the loop
dithering between two counts) — the full band, with nothing left for tool
deflection, spring, thermal growth or measurement. Loop tuning alone cannot
get there; it can only remove the extra slack the deadband adds on top.

## Options, in the order I would do them

### 1. Cut the deadband (planned, low risk, no hardware) — next owner session
`docs/handoffs/2026-11-08-x-deadband-tuning.md`: step `.0005` → `.0004` →
`.0003` → `.00025` live from the Tuning tab, stop at the first sign of
hunting. Expected: the parking window drops from ±.0010 to about ±.0005 dia.
Necessary, but on its own still wider than the band.

### 2. Measure what is left (same session, read-only: `scripts/x_error_log.py`)
A non-realtime logger (like tonight's E-stop watcher, about 20 Hz, `halcmd`
reads only): `joint.0.motor-pos-cmd`, `x-pos-fb`, `pid.x.error`,
`pid.x.output` at rest and through a finish pass. That separates
**quantization** (error flips between ±1 count) from **dynamics** (error
grows with feed / in arcs / at reversals) from **mechanics** (scale and
tool disagree: gib, scale mount, backlash). No RT components loaded, no
latency tests.

### 3. Finer X feedback — the real fix
Replace the X scale with a **1 µm** linear scale (25400 counts/in →
.00008 dia per count; Sino KA300 and similar come in 1 µm, some in 0.5 µm).
Then a deadband of about 1.5 counts (.00006 r) holds about ±.00012 dia — a
third of the band, with room for the rest of the process. Fits the existing
7i85s encoder input and the current HAL/INI; only `ENCODER_SCALE` (sign
unchanged), `DEADBAND`, and a retune of P/D change. This is the option that
makes .0004 parts routine instead of tedious.

### 4. If no new scale: dual-loop control (more work, software only)
Close the fast loop on the stepper (its integrated closed-loop drive already
holds the motor shaft; LinuxCNC commands steps at .000037 dia resolution) and
use the linear scale only as a slow outer correction (an integrator with a
1-count deadband that trims the command toward the scale). The motor then
does not dither, and the scale removes screw error and backlash on average.
Still limited by the scale's ±1 count for *absolute* accuracy, so it narrows
but does not close the gap. Needs the drive's motor-encoder resolution
(UIM8696PM manual) before committing.

### 5. Process (independent of the above)
- Spring pass on the final diameter (`finish_spring_pass`), constant finish
  DOC, same approach direction for the last pass → removes deflection and
  backlash variation that no loop tuning sees.
- Measure-and-correct as one step: a GUI "measured diameter → X wear" helper
  that computes the correction and logs it (instead of typing wear values),
  so the chase is one entry per check, not a guess.

## Proposal for the next session (owner present)
1. Deadband step-down per the 2026-11-08 handoff (30 min).
2. 20 Hz read-only error log at rest + one finish pass (15 min).
3. Decide: order a 1 µm X scale (recommended) or try the dual-loop design.
