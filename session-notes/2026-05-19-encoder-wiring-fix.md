# Session Notes: 2026-05-19 — Encoder Wiring Map Correction

## Status at end of session

**IN PROGRESS — MPGs and linear encoders all confirmed working. Next: PID tuning / following error.**

Linear encoders rewired with correct Sino DB9 pinout and confirmed counting. Both MPGs confirmed driving axes in the correct direction after wiring fixes. X linear encoder direction inverted in INI (ENCODER_SCALE = -5080). Now dialing in following error and PID tuning.

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

### 9. Z MPG direction confirmed correct
- Z MPG (encoder.02) confirmed counting correctly and driving Z in correct direction ✓
- Z linear encoder (encoder.00) has correct direction (ENCODER_SCALE = +5080, no change needed)

---

## Next session: what to do first

1. **Restart LinuxCNC** for clean state (INI change takes effect)
2. **Reconnect Z leadscrew** (was disconnected for testing)
3. **Verify MPG jog scale:** 10 clicks should move 0.010" at default selector position
4. **Dial in following error:** reduce FERROR once motion is stable, start PID tuning
   - Current: P=500, FF1=1.0, FERROR=0.050" (loose for initial testing)
   - Tune FF1 first (should be close to 1.0 for velocity-mode steppers), then P
5. **Verify Z position tracking** with Z connected to leadscrew
6. **Home/limit switches** — not yet wired

---

## Outstanding issues

- PID tuning not started (P=500, FF1=1.0 initial values — following error being resolved)
- Home/limit switches not wired
- Hardware E-stop (gpio.004) connected but not yet in HAL estop net

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
