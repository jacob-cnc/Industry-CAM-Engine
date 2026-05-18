# Implementation Plan: Material Removal Simulation

## Overview

This plan implements a dynamic material removal visualization for the Industry CAM Engine. The simulation engine (`outputs/material_sim.py`) pre-computes all material states using Shapely polygon subtraction after the pipeline completes. The graph adapter serializes these into numpy coordinate arrays, and the `MachiningGraphWidget` renders them as vector polygon fills using PyQtGraph — keeping the GUI free of Shapely dependencies. Playback indexes into pre-computed states for zero per-frame geometry work.

## Tasks

- [x] 1. Create material simulation engine core
  - [x] 1.1 Create `outputs/material_sim.py` with data models and stock polygon construction
    - Create `PassState` and `MaterialSimData` dataclasses as defined in the design
    - Implement `_build_stock_polygon()` for OD mode (X: x_start/2 to diameter/2) and ID mode (X: pilot_hole_dia/2 to x_start/2)
    - Implement `_polygon_to_arrays()` to convert Shapely Polygon/MultiPolygon to list of (x_ndarray, z_ndarray) tuples
    - Use RADIUS coordinates for X and INCHES for Z matching the validator convention
    - _Requirements: 3.2, 3.3, 2.5, 10.1_

  - [x] 1.2 Implement rectangular swept region computation for face and roughing passes
    - Implement `_compute_swept_region_polygon()` for face/roughing passes using `shapely.geometry.box(x_min/2, z_end, x_max/2, z_start)` from TurningPass bounds
    - Handle the SweptRegion dataclass fields (x_min, x_max are in DIAMETER — convert to radius for Shapely polygon)
    - Apply `make_valid()` if polygon is invalid, log warning without blocking
    - _Requirements: 1.1, 1.4, 1.5_

  - [x] 1.3 Implement arc swept band computation for cleanup and finish passes
    - Implement `_compute_arc_swept_band()` that offsets the toolpath arc inward and outward by TNR
    - Use `adaptive_densify_arc()` with `SHAPELY_COS_LIMIT` and `MAX_DENSIFICATION_DEPTH` from `models/constants.py`
    - Construct the closed polygon boundary from the offset curves
    - Fall back to rectangular polygon for linear-only cleanup/finish passes
    - _Requirements: 1.2, 1.3, 7.1, 7.4_

  - [ ]* 1.4 Write property tests for swept region computation (Properties 1, 2, 3)
    - **Property 1: Rectangular SweptRegion bounds correctness** — For any face/roughing pass, bounding box equals (x_min/2, z_end, x_max/2, z_start)
    - **Property 2: Arc swept band width equals 2×TNR** — For any arc pass with TNR, width perpendicular to centerline is within TOLERANCE of 2×TNR
    - **Property 3: Coordinate convention invariant** — All X in RADIUS, all Z in INCHES
    - **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 7.2**

- [x] 2. Implement sequential material subtraction and pre-computation
  - [x] 2.1 Implement basic sequential pass subtraction
    - Iterate TurningPass objects in order, compute SweptRegion polygon for each
    - Perform sequential `stock_polygon.difference(swept_region)` to produce pass_states
    - Store one PassState per TurningPass with move_start/move_end indices
    - _Requirements: 2.1, 2.2_

  - [x] 2.2 Handle MultiPolygon results and performance optimization
    - Handle MultiPolygon results by retaining all component polygons
    - Handle degenerate/invalid intermediate polygons via `make_valid()`
    - Target < 200ms for profiles with up to 30 passes
    - Add timing instrumentation
    - _Requirements: 2.4, 2.6_

  - [x] 2.3 Implement per-move material state computation for smooth interpolation
    - For each cutting move (FEED, ARC_CW, ARC_CCW) within a pass, compute the partial swept region
    - Store in `move_states` dict keyed by move_index
    - Skip rapid moves (no material removal during rapids)
    - Convert all per-move states to numpy coordinate arrays
    - _Requirements: 2.3, 4.4_

  - [x] 2.4 Implement final state computation and timing metadata
    - Compute `final_state` as stock minus union of all swept regions
    - Record `computation_time_ms` for performance monitoring
    - Handle edge case: zero passes returns stock polygon as both initial and final state
    - Handle edge case: empty/degenerate polygon recovery via `make_valid()`
    - _Requirements: 2.5, 5.1_

  - [ ]* 2.5 Write property tests for sequential subtraction (Properties 4, 5, 8)
    - **Property 4: Sequential subtraction produces correct Pass_States** — pass_states[i] equals stock.difference(union(swept_regions[0..i]))
    - **Property 5: Per-move swept regions exist for cutting moves only** — entries exist for FEED/ARC_CW/ARC_CCW, not for RAPID
    - **Property 8: No material removal during rapids** — material state before and after a rapid move is geometrically identical
    - **Validates: Requirements 2.1, 2.2, 2.3, 4.4**

- [x] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Extend graph adapter with material state serialization
  - [x] 4.1 Add `MaterialStateData` dataclass and extend `GraphData` in `outputs/graph_adapter.py`
    - Add `MaterialStateData` dataclass with `stock_x`, `stock_z`, `pass_states`, `final_x`, `final_z` fields
    - Add `material_states: Optional[MaterialStateData] = None` field to `GraphData`
    - _Requirements: 10.2_

  - [x] 4.2 Implement `_convert_material_sim()` helper and update `convert()` function
    - Add optional `material_sim_data: Optional[MaterialSimData] = None` parameter to `convert()`
    - Implement `_convert_material_sim()` that maps `MaterialSimData` into `MaterialStateData` coordinate arrays
    - Ensure no Shapely import in graph_adapter — only receive pre-computed arrays from material_sim
    - _Requirements: 10.1, 10.2, 10.3_

  - [ ]* 4.3 Write property test for polygon-to-array round trip (Property 6)
    - **Property 6: Polygon-to-coordinate-array round trip** — Converting to arrays and reconstructing produces geometrically equivalent polygon (symmetric difference area < TOLERANCE²)
    - **Validates: Requirements 2.5, 10.1**

- [x] 5. Implement vector material rendering in MachiningGraphWidget
  - [x] 5.1 Add material polygon rendering infrastructure to `gui/components/graph_widget.py`
    - Add `_material_fill_items` list to track active PyQtGraph fill items
    - Implement `_render_material_polygon()` using `PlotCurveItem` + `FillBetweenItem` for vector fills
    - Handle MultiPolygon (multiple fill items for disconnected regions)
    - Ensure rendering remains sharp at all zoom levels (vector, not raster)
    - _Requirements: 3.4, 4.5_

  - [x] 5.2 Implement `set_material_state()`, `set_material_to_stock()`, and `set_material_to_final()` methods
    - `set_material_state(pass_index)`: load pre-computed coordinate arrays for the given pass, call `_render_material_polygon()`
    - `set_material_to_stock()`: render the full stock polygon (reset state)
    - `set_material_to_final()`: render the final pass state within one frame (< 16ms from pre-computed arrays)
    - _Requirements: 5.1, 5.2, 6.1_

  - [x] 5.3 Implement `set_partial_material()` for smooth intra-pass interpolation
    - Accept `pass_index` and `progress` (0.0 to 1.0) parameters
    - Clip the full swept region to the partial extent based on current tool Z position
    - Subtract partial swept region from previous pass state for display
    - _Requirements: 4.1, 4.2, 4.3_

  - [x] 5.4 Update `set_graph_data()` to initialize material state from `GraphData.material_states`
    - When `material_states` is present, create initial stock polygon fill items
    - When `material_states` is None, fall back to existing `_draw_zones_as_image()` rasterization (graceful degradation)
    - _Requirements: 3.1, 8.1_

- [x] 6. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Integrate material removal into SimViewerWidget playback
  - [x] 7.1 Add `_material_enabled` feature flag to `SimViewerWidget` in `gui/components/sim_viewer.py`
    - Add a `self._material_enabled: bool = True` attribute in `__init__()`
    - Guard all material-related calls (`set_partial_material`, `set_material_to_stock`, `set_material_to_final`, `set_material_state`) behind `if self._material_enabled`
    - When `_material_enabled` is False, skip all material polygon updates — playback, Show All, Reset, and slider scrub behave as if the feature does not exist
    - This allows the entire material removal visualization to be disabled with a single toggle without modifying any other code
    - _Requirements: 8.1_

  - [x] 7.2 Wire material state updates into `_update_display()` in `gui/components/sim_viewer.py`
    - Map current `move_index` to owning pass via `ToolMove.pass_index`
    - Call `graph.set_partial_material(pass_index, progress)` during cutting moves
    - Skip material updates during rapid moves
    - Ensure toolpath line reveal and `sim_line_changed` signals continue to emit
    - All material calls guarded by `self._material_enabled`
    - _Requirements: 4.1, 4.4, 8.1, 8.2_

  - [x] 7.3 Wire "Show All" and "Reset" buttons to material state methods
    - In `_sim_show_all()`: call `graph.set_material_to_final()` if `self._material_enabled`
    - In `_sim_stop()`: call `graph.set_material_to_stock()` if `self._material_enabled`
    - _Requirements: 5.1, 6.1, 6.2_

  - [x] 7.4 Implement slider scrubbing support for material state
    - In `_on_slider()`: determine the last completed pass at or before the slider position
    - Call `graph.set_material_state(last_completed_pass_index)` if `self._material_enabled`
    - Handle edge case: slider at position before any pass completes → show full stock
    - _Requirements: 8.3, 8.4_

  - [ ]* 7.5 Write property tests for slider mapping and reset (Properties 9, 11)
    - **Property 9: Reset restores initial stock polygon** — After any number of passes, reset produces polygon identical to initial stock
    - **Property 11: Slider position maps to correct Pass_State** — Slider at move M displays pass_states[K] where K is last completed pass at or before M
    - **Validates: Requirements 6.1, 8.4**

- [x] 8. Implement OD/ID mode support and validator agreement
  - [x] 8.1 Ensure correct subtraction direction for OD and ID modes in `material_sim.py`
    - OD mode: subtract from outer stock boundary inward toward finished part
    - ID mode: subtract from inner bore boundary outward toward finished part
    - Verify stock polygon construction uses correct X ranges per mode
    - _Requirements: 9.1, 9.2_

  - [x] 8.2 Ensure geometric accuracy agreement with validator parameters
    - Use same `SHAPELY_COS_LIMIT`, `MAX_DENSIFICATION_DEPTH` as `validation/polygon_builder.py`
    - Use same coordinate convention (RADIUS for X, INCHES for Z)
    - Construct arc swept bands from same I/K center offsets and TNR values as toolpath planner
    - Verify SweptRegion does not penetrate finished_part_poly beyond TOLERANCE
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [ ]* 8.3 Write property tests for mode support and validator agreement (Properties 7, 10, 12)
    - **Property 7: Stock polygon bounds match mode parameters** — OD: X=[x_start/2, diameter/2], ID: X=[pilot_hole_dia/2, x_start/2]
    - **Property 10: SweptRegion does not penetrate finished part beyond tolerance** — Intersection area < TOLERANCE²
    - **Property 12: Subtraction direction matches machining mode** — OD remaining max X ≤ stock max X; ID remaining min X ≥ stock min X
    - **Validates: Requirements 3.2, 3.3, 7.3, 9.1, 9.2**

- [x] 9. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Wire pipeline output to material simulation
  - [x] 10.1 Call `material_sim.compute()` after pipeline produces PlanResult
    - In the appropriate call site (where PlanResult is consumed), invoke `material_sim.compute(plan_result)`
    - Pass the resulting `MaterialSimData` to `graph_adapter.convert(plan_result, material_sim_data=sim_data)`
    - Handle failure gracefully: if `compute()` raises, log error and pass `None` (falls back to raster zones)
    - _Requirements: 2.1, 10.2_

  - [x] 10.2 Ensure `MachiningGraphWidget` receives and renders material states end-to-end
    - Verify `GraphData.material_states` flows from pipeline → material_sim → graph_adapter → graph_widget
    - Confirm existing toolpath reveal, G-code sync, and playback controls remain functional
    - Confirm "Hide Rapids" toggle works independently of material removal
    - _Requirements: 8.1, 8.2, 8.3, 8.5_

- [ ] 11. Write unit tests for material simulation
  - [ ]* 11.1 Write unit tests in `tests/unit/test_material_sim.py`
    - Test stock polygon construction for specific OD/ID configurations
    - Test rectangular swept region for a known face pass
    - Test arc swept band for a known cleanup pass with specific I/K/TNR
    - Test MultiPolygon handling when subtraction splits material
    - Test Show All loads final state correctly
    - Test Reset clears to stock
    - Test empty PlanResult (zero passes) produces stock-only result
    - Test degenerate polygon recovery via make_valid
    - _Requirements: 1.1, 1.2, 2.1, 3.2, 5.1, 6.1_

  - [ ]* 11.2 Write integration tests in `tests/integration/test_material_sim_integration.py`
    - Test full pipeline → material_sim → graph_adapter → GraphData round trip
    - Test performance: < 200ms for 30-pass OD profile
    - Test performance: Show All displays in < 16ms (pre-computed array load)
    - Test compatibility: toolpath reveal still works alongside material removal
    - Test compatibility: sim_line_changed signal still emits during playback
    - _Requirements: 2.4, 5.2, 8.1, 8.2_

- [x] 12. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The implementation language is Python (Shapely, numpy, PyQtGraph) matching the existing codebase
- All X coordinates use RADIUS internally; Z in INCHES — matching the validator convention
- Graceful degradation: if material_sim fails, the widget falls back to existing raster zone shading

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "4.1"] },
    { "id": 2, "tasks": ["1.4", "2.1", "4.2"] },
    { "id": 3, "tasks": ["2.2", "2.3", "4.3"] },
    { "id": 4, "tasks": ["2.4", "2.5", "5.1"] },
    { "id": 5, "tasks": ["5.2", "5.3", "5.4"] },
    { "id": 6, "tasks": ["7.1", "8.1"] },
    { "id": 7, "tasks": ["7.2", "7.3", "7.4", "8.2"] },
    { "id": 8, "tasks": ["7.5", "8.3"] },
    { "id": 9, "tasks": ["10.1"] },
    { "id": 10, "tasks": ["10.2", "11.1"] },
    { "id": 11, "tasks": ["11.2"] }
  ]
}
```
