# Material Removal Simulation — SHELVED

**Status**: Disabled as of 2026-05-17. Feature code remains in place but is not called.  
**Reason**: Visual output not accurately reflecting real material removal during playback.

---

## What Was Built

The material removal simulation computes progressive stock subtraction during toolpath playback, showing a semi-transparent polygon fill that shrinks as the tool cuts.

### Files Created/Modified

| File | Role |
|------|------|
| `outputs/material_sim.py` | Core engine — computes pass_states, move_states, final_state via Shapely polygon subtraction |
| `outputs/graph_adapter.py` | `MaterialStateData` dataclass + `_convert_material_sim()` converter |
| `gui/components/graph_widget.py` | `_render_material_polygon()`, `set_material_state()`, `set_material_to_stock()`, `set_material_to_final()`, `render_move_state()`, `set_partial_material()` |
| `gui/components/sim_viewer.py` | `_update_material_state()`, `_build_sim_to_toolmoves_mapping()`, `_material_enabled` flag |
| `gui/program_tab.py` | Pipeline integration (currently disabled — `sim_data = None`) |

### Test Files

| File | Purpose |
|------|---------|
| `tests/properties/test_bug_condition_material_sim.py` | PBT exploration test for 4 sub-defects |
| `tests/properties/test_material_sim_preservation.py` | PBT preservation tests (9 properties) |

---

## What Worked (in unit tests)

- `material_sim.compute()` correctly produces pass_states and move_states
- Sequential polygon subtraction (stock minus swept regions) is geometrically correct
- Face pass X-tracking, arc progressive removal, and roughing Z-clipping all pass PBT
- SimMove-to-tool_moves index mapping works for coordinate correlation
- All 66 tests pass including the 13 property-based tests

---

## What Didn't Work (in the actual GUI)

### 1. `move_states` never reached the renderer
`MaterialStateData` was missing the `move_states` field entirely. Fixed late (added field + passthrough), but by then the visual was still wrong.

### 2. Visual output doesn't match reality
Even after the data plumbing fix, the rendered polygon fill doesn't accurately reflect what the tool is actually removing. The semi-transparent blue fill either:
- Doesn't appear at all during playback
- Shows incorrect geometry that doesn't match the toolpath
- Snaps between states rather than smoothly tracking the tool

### 3. Coordinate system complexity
The graph widget uses inverted Y (X+ at bottom for operator POV), plots Z on horizontal axis and X-radius on vertical. The material polygon rendering via `PlotCurveItem` with `fillLevel` doesn't handle this well for arbitrary polygon shapes — it fills to a horizontal baseline which produces visual artifacts for non-rectangular remaining material.

### 4. SimMove-to-tool_moves mapping fragility
The greedy forward-matching by endpoint coordinates (0.001" tolerance) works in tests but may fail in practice when:
- Tool changes produce position jumps
- Canned cycles generate moves not in tool_moves
- Rounding differences between G-code parser and planner exceed tolerance

### 5. Performance concerns
Computing per-move states for every cutting move in a 30-pass profile generates hundreds of Shapely polygon operations. While it meets the 200ms budget in tests, real-world profiles with arcs and cleanup passes may exceed it.

---

## How to Disable/Enable

**Currently disabled via:**
1. `gui/program_tab.py` line ~662: `sim_data = None` (skips compute)
2. `gui/components/sim_viewer.py` line ~218: `self._material_enabled = False`

**To re-enable:**
1. Restore the `material_sim.compute(plan_result)` call in program_tab.py
2. Set `self._material_enabled = True` in sim_viewer.py

**Fallback behavior when disabled:** The graph widget falls through to `_draw_zones_as_image(data)` which renders the rasterized zone shading (the gray bands visible in the screenshot).

---

## Specs for Reference

- `.kiro/specs/material-removal-simulation/` — Original feature spec (32/40 tasks done, 8 optional remaining)
- `.kiro/specs/material-sim-accuracy-fix/` — Bugfix spec for 4 sub-defects (11/11 tasks done)

---

## Recommended Next Steps When Resuming

1. **Fix the rendering approach** — `PlotCurveItem` with `fillLevel` is wrong for arbitrary polygons. Use `pg.FillBetweenItem` or render as a filled `QGraphicsPolygonItem` instead.
2. **Add visual debugging** — Print/log what polygon is being rendered and compare to expected geometry. The data may be correct but the rendering wrong.
3. **Test with real pipeline output** — The PBT tests use synthetic passes. Run the actual pipeline on a real profile and inspect the `move_states` dict contents.
4. **Consider simpler approach** — Instead of per-move polygon subtraction, consider just showing pass-level states (material after each complete pass) which is simpler and more visually stable.
5. **Validate coordinate transforms** — Ensure the polygon X/Z arrays from material_sim match what graph_widget expects (radius for X, inches for Z, with the axis inversion).
