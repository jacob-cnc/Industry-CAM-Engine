---
inclusion: auto
---

# Architecture Rules — Industry CAM Engine

## Module Dependency Order (strict)

```
models → tools → geometry → intervals → planners → transitions → validation → outputs → pipeline → gui
```

Each module may only import from modules to its LEFT in this chain. No exceptions.

## Module Responsibilities

| Module | Imports From | Responsibility | External Deps |
|--------|-------------|----------------|---------------|
| `models/` | Nothing | Pure dataclasses (ClosedProfile, StockDef, ToolMove, etc.) | None |
| `tools/` | `models/` | Tool geometry, reach analysis, TNR computation | None |
| `geometry/` | `models/`, `tools/` | Build123d zone construction, ZoneQueryAPI, boundary extraction | build123d, OCP |
| `intervals/` | `models/`, `geometry/` | Fiber/Interval classes wrapping kernel queries | None |
| `planners/` | `models/`, `tools/`, `intervals/` | Pass planning (staircase, offset-contour, face, cleanup) | None |
| `transitions/` | `models/`, `intervals/` | Retract/approach/link logic between passes | None |
| `validation/` | `models/`, `geometry/` | Shapely polygon construction, runtime safety checking | shapely |
| `outputs/` | `models/` | G-code writer, graph adapter, DXF, SVG, simulation adapter | ezdxf, matplotlib (export only) |
| `pipeline/` | Everything above | Orchestration, wires modules together | None |
| `gui/` | `outputs/`, `pipeline/`, `models/` | PyQtGraph visualization, Program Tab, Debug Tab, all Qt UI | pyqtgraph, PyQt5 |

## The 7 Design Principles

### P1: Top-Down Rule Propagation
Define rules at the highest level and let them cover all cases. No per-case special handling.

### P2: Geometry Kernel as Single Source of Truth
All geometric answers come from Build123d/OCCT. No hand math.

### P3: One Path, One Implementation
Every operation has exactly one code path. No fallbacks, no dual implementations.

### P4: Tool as Geometry
The tool is a geometric shape, not a scalar. It participates in offset and reach computations.

### P5: Explicit Over Implicit
Transitions are named objects. Intervals have merge methods. Every coordinate has a traceable origin.

### P6: Validate at Every Boundary
Pre-planning → Post-planning (Shapely) → Pre-output. Three gates, all must pass.

### P7: Separation of Boundary-Finding from Path-Ordering
Finding where material exists (Fiber/Interval) is separate from deciding cut order (planners).

## Hard Rules (NEVER violate)

1. **No silent fallbacks.** If an operation fails, it raises. Never produce degraded output.
2. **No dual implementations.** One function computes each geometric quantity. Period.
3. **No hand math on coordinates.** Offsets come from the kernel. Crossings come from queries.
4. **No dead code.** Every function has callers. Every import is used. Architecture check enforces this.
5. **Shapely validates every move.** Not spot-checks — every endpoint, every rapid, every feed.
6. **Build123d produces coordinates. Shapely confirms safety. G-code writer emits.** Three systems agreeing = high confidence.

## File Naming Conventions

- One class per file (for major classes): `staircase_planner.py`, `offset_contour_planner.py`
- Shared utilities: `_helpers.py` suffix (private to module)
- Protocols/interfaces: `protocols.py` in each module that defines them
- Tests mirror source: `tests/planners/test_staircase_planner.py`

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

## Data Flow

```
UI fields → model_builder → ClosedProfile + StockDef + RoughingParams + ToolDef
    → pipeline.execute()
        → geometry.build_zones() → ZoneSet (Finished Part, Finish Allowance, Material to Rough, True Face)
        → validation.build_polygons() → ShapelyPolygons (cached)
        → planners.plan_face() → FaceZoneResult
        → planners.plan_turning() → TurningStaircaseResult
        → planners.plan_cleanup() → List[ToolMove]
        → validation.verify_all_moves() → PASS or raise
    → PlanResult (immutable)
        → outputs.gcode_writer.write() → G-code text
        → outputs.graph_adapter.convert() → GraphData (plain coordinate arrays + metadata)
            → gui.graph_widget renders via PyQtGraph
        → outputs.sim_adapter.export() → SimMove list
```

## Visualization as Core Architecture

The graph is NOT a bonus feature. It is the machinist's primary interface for confirming program safety. The architecture is designed to feed the graph cleanly:

1. **PlanResult carries everything the graph needs** — no callbacks into the engine
2. **graph_adapter produces plain arrays** — no PyQtGraph imports in engine code
3. **gui/ is the only PyQtGraph consumer** — clean separation of concerns
4. **Same data feeds both graph and G-code** — what you see IS what will cut
5. **Arcs pre-densified once** — reused by graph, Shapely, and export (no redundant computation)

Technology choices:
- **PyQtGraph** — interactive Program Tab and Debug Tab (vector zoom, coordinate readout, real-time playback)
- **Matplotlib** — static PNG export only (Shapely polygon plots for archiving/debugging)
- **ezdxf** — DXF export with true arc entities
