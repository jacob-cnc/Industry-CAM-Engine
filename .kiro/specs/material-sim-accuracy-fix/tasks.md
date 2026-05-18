# Implementation Plan

## Overview

Fix four interrelated defects in the material removal simulation playback viewer: (1) snap behavior ignoring `move_states`, (2) face pass Z-slicing instead of X-tracking, (3) arc instant removal, and (4) SimMove-to-tool_moves index misalignment. The fix targets `_update_material_state()` in `sim_viewer.py`, `_compute_per_move_states()` in `material_sim.py`, and `graph_widget.py`.

## Tasks

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - Per-Move Material State Not Rendered During Intra-Pass Playback
  - **IMPORTANT**: Write this property-based test BEFORE implementing the fix
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate all four sub-defects exist
  - **Scoped PBT Approach**: Scope the property to concrete failing cases for each sub-condition:
    - Sub-condition 1 (Snap): Create a 5-move roughing pass, call `_update_material_state(move_3)`, assert displayed polygon == `move_states[3]` (not previous pass state)
    - Sub-condition 2 (Face Z-slice): Create a face pass moving X from 1.0 to 0.5 at Z=0.01, compute `move_states` at X=0.8, assert partial region is clipped by X extent not Z extent
    - Sub-condition 3 (Arc instant removal): Create a finish pass with arc moves, compute `move_states` for first arc cutting move, assert `partial_swept != full_swept` (band should be partial)
    - Sub-condition 4 (Index misalignment): Create G-code with extra non-move lines (comments, M-codes), parse SimMoves, assert `sim_to_toolmoves` mapping exists and `toolpath_segments[mapped_idx]` matches expected move
  - Bug condition from design: `isBugCondition(input)` returns true when `move_type != RAPID AND move_idx is within pass range AND (move_states not rendered OR face uses Z-clip OR arc uses full_swept OR sim_index != tool_moves_index)`
  - Expected behavior: `move_states[tool_moves_index]` polygon is rendered directly, face passes track X, arcs grow incrementally, index mapping is correct
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS (this is correct - it proves the bug exists)
  - Document counterexamples found:
    - `set_partial_material()` returns previous pass state for all intermediate progress values
    - Face pass `move_states` entries show Z-sliced polygons instead of X-tracked polygons
    - Arc pass `move_states` entries are identical for all moves within the pass (full removal at first move)
    - SimMove index 30 maps to wrong `toolpath_segments` entry when G-code has non-move lines
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - End-of-Pass, Boundary State, and Non-Buggy Input Behavior
  - **IMPORTANT**: Follow observation-first methodology
  - **Observe behavior on UNFIXED code for non-buggy inputs** (cases where `isBugCondition` returns false):
    - Observe: At `move_end` for each pass, displayed polygon matches `pass_states[pass_idx]` on unfixed code
    - Observe: At frame 0 (start/reset), full stock polygon is displayed unchanged on unfixed code
    - Observe: During rapid moves (G00), no material state update occurs on unfixed code
    - Observe: At "Show All" (final state), `stock - union(all swept)` polygon is displayed on unfixed code
    - Observe: Computation completes within 200ms for 30-pass profiles on unfixed code
    - Observe: ID mode and OD mode produce correct coordinate conventions (radius for X, inches for Z) on unfixed code
  - Write property-based tests capturing observed behavior patterns from Preservation Requirements:
    - For all pass indices `p` and at `move_end` position: `displayed_polygon == pass_states[p]`
    - For frame 0: `displayed_polygon == stock_polygon`
    - For all rapid move indices: `material_state` is unchanged (no subtraction)
    - For final state: `displayed_polygon == stock.difference(union(all_swept_regions))`
    - For random profiles with 1-30 passes: computation time < 200ms
    - For ID mode inputs: X coordinates are radius values; for OD mode: same convention preserved
  - Property-based testing generates many test cases for stronger preservation guarantees
  - Run tests on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (this confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

- [x] 3. Fix material simulation accuracy defects

  - [x] 3.1 Build SimMove-to-tool_moves index mapping in `sim_viewer.py`
    - In `load()` method, build a mapping `self._sim_to_toolmoves: dict[int, int]` by correlating endpoint coordinates (X, Z) between SimMove path entries and `PlanResult.tool_moves` entries
    - Handle cases where SimMove count differs from tool_moves count (G-code comments, tool changes, M-codes produce SimMoves without corresponding tool_moves)
    - Store mapping for use in `_update_material_state()`
    - _Bug_Condition: sim_move_index != corresponding_tool_moves_index (sub-condition 4)_
    - _Expected_Behavior: Verified mapping between SimMove indices and PlanResult.tool_moves indices_
    - _Preservation: Non-buggy inputs (rapids, pass boundaries) must still resolve correctly_
    - _Requirements: 1.4, 2.4_

  - [x] 3.2 Update `_update_material_state()` to use `move_states` lookup in `sim_viewer.py`
    - Convert incoming `move_idx` (SimMove index) to `tool_moves` index using `self._sim_to_toolmoves` mapping
    - Check if mapped `tool_moves_index` exists in `graph_data.material_states.move_states`
    - If entry exists, render that polygon directly via `_render_material_polygon()` (or new `render_move_state()` method)
    - If no entry exists (rapid move or pass boundary), fall back to existing pass-state logic
    - _Bug_Condition: move_states exist but are not rendered (sub-condition 1); index misalignment (sub-condition 4)_
    - _Expected_Behavior: move_states[tool_moves_index] polygon rendered directly for intermediate cutting moves_
    - _Preservation: End-of-pass, start state, rapids, final state must use existing logic unchanged_
    - _Requirements: 1.1, 1.4, 2.1, 2.4, 3.1, 3.2, 3.3_

  - [x] 3.3 Fix face pass partial region to track X position in `material_sim.py`
    - In `_compute_per_move_states()`, detect face passes (`turning_pass.pass_type == PassType.FACE`)
    - Replace Z-extent clipping with X-extent clipping for face passes:
      ```python
      # Face pass: tool moves in X, clip by X extent traversed
      current_x_r = move.x / 2.0
      partial_swept = box(min(current_x_r, x_min_r), z_end, x_max_r, z_start)
      ```
    - Keep Z-extent clipping for roughing passes (tool moves in -Z) unchanged
    - _Bug_Condition: face pass uses Z-clip instead of X-tracking (sub-condition 2)_
    - _Expected_Behavior: Partial swept region tracks tool's actual X position_
    - _Preservation: Roughing pass partial regions must remain Z-clipped as before_
    - _Requirements: 1.2, 2.2_

  - [x] 3.4 Fix arc pass progressive removal in `material_sim.py`
    - In `_compute_per_move_states()`, replace `partial_swept = full_swept` for arc passes with cumulative arc band computation
    - For each arc cutting move, compute swept band from pass start up to current move's endpoint only:
      - Collect centerline points from `move_start` up to current `move_idx`
      - Compute TNR-offset band for just those points
      - Use that partial band as `partial_swept`
    - Cache intermediate arc band computations to avoid O(n²) recomputation (build incrementally by appending points)
    - _Bug_Condition: arc pass shows full removal at first cutting move (sub-condition 3)_
    - _Expected_Behavior: Cumulative swept region grows incrementally with each arc cutting move_
    - _Preservation: Final arc move must produce same full_swept result as before_
    - _Requirements: 1.3, 2.3_

  - [x] 3.5 Add `render_move_state()` method to `graph_widget.py`
    - Add new method that accepts polygon coordinate arrays directly (from `move_states`) and calls `_render_material_polygon()`
    - Bypasses progress-based logic entirely for per-move rendering
    - _Bug_Condition: set_partial_material() ignores move_states (sub-condition 1)_
    - _Expected_Behavior: Direct polygon rendering from pre-computed move_states data_
    - _Preservation: Existing set_partial_material() method remains unchanged for pass-level rendering_
    - _Requirements: 2.1_

  - [x] 3.6 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - Per-Move Material State Rendering
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior for all four sub-conditions
    - When this test passes, it confirms:
      - `move_states` entries are rendered for intermediate cutting moves (snap fixed)
      - Face pass partial regions track X position (Z-slice fixed)
      - Arc pass swept bands grow incrementally (instant removal fixed)
      - SimMove indices correctly map to tool_moves indices (misalignment fixed)
    - Run bug condition exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms all four defects are fixed)
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [x] 3.7 Verify preservation tests still pass
    - **Property 2: Preservation** - End-of-Pass and Boundary State Behavior
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm all preservation tests still pass after fix:
      - End-of-pass polygons unchanged
      - Start state (full stock) unchanged
      - Rapid move skipping unchanged
      - Final state unchanged
      - Performance within 200ms budget
      - ID/OD mode coordinate conventions unchanged

- [x] 4. Checkpoint - Ensure all tests pass
  - Run full test suite to confirm both exploration and preservation tests pass
  - Verify no regressions in existing material simulation tests
  - Ensure all tests pass, ask the user if questions arise


## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1", "2"] },
    { "id": 1, "tasks": ["3.1", "3.3", "3.4", "3.5"] },
    { "id": 2, "tasks": ["3.2"] },
    { "id": 3, "tasks": ["3.6"] },
    { "id": 4, "tasks": ["3.7"] },
    { "id": 5, "tasks": ["4"] }
  ]
}
```

## Notes

- Tasks 1 and 2 MUST be completed BEFORE any implementation tasks (3.x) begin
- Task 1 is expected to FAIL on unfixed code — this confirms the bug exists
- Task 2 is expected to PASS on unfixed code — this captures baseline behavior
- Tasks 3.1–3.5 can be implemented in parallel after tasks 1 and 2 are complete, except 3.1 must precede 3.2
- Tasks 3.6 and 3.7 re-run the SAME tests from tasks 1 and 2 respectively — no new tests are written
- The 200ms performance budget (requirement 3.4) applies to profiles with up to 30 passes
- Arc band caching in task 3.4 is critical to avoid O(n²) recomputation during incremental band building
