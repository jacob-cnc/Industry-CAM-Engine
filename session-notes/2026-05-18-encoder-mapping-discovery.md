# Session Notes: 2026-05-18 — Encoder Mapping Discovery

## Status at end of session

**Partially working.** Machine reaches STATE_ON. X MPG moves X stepper. But encoder assignments in HAL are wrong — the spindle rotation drives Z axis motion, indicating encoder.01 (Z axis feedback) is actually reading the spindle encoder signals.

---

## What was fixed this session (continuing from commissioning session)

### 1. EMCIO = iov2 (ROOT CAUSE of ESTOP — SOLVED)
- Without `EMCIO = iov2`, LinuxCNC uses iocontrol v1, which never clears aux.estop via NML
- Found by comparing with reference config `7i96s_p1-7i85s_zx_testing.ini` on desktop
- Fix: added `EMCIO = iov2` to `[EMCIO]` section in `industry-cam.ini`
- Machine now reaches STATE_ON ✓

### 2. POSTGUI_HALFILE never loaded (SOLVED)
- `linuxcnc` shell script does NOT load POSTGUI_HALFILE — only the AXIS display does
- Our custom display (`display_gui.sh`) doesn't call `halcmd -f postgui.hal`
- Fix: moved all postgui.hal content directly into `industry-cam.hal`, removed `POSTGUI_HALFILE` from INI

### 3. GUI HAL monitor in offline mode (SOLVED — fix in this session)
- `display_gui.sh` puts project dir first in PYTHONPATH
- So `import hal` in `pin_providers.py` found project's `hal/` package instead of system LinuxCNC hal.so
- LivePinProvider failed to initialize → fell back to OfflinePinProvider (fake data)
- Fix: `pin_providers.py` now loads system hal via `importlib.util.spec_from_file_location("/usr/lib/python3/dist-packages/hal.py")`
- Will take effect on next GUI launch — **needs testing**

### 4. num_encoders reverted to 5
- Temporarily changed to 6 during testing; reverted back to 5
- num_encoders=5 covers all needed channels: encoder.00-04

---

## Critical Findings — Encoder Assignments Are Wrong

### Observation
- Turning the chuck by hand causes Z axis to move with correct directional sense
- encoder.03 rawcounts stay frozen when X MPG is turned, BUT X stepper does move

### What this means
The Z axis PID uses `encoder.01.position` as feedback. If Z moves when the spindle turns, then **encoder.01 is reading the spindle encoder signals**, not the Z linear scale.

### Hypothesis A — Hardware wiring swap
The spindle encoder cable and the Z linear encoder cable may be physically swapped:
- 7i85s TB1 (Z linear input slot) has the spindle encoder plugged in
- 7i96s TB2 (spindle encoder input) has the Z linear scale plugged in

Result: encoder.01 (HAL: Z linear) = spindle; encoder.02 (HAL: spindle) = Z linear scale movement

### Hypothesis B — HAL encoder numbering wrong
Mesa firmware assigns encoder.00 to the 7i96s onboard encoder (TB2 = spindle), not the 7i85s first channel. Our HAL assumed the opposite order.

Possible correct mapping if 7i96s spindle = encoder.00:
- encoder.00 = Spindle (7i96s TB2) ← we map this as X linear (WRONG)
- encoder.01 = 7i85s TB1 ch0 = X linear ← we map as Z linear (WRONG)
- encoder.02 = 7i85s TB1 ch1 = Z linear ← we map as Spindle (WRONG)
- encoder.03 = 7i85s TB2 = X MPG (may be correct)
- encoder.04 = 7i85s TB3 = Z MPG (may be correct)

### For X MPG: encoder.03 frozen despite X stepper moving
- The X stepper did respond to MPG turns — position changed ~0.004"/click
- But encoder.03 rawcounts never changed in halcmd
- Possible: X MPG is on a different encoder number than 03
- Possible: halcmd timing artifact (polled between updates)
- 0.004"/click is consistent with 4 counts/detent × 0.001"/count (100 PPR × 4-edge quadrature)

---

## Next Session: Encoder Identification Test

Run this with LinuxCNC in STATE_ON, in a second terminal.
Watch all 5 encoder rawcounts simultaneously while doing each physical action.

**Command (watch all encoders):**
```bash
watch -n 0.1 'for i in 00 01 02 03 04; do echo -n "enc.$i: "; halcmd show pin hm2_7i96s.0.encoder.$i.rawcounts 2>/dev/null | grep -o "[0-9-]*$"; done'
```

Or simpler:
```bash
halcmd show pin hm2_7i96s.0.encoder | grep rawcounts
```

**Physical actions to do one at a time:**
1. Turn chuck/spindle by hand (a few full rotations) — note which encoder(s) change
2. Turn X MPG handwheel 10 clicks CW then CCW — note which encoder(s) change and direction
3. Turn Z MPG handwheel 10 clicks CW then CCW — note which encoder(s) change
4. Physically push X axis by hand (with steppers on, the PID will resist — power off steppers or disable): note which encoder(s) track motion
5. Physically push Z axis by hand: same

From this matrix we get the ground truth encoder assignment.

---

## Correct MPG Scale (once direction confirmed)

With 100 PPR × 4-edge quadrature = 4 counts per detent click:
- Current: jog-scale = 0.001"/count → 0.004"/detent (matches observation)
- Correct: jog-scale = 0.00025"/count → 0.001"/detent

Update mux4 values in industry-cam.hal:
```hal
setp mux4.jogscale-x.in0 0.000025   # → 0.0001"/click
setp mux4.jogscale-x.in1 0.00025    # → 0.001"/click  ← default
setp mux4.jogscale-x.in2 0.0025     # → 0.010"/click
setp mux4.jogscale-x.in3 0.025      # → 0.100"/click
# same for jogscale-z
```

---

## Ongoing Issues

- **Encoder assignments wrong** — do identification test above before any further tuning
- **Z MPG unresponsive** — encoder.04 rawcounts stayed at 65535 (uninitialized), possible wrong channel
- **HAL monitor needs testing** — pin_providers.py fix in this session, not yet confirmed working
- **cpu-performance.service** — was enabled this session; verify it persists across reboots
- **Hardware E-stop** — gpio.004 connected; industry-cam-commissioning.hal has the correct `.in` net, not yet in industry-cam.hal
- **Home/limit switches** — not wired; HOME_SEARCH_VEL=0 (home-in-place)

---

## File State Summary

| File | Change |
|------|--------|
| `industry-cam.ini` | EMCIO=iov2, SERVO_PERIOD=2ms, TASK CYCLE_TIME=0.010 |
| `industry-cam.hal` | POSTGUI content merged in, num_encoders=5, iov2 estop loop, DPLL/watchdog |
| `industry-cam-commissioning.hal` | estop gpio: .in_not → .in |
| `postgui.hal` | Content moved to main HAL; file now stale/unused |
| `gui/commissioning/pin_providers.py` | Fix system hal import shadowed by project hal package |
| `hal/live_backend.py` | machine_is_on guard, state logging |
| `set-cpu-performance.sh` | New — RT tuning |
| `cpu-performance.service` | New — systemd unit, enabled |
