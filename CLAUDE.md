# Industry CAM Engine — Claude Code Context

## Machine: Industry-CAM ZX CNC Lathe

**LinuxCNC 2.9.6** (uspace) on Debian 12 bookworm, kernel 6.1.0-30-rt-amd64 (PREEMPT_RT)

**Active config:** `/home/jacob/linuxcnc/configs/industry-cam/`

---

## Hardware

| Component | Detail |
|---|---|
| Motion controller | Mesa 7i96s (Ethernet) at 192.168.1.121 |
| Daughter card | Mesa 7i85s via SSERIAL (firmware: 7i96s_7i85sd.bin) |
| Drives | UIRobot UIM8696PM closed-loop integrated steppers, 48V |
| Linear encoders | Sino KA300/KA500, 5µm = 5080 counts/inch |
| Spindle | Manual (no VFD), 1000 PPR encoder on 7i96s TB2 |
| MPGs | 2× 100 PPR handwheels: X on 7i85s TB2, Z on 7i85s TB3 |

---

## CRITICAL: stepgen/joint reversal

The physical wiring reverses stepgen numbering from joint numbering:

| stepgen | axis | joint | encoder (linear feedback) |
|---|---|---|---|
| stepgen.00 | Z | Joint 1 | encoder.01 |
| stepgen.01 | X | Joint 0 | encoder.00 |

encoder.02 = Spindle, encoder.03 = X MPG, encoder.04 = Z MPG

**Never assume stepgen N = joint N. Always verify against this table.**

---

## Axis Config

| Axis | Travel | Max vel | STEP_SCALE | ENCODER_SCALE |
|---|---|---|---|---|
| X (Joint 0) | 0–4.25" radius | 2.0 in/s | 54186.667 | 5080 |
| Z (Joint 1) | 0–23.5" | 2.0 in/s | 27093.333 | 5080 |

PID initial: P=500, FF1=1.0 (critical for velocity-mode stepgen), deadband=0.0001", FERROR=0.050" (loose, for tuning)

---

## 7i96s TB3 I/O

| GPIO | TB3 Pin | Signal | Status |
|---|---|---|---|
| gpio.000 | P1 | Z Home/Limit- | NOT wired |
| gpio.001 | P2 | Z Limit+ | NOT wired |
| gpio.002 | P3 | X Limit- | NOT wired |
| gpio.003 | P4 | X Home/Limit+ | NOT wired |
| gpio.004 | P5 | E-Stop | CONNECTED (NC button, uses .in — LED ON = released = safe) |
| gpio.005 | P6 | Jog Z- | NOT wired |
| gpio.006 | P7 | Jog Z+ | NOT wired |
| gpio.007 | P8 | Jog X- | NOT wired |
| gpio.008 | P9 | Jog X+ | NOT wired |
| gpio.009 | P10 | Cycle Start | NOT wired |
| gpio.010 | P11 | Cycle Stop | NOT wired |

**Switch wiring convention:** 24V+ → NO switch → input pin; P12 = 24V−  
Triggered = `.in` HIGH = `.in_not` LOW (sourcing type)

**HAL note:** when home/limit switches are eventually wired, use `.in` (not `.in_not`) for homing — the HAL currently has `.in_not` which would be wrong.

**E-stop HAL note:** The correct iov2 estop loop is `net estop-loop iocontrol.0.user-enable-out => iocontrol.0.emc-enable-in`. This is NOT a deadlock — iov2 sets user-enable-out=TRUE after RESET clears aux.estop internally, breaking the loop. Do NOT use an and2 bypass or `setp iocontrol.0.emc-enable-in 1` — these drive emc-enable-in HIGH permanently but iov2 never clears aux.estop via NML, so task_state stays 1 forever. When hardware E-stop button is wired, extend the net: `net estop-loop iocontrol.0.user-enable-out hm2_7i96s.0.gpio.004.in => iocontrol.0.emc-enable-in` (gpio.004.in is HIGH when button released = safe, acts as AND with user-enable-out).

---

## Current Commissioning State

**Connected and working:**
- Both MPG handwheels (X and Z)
- E-Stop
- Linear encoders (X and Z feedback)
- Spindle encoder
- Steppers (both axes move)

**Not yet connected:**
- Home switches
- Limit switches
- Jog buttons (TB3 P6–P9)
- Cycle Start/Stop (TB3 P10–P11)

**HAL flags:**
- `HOME_SEARCH_VEL=0` — home-in-place, no switch search
- `NO_FORCE_HOMING=1` — can run without homing
- `postgui.hal` active (direct MPG routing, no compound-slide)
- `custom.hal` listed in INI (must exist or LinuxCNC fails to start)

---

## Workflow Notes

- **Development:** Windows machine with Kiro AI IDE → push to GitHub
- **Deployment:** This Linux machine → pull from GitHub, test live
- **Repo:** https://github.com/jacob-cnc/Industry-CAM-Engine
- **GUI:** PyQt5 + PyQtGraph, `/home/jacob/linuxcnc/configs/industry-cam/gui/`
- **Geometry:** Build123d/OCCT (only in `geometry/` module), Shapely for validation
- X axis = **diameter** in G-code/UI, **radius** internally — arc direction inverted in UI due to invertY
- Backup of pre-restructure state: `/home/jacob/linuxcnc/configs/industry-cam-backup-2026-05-17`

---

## Start of Session Checklist

When beginning a new session, tell Claude:
1. What changed since last time (new wiring, config edits, test results)
2. What the current symptom or goal is
3. Paste any error output raw — do not summarize it
