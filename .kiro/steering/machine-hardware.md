---
inclusion: auto
---

# Machine Hardware & LinuxCNC Configuration

## Hardware Summary

| Component | Model | Details |
|-----------|-------|---------|
| Motion Controller | Mesa 7i96s | Ethernet FPGA, 5-axis step/dir, 10MHz step rate |
| Daughter Card | Mesa 7i85s | 4 encoder inputs (differential), 4 step/dir outputs, 1 RS-422 serial |
| X Stepper | UIRobot UIM8696PM | Closed-loop integrated stepper |
| Z Stepper | UIRobot UIM8696PM | Closed-loop integrated stepper |
| X Encoder | Sino KA300/KA500 | Linear scale, 5µm resolution (5080 counts/inch) |
| Z Encoder | Sino KA300/KA500 | Linear scale, 5µm resolution (5080 counts/inch) |
| Spindle | Manual (no VFD) | On/off + gears, rotary encoder for threading/CSS |
| Spindle Encoder | 1000 PPR | 4000 counts/rev (quadrature), on 7i96s TB2 |
| MPG Handwheels | 2x | For manual jogging |
| Home Switches | 1 per axis | Software limits only (no physical limit switches) |
| Tool Post | Quick-change | Manual tool changes |

## Mesa 7i96s Key Specs

- Ethernet connected (192.168.1.121)
- 5 axis step/dir outputs (up to 10 MHz step rate)
- 11 isolated inputs + 6 isolated outputs
- Smart Serial port for daughter cards (7i85s)
- Spindle encoder input on TB2
- HostMot2 firmware (open source, configurable)
- TB3 P2 and P3 are FREE (formerly limit switches, now unused)

## Mesa 7i85s Key Specs

- Connects via Smart Serial to 7i96s
- 4 TTL or differential encoder inputs (with index)
- 8 differential outputs (4 step/dir pairs OR PWM)
- 1 RS-422 serial interface for I/O expansion
- Used for: X encoder, Z encoder, (2 encoder channels available)

## Machine Axes

### X Axis (Cross-Slide)
- Travel: 0 to 4.25" (diameter mode = 0 to 8.5" diameter capacity)
- Max velocity: 2.0 in/sec
- Max acceleration: 10.0 in/sec²
- Step scale: 54186.667 steps/inch
- Encoder scale: 5080 counts/inch
- PID: P=1000, FF1=1.0 (velocity feedforward)
- Deadband: 0.000050" (50 millionths)
- Following error: 0.005" max, 0.001" min

### Z Axis (Carriage)
- Travel: 0 to 23.5"
- Max velocity: 2.0 in/sec
- Max acceleration: 10.0 in/sec²
- Step scale: 27093.333 steps/inch
- Encoder scale: 5080 counts/inch
- PID: P=1000, FF1=1.0 (velocity feedforward)
- Deadband: 0.000050" (50 millionths)
- Following error: 0.005" max, 0.001" min

### Spindle
- Manual speed control (no CNC speed command)
- Encoder provides position feedback for G33 threading and G96 CSS
- 4000 counts/rev (1000 PPR × 4 quadrature)
- Speed range: 100-3000 RPM (set by operator)

## LinuxCNC Configuration Structure

```
my-lathe/
├── my-lathe.ini      ← Main config (axes, joints, display, mesa)
├── my-lathe.hal      ← Primary HAL wiring (mesa, stepgen, encoder, PID)
├── custom.hal        ← Custom HAL additions (MPG, jog buttons)
├── postgui.hal       ← Post-GUI HAL connections (GUI-created pins)
├── my-lathe.var      ← Persistent parameters (G92 offsets, tool offsets)
├── tool.tbl          ← Tool table (tool numbers, offsets, nose radius)
└── gui/              ← Custom PyQt5 GUI (DISPLAY = launch_gui.sh)
```

## HAL Architecture (How Hardware Connects to Software)

```
Physical Hardware → Mesa 7i96s FPGA → HAL Pins → Motion Controller → G-code Interpreter

Encoder signals → hm2_7i96s.0.encoder.N → joint.N.motor-pos-fb
Step commands  ← hm2_7i96s.0.stepgen.N ← joint.N.motor-pos-cmd (via PID)
Spindle encoder → hm2_7i96s.0.encoder.2 → spindle.0.revs (for threading)
Home switches → hm2_7i96s.0.gpio.N → joint.N.home-sw-in
```

## Key INI Parameters for CAM Engine

These values affect G-code generation and must be respected:

| Parameter | Value | Impact on CAM |
|-----------|-------|---------------|
| LINEAR_UNITS | inch | All coordinates in inches |
| MAX_LINEAR_VELOCITY | 2.0 in/sec | Max rapid rate = 120 IPM |
| MAX_LINEAR_ACCELERATION | 10.0 in/sec² | Affects path blending |
| FERROR | 0.005" | Max following error before fault |
| MIN_FERROR | 0.001" | Min following error at low speed |
| DEADBAND | 0.000050" | Position resolution limit |
| Encoder resolution | 5µm = 0.000197" | Actual position feedback resolution |
| GEOMETRY | -XZ | X axis is inverted in display (lathe convention) |

## Implications for CAM Engine

1. **Position resolution is 0.000197"** (encoder) — coordinates below this are meaningless
2. **Following error budget is 0.001-0.005"** — toolpath accuracy is limited by servo performance, not G-code precision
3. **Max rapid is 120 IPM (2 in/sec)** — retract moves are fast but not instant
4. **No spindle speed control** — G96/G97 commands are informational only (operator sets speed manually)
5. **Threading requires spindle encoder** — G33/G76 work because encoder provides position feedback
6. **Software limits only** — no physical limit switches means homing accuracy depends on switch repeatability
7. **Closed-loop steppers** — position is corrected by PID loop, so commanded vs actual position may differ by up to DEADBAND (0.00005")

## LinuxCNC HAL Components (Relevant to GUI)

The GUI communicates with LinuxCNC via:
- `linuxcnc` Python module — command interface (MDI, jog, mode changes)
- `hal` Python module — direct HAL pin reading/writing
- `linuxcnc.stat()` — machine state polling (position, status, errors)

Key HAL pins the GUI monitors:
- `halui.joint.N.pos-feedback` — actual position from encoders
- `halui.spindle.0.override.value` — spindle override
- `motion.current-vel` — current velocity
- `halui.program.is-running` — program execution state
