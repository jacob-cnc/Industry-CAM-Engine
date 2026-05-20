# Session Notes: 2026-05-19 — Encoder Wiring Map Correction

## Status at end of session

**CLOSED — Both MPGs and both linear encoders confirmed working in correct directions. Next session: reconnect Z leadscrew and begin PID tuning.**

All encoders counting. Both MPGs driving correct directions (CW = X- toward centerline, CW = Z+ toward tailstock). X linear encoder direction inverted in INI. Both MPG jog-scales negated in HAL. Machine is ready for closed-loop motion testing with Z leadscrew reconnected.

---

## What was found this session

### 1. cpu-performance.service (VERIFIED)
- `systemctl is-enabled` = enabled, `is-active` = active, governor = performance
- Persists across reboots. This item is closed.

### 2. Encoder enumeration confirmed correct (halcmd live test)
- Turned spindle by hand → encoder.04 moved. Spindle = encoder.04 ✓
- encoder.02 briefly ticked when Z MPG turned. Z MPG = encoder.02 ✓
- HAL mapping is correct — no HAL changes needed for encoder numbering.

### 3. Linear encoders not counting (encoder.00, encoder.01 stuck at 0)
- `input-a = FALSE, input-b = FALSE` on both channels — no signal reaching FPGA
- Z axis jogged 0.5" physically, LinuxCNC reported Z = 0.0 — confirmed dead feedback
- 7i85s SSERIAL link is alive (encoder.02 responded); issue is specific to linear scale wiring
- Jumpers on 7i85s verified ALL UP = TTL single-ended mode ✓
- Power (5V from 7i85s) confirmed sufficient — 80mA per scale, 640mA available

### 4. Root cause: wrong Sino DB9 pinout assumption
The initial wiring assumed the common DRO pinout (A=pin1, B=pin3, Z=pin5).
The actual Sino KA300/KA500 TTL pinout (from official manual) is:
- Pin 2 = GND
- Pin 6 = A
- Pin 7 = +5V
- Pin 8 = B
- Pin 9 = Z

Pins 6, 8, 9 were wired to wrong Mesa terminals. +5V (pin7/Blue) and GND (pin2/Brown) were correct — scales had power but no signal.

### 5. MPG jog scale corrected (HAL change committed)
- Previous: mux4 in0–in3 = 0.0001, 0.001, 0.01, 0.1 (4× too large)
- Corrected: 0.000025, 0.00025, 0.0025, 0.025 → 0.001"/click at default index

---

## Correct Sino → DB9 → Mesa wiring

See `reference/SINO WIRING MAP.csv` for full table.

Store-bought DB9 cable wire colors (straight-through, resistor color code):
Black=pin1, Brown=pin2, Red=pin3, Orange=pin4, Yellow=pin5,
Green=pin6, Blue=pin7, Gray=pin8, White=pin9

| Sino pin | Signal | DB9 pin | Wire color | 7i85s TB3 enc 0 pin | 7i85s enc 1 pin |
|---|---|---|---|---|---|
| 2 | GND | 2 | Brown | 3 | 11 |
| 6 | A | 6 | Green | 1 (QA+) | 9 (QA+) |
| 7 | +5V | 7 | Blue | 6 | 14 |
| 8 | B | 8 | Gray | 4 (QB+) | 12 (QB+) |
| 9 | Z | 9 | White | 7 (IDX+) | 15 (IDX+) |
| — | NC | — | Black, Red, Orange, Yellow | — | — |
| — | NC | — | — | 2, 5, 8 | 10, 13, 16 |

---

## Session continuation — MPG and encoder direction fixes (2026-05-19)

### 6. Linear encoders confirmed working after rewiring
- encoder.00 (Z linear): pushed Z carriage → 6991 counts. WORKING ✓
- encoder.01 (X linear): pushed X carriage → 112 counts. WORKING ✓
- encoder.04 (Spindle): confirmed from earlier test ✓

### 7. X MPG A/B swap fixed (pins 1 & 4 at 7i85s TB2 enc3)
- Symptom: X MPG caused axis to jiggle back and forth, encoder.03 netted 0 counts per click
- Root cause: A and B signals swapped at Mesa TB2 enc3 terminals — each quadrature edge
  alternated direction, net count = 0 per detent → rapid position command reversals
- Fix: swapped green (QA+, pin 1) and gray (QB+, pin 4) wires at 7i85s TB2 enc3
- Result: encoder.03 counts consistently (−4 per click), jiggling stopped ✓

### 8. X linear encoder direction inverted
- Symptom: with X connected to leadscrew and X MPG turned, axis jiggled even after A/B fix
- Root cause: encoder.01 was counting in the wrong direction — PID feedback opposed command
- Fix: set ENCODER_SCALE = −5080 in [JOINT_0] (industry-cam.ini:98)
  Applied at runtime first (`halcmd setp hm2_7i96s.0.encoder.01.scale -5080`), confirmed fix,
  then made permanent in INI
- Result: jiggling gone. Now shows following error = next item to address ✓

### 9. MPG direction convention established and fixed

Both MPGs had jog-scale signs wrong for the machine coordinate convention:
- X MPG CW was moving X+ (away from centerline) — should be X- (toward centerline)
- Z MPG CW was moving Z- (toward headstock) — should be Z+ (toward tailstock)

Fix: negated all mux4.jogscale-x and mux4.jogscale-z values in HAL (all four in0–in3
values flipped to negative). This is the correct approach — the encoder.01 ENCODER_SCALE
stays at -5080 (necessary for loop stability; see lesson below). The MPG direction is
independently controlled by the jog-scale sign.

### 10. X linear encoder direction — ENCODER_SCALE = -5080

The X linear encoder (encoder.01) rawcounts decrease when the carriage moves away from
centerline. With ENCODER_SCALE = +5080, position increases as the carriage moves away
(X+ = away, correct machine convention), but this makes feedback move in the wrong direction
relative to the stepgen, causing PID divergence (jiggling).

With ENCODER_SCALE = -5080, position decreases as carriage moves away from centerline
(X- = away, inverted convention) — but the feedback correctly opposes the stepgen command,
making the loop stable. The MPG jog-scale being negative compensates for this at the
command level: CW MPG → negative count delta × negative jog-scale → positive position
command toward centerline (X- in machine convention matches).

**Key lesson: In velocity-mode closed loop, encoder scale sign must make feedback track
the stepgen direction. Machine coordinate convention is secondary — establish loop
stability first, then handle direction via jog-scale sign if needed.**

### 11. Z MPG and Z encoder direction — no change needed

Z MPG (encoder.02): jog-scale negated, now CW = Z+ (toward tailstock) ✓
Z linear encoder (encoder.00): ENCODER_SCALE = +5080, direction correct, no change ✓

---

## Lessons learned this session

### Lesson A: Sino KA-type linear encoder DB9 pinout is NOT the standard DRO pinout
Common DRO pinout assumes A=pin1, B=pin3, Z=pin5. Sino TTL pinout:
- Pin 2 = GND, Pin 6 = A, Pin 7 = +5V, Pin 8 = B, Pin 9 = Z
Using wrong pinout gives power to the scales (so no continuity alarm) but zero signal.
Always confirm pinout from the manufacturer manual before wiring.

### Lesson B: MPG A/B swap produces net-zero counts, not reversed direction
When A and B are swapped at the Mesa terminal, the FPGA quadrature decoder sees the
phase sequence reversed. Each detent that should give +4 counts instead gives alternating
+1/-1 edges → net 0 counts per click. The symptom is axis jiggling (rapid zero-amplitude
oscillation of the position command), not reversed motion. Fix: swap the two signal wires
at the terminal block.

### Lesson C: Testing with leadscrew disconnected masks encoder feedback issues
With Z leadscrew disconnected, the carriage doesn't move when the stepper runs. The
linear encoder (which reads carriage position) stays at 0. The PID sees a permanent error
and drives the stepper continuously — this looks like "sustained motion" but is actually
correct PID behavior with no physical feedback. Always reconnect the leadscrew before
interpreting closed-loop motion behavior.

### Lesson D: Encoder SCALE sign and MPG jog-scale sign are independent
- ENCODER_SCALE sign controls closed-loop stability (must match stepgen mechanical direction)
- MPG jog-scale sign controls MPG direction convention (can be negated freely)
- Changing ENCODER_SCALE to fix MPG direction breaks the closed loop. Fix MPG direction
  by negating jog-scale values only. Encoder scale must remain whatever makes the loop stable.

### Lesson E: Changing encoder scale at runtime flips the feedback sign mid-run
Using `halcmd setp encoder.N.scale` while LinuxCNC is running immediately flips the
feedback sign. If there is any non-zero error at that moment, the PID sees a sign-flipped
error and may trigger FERROR. Always test runtime scale changes with the axis at rest and
command = 0, or restart LinuxCNC for a clean state.

---

## Next session: what to do first

1. **Reconnect Z leadscrew** (was disconnected for testing this session)
2. **Boot LinuxCNC**, go to STATE_ON
3. **Verify MPG scale:** 10 clicks on either MPG should move 0.010" (index 1 = 0.001"/click)
4. **Test closed-loop motion on both axes** — jog with MPG, watch DRO, confirm position
   tracks and stops cleanly
5. **Begin PID tuning** — reduce FERROR incrementally:
   - Start: FERROR=0.050" (current, loose)
   - Tune FF1 first: at constant velocity, check if following error is near zero
     (FF1=1.0 should be close for velocity-mode steppers with matched STEP_SCALE)
   - Reduce FERROR once motion is stable
   - Then adjust P as needed for position accuracy at rest
6. **Verify Z direction:** Z MPG CW should increase DRO (toward tailstock = Z+)
7. **Home/limit switches** — still not wired

---

## Outstanding issues

- PID tuning not started — P=500, FF1=1.0, FERROR=0.050" (intentionally loose)
- Following error: expected once leadscrew reconnected and clean LinuxCNC restart done
- Home/limit switches not wired
- Hardware E-stop (gpio.004) connected but not yet in HAL estop net
- X MPG direction fix required negating ENCODER_SCALE (−5080) AND jog-scale (negative);
  future wiring revision could normalise encoder direction so ENCODER_SCALE = +5080

## GUI Setup section — known bugs (deferred, do not fix yet)

Reviewed all ~3000 lines of gui/commissioning/. What works: commissioning
checklist, HAL monitor pin tree/filter/watch, tuning Load/Save/Apply Live,
following error graph, offline mode. Bugs found:

1. CRITICAL — tuning_tab.py:56-76 TUNING_PINS has wrong encoder numbers.
   X encoder_pos reads encoder.00 (Z linear), Z reads encoder.01 (X linear),
   spindle velocity reads encoder.02 (Z MPG). Tuning tab shows swapped axes.
2. MEDIUM — commissioning_tab.py steps 5 and 8 description text references
   wrong encoder numbers (same flip + spindle on .02 instead of .04).
3. MEDIUM — LivePinProvider.get_signal_pins() always returns [] (TODO stub).
   Signal tracing shows signal name but not connected pins in live mode.
4. LOW — CommissioningTab.set_state_file() never called from SetupTab.
   Checklist saves to fallback path inside gui/commissioning/ not config dir.
5. LOW — _apply_live() only validates X P Gain; other fields go to HAL
   without format checking.

Estimate to fix all five: ~65 min. Fix #1 alone: 5 min.
