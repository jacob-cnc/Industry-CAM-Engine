---
inclusion: auto
---

# 7i73 Operator Panel Integration

## Overview

The Mesa 7i73 pendant/control panel interface card connects to the existing 7i96s+7i85s system via the 7i85s's RS-422 serial port. It provides dedicated I/O for operator panel controls, eliminating GPIO conflicts with machine I/O on TB3.

## Hardware Topology

```
PC ──ethernet──→ 7i96s (FPGA, 192.168.1.121)
                    ├── TB1: Step/Dir (X stepper, Z stepper)
                    ├── TB2: Spindle encoder (1000 PPR)
                    ├── TB3: Machine GPIO (home, estop, jog buttons, cycle)
                    └── 25-pin ribbon ──→ 7i85s (daughter card)
                                            ├── TB1: Linear encoders (X, Z — 5µm)
                                            ├── TB2: X MPG handwheel
                                            ├── TB3: Z MPG handwheel
                                            └── RS-422 serial ──→ 7i73 (panel card)
                                                                    ├── IN0–IN15: Digital inputs
                                                                    ├── AIN0–AIN3: Analog inputs
                                                                    ├── OUT0–OUT9: Digital outputs
                                                                    └── ENC0–ENC3: Encoder inputs
```

## Physical Wiring: 7i85s → 7i73

The 7i85s has RS-422 serial screw terminals. The 7i73 has an RJ-45 jack. Connect with a CAT5 cable or 4-wire shielded:

```
7i85s TX+  →  7i73 RX+
7i85s TX-  →  7i73 RX-
7i85s RX+  →  7i73 TX+
7i85s RX-  →  7i73 TX-
+5V        →  7i73 VCC (or use separate 5V supply for long runs)
GND        →  7i73 GND
```

Max cable length: 100 feet (RS-422 spec). Use shielded cable for runs over 10 feet.

## Software Configuration

### HAL loadrt line change

```hal
# Before (7i85s only):
loadrt hm2_eth board_ip="192.168.1.121" config="num_encoders=5 num_stepgens=2 sserial_port_0=00000000"

# After (7i85s on channel 0, 7i73 on channel 1):
loadrt hm2_eth board_ip="192.168.1.121" config="num_encoders=5 num_stepgens=2 sserial_port_0=00xxxxxx"
```

The `sserial_port_0` string: position 0 = 7i85s (mode 0), position 1 = 7i73 (mode 0), positions 2–7 = disabled.

### 7i73 HAL Pin Names

After loading, pins appear as:
```
hm2_7i96s.0.7i73.0.1.input-00 through input-15   (digital inputs)
hm2_7i96s.0.7i73.0.1.analogin0 through analogin3 (analog inputs, 0.0–1.0 range)
hm2_7i96s.0.7i73.0.1.output-00 through output-09 (digital outputs)
```

The `.0.1.` means port 0, channel 1 (channel 0 is the 7i85s).

## Panel Controls — Pin Assignment

### Rotary Switches (1P6T, one-hot)

Two uxcell 1P6T rotary selector switches. Each has 1 common + 6 throw terminals. Common wired to +5V, each throw to a digital input (with pull-down).

**Jog Increment Knob → inputs 0–5:**

| Position | Input Pin | Value | Label |
|----------|-----------|-------|-------|
| 1 | input-00 | 0.0001" | .0001 |
| 2 | input-01 | 0.0005" | .0005 |
| 3 | input-02 | 0.001" | .001 |
| 4 | input-03 | 0.005" | .005 |
| 5 | input-04 | 0.010" | .010 |
| 6 | input-05 | 0.050" | .050 |

**Jog Speed Knob → inputs 6–11:**

| Position | Input Pin | Value | Label |
|----------|-----------|-------|-------|
| 1 | input-06 | 0.1 in/sec (6 IPM) | CREEP |
| 2 | input-07 | 0.25 in/sec (15 IPM) | SLOW |
| 3 | input-08 | 0.5 in/sec (30 IPM) | MED |
| 4 | input-09 | 1.0 in/sec (60 IPM) | FAST |
| 5 | input-10 | 1.5 in/sec (90 IPM) | RAPID |
| 6 | input-11 | 2.0 in/sec (120 IPM) | MAX |

**Spare digital inputs:** input-12 through input-15 (4 available for future buttons)

### Analog Pots

| Pot | Analog Pin | Range | Function |
|-----|-----------|-------|----------|
| Feed Override | analogin0 | 0–200% | Continuous feed rate adjustment during cuts |
| Spindle Override | analogin1 | 25–150% | Spindle speed override (informational for manual spindle) |
| Spare | analogin2 | — | Future: rapid override or jog velocity fine-tune |
| Spare | analogin3 | — | Future |

### Panel LEDs (digital outputs)

| Output Pin | Function | Color |
|-----------|----------|-------|
| output-00 | Machine ON | Green |
| output-01 | All Homed | Green |
| output-02 | Program Running | Blue |
| output-03 | E-Stop Active | Red |
| output-04 | Spindle On | Yellow |
| output-05 | Following Error Warning | Orange |
| output-06–09 | Spare | — |

## HAL Wiring (custom.hal additions)

```hal
# ============================================================================
# 7i73 Operator Panel — Jog Increment Rotary Switch (1P6T, one-hot)
# Uses select8 to decode one-hot inputs to a single float value
# ============================================================================

# Jog increment — weighted sum approach (simpler than mux for one-hot)
loadrt weighted_sum wsum_sizes=6
addf process_wsums servo-thread

setp wsum.0.offset 0.0
setp wsum.0.weight-0 0.0001
setp wsum.0.weight-1 0.0005
setp wsum.0.weight-2 0.001
setp wsum.0.weight-3 0.005
setp wsum.0.weight-4 0.010
setp wsum.0.weight-5 0.050

net inc-pos0 hm2_7i96s.0.7i73.0.1.input-00 => wsum.0.bit.0.in
net inc-pos1 hm2_7i96s.0.7i73.0.1.input-01 => wsum.0.bit.1.in
net inc-pos2 hm2_7i96s.0.7i73.0.1.input-02 => wsum.0.bit.2.in
net inc-pos3 hm2_7i96s.0.7i73.0.1.input-03 => wsum.0.bit.3.in
net inc-pos4 hm2_7i96s.0.7i73.0.1.input-04 => wsum.0.bit.4.in
net inc-pos5 hm2_7i96s.0.7i73.0.1.input-05 => wsum.0.bit.5.in

net mpg-jog-scale wsum.0.sum => joint.0.jog-scale joint.1.jog-scale
                              => axis.x.jog-scale axis.z.jog-scale

# ============================================================================
# 7i73 Operator Panel — Jog Speed Rotary Switch (1P6T, one-hot)
# ============================================================================

loadrt weighted_sum wsum_sizes=6,6
# (second instance is wsum.1)

setp wsum.1.offset 0.0
setp wsum.1.weight-0 0.1
setp wsum.1.weight-1 0.25
setp wsum.1.weight-2 0.5
setp wsum.1.weight-3 1.0
setp wsum.1.weight-4 1.5
setp wsum.1.weight-5 2.0

net spd-pos0 hm2_7i96s.0.7i73.0.1.input-06 => wsum.1.bit.0.in
net spd-pos1 hm2_7i96s.0.7i73.0.1.input-07 => wsum.1.bit.1.in
net spd-pos2 hm2_7i96s.0.7i73.0.1.input-08 => wsum.1.bit.2.in
net spd-pos3 hm2_7i96s.0.7i73.0.1.input-09 => wsum.1.bit.3.in
net spd-pos4 hm2_7i96s.0.7i73.0.1.input-10 => wsum.1.bit.4.in
net spd-pos5 hm2_7i96s.0.7i73.0.1.input-11 => wsum.1.bit.5.in

net jog-btn-speed wsum.1.sum => halui.axis.x.jog-speed halui.axis.z.jog-speed
                              => halui.joint.0.jog-speed halui.joint.1.jog-speed

# ============================================================================
# 7i73 Operator Panel — Feed Override Pot (analog)
# 7i73 analog reads 0.0–1.0, scale to 0.0–2.0 for 0–200%
# ============================================================================

net feed-ovr-raw hm2_7i96s.0.7i73.0.1.analogin0 => scale.feed-override.in
setp scale.feed-override.gain 2.0
setp scale.feed-override.offset 0.0
net feed-ovr-scaled scale.feed-override.out => halui.feed-override.direct-value
setp halui.feed-override.count-enable 1

# ============================================================================
# 7i73 Operator Panel — Spindle Override Pot (analog)
# Scale 0.0–1.0 → 0.25–1.5
# ============================================================================

net spindle-ovr-raw hm2_7i96s.0.7i73.0.1.analogin1 => scale.spindle-override.in
setp scale.spindle-override.gain 1.25
setp scale.spindle-override.offset 0.25
net spindle-ovr-scaled scale.spindle-override.out => halui.spindle.0.override.direct-value
setp halui.spindle.0.override.count-enable 1

# ============================================================================
# 7i73 Operator Panel — Status LEDs (active-high outputs)
# ============================================================================

net machine-is-on     halui.machine.is-on       => hm2_7i96s.0.7i73.0.1.output-00
net all-homed         halui.joint.0.is-homed    => hm2_7i96s.0.7i73.0.1.output-01
net program-running   halui.program.is-running  => hm2_7i96s.0.7i73.0.1.output-02
net estop-active      halui.estop.is-activated  => hm2_7i96s.0.7i73.0.1.output-03
```

## Design Decisions

### Why detented switches (not pots) for jog increment and speed
- Tactile feedback — operator knows position by feel without looking
- Repeatable — position 3 is always 0.001", no drift or dead spots
- Safe — can't accidentally bump to max speed
- Discrete choices match the use case (you only need ~6 jog speeds)

### Why pots for feed/spindle override
- Continuous adjustment needed (±5% tweaks while watching a cut)
- 6 detent positions too coarse for override (jumps of 25% are jarring)
- Pot gives smooth, proportional control

### Why NOT dual-purpose jog speed / feed override
- Mode-dependent behavior is dangerous (knob at max jog speed → start program → 200% feed override = crash)
- 6 discrete positions too coarse for feed override anyway
- No visual feedback on which mode is active with a physical switch
- Each knob should have ONE job

## GUI Integration

The GUI should:
1. **Display current knob positions** — read the weighted sum outputs and show "INC: 0.001" and "SPD: 60 IPM" in the status bar
2. **Display override percentages** — read the scaled analog values and show "F: 100%" and "S: 100%"
3. **Show in HAL Monitor** — add "Panel" preset to filter presets showing all 7i73 pins
4. **LED status in commissioning** — add a commissioning step to verify all panel LEDs

## Commissioning Steps (additions)

Add to the commissioning checklist:
- **Panel I/O Verify** — rotate each knob through all positions, confirm correct values in HAL Monitor
- **Override Pots** — sweep each pot, confirm 0–200% and 25–150% ranges
- **LED Test** — verify each output drives the correct LED

## Parts List

| Item | Qty | Notes |
|------|-----|-------|
| Mesa 7i73 | 1 | Already owned, on shelf |
| 1P6T rotary switch (uxcell) | 2 | Already purchased |
| 10kΩ linear pot | 2 | For feed and spindle override |
| CAT5 cable (shielded) | 1 | 7i85s → 7i73, length as needed |
| Panel-mount LEDs (5mm) | 6 | Green×2, Blue×1, Red×1, Yellow×1, Orange×1 |
| 10kΩ pull-down resistors | 12 | One per rotary switch terminal |
| Panel enclosure | 1 | Operator-side mounting |

## Future Expansion (using spare 7i73 capacity)

- inputs 12–15: Cycle pause button, tool change confirm, coolant toggle, spare
- analogin2: Rapid override pot (0–100%)
- analogin3: Jog velocity fine-tune pot (alternative to detented switch)
- encoder inputs: Relocate MPG handwheels to panel (if pendant-style build)
- outputs 05–09: Coolant indicator, tool number display driver, alarm buzzer
