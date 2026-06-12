# Session Notes — 2026-06-05: Multi-Block, Threading, Grooving

## Summary

Major feature session implementing the P2 multi-block program architecture, threading (G76), and grooving/parting planners. Also fixed several pre-existing issues in the G-code writer approach logic and peck roughing.

---

## Work Completed

### 1. Tool Change Between Roughing and Finishing (M0 + M6)

**Problem:** The Program Tab collected separate tool numbers for roughing and finishing, but the pipeline only supported a single `ToolDef`. The G-code writer had dead-code branches for tool changes.

**Solution:**
- Added `finish_tool: Optional[ToolDef]` to `PlanResult`
- Added `finish_tool` parameter to `pipeline.execute()`
- G-code writer now compares roughing/finishing tool numbers and emits: G40 → park → M5 → **M0** → T# M6 → G43 → S# M3 → G41/G42
- GUI resolves the finish tool from the tool table via a `_tool_resolver` callback set by `main_window`
- Handles both cases: cleanup exists (tool change after cleanup) and no cleanup (tool change before finish)

### 2. Peck Roughing Implementation

**Problem:** The peck checkbox in the UI had no effect — `RoughingParams.peck_enabled` was never read by any planner.

**Solution:**
- Added `MoveType.DWELL` to the enum (maps to G04)
- Implemented `_make_pass_moves()` in `StaircasePlanner` — splits feed moves at `peck_length` intervals with G04 dwell moves between them
- Dwell time = `(5 / RPM) * 60` seconds (5 spindle revolutions for chip break)
- Added `_dwell()` method to G-code writer (emits `G04 P{seconds}`)
- Excluded DWELL from zero-length move filters in pipeline and validator

### 3. Roughing Approach Optimization

**Problem:** Normal roughing passes were feeding from the retract position (stock OD) all the way to the DOC level — wasting time feeding through air on deeper passes.

**Solution:** For normal passes, rapid to the previously-cleared X level (one DOC back), then feed only the last DOC into material. Valley passes already had this logic; normal passes were missing it.

### 4. Multi-Block Data Model

**New file: `models/program.py`**
- `ThreadingParams` — frozen dataclass for G76 cycle (standard, pitch, depth, infeed, passes, spring passes, chamfer, taper, multi-start)
- `GroovingParams` — frozen dataclass for grooving/parting (Z extent, depth, peck config, blade width)
- `ProgramBlock` — mutable dataclass for block list management (type, tool, enabled, visible, params_data dict)

Added `THREADING` and `GROOVING` to `PassType` enum.

### 5. Threading Planner

**New file: `planners/threading_planner.py`**
- `compute_g76_params()` — derives all G76 word values (P, Z, I, J, K, R, Q, H, E, L)
- `compute_pass_depths()` — constant-area (sqrt) progression for infeed
- `plan()` — produces approach/retract ToolMoves for graph visualization
- Validates max Z velocity (pitch × RPM ≤ 1.5 in/s machine limit)
- Handles tapered threads (NPT), multi-start, all infeed methods

### 6. Grooving Planner

**New file: `planners/grooving_planner.py`**
- `_compute_plunge_positions()` — distributes blade-width plunges to fill groove width with overlap only when remainder requires it
- `_make_plunge_moves()` — single plunge or peck cycle with retract
- Handles OD and ID grooving, validates parting depth
- No side-cutting — grooving tools plunge only

### 7. G-code Writer Extensions

- `write_threading_block()` — emits G76 cycle with header comments, approach/retract
- `write_grooving_block()` — emits multi-position plunge cycles with peck
- `write_tool_change()` — reusable M0/M6 sequence between any blocks

### 8. Block List GUI Widget

**New file: `gui/components/block_list.py`**
- `BlockListWidget` — QListWidget with drag-drop reorder
- Add menu (7 block types), Duplicate, Move Up/Down, Visibility toggle, Delete
- Each block shows: index, label, tool number, visibility state

### 9. Threading & Grooving Parameter Panels

**New files: `gui/components/threading_panel.py`, `gui/components/grooving_panel.py`**
- Threading: standard/size dropdowns, auto-fill TPI/depth, infeed method, passes, Z positions
- Grooving: Z start/end, depth, peck config, blade width, computed plunge count

### 10. Program Tab Refactor (Multi-Block)

- Block list added as a collapsible section at the top of the left panel
- Old "Toolpath Type" combo hidden (replaced by block list)
- Section visibility switches based on active block type (profile/threading/grooving)
- **Per-block data isolation:** `_save_active_block_data()` / `_restore_block_data()` saves/restores all field values when switching blocks
- **Multi-block Generate:** iterates all visible+enabled blocks, runs profile pipeline or threading/grooving planners, inserts tool changes, combines into one G-code program
- **Multi-block Save/Load:** version 2 format saves `"blocks"` array with full params_data per block; backward-compatible with version 1 (legacy single-block) files
- **Multi-profile preview:** all visible profile blocks' contours drawn on the graph (active = bold white, others = dim)

### 11. Misc Fixes

- Fixed `UnboundLocalError: 'ToolType'` caused by redundant local import shadowing module-level import
- Fixed profile preview drawing from X=0 (centerline) — now starts at first segment's X
- Decreased playback sim speed by 50% (base interval 100ms → 200ms)

---

## File Changes Summary

### New Files
- `models/program.py` — ThreadingParams, GroovingParams, ProgramBlock
- `planners/threading_planner.py` — G76 parameter computation
- `planners/grooving_planner.py` — Multi-position peck plunge planning
- `gui/components/block_list.py` — Block list management widget
- `gui/components/threading_panel.py` — Threading parameter UI
- `gui/components/grooving_panel.py` — Grooving parameter UI

### Modified Files
- `models/moves.py` — Added DWELL, THREADING, GROOVING to enums
- `models/results.py` — Added `finish_tool` field to PlanResult
- `models/__init__.py` — Exports new types
- `pipeline/pipeline.py` — `finish_tool` parameter, DWELL in zero-length filter
- `outputs/gcode_writer.py` — Threading/grooving/tool-change writers, DWELL support, approach optimization
- `planners/staircase_planner.py` — Peck roughing implementation
- `validation/pre_output_validator.py` — DWELL excluded from zero-length check
- `gui/program_tab.py` — Multi-block generate, save/load, block switching, profile preview
- `gui/main_window.py` — Tool resolver wiring
- `gui/components/playback_controller.py` — 50% speed reduction

---

## Design Decisions

1. **G76 over manual G33 passes:** LinuxCNC's G76 handles spindle-synchronized multi-pass threading internally. Our job is computing the parameters — the controller does the real-time work.

2. **Grooving = radial plunge only:** No side-cutting. For grooves wider than blade width, multiple adjacent plunges fill the width. Overlap only when remainder < blade_width.

3. **Independent stock per block:** Each block carries its own stock/param data rather than a shared program-level stock definition. Avoids risky pipeline refactor.

4. **Visibility = generation filter:** Hidden blocks are skipped during Generate. This lets operators quickly test subsets without deleting blocks.

5. **Version 2 file format:** Backward-compatible — old version 1 files auto-migrate to a single-block program on load.

---

## Test Results

290 tests passing (1 pre-existing failure in `test_quadrant_arc_pipeline` — cleanup arc gouge, unrelated to this session's work).
