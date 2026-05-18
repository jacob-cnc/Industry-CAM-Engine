# Material Simulation Accuracy Fix — Bugfix Design

## Overview

The material removal simulation in the playback viewer has four interrelated defects that cause the rendered material polygon to not correspond to the tool's actual position during animated playback. The fix targets `_update_material_state()` in `sim_viewer.py` and `_compute_per_move_states()` in `material_sim.py` to: (1) use pre-computed `move_states` for per-move granularity, (2) compute face-pass partial regions by X-position rather than Z-slices, (3) progressively grow arc swept bands instead of showing full removal instantly, and (4) correctly map SimMove interpolated path indices to `PlanResult.tool_moves` indices.

## Glossary

- **Bug_Condition (C)**: The condition that triggers the bug — playback is at an intermediate cutting move within a pass (progress between 0 and 1), and the material polygon does not reflect the tool's actual position
- **Property (P)**: The desired behavior — material polygon matches the pre-computed `move_states[move_index]` data, showing progressive removal as each cutting move completes
- **Preservation**: Existing end-of-pass states, start-of-sim stock display, rapid-move skipping, performance budget, final state, and mode-aware coordinate conventions must remain unchanged
- **`_update_material_state()`**: The method in `gui/components/sim_viewer.py` that maps the current playback move index to a material polygon for display
- **`_compute_per_move_states()`**: The function in `outputs/material_sim.py` that pre-computes per-move material polygons for smooth intra-pass interpolation
- **`move_states`**: A dictionary in `MaterialSimData` keyed by `tool_moves` index → polygon coordinate arrays
- **SimMove index**: The index into the interpolated playback path (derived from G-code parsing), which may differ from `tool_moves` indices
- **`tool_moves` index**: The index into `PlanResult.tool_moves`, used by `toolpath_segments`, `pass_states`, and `move_states`
- **TNR**: Tool Nose Radius — the offset distance used to compute swept band width

## Bug Details

### Bug Condition

The bug manifests when playback is at an intermediate position within a pass (not at the start or end). Four sub-conditions produce incorrect material display:

1. **Snap behavior**: `set_partial_material()` falls through to showing the previous pass state for any intermediate progress, ignoring the pre-computed `move_states` dictionary
2. **Face pass Z-slicing**: `_compute_per_move_states()` clips face-pass partial regions using Z bounds (`box(x_min, partial_z_min, x_max, partial_z_max)`) when face passes move primarily in X
3. **Arc instant removal**: `_compute_per_move_states()` uses `partial_swept = full_swept` for all arc cutting moves, removing the entire arc band at the first cutting move
4. **Index misalignment**: `_update_material_state()` passes the SimMove index (from the interpolated G-code path) directly as `move_idx` into `toolpath_segments[]`, but `toolpath_segments` is built from `PlanResult.tool_moves` which may have a different count/ordering than SimMoves

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type PlaybackState (sim_step, path, graph_data)
  OUTPUT: boolean
  
  move_idx := path[sim_step].move_index  // SimMove index from interpolated path
  segment := graph_data.toolpath_segments[move_idx]
  
  RETURN segment.move_type != RAPID
         AND move_idx is within a pass's move range (not at move_end)
         AND (
           // Sub-condition 1: move_states exist but are not rendered
           move_idx IN graph_data.material_states.move_states.keys()
           AND displayed_polygon != move_states[move_idx]
         ) OR (
           // Sub-condition 2: face pass uses Z-clip instead of X-tracking
           segment.pass_type == FACE AND partial_region uses Z bounds
         ) OR (
           // Sub-condition 3: arc pass shows full removal
           segment.move_type IN (ARC_CW, ARC_CCW) AND partial_swept == full_swept
         ) OR (
           // Sub-condition 4: SimMove index != tool_moves index
           sim_move_index != corresponding_tool_moves_index
         )
END FUNCTION
```

### Examples

- **Snap behavior**: During a 10-move roughing pass, at move 5 the material shows the state from before the pass started (pass N-1 completed state), then jumps to the pass N completed state at move 10. Expected: material progressively shrinks at each move 1–10.
- **Face pass Z-slicing**: A face pass moves from X=1.0" to X=0.5" at Z=0.010". At move 3 (X=0.8"), the material shows a Z-slice removed across the full X range instead of showing material removed only from X=1.0" down to X=0.8".
- **Arc instant removal**: A finish pass with a 0.5" radius arc. At the first arc cutting move, the entire arc band disappears. Expected: the band should grow incrementally as the tool traces the arc.
- **Index misalignment**: G-code has 45 SimMoves (including comments, tool changes parsed as no-ops). `PlanResult.tool_moves` has 38 entries. At SimMove index 30, the system looks up `toolpath_segments[30]` which corresponds to a different physical move than intended.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- End-of-pass material state (when progress reaches 1.0 or move_idx == pass.move_end) must display the same polygon as currently computed by sequential `stock.difference(swept_region)` logic
- Frame 0 (start) must display the full stock polygon unchanged
- Rapid moves (G00) must continue to skip material state updates
- Computation must complete within the 200ms performance budget for profiles with up to 30 passes
- Final state (all passes complete) must display the canonical `stock - union(all swept regions)` polygon
- ID mode vs OD mode must continue using correct coordinate conventions (radius for X, inches for Z)

**Scope:**
All inputs that do NOT involve intermediate intra-pass playback positions should be completely unaffected by this fix. This includes:
- End-of-pass boundary states
- Start/reset state (full stock)
- Show All (final state)
- Rapid move handling
- Slider scrubbing to pass boundaries

## Hypothesized Root Cause

Based on the bug description and code analysis, the root causes are:

1. **`set_partial_material()` ignores `move_states`**: The method in `graph_widget.py` (line ~270) has a comment "The SimViewerWidget handles per-move granularity via move_states" but `_update_material_state()` in `sim_viewer.py` never actually looks up `move_states`. It computes a progress float and calls `set_partial_material(ps_idx, progress)`, which for intermediate progress just shows the previous pass state. The `move_states` dictionary is computed but never consumed during playback.

2. **Face pass partial region uses Z-clip for X-moving passes**: In `_compute_per_move_states()` (material_sim.py ~line 290), the partial swept region for rectangular passes is computed as:
   ```python
   partial_swept = box(x_min_r, partial_z_min, x_max_r, partial_z_max)
   ```
   This clips by Z extent, which is correct for roughing passes (tool moves in -Z). But face passes move primarily in X (from stock OD toward centerline), so the partial region should be clipped by X extent instead.

3. **Arc passes use `partial_swept = full_swept`**: In `_compute_per_move_states()` (~line 310), the else branch for arc passes simply assigns:
   ```python
   partial_swept = full_swept
   ```
   This means every cutting move in an arc pass subtracts the entire arc band, causing instant full removal at the first cutting move.

4. **SimMove index used as `tool_moves` index without mapping**: In `_update_display()` (sim_viewer.py ~line 586), `move_idx` comes from `self._path[self._sim_step]` which is the SimMove index (from G-code parsing). This is passed directly to `_update_material_state(move_idx)` which uses it to index into `graph_data.toolpath_segments[move_idx]`. However, `toolpath_segments` is built from `PlanResult.tool_moves` in `graph_adapter._build_toolpath_segments()`, and the SimMove count may differ from `tool_moves` count due to G-code lines that don't produce ToolMoves (comments, tool changes, M-codes) or vice versa.

## Correctness Properties

Property 1: Bug Condition - Per-Move Material State Rendering

_For any_ playback position where the current move index maps to a cutting move within a pass (isBugCondition returns true), the fixed `_update_material_state` function SHALL render the pre-computed `move_states[tool_moves_index]` polygon data directly, showing material progressively removed as each cutting move completes, with face passes tracking X position and arc passes growing incrementally.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4**

Property 2: Preservation - End-of-Pass and Boundary State Behavior

_For any_ playback position where the bug condition does NOT hold (end-of-pass, start state, rapid moves, final state, or slider at pass boundaries), the fixed code SHALL produce exactly the same material polygon as the original code, preserving all existing pass-completion states, stock display, rapid skipping, and final state rendering.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `gui/components/sim_viewer.py`

**Function**: `_update_material_state()`

**Specific Changes**:
1. **Build SimMove→tool_moves index mapping**: During `load()`, build a mapping from SimMove indices to `tool_moves` indices by correlating endpoint coordinates (X, Z) between the two lists. Store as `self._sim_to_toolmoves: dict[int, int]`.

2. **Use mapping in `_update_material_state()`**: Convert the incoming `move_idx` (SimMove index) to the corresponding `tool_moves` index before looking up `toolpath_segments` or `move_states`.

3. **Look up `move_states` directly**: Instead of computing progress and calling `set_partial_material()`, check if the mapped `tool_moves_index` exists in `graph_data.material_states.move_states`. If it does, render that polygon directly via `_render_material_polygon()`.

4. **Fallback to pass state**: If no `move_states` entry exists for the current index (e.g., it's a rapid or the index is at a pass boundary), fall back to the existing pass-state logic.

---

**File**: `outputs/material_sim.py`

**Function**: `_compute_per_move_states()`

**Specific Changes**:
5. **Fix face pass partial region**: Detect face passes (`turning_pass.pass_type == PassType.FACE`) and clip by X extent instead of Z extent. The partial box should be:
   ```python
   # Face pass: tool moves in X, so clip by X extent traversed
   current_x_r = move.x / 2.0
   partial_swept = box(min(current_x_r, x_min_r), z_end, x_max_r, z_start)
   ```
   This tracks the tool's X position rather than spanning the full X range.

6. **Fix arc pass progressive removal**: Replace `partial_swept = full_swept` with cumulative arc band computation. For each arc cutting move, compute the swept band from the pass start up to the current move's endpoint only:
   - Collect centerline points from `move_start` up to the current `move_idx`
   - Compute the TNR-offset band for just those points
   - Use that partial band as `partial_swept`

7. **Performance guard**: Cache intermediate arc band computations to avoid O(n²) recomputation. Build the arc band incrementally by appending points as we iterate through moves.

---

**File**: `gui/components/graph_widget.py`

**Function**: `set_partial_material()`

**Specific Changes**:
8. **Add `render_move_state()` method**: Add a new method that accepts polygon coordinate arrays directly (from `move_states`) and calls `_render_material_polygon()`. This avoids the progress-based logic entirely for per-move rendering.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write tests that create a `PlanResult` with known passes (face, roughing, arc finish), compute `MaterialSimData`, then simulate playback at intermediate move indices and assert the displayed polygon matches `move_states[index]`. Run these tests on the UNFIXED code to observe failures.

**Test Cases**:
1. **Snap Behavior Test**: Create a 5-move roughing pass, call `_update_material_state(move_3)`, assert material polygon != previous pass state (will fail on unfixed code — shows snap)
2. **Face Pass Z-Slice Test**: Create a face pass moving X from 1.0 to 0.5 at Z=0.01, compute `move_states` for move at X=0.8, assert partial region is clipped by X not Z (will fail on unfixed code)
3. **Arc Instant Removal Test**: Create a finish pass with arc moves, compute `move_states` for first arc cutting move, assert partial swept != full swept (will fail on unfixed code)
4. **Index Mapping Test**: Create a G-code with extra non-move lines, parse SimMoves, compare count to `tool_moves` count, assert mapping exists (will fail on unfixed code if counts differ)

**Expected Counterexamples**:
- `set_partial_material()` returns previous pass state for all intermediate progress values
- Face pass `move_states` entries show Z-sliced polygons instead of X-tracked polygons
- Arc pass `move_states` entries are identical for all moves within the pass (full removal)
- Possible causes: missing `move_states` lookup, incorrect axis for face clip, `full_swept` assignment for arcs

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  result := _update_material_state_fixed(input.move_idx)
  tool_moves_idx := sim_to_toolmoves_map[input.move_idx]
  expected := move_states[tool_moves_idx]
  ASSERT displayed_polygon == expected
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT _update_material_state_original(input) == _update_material_state_fixed(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the input domain (various pass counts, move types, modes)
- It catches edge cases that manual unit tests might miss (zero-length passes, single-move passes, ID mode)
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs

**Test Plan**: Observe behavior on UNFIXED code first for end-of-pass states, start state, rapids, and final state, then write property-based tests capturing that behavior.

**Test Cases**:
1. **End-of-Pass Preservation**: Verify that at `move_end` for each pass, the displayed polygon matches the pass_state polygon (same as unfixed code)
2. **Stock Display Preservation**: Verify that at frame 0 / reset, the full stock polygon is displayed unchanged
3. **Rapid Skip Preservation**: Verify that during rapid moves, no material state update occurs
4. **Final State Preservation**: Verify that "Show All" displays `stock - union(all swept)` polygon identically
5. **Performance Preservation**: Verify computation completes within 200ms for 30-pass profiles
6. **Mode Preservation**: Verify ID mode and OD mode produce correct coordinate conventions

### Unit Tests

- Test `_build_sim_to_toolmoves_mapping()` with matching and mismatched move counts
- Test face pass partial region computation clips by X extent
- Test arc pass partial band grows incrementally (move N has smaller band than move N+1)
- Test `_update_material_state()` renders `move_states` entry when available
- Test fallback to pass state when `move_states` entry is missing (rapid moves)

### Property-Based Tests

- Generate random `PlanResult` configurations (1–30 passes, mixed types) and verify `move_states` entries are monotonically "smaller" (less material) within each pass
- Generate random face passes with varying X ranges and verify partial regions track X position
- Generate random arc passes and verify partial swept band area grows monotonically with move index
- Generate random playback positions at pass boundaries and verify preservation of end-state polygons

### Integration Tests

- Full pipeline test: generate G-code from a profile, compute `MaterialSimData`, simulate playback frame-by-frame, verify material polygon changes at each cutting move
- Round-trip test: verify that the final `move_states` entry for each pass matches the `pass_states` polygon
- Visual regression test: compare rendered polygon sequences against known-good reference data for OD arc profile and ID bore profile
