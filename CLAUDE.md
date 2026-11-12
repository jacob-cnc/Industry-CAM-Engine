# Industry CAM Engine — Claude Code Context

## Required cross-agent coordination

Before repository work and before edits, commits, merges, or deployment, follow
`docs/coordination/README.md`: fetch `agent-sync`, read both agent status files,
and publish your scope before implementation. Poll at least every five minutes
during active work and after long commands. Use the remote branch's current
contents, not a stale feature-branch copy. The user directs priorities and
observes the machine; agents exchange status and handoffs through this folder.

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
| Linear encoders | Sino KA300/KA500, 5µm = 5080 counts/inch; Z=enc 0, X=enc 1, both on 7i85s TB3 |
| Spindle | Manual (no VFD), 1000 PPR encoder on 7i96s TB2 |
| MPGs | 2× 100 PPR handwheels: X MPG on 7i85s TB2 (enc 3), Z MPG on 7i85s TB3 (enc 2) |

---

## CRITICAL: stepgen/joint reversal

The physical wiring reverses stepgen numbering from joint numbering:

| stepgen | axis | joint | encoder (linear feedback) |
|---|---|---|---|
| stepgen.00 | Z | Joint 1 | encoder.00 (7i85s TB3 enc 0) |
| stepgen.01 | X | Joint 0 | encoder.01 (7i85s TB3 enc 1) |

encoder.02 = Z MPG (7i85s TB3 enc 2), encoder.03 = X MPG (7i85s TB2 enc 3), encoder.04 = Spindle (7i96s TB2 onboard)

**Never assume stepgen N = joint N. Always verify against this table.**

---

## Axis Config

**`industry-cam.ini` is the source of truth** — this table is a snapshot
(2026-11-10). Re-read the INI before relying on any number here.

| | X (Joint 0) | Z (Joint 1) |
|---|---|---|
| Soft limits (joint) | -0.05 … 5.95 | -5.0 … 5.0 |
| MAX_VELOCITY joint / axis (in/s) | 1.7 / 1.8 | 1.5 / 0.75 |
| MAX_ACCELERATION joint / axis | 10 / 10 | 5 / 2 |
| STEPGEN_MAXVEL | 1.8 | 2.0 |
| STEP_SCALE | **-54186.667** | **-27093.333** |
| ENCODER_SCALE | **-5080** | **+5080** |
| PID P / I / D / FF1 | 125 / 0 / .002 / 1.0 | 60 / 0 / .005 / 1.0 |
| DEADBAND | .0005 | .0002 |
| FERROR / MIN_FERROR | .100 / .050 | .200 / .100 |

Signs: both STEP_SCALEs are negative and the ENCODER_SCALE signs differ per
axis (2026-05-20 "triple flip"). Never flip ENCODER_SCALE alone — the loop
goes unstable (positive feedback). See
`session-notes/2026-05-20-axis-convention-triple-flip.md`.

---

## 7i96s TB3 I/O

| GPIO | TB3 Pin | Signal | Status |
|---|---|---|---|
| gpio.000 | P1 | Z Home/Limit- | NOT wired |
| gpio.001 | P2 | Z Limit+ | NOT wired |
| gpio.002 | P3 | X Limit- | NOT wired |
| gpio.003 | P4 | X Home/Limit+ | NOT wired |
| gpio.004 | P5 | E-Stop | WIRED into estop chain (NC button, .in TRUE = released = safe) |
| gpio.005 | P6 | Jog Z- | NOT wired |
| gpio.006 | P7 | Jog Z+ | NOT wired |
| gpio.007 | P8 | Jog X- | NOT wired |
| gpio.008 | P9 | Jog X+ | NOT wired |
| gpio.009 | P10 | Cycle Start | NOT wired |
| gpio.010 | P11 | Cycle Stop | NOT wired |

**Switch wiring convention:** 24V+ → NO switch → input pin; P12 = 24V−  
Triggered = `.in` HIGH = `.in_not` LOW (sourcing type)

**HAL note:** when home/limit switches are eventually wired, use `.in` (not `.in_not`) for homing — the HAL currently has `.in_not` which would be wrong.

**X vernier (branch claude/x-vernier, 2026-11-10):** `rtcomp/xvernier.comp` estimates X between scale counts from scale edges + `stepgen.01.position-fb`. Add-on HAL only (`x-vernier-observe.hal` = shadow, `x-vernier-close.hal` = pid.x/motor-pos-fb on `xvernier.pos-est`), switched by commented `HALFILE` lines in `[HAL]`; `industry-cam.hal` itself is untouched. Params in `[XVERNIER]`, calibrated by `scripts/xvernier/fit_calibration.py`. The RT module must be installed with `sudo halcompile --install` (uspace `loadrt` can't load from a path). The estimator core is shared verbatim with the offline bench `tests/xvernier/` (test enforces it): edit it only between CORE-BEGIN/CORE-END and rerun `pytest tests/xvernier`. Runbook: `docs/handoffs/2026-11-10-x-vernier-commissioning.md`.

**E-stop HAL (wired 2026-11-10):** documented `estop_latch` pattern: ok-in <= `iocontrol.0.user-enable-out`, fault-in <= `hm2_7i96s.0.gpio.004.in_not`, reset <= `iocontrol.0.user-request-enable`, ok-out => `iocontrol.0.emc-enable-in`. NC button on TB3 P5: `.in` TRUE = released, FALSE = pressed or broken wire. Latches until Reset. Do NOT use a plain and2 (tried 2026-11-10: release cleared ESTOP by itself, because iocontrol keeps user-enable-out TRUE through an external E-stop) and do NOT add the button to the old estop-loop net (a net has one driver). Do NOT drive emc-enable-in HIGH permanently (setp or a bypass): task_state then stays 1 forever.

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
- `postgui.hal` is **NOT loaded** (stub only) — the INI has no `POSTGUI_HALFILE` and `DISPLAY = display_gui.sh` is a plain program. All MPG routing is in `industry-cam.hal`: `mux_generic` (`mux-gen.00` X, `mux-gen.01` Z, s32) selects direct MPG counts (default) or `compound-slide.x/z-jog-counts`; jog-enable = `halui.machine.is-on` AND NOT `compound-jog-inhibit`. `hal/live_backend.py` attaches the compound-slide pins to those signals at GUI startup and holds the inhibit while switching the mux (jump-free). With no GUI attached, routing falls back to direct MPG.
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

## Repository Layout (reorganized 2026-05-20)

```
Industry CAM Engine/
├── geometry/          CAM geometry kernel (Build123d/OCCT); planners use geometry/kernel.py only
├── gui/               PyQt5 GUI application
├── hal/               LinuxCNC HAL abstraction
├── intervals/         Fiber/interval classes
├── models/            Pure dataclasses (ClosedProfile, ToolDef, etc.)
├── outputs/           G-code writer (emits only), graph adapter, DXF/SVG export
├── pipeline/          Orchestration (execute() wires modules)
├── planners/          Pass planning (staircase, face, finish, etc.)
├── tools/             Tool data: .tbl I/O, tool editor record, insert angles
├── transitions/       Retract/approach/link logic
├── validation/        Safety checking (3 gates), cut_regions (rs274), architecture check + ratchet
├── tests/             All tests (unit/, properties/, integration/, etc.)
├── scripts/           Debug, export, and visual test scripts (not imported)
├── session-notes/     AI session checkpoints, commissioning logs
├── reference/         External reference repos (.gitignored)
├── backups/           Timestamped source snapshots (.gitignored)
├── .kiro/             Specs, steering rules, hooks (Kiro IDE)
│
├── industry-cam.*     LinuxCNC machine config (deployed to Linux)
├── custom.hal         HAL additions
├── postgui.hal        Post-GUI HAL connections (NOT loaded by this config)
├── tool.tbl           Tool table
├── *.sh               Linux launcher/utility scripts
├── *.bat              Windows dev launchers
│
├── ARCHITECTURE.md    Full system architecture reference
├── README.md          Project overview
├── CLAUDE.md          THIS FILE — Claude Code session context
├── pyproject.toml     Python project config
└── requirements.txt   Dependencies
```

**Key paths for Claude on Linux:**
- Session notes: `session-notes/` (checkpoints, commissioning logs, handoff docs)
- Debug scripts: `scripts/` (standalone, never imported by source)
- This file: `CLAUDE.md` at repo root (Claude Code reads this automatically)

---

## Start of Session Checklist

When beginning a new session, tell Claude:
1. What changed since last time (new wiring, config edits, test results)
2. What the current symptom or goal is
3. Paste any error output raw — do not summarize it
