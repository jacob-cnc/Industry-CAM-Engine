# Industry CAM Engine — Architecture Reference

This document is for agents or developers who need to understand how the project is built, how data flows, and where to make changes. It covers the full system: CAM engine, GUI, HAL layer, and LinuxCNC integration.

---

## System Overview

The Industry CAM Engine is a conversational CAM system for a 2-axis CNC lathe. The operator defines a part profile (segments of lines and arcs), sets cutting parameters, and the engine generates safe, validated G-code with full toolpath visualization.

The system runs in two modes:
- **Online** (Linux + LinuxCNC): Full machine control, real HAL data, live DRO
- **Offline** (Windows or Linux without LinuxCNC): GUI preview with simulated data

```
┌─────────────────────────────────────────────────────────────────┐
│                    Industry CAM Engine                           │
├─────────────────────────────────────────────────────────────────┤
│  GUI (PyQt5 + PyQtGraph)                                        │
│    ├── Program Tab — conversational part definition              │
│    ├── Edit Tab — G-code viewer/editor                          │
│    ├── Tools Tab — tool table management                        │
│    ├── Debug Tab — plan result inspection                       │
│    ├── Manual Tab — jog, MPG, DRO                               │
│    └── Setup Tab — HAL monitor, PID tuning, commissioning       │
├─────────────────────────────────────────────────────────────────┤
│  Pipeline (orchestration)                                       │
│    execute() wires all modules together in sequence             │
├─────────────────────────────────────────────────────────────────┤
│  CAM Engine Modules                                             │
│    models → tools → geometry → intervals → planners             │
│                                          → transitions          │
│                              → validation                       │
│    → outputs (gcode, graph, dxf, svg, material sim)             │
├─────────────────────────────────────────────────────────────────┤
│  HAL Layer (machine abstraction)                                │
│    LiveBackend ←→ linuxcnc Python module                        │
│    MockBackend ←→ simulated state (offline)                     │
├─────────────────────────────────────────────────────────────────┤
│  LinuxCNC (realtime motion control)                             │
│    INI → HAL → Mesa 7i96s → steppers/encoders                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Module Dependency Chain (Strict)

```
models → tools → geometry → intervals → planners → transitions → validation → outputs → pipeline → gui
```

Each module may ONLY import from modules to its LEFT. No exceptions. This is enforced by `validation/architecture_check.py`.

| Module | Imports From | External Deps | Responsibility |
|--------|-------------|---------------|----------------|
| `models/` | Nothing | None | Pure dataclasses: ClosedProfile, StockDef, ToolDef, ToolMove, PlanResult |
| `tools/` | models/ | None | Tool geometry, reach analysis, TNR computation |
| `geometry/` | models/, tools/ | **build123d, OCP** | Zone construction, boundary extraction, ZoneQueryAPI |
| `intervals/` | models/, geometry/ | None | Fiber/Interval classes wrapping kernel queries |
| `planners/` | models/, tools/, intervals/ | None | Pass planning: staircase, face, finish, cleanup, offset-contour |
| `transitions/` | models/, intervals/ | None | Retract/approach/link logic between passes |
| `validation/` | models/, geometry/ | **shapely** | Polygon construction, runtime safety checking (3 gates) |
| `outputs/` | models/ | ezdxf, matplotlib | G-code writer, graph adapter, DXF/SVG export, material sim |
| `pipeline/` | All above | None | Orchestration: `execute()` wires modules together |
| `gui/` | outputs/, pipeline/, models/ | **PyQt5, pyqtgraph** | All Qt UI, visualization, user interaction |
| `hal/` | None (standalone) | linuxcnc (optional) | Machine control abstraction |

---

## Data Flow: Profile → G-code

```
User input (GUI fields)
    │
    ▼
pipeline.model_builder.build_from_fields()
    → ClosedProfile + StockDef + RoughingParams + ToolDef
    │
    ▼
pipeline.execute()
    ├── geometry.build_zones() → ZoneSet
    │     (Finished Part, Finish Allowance, Material to Rough, True Face)
    │
    ├── validation.build_polygons() → ShapelyPolygons (cached)
    │
    ├── planners.plan_face() → FaceZoneResult (face passes)
    │
    ├── planners.plan_turning() → TurningStaircaseResult (roughing passes)
    │     Uses: staircase_planner or offset_contour_planner
    │
    ├── planners.plan_cleanup() → List[ToolMove] (cleanup passes)
    │
    ├── planners.plan_finish() → List[ToolMove] (finish pass)
    │
    ├── transitions.plan_transitions() → adds rapids/retracts between passes
    │
    ├── validation.verify_all_moves() → PASS or raise
    │     (every endpoint, every rapid, every feed checked against Shapely polygons)
    │
    └── → PlanResult (immutable, carries everything)
            │
            ├── outputs.gcode_writer.write() → G-code text string
            │
            ├── outputs.graph_adapter.convert() → GraphData
            │     (plain coordinate arrays + metadata for PyQtGraph)
            │
            └── outputs.material_sim → per-move material states for animation
```

---

## Key Data Structures

### ClosedProfile (models/profile.py)
The part geometry — a list of `ProfileMove` segments (LINE or ARC) forming a closed contour. X values are in DIAMETER, Z in inches. Arc radius is signed: +CW (G02), -CCW (G03).

### StockDef (models/stock.py)
Stock dimensions: OD, ID (if bore), Z-start, Z-end. Defines the raw material envelope.

### ToolDef (models/tool.py)
Tool geometry: nose radius, orientation (Q1-Q8), type (roughing/finishing/threading/grooving), direction.

### ToolMove (models/moves.py)
A single motion command: move_type (RAPID/FEED/ARC_CW/ARC_CCW), endpoint (x diameter, z), feed rate, arc center (center_i diameter, center_k), pass type.

### PlanResult (models/results.py)
The complete output of `pipeline.execute()`. Contains: all roughing passes, face passes, cleanup moves, finish moves, swept regions, zone data. Immutable — passed to GUI for display.

### GraphData (outputs/graph_adapter.py)
Plain coordinate arrays ready for PyQtGraph rendering. Contains: toolpath segments (with move type + color), zone shadings, stock rect, profile boundary, centerline range. No Qt imports in this module.

---

## Coordinate Conventions

| Context | X Convention | Notes |
|---------|-------------|-------|
| User-facing fields (GUI) | DIAMETER | What the operator types |
| G-code output | DIAMETER | Standard lathe G-code |
| Internal computation | RADIUS | All planners, geometry, validation work in radius |
| Graph display | RADIUS (Y-axis shows diameter labels) | DiameterAxisItem converts for display |
| ToolMove.x | DIAMETER | Stored as diameter, converted at boundaries |
| ToolMove.center_i | DIAMETER | Arc center X offset in diameter |
| Encoder/HAL values | RADIUS | Raw machine coordinates |

**Critical rule:** Never apply the 2× diameter conversion inside planners or geometry. The conversion happens at the boundary (model_builder input, gcode_writer output, graph_adapter display).

---

## The Three Validation Gates

Every toolpath passes through three independent validation stages:

1. **Pre-planning** (`validation/pre_planning_validator.py`)
   - Profile geometry is valid (closed, no self-intersections)
   - Stock encloses the profile
   - Tool can reach all features

2. **Post-planning** (`validation/post_planning_validator.py`)
   - Every cutting move stays within the material zone (Shapely polygon check)
   - No gouging of the finished part
   - Every rapid is in free space (not through material)

3. **Pre-output** (`validation/pre_output_validator.py`)
   - G-code geometry matches the plan (arc radii, endpoints)
   - Feed rates are set before cutting moves
   - No impossible arcs (radius < chord/2)

If any gate fails, the pipeline raises — no degraded output, no silent fallbacks.

---

## Geometry Kernel (Build123d / OCCT)

The `geometry/` module is the ONLY place that imports Build123d or OpenCASCADE. It provides:

- **ZoneBuilder**: Constructs 2D zones (Finished Part, Material to Rough, etc.) as OCCT shapes
- **ZoneQueryAPI**: Answers geometric queries (boundary at X, crossing points, fiber intervals)
- **ContourIntersect**: Finds where toolpath crosses zone boundaries
- **adaptive_sampling**: Densifies arcs into point arrays for display and validation

All other modules receive geometric answers as plain numbers (floats, lists of coordinates). They never touch OCCT directly.

---

## GUI Architecture

### Tab Structure

```
MainWindow (QMainWindow)
├── StatusBar (top, 48px)
└── QTabWidget
    ├── ProgramTab — profile editor, parameter fields, generate button, graph
    ├── EditTab — G-code text editor with syntax highlighting
    ├── ToolsTab — tool table (QTableWidget), touch-off controls
    ├── DebugTab — plan result panels, zone data, validation status
    ├── (Run placeholder)
    ├── ManualTab — jog controls, MPG settings, DRO
    ├── SetupTab — commissioning sub-tabs:
    │   ├── HALMonitorTab — pin browser, signal tracing, watch list
    │   ├── TuningTab — PID tuning, following error graph
    │   └── CommissioningTab — guided 9-step checklist
    └── (Help placeholder)
```

### Signal Flow Between Tabs

```
ProgramTab.gcode_generated → EditTab.receive_gcode
ProgramTab.plan_result_ready → DebugTab.update_panels
ProgramTab.state_changed → StatusBar.update_state
ToolsTab.tool_changed → MainWindow._on_tool_changed
ToolsTab.tool_selected → ProgramTab.set_active_tool
TabWidget.currentChanged → SetupTab.set_active (timer management)
```

### Graph Widget (gui/components/graph_widget.py)

Uses PyQtGraph for interactive visualization:
- **Aspect locked 1:1** (lathe parts aren't square, but we lock for accuracy)
- **Y-axis inverted** (`invertY(True)`) — operator POV: X+ is down (toward centerline)
- **DiameterAxisItem** — Y-axis labels show diameter while plotting in radius
- **Zone shadings** — rasterized as ImageItem overlay (avoids pyqtgraph fill bugs)
- **Toolpath traces** — PlotCurveItem per segment, color-coded by move type
- **Playback** — animated tool dot with progressive toolpath reveal

### Arc Direction Convention (UI ↔ Backend)

The graph's `invertY` flips visual rotation direction. The UI labels match what the operator SEES:
- UI "CW" (clockwise on screen) → produces G03 → negative signed radius
- UI "CCW" (counter-clockwise on screen) → produces G02 → positive signed radius

This mapping lives in `gui/components/segment_list.py` (`_read_row` and `set_segments`).

---

## HAL Abstraction Layer (hal/)

### Interface (hal/interface.py)

Defines `HALBackend` abstract class with:
- `poll()` → updates `MachineState` snapshot
- `state` property → immutable `MachineState` dataclass
- Motion commands: `jog_continuous`, `jog_increment`, `jog_stop`
- Mode control: `set_mode_manual`, `set_mode_mdi`, `set_mode_auto`
- Machine control: `estop_reset`, `machine_on`, `machine_off`
- Homing: `home_axis`, `home_all`
- Program: `program_open`, `program_run`, `program_pause`, `program_stop`

### Factory (hal/factory.py)

```python
from hal.factory import get_backend
backend = get_backend()  # Returns LiveBackend or MockBackend (singleton)
```

Tries to import `linuxcnc`. If available and connected → `LiveBackend`. Otherwise → `MockBackend`.

### Pin Providers (gui/commissioning/pin_providers.py)

Separate from HALBackend — provides raw pin-level access for diagnostics:
- `LivePinProvider` — reads HAL pins via `hal.get_info_pins()`
- `OfflinePinProvider` — returns demo data matching machine config
- `get_pin_provider()` — factory function

The distinction: HALBackend is for **operating** the machine. PinProvider is for **diagnosing** it.

---

## LinuxCNC Integration

### File Structure on Machine

```
/home/jacob/linuxcnc/configs/industry-cam/
├── industry-cam.ini        ← Machine config (LinuxCNC reads this)
├── industry-cam.hal        ← HAL wiring (loaded by LinuxCNC)
├── custom.hal              ← User additions (loaded after main HAL)
├── postgui.hal             ← Post-GUI connections (compound slide)
├── industry-cam.var        ← Persistent parameters (auto-managed)
├── display_gui.sh          ← Called by LinuxCNC to start GUI
├── launch_gui.sh           ← Smart launcher (desktop icon target)
├── gui/                    ← Python GUI application
├── hal/                    ← HAL abstraction layer
├── models/ ... pipeline/   ← CAM engine modules
└── tool.tbl                ← Tool table
```

### Launch Sequence

```
Desktop icon → launch_gui.sh
    ├── Mesa board reachable? → linuxcnc industry-cam.ini
    │                              ├── Load realtime modules
    │                              ├── Load industry-cam.hal (Mesa → PID → stepgen)
    │                              ├── Load custom.hal
    │                              ├── Start motion controller
    │                              └── Call display_gui.sh (DISPLAY setting)
    │                                    └── python3 -m gui.main_window
    │                                          └── GUI connects to linuxcnc API
    │
    └── Mesa NOT reachable? → python3 -m gui.main_window (offline mode)
                                    └── MockBackend + OfflinePinProvider
```

### HAL Signal Flow

```
joint.0.motor-pos-cmd ──→ pid.x.command
                          pid.x.feedback ←── encoder.00.position (X linear scale)
                          pid.x.output ──→ stepgen.01.velocity-cmd (X stepper)

joint.1.motor-pos-cmd ──→ pid.z.command
                          pid.z.feedback ←── encoder.01.position (Z linear scale)
                          pid.z.output ──→ stepgen.00.velocity-cmd (Z stepper)
```

**CRITICAL:** stepgen.00 = Z axis, stepgen.01 = X axis (reversed from joint numbering due to physical wiring order on TB1).

---

## Machine Hardware Summary

| Component | Details |
|-----------|---------|
| Controller | Mesa 7i96s (Ethernet FPGA) + 7i85s (daughter card) |
| Steppers | UIRobot UIM8696PM closed-loop integrated (48V) |
| Linear Encoders | Sino KA300/KA500, 5µm resolution (5080 counts/inch) |
| Spindle | Manual (no VFD), 1000 PPR rotary encoder for threading |
| MPG | 2× handwheels (100 PPR), X on 7i85s TB2, Z on 7i85s TB3 |
| Axes | X: 0–4.25" (radius), Z: 0–23.5" |
| Max Velocity | 2.0 in/sec both axes |
| PID | P=500 (initial), FF1=1.0, deadband=0.0001" |
| FERROR | 0.050" (tuning), tighten to 0.005" after tuning |

---

## Design Principles

1. **Top-Down Rule Propagation** — Define rules at the highest level, let them cover all cases
2. **Geometry Kernel as Single Source of Truth** — All geometric answers from Build123d/OCCT
3. **One Path, One Implementation** — No fallbacks, no dual implementations
4. **Tool as Geometry** — The tool is a shape, not a scalar
5. **Explicit Over Implicit** — Transitions are named objects, intervals have merge methods
6. **Validate at Every Boundary** — Three gates, all must pass
7. **Separation of Boundary-Finding from Path-Ordering** — Fibers find material, planners decide order

---

## Hard Rules (Never Violate)

1. **No silent fallbacks.** If an operation fails, it raises. Never produce degraded output.
2. **No dual implementations.** One function computes each geometric quantity.
3. **No hand math on coordinates.** Offsets come from the kernel. Crossings come from queries.
4. **No dead code.** Every function has callers. Every import is used.
5. **Shapely validates every move.** Not spot-checks — every endpoint, every rapid, every feed.
6. **Build123d produces coordinates. Shapely confirms safety. G-code writer emits.** Three systems agreeing = high confidence.

---

## File Naming Conventions

- One class per file (major classes): `staircase_planner.py`, `offset_contour_planner.py`
- Shared utilities: `_helpers.py` suffix (private to module)
- Protocols/interfaces: `protocols.py` in each module
- Tests mirror source: `tests/planners/test_staircase_planner.py`

---

## Error Handling Pattern

```python
# CORRECT: Raise with context
raise RuntimeError(
    f"boundary_at_x failed at x_dia={x_dia:.4f} for zone '{zone_name}': "
    f"BRepAlgoAPI_Section returned no edges"
)

# WRONG: Catch and degrade
try:
    result = kernel_operation()
except Exception:
    result = fallback_computation()  # NEVER DO THIS
```

---

## Testing Strategy

- **Unit tests** in `tests/` mirroring source structure
- **Property-based tests** using Hypothesis (e.g., material simulation preservation)
- **Round-trip tests** — generate G-code, parse it back, verify geometry matches
- **Visual tests** — `_visual_test_*.py` scripts for manual graph inspection
- **Architecture check** — `validation/architecture_check.py` enforces import rules

---

## Key Gotchas for New Agents

1. **X is diameter in user fields and G-code, radius internally.** The conversion boundary is model_builder (input) and gcode_writer (output). Never convert inside planners.

2. **Arc direction is inverted in the UI** due to `invertY`. UI "CW" = G03 = negative radius. See `segment_list.py`.

3. **stepgen.00 = Z, stepgen.01 = X.** Physical wiring order doesn't match joint numbering.

4. **PID pin names use capitals.** `pid.x.Pgain` not `pid.x.pgain`.

5. **FF1 = 1.0 is critical.** For velocity-mode stepgen, FF1 is the primary feedforward. Without it, the PID has to do all the work and will be sluggish or oscillate.

6. **The graph is NOT a bonus feature.** It's the machinist's primary safety interface. The architecture is designed to feed it cleanly (PlanResult → graph_adapter → PyQtGraph).

7. **No pyqtgraph imports outside gui/.** The `outputs/graph_adapter.py` produces plain arrays. Only `gui/components/graph_widget.py` imports pyqtgraph.

8. **Timer management in Setup tab.** All polling stops when the tab isn't visible. Use `set_active(bool)`. Never leave timers running in background.

9. **INI file I/O uses regex, not configparser.** LinuxCNC INI files have quirks (inline comments, specific formatting) that configparser breaks. Use `gui/commissioning/ini_io.py`.

10. **The MockBackend reports `connected=True`.** Use `isinstance(pin_provider, OfflinePinProvider)` to detect offline mode, not `backend.connected`.
