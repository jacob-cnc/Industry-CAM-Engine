# Commissioning Module — Architecture & Integration Guide

## Overview

The `gui/commissioning/` module provides the **Setup tab** for the Industry CAM Engine GUI. It covers the full machine commissioning lifecycle: HAL diagnostics, PID tuning, and guided validation.

## Module Structure

```
gui/commissioning/
├── __init__.py              # Public API: exports SetupTab
├── setup_tab.py             # Top-level container (3 sub-tabs)
├── hal_monitor_tab.py       # Pin browser, signal tracing, watch list
├── hal_utils.py             # Pure functions: tree building, formatting
├── pin_providers.py         # Live + Offline HAL pin data access
├── tuning_tab.py            # PID tuning UI, INI load/save, Apply Live
├── tuning_graph.py          # Following error strip chart (QPainter)
├── tuning_provider.py       # Simulated data for offline development
├── ini_io.py                # Regex-based INI read/write (preserves comments)
├── commissioning_tab.py     # Guided checklist with persistence
└── README.md                # This file
```

## Architecture Layers

```
┌─────────────────────────────────────────────────────────┐
│  MainWindow (gui/main_window.py)                        │
│    └── SetupTab (setup_tab.py)                          │
│          ├── HALMonitorTab    ← pin_providers.py        │
│          ├── TuningTab        ← tuning_provider.py      │
│          │     └── FollowingErrorPanel (tuning_graph.py)│
│          └── CommissioningTab                           │
├─────────────────────────────────────────────────────────┤
│  Data Layer                                             │
│    ├── pin_providers.py  (raw HAL pin access)           │
│    ├── ini_io.py         (INI file read/write)          │
│    └── hal/interface.py  (machine control - existing)   │
├─────────────────────────────────────────────────────────┤
│  Backend (hal/)                                         │
│    ├── LiveBackend   → real LinuxCNC                    │
│    └── MockBackend   → offline simulation               │
└─────────────────────────────────────────────────────────┘
```

## Two Provider Layers (Why Both Exist)

| Layer | Purpose | Interface |
|-------|---------|-----------|
| `hal/interface.py` (HALBackend) | Machine control: jog, home, MDI, mode switching | `poll()`, `jog_continuous()`, `home_axis()`, etc. |
| `pin_providers.py` (PinProvider) | Raw diagnostics: read any HAL pin by name | `get_all_pins()`, `get_pin_value()`, `get_signal_pins()` |

The HALBackend is for **operating** the machine. The PinProvider is for **diagnosing** it. Both have Live and Offline implementations.

## Timer Management

All polling stops when the Setup tab is not visible:

```
MainWindow._on_tab_changed(index)
  └── SetupTab.set_active(is_setup_tab)
        ├── HALMonitorTab.set_active(is_hal_monitor)  → watch list polling
        ├── TuningTab.set_active(is_tuning)           → graph + status polling
        └── CommissioningTab.set_active(is_commission) → no polling needed
```

Timer intervals:
- Following error graph: **50ms** (20 FPS for smooth animation)
- Status readouts: **200ms** (5 Hz, sufficient for numeric displays)
- Watch list: **100ms** (configurable 50–500ms via combo box)

## Offline Mode Detection

The module uses `isinstance(pin_provider, OfflinePinProvider)` rather than `backend.connected` to determine offline mode. This is because the MockBackend reports `connected=True` (it simulates a running machine), but we still need simulated tuning data on Windows.

## Key Machine Facts (Encoded in Constants)

- `stepgen.00 = Z axis`, `stepgen.01 = X axis` (REVERSED from joint numbering)
- PID pins use capitals: `pid.x.Pgain`, not `pid.x.pgain`
- X is always RADIUS internally — no diameter conversion in tuning
- FF1 = 1.0 is critical for velocity-mode stepgens
- Linear encoders: 5080 counts/inch (5µm resolution)
- Spindle encoder: 4000 counts/rev (1000 PPR × 4 quadrature)

## Integration Point

In `gui/main_window.py`:

```python
from gui.commissioning import SetupTab
from hal.factory import get_backend

class MainWindow(QMainWindow):
    def __init__(self):
        self._backend = get_backend()
        # ...
        self._setup_tab = SetupTab(
            backend=self._backend,
            ini_path=self._get_ini_path(),
        )
        self._tab_widget.addTab(self._setup_tab, "Setup")

    def _on_tab_changed(self, index):
        is_setup = (self._tab_widget.widget(index) is self._setup_tab)
        self._setup_tab.set_active(is_setup)
```

## Features by Sub-Tab

### HAL Monitor
- Hierarchical pin tree (split on '.' separators)
- Preset filter buttons: Home, E-Stop, Jog, Cycle, MPG, Spindle, PID, Stepgen, Encoders
- Text filter with substring matching
- **Signal tracing**: select a pin → see all other pins on the same signal
- Watch list with live polling and change highlighting
- Configurable refresh rate (50–500ms)

### Tuning
- Per-axis parameter panels (stepper, encoder, PID, FERROR)
- Real-time following error strip chart with:
  - Click to freeze, scroll to pan history
  - Mouse wheel Y-axis zoom
  - FERROR/MIN_FERROR limit lines
  - Peak tracking with decay
- Load from INI / Save to INI (regex-based, preserves comments)
- Apply Live (halcmd setp for PID gains — no restart)
- Validation before apply (sanity checks on values)

### Commissioning Checklist
- 9-step guided workflow (I/O → E-Stop → Jog → Home → Encoder → PID → FERROR → Spindle → Tool)
- Pass/Fail/Skip status per step
- Notes field for recording observations
- JSON persistence (survives restarts)
- Progress summary

## Future Enhancements

- [ ] Step response test (command a jog, capture the response curve)
- [ ] Dual Y-axis on graph (error + velocity overlay)
- [ ] HAL signal flow diagram (visual wiring)
- [ ] Auto-tune wizard (automated P gain search)
- [ ] Export tuning session (graph data + parameters as CSV)
