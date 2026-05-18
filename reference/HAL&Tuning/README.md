# HAL Monitor & Stepper/Encoder Tuning Tab — Implementation Guide

## Purpose

This directory contains all reference files and new implementation files needed to build
a combined HALShow/HALCmd & Stepper/Encoder Tuning tab for the My-Lathe LinuxCNC GUI.
An agent (or developer) can use these files as a complete blueprint for implementation.

---

## Architecture Overview

The My-Lathe GUI uses a **provider pattern** to abstract HAL data access:

- **Online** (LinuxCNC running on Linux): `LiveHALProvider` reads real HAL pins
- **Offline** (Windows development): `OfflineHALProvider` / `SimulatedTuningProvider` returns demo data

Both providers expose the same interface, so the UI code never needs to know which is active.

### Key Principle: `HAS_LINUXCNC`

```python
try:
    import linuxcnc
    import hal
    HAS_LINUXCNC = True
except ImportError:
    HAS_LINUXCNC = False
```

All HAL writes (`halcmd setp`, subprocess calls) are gated behind this flag.
All UI code works identically in both modes.

---

## File Inventory

### Existing Files (copied here for reference)

| File | Description |
|------|-------------|
| `hal_providers.py` | Live + Offline HAL pin providers (the core abstraction) |
| `hal_monitor.py` | Existing HALMonitorTab — pin browser, tree, watch list, polling |
| `hal_monitor_utils.py` | Pure helper functions — tree building, formatting, filtering |
| `tuning.py` | Existing TuningTab — parameter editor UI skeleton |
| `my-lathe.hal` | Full HAL configuration — pin names, signal wiring, component loading |
| `my-lathe.ini` | Machine INI — all tuning parameters (PID, stepgen, encoder, ferror) |

### New Files (to be integrated into `gui/`)

| File | Description |
|------|-------------|
| `tuning_provider.py` | Simulated tuning data provider for offline development |
| `tuning_graph.py` | Real-time following error strip chart widget |
| `tuning_enhanced.py` | Enhanced TuningTab with live polling, INI I/O, halcmd writes |

---

## Hardware Context

- **Mesa 7i96s + 7i85s** motion control
- **Closed-loop steppers** on X and Z with linear encoder feedback
- **Spindle encoder** on 7i96s TB2 (rotary, for threading/CSS)
- **2x MPG handwheels** on 7i85s TB2/TB3
- **Units: inches** (always — metric is display-only conversion)

### Critical Pin Mapping

```
Stepgen.00 = Z AXIS (Joint 1) — TB1 Step/Dir 0
Stepgen.01 = X AXIS (Joint 0) — TB1 Step/Dir 1
Encoder.00 = X linear scale (7i85s TB1 ch0)
Encoder.01 = Z linear scale (7i85s TB1 ch1)
Encoder.02 = Spindle rotary encoder (7i96s TB2)
Encoder.03 = X MPG handwheel (7i85s TB2)
Encoder.04 = Z MPG handwheel (7i85s TB3)
```

**WARNING**: Stepgen numbering is REVERSED from joint numbering. stepgen.00 = Z, stepgen.01 = X.

---

## Integration Steps

### 1. Add new files to `gui/`

```
gui/
├── tuning_provider.py    # NEW — copy from this directory
├── tuning_graph.py       # NEW — copy from this directory
├── tabs/
│   └── tuning.py         # REPLACE with tuning_enhanced.py content
```

### 2. Update `lathe_gui.py`

In `LatheGUI.__init__()`, change the TuningTab instantiation:

```python
import os
ini_path = os.path.join(os.path.dirname(_GUI_DIR), "my-lathe.ini")
self.tuning_tab = TuningTab(
    ini_path=ini_path,
    has_linuxcnc=HAS_LINUXCNC
)
```

In `_on_tab_changed()`, add activation:

```python
is_tuning = (self.tabs.widget(index) == self.tuning_tab)
self.tuning_tab.set_active(is_tuning)
```

In `periodic_update()`, feed live data to the tuning tab:

```python
if self.connected:
    # ... existing stat polling ...
    self.tuning_tab.update_from_stat(self.lcnc_stat)
```

### 3. Offline Demo Data Flow

```
QTimer (50ms) → SimulatedTuningProvider.tick()
                → tuning_graph.add_sample(x_err, z_err)
                → update numeric readouts
```

### 4. Online Data Flow

```
QTimer (50ms) → LiveHALProvider.get_pin_value('pid.x.error')
                → tuning_graph.add_sample(x_err, z_err)
                → update numeric readouts

User adjusts PID slider → halcmd setp pid.x.Pgain <value>
                         → immediate effect (no restart needed)

User clicks "Save to INI" → regex-replace values in my-lathe.ini
                           → requires LinuxCNC restart for persistence
```

---

## PID Tuning Workflow (for the operator)

1. Open Tuning tab
2. Click "Load from INI" to populate fields with current values
3. Watch the Following Error graph — it shows real-time deviation
4. Adjust P gain up until oscillation appears, then back off 20%
5. FF1 should be 1.0 for velocity-mode stepgens (already set)
6. Adjust Deadband to ignore encoder noise (typically 0.00005" for 5µm scales)
7. Click "Apply Live" to push changes to HAL without restart
8. Once satisfied, click "Save to INI" to persist

---

## Gotchas & Notes

1. **X is diameter in UI, radius internally** — the tuning tab shows RAW encoder/stepgen
   values which are always radius. Do NOT apply the 2× diameter conversion here.

2. **PID pin names use capital letters** — `pid.x.Pgain` not `pid.x.pgain`

3. **INI keys map to HAL pins**:
   - `[JOINT_0] P` → `pid.x.Pgain`
   - `[JOINT_0] I` → `pid.x.Igain`
   - `[JOINT_0] D` → `pid.x.Dgain`
   - `[JOINT_0] FF1` → `pid.x.FF1`
   - `[JOINT_0] DEADBAND` → `pid.x.deadband`
   - `[JOINT_0] MAX_OUTPUT` → `pid.x.maxoutput`

4. **Timer management** — STOP polling when tab is not visible. Use `set_active(bool)`.

5. **Thread safety** — All HAL reads happen in the main Qt thread via QTimer. Never use
   background threads for HAL access.

6. **INI path** — From gui/: `os.path.join(os.path.dirname(_GUI_DIR), "my-lathe.ini")`

7. **configparser quirks** — Use `interpolation=None`. For writes, prefer regex line
   replacement to preserve comments and formatting.

8. **Encoder scale** — X and Z linear encoders: 5080 counts/inch (5µm resolution).
   Spindle: 4000 counts/rev (1000 PPR × 4 quadrature).

---

## Testing

- **Windows**: Run `python gui/lathe_gui.py` — offline mode activates automatically
- **Linux (no LinuxCNC)**: Same offline mode
- **Linux (LinuxCNC running)**: Full live mode with real HAL data

The `SimulatedTuningProvider` generates realistic-looking data:
- Following error: sine wave + gaussian noise (~±0.0002")
- Encoder positions: slow linear drift
- Spindle RPM: random walk around 800 RPM
- PID output: proportional to simulated error

---

## Color Palette (from theme.py)

- Section headers: `COLORS['accent_blue']`
- Values/DRO: `COLORS['dro_text']` on `COLORS['dro_bg']`
- Warnings (near FERROR limit): `COLORS['accent_orange']`
- Faults (exceeded FERROR): `COLORS['accent']` (red)
- Good/normal: `COLORS['accent_green']`
- Labels: `COLORS['text_dim']`
- Backgrounds: `COLORS['bg_dark']`, `COLORS['bg_mid']`, `COLORS['bg_light']`
