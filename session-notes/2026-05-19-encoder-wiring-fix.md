# Session Notes: 2026-05-19 — Encoder Wiring Map Correction

## Status at end of session

**IN PROGRESS — Wiring map identified, physical rewiring not yet done.**

Linear encoders (Z and X) confirmed not counting. Root cause found: incorrect signal pinout assumption on Sino KA300/KA500 DB9 connector. Rewiring needed before encoders will work.

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

## Next session: what to do first

1. **Rewire Z linear scale** (encoder.00, TB3 pins 1–8) per wiring map
2. **Rewire X linear scale** (encoder.01, TB3 pins 9–16) per wiring map
3. **Boot LinuxCNC**, go to STATE_ON
4. **Verify encoders counting:**
   ```bash
   watch -n 0.1 'halcmd show pin hm2_7i96s.0.encoder | grep rawcounts'
   ```
   Jog Z — encoder.00 should count. Jog X — encoder.01 should count.
5. **Verify Z position tracking:** jog Z 0.5", confirm `s.position[1]` matches physical movement
6. **Check MPG scale:** 10 MPG clicks should move 0.010" at default scale
7. **PID tuning** — once linear encoders confirmed working

---

## Outstanding issues

- X MPG (encoder.03) not yet confirmed — Z MPG confirmed encoder.02
- PID tuning not started (P=500, FF1=1.0 initial values)
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
