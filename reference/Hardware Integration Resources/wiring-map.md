# My-Lathe Wiring Map
## Mesa 7i96S + 7i85S — CQ6133 Lathe

> **Firmware**: `7i96s_7i85sd.bin`
> **Units**: inches | **Power**: 48V steppers, 24V control, 5V logic

---

## Mesa 7i96S

### TB1 — Step/Dir Outputs

| Function | Pin | Wire Color | Signal |
|----------|-----|------------|--------|
| **Z Stepper (Step/Dir 0)** | P1 | Black (0V) | Stepper GND / 24V- bus |
| | P2 | Yellow | PULSE (step) |
| | P3 | — | 24V+ bus |
| | P4 | Orange (Gray) | DIR (direction) |
| | P6 | — | 5V+ bus |
| **X Stepper (Step/Dir 1)** | P1 | Black (0V) | Stepper GND / 24V- bus |
| | P2 | Yellow | PULSE (step) |
| | P3 | — | 24V+ bus |
| | P4 | Orange (Gray) | DIR (direction) |
| | P6 | — | 5V+ bus |

### TB2 — Spindle Encoder (7i96S onboard encoder, encoder.02)

| Pin | Wire Color | Signal |
|-----|------------|--------|
| P1 | Green | A (channel A) |
| P3 | Black | GND |
| P4 | White | B (channel B) |
| P6 | Red | +5V (Vcc) |
| P7 | Yellow | Z (index) |

### TB3 — Isolated Inputs (gpio.000–gpio.010, active with 24V)

| Pin | GPIO | Function | Wire Color | Signal |
|-----|------|----------|------------|--------|
| P1 | gpio.000 | Limit-/Home Z | Blue | NC switch, 24V+ on Black |
| P2 | gpio.001 | Limit Z+ | Blue | NC switch, 24V+ on Black |
| P3 | gpio.002 | Limit X- | Blue | NC switch, 24V+ on Black |
| P4 | gpio.003 | Limit X+/Home X | Blue | NC switch, 24V+ on Black |
| P5 | gpio.004 | E-Stop | Blue | NC switch, 24V+ on Green |
| P6 | gpio.005 | Jog Z- | Yellow | NO momentary, 24V+ on Green |
| P7 | gpio.006 | Jog Z+ | Yellow | NO momentary, 24V+ on Green |
| P8 | gpio.007 | Jog X- | Yellow | NO momentary, 24V+ on Green |
| P9 | gpio.008 | Jog X+ | Yellow | NO momentary, 24V+ on Green |
| P10 | gpio.009 | Cycle Start | Yellow | NO momentary, 24V+ on Green |
| P11 | gpio.010 | Cycle Stop | Yellow | NO momentary, 24V+ on Green |
| P12 | — | 24V- Bus | — | Input common |

> **All 11 TB3 inputs are used.** Additional inputs (Cycle Pause, rotary
> switches) use 7i85S GPIO — see below.

---

## Mesa 7i85S (connected via ribbon cable from 7i96S)

### TB1 — Linear Encoders (encoder.00 = X, encoder.01 = Z)

The 7i85S TB1 has two encoder channels. Each uses the standard Mesa
7-pin encoder pinout. The Sino KA300/KA500 scales are TTL 5V
single-ended with DB9 connectors.

**X Linear Encoder — encoder.00 (Sino KA300/KA500)**

| TB1 Pin | Function | DB9 Pin | Wire Color | Notes |
|---------|----------|---------|------------|-------|
| P1 | A (ENC0-A) | Pin 6 | — | Channel A |
| P2 | /A (ENC0-A/) | — | — | Not connected (single-ended) |
| P3 | GND | Pin 2 | — | Signal ground |
| P4 | B (ENC0-B) | Pin 8 | — | Channel B |
| P5 | /B (ENC0-B/) | — | — | Not connected (single-ended) |
| P6 | +5V | Pin 7 | — | Encoder power |
| P7 | IDX (ENC0-Z) | Pin 9 | — | Index pulse |

**Z Linear Encoder — encoder.01 (Sino KA300/KA500)**

| TB1 Pin | Function | DB9 Pin | Wire Color | Notes |
|---------|----------|---------|------------|-------|
| P8 | A (ENC1-A) | Pin 6 | — | Channel A |
| P9 | /A (ENC1-A/) | — | — | Not connected (single-ended) |
| P10 | GND | Pin 2 | — | Signal ground |
| P11 | B (ENC1-B) | Pin 8 | — | Channel B |
| P12 | /B (ENC1-B/) | — | — | Not connected (single-ended) |
| P13 | +5V | Pin 7 | — | Encoder power |
| P14 | IDX (ENC1-Z) | Pin 9 | — | Index pulse |

> **Sino KA300/KA500 DB9 pinout**: Pin 2 = GND, Pin 6 = A, Pin 7 = +5V,
> Pin 8 = B, Pin 9 = Z (index). Pins 1, 3, 4, 5 are not connected.
>
> **Jumper setting**: Set 7i85S TB1 encoder mode jumpers to **TTL**
> (single-ended) — not RS-422 differential.

### TB2 — X MPG Handwheel (encoder.03)

| Pin | Wire Color | Signal |
|-----|------------|--------|
| P1 | Blue (A) | Channel A |
| P3 | Black (0V) | GND |
| P4 | White (B) | Channel B |
| P6 | Yellow (Vcc) | +5V |

### TB3 — Z MPG Handwheel (encoder.04)

| Pin | Wire Color | Signal |
|-----|------------|--------|
| P1 | Green (A) | Channel A |
| P3 | Black (0V) | GND |
| P4 | White (B) | Channel B |
| P6 | Red (Vcc) | +5V |

### 7i85S GPIO — Additional Inputs

The 7i85S with the `7i96s_7i85sd.bin` firmware exposes additional GPIO
pins beyond the encoder channels. These are accent on the differential
output pins (directly accessible on the 7i85S connector) and can be
configured as inputs in HAL.

**Cycle Pause Button**

| 7i85S GPIO | Function | Wiring |
|------------|----------|--------|
| gpio.011 | Cycle Pause | NO momentary, 24V sourcing (same scheme as jog buttons) |

> Wire: Green to 24V+, Yellow to 7i85S GPIO input pin, Black to 24V-.
> Red jumpered to Yellow (same as other pushbuttons).

**Jog Scale Rotary Switch (2-bit BCD for mux4 selector)**

A 4-position detented rotary switch selects MPG jog increment:
- Position 0: x1 (0.0001")
- Position 1: x10 (0.001")
- Position 2: x100 (0.01")
- Position 3: x1000 (0.1")

Two GPIO inputs encode the 4 positions in binary:

| 7i85S GPIO | Function | Rotary Switch | Wiring |
|------------|----------|---------------|--------|
| gpio.012 | Jog Scale Sel0 (bit 0) | Common → 24V+, position taps to GPIO | 24V sourcing |
| gpio.013 | Jog Scale Sel1 (bit 1) | Common → 24V+, position taps to GPIO | 24V sourcing |

| Switch Position | Sel1 | Sel0 | mux4 Output | Increment |
|-----------------|------|------|-------------|-----------|
| 0 | OFF | OFF | in0 | 0.0001" |
| 1 | OFF | ON | in1 | 0.001" |
| 2 | ON | OFF | in2 | 0.01" |
| 3 | ON | ON | in3 | 0.1" |

> **Note**: The exact 7i85S GPIO pin numbers (011, 012, 013) depend on
> the firmware bitfile. Run `halcmd show pin | grep gpio` after loading
> to confirm available GPIO numbers. The HAL file has placeholder
> comments for these connections — uncomment and adjust pin numbers
> when wired.

---

## Stepper Wiring (UIRobot UIM8696PM — both axes identical)

| Wire Color | Connection | Signal |
|------------|------------|--------|
| Red | 48V PSU + | Motor power + |
| Black | 48V PSU - | Motor power - |
| Blue | 24V+ bus | Enable power |
| Brown | 24V- bus | Enable common (COM) |
| Yellow | TB1 P2 (7i96S) | PULSE (step) |
| Gray (Orange) | TB1 P4 (7i96S) | DIR (direction) |
| Black | TB1 P1 (7i96S) | Signal GND |

> Connected via 5-pin aviation connectors between motor and panel harness.

---

## Pushbutton Wiring (all identical scheme)

All pushbuttons use NO (normally open) momentary switches with 24V
sourcing to 7i96S TB3 isolated inputs.

| Wire Color | Connection | Signal |
|------------|------------|--------|
| Green | 24V+ bus | Power source |
| Black | 24V- bus | Power return |
| Yellow | TB3 pin (7i96S) | Signal to GPIO input |
| Red | Jumper to Yellow | Parallel connection |

Applies to: Jog Z-, Jog Z+, Jog X-, Jog X+, Cycle Start, Cycle Stop,
Cycle Pause (on 7i85S GPIO).

---

## Limit Switch Wiring (all identical scheme)

All limit switches use NC (normally closed) contacts with 24V sourcing.
Wire break or switch open = fault detected (fail-safe).

| Wire Color | Connection | Signal |
|------------|------------|--------|
| Black | 24V+ bus | Power source |
| Blue | TB3 pin (7i96S) | Signal to GPIO input |

Applies to: Limit-/Home Z (P1), Limit Z+ (P2), Limit X- (P3),
Limit X+/Home X (P4).

---

## E-Stop Wiring

NC (normally closed) contact. Opens on press = machine stops.

| Wire Color | Connection | Signal |
|------------|------------|--------|
| Green | 24V+ bus | Power source |
| Blue | TB3 P5 (7i96S) | Signal to gpio.004 |

---

## Power Distribution

### 5V Bus (Mean Well RS-25-5)

| Terminal | Connection |
|----------|------------|
| L | AC 110V Black |
| N | AC 110V White |
| + | 5V Bus + → 7i96S PWR In +, TB1 P6 (Z Step), TB1 P6 (X Step) |
| - | Shared Ground → 5V Bus - |

### 24V Bus (Mean Well LRS-150-24)

| Terminal | Connection |
|----------|------------|
| L | AC 110V Black |
| N | AC 110V White |
| + | 24V Bus + → Stepper Blue (ENA), TB1 P3, limit switches, jog buttons, cycle buttons, E-stop |
| - | Shared Ground → 24V Bus - → TB3 P12, stepper Brown (COM), button returns |

### 48V Bus (Mean Well LRS-600-48)

| Terminal | Connection |
|----------|------------|
| L | AC 110V Black |
| N | AC 110V White |
| + | Z Stepper Red, X Stepper Red |
| - | Shared Ground → Z Stepper Black, X Stepper Black |

### AC 110V Distribution

| Wire Color | Connection |
|------------|------------|
| Black (L) | 5V PSU L, 24V PSU L, 48V PSU L |
| White (N) | 5V PSU N, 24V PSU N, 48V PSU N |
| Green (GND) | Shared Ground → chassis, 5V PSU -, 24V PSU -, 48V PSU - |

### Shared Ground

All PSU negative terminals and chassis ground are bonded together:
- Chassis
- AC Green (earth)
- 5V PSU -
- 24V PSU -
- 48V PSU -

---

## Encoder Channel Summary

| Encoder # | Board | Connector | Function | Type |
|-----------|-------|-----------|----------|------|
| encoder.00 | 7i85S | TB1 (pins 1-7) | X Linear Scale (Sino KA300/KA500) | TTL 5V, 5µm |
| encoder.01 | 7i85S | TB1 (pins 8-14) | Z Linear Scale (Sino KA300/KA500) | TTL 5V, 5µm |
| encoder.02 | 7i96S | TB2 | Spindle Encoder (~1000 PPR) | TTL 5V, A/B/Z |
| encoder.03 | 7i85S | TB2 | X MPG Handwheel (100 PPR) | Differential |
| encoder.04 | 7i85S | TB3 | Z MPG Handwheel (100 PPR) | Differential |

---

## Planned / Not Yet Wired

| Item | Status | Notes |
|------|--------|-------|
| X Linear Encoder (encoder.00) | **Wiring defined above** — not yet physically connected | Sino KA300/KA500 → 7i85S TB1 pins 1-7 |
| Z Linear Encoder (encoder.01) | **Wiring defined above** — not yet physically connected | Sino KA300/KA500 → 7i85S TB1 pins 8-14 |
| Spindle Encoder | **Wired** on 7i96S TB2 | ~1000 PPR, confirm exact model |
| Cycle Pause button | **Wiring defined above** — not yet physically connected | 7i85S GPIO (gpio.011 placeholder) |
| Jog Scale Rotary Switch | **Wiring defined above** — not yet physically connected | 2-bit BCD → 7i85S GPIO (gpio.012, gpio.013 placeholders) |
| Analog Pots (feed/spindle/jog) | Planned | 7i96S analogin0/1/2 — wiring TBD |
