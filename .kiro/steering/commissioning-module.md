---
inclusion: auto
---

# Commissioning Module — Setup Tab Architecture

## Status

Implemented in `gui/commissioning/`. Wired into MainWindow as the "Setup" tab (replaces Phase 3 placeholder). All 9 files import cleanly and the full app launches with 8 tabs on Windows offline mode.

## Module Location & Structure

```
gui/commissioning/
├── __init__.py              # Public API: exports SetupTab
├── setup_tab.py             # Top-level container (3 sub-tabs, timer lifecycle)
├── hal_monitor_tab.py       # Pin browser, signal tracing, watch list
├── hal_utils.py             # Pure functions: tree building, formatting, filtering
├── pin_providers.py         # Live + Offline HAL pin data access
├── tuning_tab.py            # PID tuning UI, INI load/save, Apply Live
├── tuning_graph.py          # Following error strip chart (QPainter, no pyqtgraph)
├── tuning_provider.py       # Simulated data for offline development
├── ini_io.py                # Regex-based INI read/write (preserves comments)
└── commissioning_tab.py     # Guided 9-step checklist with JSON persistence
```

## Integration Point

In `gui/main_window.py`:
- `from gui.commissioning import SetupTab`
- `from hal.factory import get_backend`
- `MainWindow.__init__` creates `self._backend = get_backend()` and passes it to SetupTab
- `_on_tab_changed` calls `self._setup_tab.set_active(is_setup)` to manage polling

## Two Provider Layers

| Layer | Module | Purpose |
|-------|--------|---------|
| Machine Control | `hal/interface.py` (HALBackend) | Jog, home, MDI, mode switching |
| Pin Diagnostics | `gui/commissioning/pin_providers.py` (PinProvider) | Read any HAL pin by name, signal tracing |

Both have Live (Linux) and Offline (Windows) implementations. The commissioning module uses BOTH — HALBackend for machine operations, PinProvider for raw diagnostics.

## Offline Detection

Uses `isinstance(pin_provider, OfflinePinProvider)` — NOT `backend.connected`. The MockBackend reports `connected=True` (simulates a running machine), but we still need `SimulatedTuningProvider` on Windows for the following error graph.

## Timer Management Rules

- ALL polling stops when Setup tab is not the active main tab
- Within Setup, only the active sub-tab polls
- Graph timer: 50ms (20 FPS)
- Status readouts: 200ms (5 Hz)
- Watch list: 100ms (configurable 50–500ms)
- Timers controlled via `set_active(bool)` — never left running in background

## Key Design Decisions

1. **Separate sub-tabs** — HAL Monitor (diagnostics) vs Tuning (workflow) vs Commission (checklist). Different purposes at different stages of machine life.
2. **Signal tracing** — `OfflinePinProvider` builds a signal→pins index. Click a pin, see all other pins on the same signal. Critical for debugging wiring issues.
3. **Interactive graph** — Click to freeze, scroll history, mouse wheel zoom. QPainter-based (no pyqtgraph dependency for this widget).
4. **INI I/O via regex** — `ini_io.py` preserves comments and formatting. Never use configparser for LinuxCNC INI files.
5. **Commissioning checklist persists to JSON** — Progress survives restarts. 9 steps from I/O verification through tool change validation.
6. **Validation before Apply Live** — Sanity checks on PID values before pushing to HAL.

## Critical Machine Facts (Encoded in Code)

- `stepgen.00 = Z axis`, `stepgen.01 = X axis` (REVERSED from joint numbering)
- PID pins use capitals: `pid.x.Pgain`, not `pid.x.pgain`
- X is RADIUS in tuning tab — no diameter conversion (raw encoder/stepgen values)
- FF1 = 1.0 is the critical feedforward for velocity-mode stepgens
- `halcmd setp` changes PID gains live without restart
- INI changes require LinuxCNC restart to take effect

## Commissioning Checklist Steps

1. Verify I/O — confirm inputs read, outputs toggle
2. E-Stop Chain — verify emergency stop end-to-end
3. Jog Test — axis direction, scale, soft limits
4. Home Test — homing sequence, repeatability
5. Encoder Verify — compare stepgen vs encoder positions
6. PID Tune — P gain, FF1, deadband adjustment
7. FERROR Test — run at speed, confirm no faults
8. Spindle Encoder — verify RPM reads correctly
9. Tool Change — tool table and offset verification

## Future Work

- Step response test (command a jog, capture the response curve for PID analysis)
- Dual Y-axis on graph (following error + velocity command overlay)
- HAL signal flow diagram (visual wiring representation)
- Auto-tune wizard (automated P gain binary search)
- Export tuning session (graph data + parameters as CSV for documentation)

## Reference Implementation

The `reference/HAL&Tuning/` directory contains the original agent's implementation that informed this design. Key differences from reference:
- We use the existing `hal/` backend layer instead of a separate provider pattern for machine control
- Separated HAL Monitor from Tuning (reference combined them)
- Added commissioning checklist (reference had none)
- Added signal tracing (reference only had pin-level browsing)
- Added graph interactivity (freeze/zoom — reference was view-only)
- Used project's COLORS dict instead of a separate theme.py
