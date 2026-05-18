# Hardware Integration Resources

## Agent Prompt: Understand My-Lathe Hardware & Wiring

**Goal:** Build a complete understanding of the hardware configuration, wiring map, HAL signal routing, and INI machine parameters for this 2-axis CNC lathe running LinuxCNC with Mesa 7i96S + 7i85S motion control.

**Read these files in order:**

1. **`wiring-map.md`** — Complete physical wiring map covering:
   - Mesa 7i96S: TB1 (step/dir for X & Z steppers), TB2 (spindle encoder), TB3 (11 isolated inputs: limits, home, e-stop, jog buttons, cycle start/stop)
   - Mesa 7i85S: TB1 (X & Z linear encoders), TB2 (X MPG handwheel), TB3 (Z MPG handwheel), GPIO (cycle pause, jog scale rotary switch)
   - Stepper wiring (UIRobot UIM8696PM closed-loop, 48V)
   - Power distribution (5V, 24V, 48V buses)
   - Encoder channel assignments (encoder.00–04)
   - Planned/not-yet-wired items (linear scales, cycle pause, jog scale rotary, analog pots)

2. **`my-lathe.ini`** — Machine configuration (axis limits, velocities, stepper tuning, encoder scales, homing sequences, display settings)

3. **`my-lathe.hal`** — Primary HAL file (signal routing between Mesa hardware pins, motion controller, and I/O)

4. **`postgui.hal`** — Post-GUI HAL connections (signals wired after the GUI loads, typically MPG/jog/DRO connections)

5. **`custom.hal`** — Custom HAL additions (any extra logic, mux components, or overrides)

6. **`tool.tbl`** — Tool table (tool offsets, descriptions)

7. **`commissioning-wcs-tool-offsets.txt`** — Commissioning guide for WCS setup and tool touch-off procedures

8. **`tool_limits.json`** — Per-tool safety limits (Z-minus boundaries)

---

## Key Hardware Facts

- **Machine**: CQ6133 2-axis lathe (X and Z only), units in inches
- **Motion Control**: Mesa 7i96S + 7i85S, firmware `7i96s_7i85sd.bin`
- **Steppers**: UIRobot UIM8696PM closed-loop integrated steppers, 48V power
- **Linear Encoders**: Sino KA300/KA500, 5µm resolution, TTL — scales defined but **not yet physically connected**
- **Spindle**: Manual (no VFD), rotary encoder on spindle (~1000 PPR) for threading/CSS
- **MPG**: 2x handwheels (100 PPR each) — X on 7i85S TB2, Z on 7i85S TB3
- **Jog Buttons**: 4 directional (Z-, Z+, X-, X+) on 7i96S TB3
- **Home Switches**: 1 per axis (X on TB3 P4/gpio.003, Z on TB3 P1/gpio.000)
- **Limits**: Software limits only — no physical limit switches (linear scales will provide position)
- **Free Pins**: TB3 P2 (gpio.001) and P3 (gpio.002) are unused
- **Tool Post**: Quick change tool post, manual tool change

---

## What to Extract

- Full signal flow from physical pins → HAL pins → motion controller
- Current vs. planned hardware (what's wired vs. what's defined but not connected)
- Any discrepancies between the wiring map and the HAL/INI configuration
- Encoder scaling and feedback loop configuration
- Homing strategy and limit handling
- MPG/jog wiring and mux logic
- Compound slide virtual jog routing (postgui.hal)

---

## Encoder Channel Map

| Encoder # | Board | Connector | Function | Type |
|-----------|-------|-----------|----------|------|
| encoder.00 | 7i85S | TB1 (pins 1-7) | X Linear Scale (Sino KA300/KA500) | TTL 5V, 5µm |
| encoder.01 | 7i85S | TB1 (pins 8-14) | Z Linear Scale (Sino KA300/KA500) | TTL 5V, 5µm |
| encoder.02 | 7i96S | TB2 | Spindle Encoder (~1000 PPR) | TTL 5V, A/B/Z |
| encoder.03 | 7i85S | TB2 | X MPG Handwheel (100 PPR) | Differential |
| encoder.04 | 7i85S | TB3 | Z MPG Handwheel (100 PPR) | Differential |

---

## Signal Flow Summary

```
                    ┌─────────────────────────────────────────────┐
                    │              LinuxCNC Motion                 │
                    │  joint.0 (X)              joint.1 (Z)       │
                    └──────┬──────────────────────────┬───────────┘
                           │                          │
                    ┌──────▼──────┐            ┌──────▼──────┐
                    │   pid.x     │            │   pid.z     │
                    │ cmd←joint   │            │ cmd←joint   │
                    │ fb←enc.00   │            │ fb←enc.01   │
                    └──────┬──────┘            └──────┬──────┘
                           │                          │
                    ┌──────▼──────┐            ┌──────▼──────┐
                    │ stepgen.01  │            │ stepgen.00  │
                    │ (TB1 S/D 1) │            │ (TB1 S/D 0) │
                    └──────┬──────┘            └──────┬──────┘
                           │                          │
                    ┌──────▼──────┐            ┌──────▼──────┐
                    │ X Stepper   │            │ Z Stepper   │
                    │ UIM8696PM   │            │ UIM8696PM   │
                    └─────────────┘            └─────────────┘
```

Note: stepgen.00 = Z (TB1 slot 0), stepgen.01 = X (TB1 slot 1). This is a
common source of confusion — the physical wiring order doesn't match the
joint numbering.

---

## Planned / Not Yet Wired

| Item | Status | Notes |
|------|--------|-------|
| X Linear Encoder (encoder.00) | Wiring defined — not physically connected | Sino KA300/KA500 → 7i85S TB1 pins 1-7 |
| Z Linear Encoder (encoder.01) | Wiring defined — not physically connected | Sino KA300/KA500 → 7i85S TB1 pins 8-14 |
| Cycle Pause button | Wiring defined — not physically connected | 7i85S GPIO (gpio.011 placeholder) |
| Jog Scale Rotary Switch | Wiring defined — not physically connected | 2-bit BCD → 7i85S GPIO (gpio.012, gpio.013) |
| Analog Pots (feed/spindle/jog) | Planned | 7i96S analogin0/1/2 — wiring TBD |
