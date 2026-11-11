# X vernier: commissioning runbook (prepared 2026-11-10)

Goal: X parks within about ±.0001" of command on **diameter**, so the .0004" parts
band has room for tool and process variation, and a .0002 wear change actually
moves the part .0002. No new hardware. The wear-offset workflow stays exactly as
it is (owner decision 2026-11-10).

Branch: `claude/x-vernier`. Nothing on it changes the machine until the
`HALFILE` lines below are uncommented, and either step rolls back with one line.

## Why the loop parks where it does

- X closes on the scale: `encoder.01` → `pid.x` → `stepgen.01`, velocity mode.
- One scale count = .000197 radius = **.0004 dia**, the whole tolerance band.
- `DEADBAND = .0005` radius means the loop stops anywhere inside **±.0010 dia**.
  The owner saw this as "commanded 2.9505, DRO 2.9500–2.9510".
- Even with a deadband of zero, a scale-only loop can only stop *on* a count, a
  **.0004 dia grid**. Example for 2.9505: the nearest counts are 2.95039 and
  2.95079. A .0002 wear change either does nothing or jumps .0004. That's the
  tedious wear chase.
- The part matched the DRO closely. So the scale is truthful and the mechanics are fine:
  the problem is purely *where the loop stops*.

## How the vernier fixes it

The motor is 11× finer than the scale: .0000185 radius per step, and the closed-loop
drive holds each step. `rtcomp/xvernier.comp` estimates the true carriage
position **between** scale counts:

    pos_est = step_fb - b0 - screw(step_fb) + play

- **Scale edges are exact.** The instant the count ticks, the carriage is
  *exactly* on that edge, and `step_fb` at that instant is known to within one
  servo period of step travel: about .00002 radius at finish feeds. Each edge measures
  the step-to-scale offset `b0`.
- **screw()** is a slope plus a once-per-lead harmonic (periodic screw/step error),
  calibrated from a slow sweep and refined online.
- **play** is a backlash play operator (±H). The estimate never jumps, and a
  reversal is handled as the carriage really behaves.
- **Safety property:** the estimate is clamped to agree with the scale within
  half a count + 0.1 count. It can never be worse than the raw scale: if it is
  wrong, it degenerates to the scale. If a correction of more than `FAULT_LIMIT`
  has to be forced in one cycle (lost steps, scale glitch), `xvernier.fault`
  latches and, in closed mode, drops the machine out like a drive fault.

`pid.x` keeps its gains. It just closes on `xvernier.pos-est` instead of the raw
scale, with a deadband of .00001 (about 0.6 step) instead of .0005.

## Offline evidence (bench)

`tests/xvernier/` holds the evidence:
- `bench.c` simulates the X loop at 2 ms: LinuxCNC pid semantics, hm2 stepgen velocity mode, integer steps, drive lag, backlash, slope and periodic screw error, a quantized scale with noise and edge hysteresis, and thermal drift.
- It uses the **same estimator code** as the RT module: the `CORE-BEGIN..CORE-END` block is extracted verbatim, and a test enforces that.
- The calibration is **fitted** from a simulated sweep by the same `fit_calibration.py` used on the machine, not hand-set.

Worst parking error in DIAMETER inches, 30 random targets per cell (after warm-up roughing travel):

| plant | loop | feed up | feed down | rapid in | .0001 wear steps |
|---|---|---|---|---|---|
| nominal | today (db .0005) | .00089 | .00089 | .00113 | .00089 |
| nominal | Step 1 (db .00011) | .00020 | .00017 | .00035 | .00025 |
| nominal | **vernier, fitted** | **.00005** | **.00005** | **.00005** | **.00006** |
| loose (backlash .0008 total) | today | .00066 | .00069 | .00105 | .00069 |
| loose | Step 1 | .00028 | .00025 | .00028 | .00022 |
| loose | **vernier, fitted** | **.00006** | **.00005** | **.00005** | **.00006** |
| laggy drive (4 ms) | today | .00065 | .00063 | .00087 | .00089 |
| laggy | Step 1 | .00033 | .00032 | .00015 | .00029 |
| laggy | **vernier, fitted** | **.00007** | **.00009** | **.00013** | **.00009** |
| warming (thermal drift) | today | .00088 | .00091 | .00113 | .00087 |
| warming | Step 1 | .00019 | .00018 | .00037 | .00022 |
| warming | **vernier, fitted** | **.00008** | **.00008** | **.00008** | **.00010** |

- "today" reproduces the owner's experience (±.0005–.001 dia).
- Uncalibrated, the vernier is about ±.0002. **Calibration is the step that matters.**
- A simulated .001 slip latches the fault, and every other hold stays within .0001.

To run: `QT_QPA_PLATFORM=offscreen LD_LIBRARY_PATH=/home/jacob/miniforge3/lib /home/jacob/miniforge3/bin/python3 -m pytest tests/xvernier -q`
(12 tests, about 1 minute, gcc only: no HAL, no RT). The bench by hand: `tests/xvernier/build_bench.sh OUTDIR && OUTDIR/xv_bench nominal`.

## Files

| file | what |
|---|---|
| `rtcomp/xvernier.comp` | the RT component (singleton: pins `xvernier.*`, function `xvernier`) |
| `x-vernier-observe.hal` | shadow mode: loads it, `addf xvernier servo-thread 2` (right after hm2 read), feeds it, sets params from `[XVERNIER]` |
| `x-vernier-close.hal` | closed mode: `pid.x.feedback` and `joint.0.motor-pos-fb` ← `xvernier.pos-est`, `pid.x.deadband` ← `PID_DEADBAND`, `xvernier.fault` → `joint.0.amp-fault-in` |
| `industry-cam.ini` | `[XVERNIER]` section (zeros = uncalibrated), and two commented `HALFILE` lines in `[HAL]` |
| `scripts/xvernier/capture.sh` | servo-rate capture (standard `sampler` + `halsampler`) |
| `scripts/xvernier/fit_calibration.py` | sweep capture → `[XVERNIER]` values |
| `scripts/xvernier/analyze_holds.py` | positioning capture → parking error per hold |
| `scripts/xvernier/x_calibration_sweep.ngc` | air: slow X sweeps at 3 feeds + 10 reversals (~2 min) |
| `scripts/xvernier/x_positioning_test.ngc` | air: 12 targets × (feed up, feed down, rapid) with 3 s dwells (~3 min) |
| `scripts/xvernier/x_wear_staircase.ngc` | air: 10 × .0002 dia steps up and down, 5 s dwells, for an indicator |

`industry-cam.hal` is **not** modified. The add-on files only add to it.

## The tuning session (owner present). Roughly 1.5–2 hours

All test programs are **air cuts, X only, spindle off**. Set `#<xd>` at the top of
each program to a diameter with the stated clear travel above it, with Z positioned clear.
Run captures from a terminal in the config directory (`~/linuxcnc/configs/industry-cam`).

### 0. Before the session (desk work, any time)

1. Merge `claude/x-vernier` (owner OK). With the `HALFILE` lines commented, it
   changes nothing on the machine.
2. Install the component (needs your sudo, in your own terminal):
   `sudo halcompile --install rtcomp/xvernier.comp`
   Check: `ls /usr/lib/linuxcnc/modules/xvernier.so`.
   Repeat after any change to the `.comp`.

### 1. Shadow mode: does the estimate behave? (15 min)

1. `industry-cam.ini [HAL]`: uncomment `HALFILE = x-vernier-observe.hal` only.
2. Start LinuxCNC, Reset, On, home as usual. **Nothing about X behaviour changes.**
3. `halcmd show pin xvernier`. At rest, expect:
   - `residual` within ±0.6,
   - `fault` FALSE,
   - `samples` climbing while you jog X slowly (MPG ×1/×10).
4. If LinuxCNC fails to start, read the error.
   - A missing module means step 0.2 wasn't done.
   - Rollback: re-comment the line.

### 2. Baseline: today's loop, measured properly (10 min)

1. `scripts/xvernier/capture.sh 200 xv_baseline.txt`, then run `x_positioning_test.ngc`.
2. `python3 scripts/xvernier/analyze_holds.py xv_baseline.txt`
   - `est-cmd` is today's real parking error at sub-count resolution. Expect ±.0005–.001 dia, as on the bench.
   - Keep the output: it's the "before".
3. Optional: indicator (.0001) on the cross-slide, run `x_wear_staircase.ngc`, and note the readings. Expect lumps.

### 3. Calibration sweep (10 min)

1. `scripts/xvernier/capture.sh 150 xv_sweep.txt`, then run `x_calibration_sweep.ngc` (~2 min).
2. `python3 scripts/xvernier/fit_calibration.py xv_sweep.txt` (add `--plot xv_sweep.png` for a picture). Sanity checks:
   - Fit residual rms about .00004 dia is normal (the bench gets .000038). Over .0001 the script warns: something unmodelled is moving (gib, scale mount, vibration). Stop and look.
   - Backlash: owner expects small (tight adjustable acme nut). Total = 4 × H on diameter.
   - Screw harmonic: "lead … (= N motor steps)". A lead of one motor revolution or one screw turn makes sense. The fit drops the harmonic when it doesn't explain anything.
   - Drive lag: a few ms at most.
   - b0 drift across 5 chunks: a few tenths of a .0001 at most. Bigger means thermal growth or a loose scale.
3. Paste the printed `[XVERNIER]` lines into `industry-cam.ini`.
4. Optional consistency check: repeat with `#<xd>` in another region of travel. The values should agree.

### 4. Shadow with calibration: check the estimate against an indicator (15 min)

This is the key check **before** the estimate drives anything.

1. Restart LinuxCNC (still shadow), home.
2. Indicator on the cross-slide. Watch `xvernier.pos-est` (halmeter) and the indicator, while the DRO still shows the raw scale.
3. Jog X in single MPG clicks.
   - The scale moves in .0002 radius lumps.
   - `pos-est` should track the indicator to about .00005 radius at every click.
   - Do it both directions, and after a reversal.
4. Rerun step 2's capture + positioning test. `resid` must stay ≤ 0.6 and `samples` must climb. `est-cmd` is still today's error, since nothing is closed yet.

### 5. Close the loop, air (20 min)

1. Uncomment `HALFILE = x-vernier-close.hal` too (after observe). Restart, home.
2. Machine on, no motion, listen and watch for 30 s.
   - Expect: `pid.x.output` ≈ 0, stepgen counts still, no hum.
   - If it hunts: `PID_DEADBAND` .00001 → .00002.
3. Jog X slowly, then quickly. The DRO now shows `pos-est`: smooth, with finer than .0004 steps.
4. Capture + positioning test + analyze, the same as step 2.
   - **Pass: max |est-cmd| ≤ .0001 dia, resid ≤ 0.6, fault FALSE.**
   - Compare with the step 2 baseline.
5. Indicator + `x_wear_staircase.ngc`: **pass = .0001 on the indicator per step, every step, up and down.**
6. If `fault` trips during normal motion, read `xvernier.max-shift`, and set `FAULT_LIMIT` a bit above it (the fit's suggestion is `4·H + .0004`).

### 6. Cut (rest of the session)

1. Turn a test diameter with the normal finish pass. Measure.
2. Apply a normal wear correction (e.g. .0002 dia) and recut. **The part should move by the correction ± .0001.**
3. Repeat 2–3 times, including after a long roughing cycle (warm screw).
4. Then real parts.

### Rollback (any time)

- Re-comment `HALFILE = x-vernier-close.hal` → back to the old loop (still logging in shadow).
- Re-comment both → exactly the pre-vernier machine.
- The module file left in `/usr/lib/linuxcnc/modules` is inert when not loaded.

## Tuning knobs (`[XVERNIER]`)

| key | default | when to touch |
|---|---|---|
| `H_INIT`, `LEAD`, `HARM_COS`, `HARM_SIN`, `SLOPE`, `LAG_TIME` | 0 | from `fit_calibration.py` |
| `ALPHA` | 0.3 | b0 learning per edge. Lower (0.1) if `pos-est` looks noisy at rest |
| `ALPHA_H` | 0 | backlash frozen at `H_INIT`. Online learning is off because drive lag at reversals biased it on the bench |
| `ALPHA_HARM` | 0.02 | online refinement of the screw harmonic. 0 freezes it |
| `SPAN_MAX` | .0001 | edges are used only below ~3 in/min of X travel. Raise to .0002 if finish faces feed faster than that |
| `FAULT_LIMIT` | .0005 | keep above `4·H_INIT + .0004` |
| `PID_DEADBAND` | .00001 | .00002 if X hums at rest |

## What is not covered

- **Rapid straight onto a finish diameter with a loose nut:** ±.00015 on the bench. Finish passes in our programs feed in (comp entry → face → diameter), so this is the uncommon case.
- **Scale edge hysteresis** is indistinguishable from backlash and lands in `H_INIT`. Effect about .00001 dia.
- **Z** is not touched. The same component would work for Z, but Z's scale resolution isn't the limiting factor for these parts.
- **Fallback:** if the vernier can't be made to work, Step 1 (deadband .00011 on the raw scale) still gets ±.0002–.0004.
