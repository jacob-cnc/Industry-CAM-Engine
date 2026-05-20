# 2026-05-20 — Compound Slide Feature Buildout

## Summary

Built out the compound slide feature into a fully robust implementation with
unit tests, preset angles, distance reset, proper HAL wiring, and fixed the
NE/SE NW/SW quadrant inversion and Arc Top/Bottom start type inversion.

---

## Changes Made

### 1. Unit Tests (64 tests in 2 files)

- `tests/unit/test_compound_logic.py` — Pure logic layer tests:
  - Angle validation, pulse decomposition, soft limits, distance accumulation
  - Arc radius validation, quadrant ranges, activation, process_pulse, get_arc_points
- `tests/unit/test_compound_integration.py` — Integration-level tests:
  - Preset angles, distance reset, fractional accumulator, axis coupling, edge cases

### 2. Preset Angle Buttons

- Added `CompoundLinearLogic.PRESETS` dict: 29.5° Thread, 45° Chamfer, 60° Dovetail, 30° Taper
- Row of buttons in the UI that set the angle with one click
- Hidden when in Arc mode (not applicable)

### 3. Distance Reset Button

- "Reset" button next to the distance display
- Zeros the counter without deactivating compound mode
- Uses `reset_distance()` method (preserves active state)

### 4. postgui.hal — Mux2 Wiring

- Full mux2-based routing: `mux2.x-jog` and `mux2.z-jog` select between
  direct MPG counts (normal jog) and compound-slide output (compound jog)
- `compound-slide.compound-enable` drives the mux select pins
- MPG scale selection routed through the compound-slide component
- `postgui-simple.hal` — fallback version for commissioning without compound

### 5. Radius Validation Wiring

- Connected `input_radius.editingFinished` → `_on_compound_radius_changed()`
- Validates using `CompoundArcLogic.validate_radius()`, reverts to "0.250" on invalid

### 6. Fixed NE/SE NW/SW Quadrant Inversion

The arc logic uses `atan2(dx, dz)` convention where +X is at π/2. On the
inverted-Y graph, +X is at the bottom. So the logic's "NE" quadrant (0 to π/2)
draws bottom-right on the graph — which is visually "SE" to the operator.

Fix in `_get_selected_quadrant()`:
- User "NE" (top-right on graph) → Logic `Quadrant.SE` (3π/2 to 2π)
- User "SE" (bottom-right on graph) → Logic `Quadrant.NE` (0 to π/2)
- User "NW" (top-left on graph) → Logic `Quadrant.SW` (π to 3π/2)
- User "SW" (bottom-left on graph) → Logic `Quadrant.NW` (π/2 to π)

Quadrant graphic receives user-facing enum directly (not the swapped logic enum).

### 7. Fixed Arc Top/Bottom Start Type Inversion

- The start_type mapping was backwards: "Arc Top" was mapped to `ARC_BOTTOM`
- Fixed to: index 0 ("Arc Top") → `ARC_TOP`, index 1 ("Arc Bottom") → `ARC_BOTTOM`
- For north quadrants (NE, NW), the N↔S swap also inverts top/bottom meaning,
  so the start_type is flipped for those cases

### 8. UI Layout Reformat

- Quadrant graphic enlarged from 60×60 to 150×150 with 60px radius arcs
- All fields use `stretch=1` to fill the full section width
- Arc container has `minHeight=160` to guarantee graphic space
- Preset buttons fill width equally
- Distance display + reset button on same row
- Touch-friendly heights (30px for inputs/combos, 36px for activate button)

---

## Removed

- **Distance target (auto-stop)** — removed per user request. The feature
  added `set_distance_target()`, `has_reached_target()`, `remaining_distance()`
  and a target input field. All removed; the simpler distance reset is sufficient.

---

## Test Results

All 157 tests pass (93 pre-existing + 64 new compound tests).

---

## Files Modified

| File | Change |
|------|--------|
| `hal/compound_logic.py` | Added PRESETS, reset_distance(); removed distance_target |
| `gui/manual/sections.py` | Rebuilt compound section layout (presets, reset, full-width) |
| `gui/manual/manual_tab.py` | Wired presets, reset, radius validation; fixed quadrant/start inversions |
| `gui/components/quadrant_graphic.py` | Enlarged to 150×150, updated paint coords |
| `postgui.hal` | Full mux2 routing for compound mode |
| `postgui-simple.hal` | NEW — fallback direct routing |
| `tests/unit/test_compound_logic.py` | NEW — 48 logic tests |
| `tests/unit/test_compound_integration.py` | NEW — 16 integration tests |
