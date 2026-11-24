# Implementation Plan: Drilling Cycles

## Overview

Add on-center axial drilling as a new conversational operation. Implementation proceeds bottom-up:
models first (params, enum, block type), then the planner and its validation, then the G-code writer,
then the Program-tab panel and dispatch, then the Tools-tab drill support and graphic. Drilling
follows the grooving/threading block-writer pattern and bypasses `pipeline.execute()`, so no
`pipeline/model_builder.py` changes are needed.

Phasing: tasks 1–6 deliver Center/Spot/Twist/Reamer drilling with peck (the output-format decision —
explicit peck moves — is already baked into the planner and writer). Rigid tapping (G33.1) is a later
phase and is only stubbed here (task 9).

## Tasks

- [ ] 1. Models: drilling params, block type, enums
  - [ ] 1.1 Add `DrillingParams` and `is_drilling`
    - Add the `DrillingParams` frozen dataclass to `models/program.py` (model on `GroovingParams`)
    - Add `ProgramBlock.is_drilling`, a `"Drilling"` entry in `display_label.type_labels`, and
      `"drilling"` to the `block_type` doc comment
    - _Requirements: 1.3_
  - [ ] 1.2 Add drilling enums
    - Add `ToolType.DRILLING` to `models/tool.py` (optionally TAP/REAMER)
    - Add `"drill"` to `INSERT_SHAPES`; add a point-angle field to `InsertSpec` (or document the
      front_angle-as-half-angle reuse the `_drill()` outline will read)
    - Add `PassType.DRILLING` to `models/moves.py` (for graph/sim colouring)
    - _Requirements: 6.6, 8.2, 3.1_
  - [ ] 1.3 Register the block type
    - Add `"drilling"` to `BLOCK_TYPE_INFO` and `ADDABLE_BLOCK_TYPES`, and a default in
      `_default_tool_for_type` in `gui/components/block_list.py`
    - _Requirements: 1.1, 1.2_

- [ ] 2. Planner: `DrillingPlanner`
  - [ ] 2.1 Create `planners/drilling_planner.py`
    - `plan(params, tool, stock) -> List[ToolMove]`; `tip_length(dia, point_angle)` helper
    - Single-feed and peck schedules (full-retract and chip-break), bottom dwell, through-hole tip
      extension, depth-to-tip vs depth-to-shoulder
    - Tag moves `PassType.DRILLING`; small-clearance module constant
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9_
  - [ ] 2.2 Plan-time validation
    - `_validate`: blind depth vs stock length, drill dia vs bore/stock, Z travel limits, positive
      feed, positive peck increment when pecking; raise with context (no silent fallback)
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [ ] 3. Property and unit tests for planner (pure, no Qt)
  - [ ]* 3.1 Property tests `tests/properties/test_drilling_properties.py`
    - Property 1 (feeds monotone/bounded), Property 2 (peck sum), Property 3 (through-hole tip),
      Property 5 (depth-reference consistency)
    - _Requirements: 9.1, 9.2, 9.3, 3.9_
  - [ ]* 3.2 Unit tests `tests/unit/test_drilling_planner.py`
    - single-feed vs peck, full-retract vs chip-break, dwell, through vs blind, each error path
    - _Requirements: 3.3, 3.4, 3.5, 3.6, 4.1, 4.2, 4.3, 4.4_

- [ ] 4. Checkpoint — planner + models tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Outputs: `write_drilling_block`
  - [ ] 5.1 Add `write_drilling_block(...)` to `outputs/gcode_writer.py`
    - Model on `write_grooving_block`; local `conv`/`fmt`/`n()`, `G7` + `S.. M3`, iterate moves via
      `_rapid`/`_feed_line`/`_dwell`/`_line`, human comments; no G8x/G80; inherit G95
    - _Requirements: 5.1, 5.2, 5.3, 5.5_
  - [ ]* 5.2 Golden unit test `tests/unit/test_write_drilling_block.py`
    - Known params/moves → expected lines; unit scaling; tool-change injection
    - _Requirements: 5.1, 5.4, 5.5_

- [ ] 6. Program tab: panel, dispatch, save/restore
  - [ ] 6.1 Create `gui/components/drilling_panel.py`
    - `params_changed` / `get_values()` / `set_values()` / `get_tool_number()`; fields per
      `DrillingParams`; center/spot chamfer-diameter → depth from point angle
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_
  - [ ] 6.2 Wire the panel into the program tab
    - Build `self._section_drilling` in `_build_left_panel`; connect `params_changed` in
      `_connect_signals`; add `elif block.is_drilling:` to `_save_active_block_data` and
      `_restore_block_data`
    - _Requirements: 2.1, 2.5_
  - [ ] 6.3 Decouple section visibility from the legacy combo
    - In `_on_block_selected` and `_on_block_type_changed`, switch section visibility on
      `block.is_profile/is_threading/is_grooving/is_drilling` directly; show `_section_drilling` and
      hide the others for a drilling block
    - _Requirements: 2.6_
  - [ ] 6.4 Generate dispatch
    - Add `_generate_drilling_block(block, writer, prev_tool_number)` (model on
      `_generate_grooving_block`): `_resolve_tool_for_block`, tool-change, build `DrillingParams`,
      `DrillingPlanner().plan(...)`, `writer.write_drilling_block(...)`; add `elif block.is_drilling:`
      to the generate loop; drilling-tool suitability check (Req 4.5)
    - _Requirements: 5.4, 5.6, 4.5_
  - [ ]* 6.5 Restore test `tests/unit/test_drilling_block_restore.py`
    - program save/load with a drilling block; load validation accepts `"drilling"`
    - _Requirements: 1.4_

- [ ] 7. Tools tab: drill tool data + persistence
  - [ ] 7.1 Drill types and fields in `tools/tool_card_data.py`
    - Add drill `TOOL_TYPES`; `TYPE_ORIENTATIONS` → `[9]`; `TYPE_INSERTS` → `["N/A"]`; add
      `drill_diameter`/`point_angle`/`flute_length`/`max_peck`(/`pitch`) to `ToolCardData`; extend the
      type/direction maps, `tool_def_to_tool_card`, and `insert_spec()` drill branch
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.6_
  - [ ] 7.2 `.tbl` round-trip in `tools/tool_table_io.py`
    - Register drill type keys; serialize `D = drill_diameter`, metadata
      `pointangle|flute|maxpeck|pitch`; deserialize them; accept Q9; respect comment budget
    - _Requirements: 7.1, 7.2, 7.3, 7.5_
  - [ ]* 7.3 Round-trip tests `tests/unit/test_tool_table_io_drill.py`, `tests/unit/test_drill_tool_card.py`
    - Property 4 round-trip; D-column mapping; cascade (Q9, no insert); card-to-ToolDef map
    - _Requirements: 7.4, 9.4, 6.2, 6.6_

- [ ] 8. Tools tab: card fields + drill graphic
  - [ ] 8.1 Drill-conditional card fields in `gui/components/tool_geometry_row.py`
    - Add drill field group (diameter, point angle, flute length, max peck) mirroring blade-width
      visibility; hide insert dropdown + front/back angle rows for drilling types;
      `_update_orientation_graphic` builds a drill `InsertSpec`
    - _Requirements: 6.3, 6.5_
  - [ ] 8.2 `_drill()` outline in `geometry/tool_outline.py`
    - Cylinder + conical point about the centreline at Q9; add to the shape dispatch; avoid the
      `I0 J0` raise
    - _Requirements: 8.1, 8.2, 8.3_
  - [ ] 8.3 Add-tool default for drills in `gui/tools_tab.py`
    - Let `_on_add_tool_clicked` create a drill (type picker or an "Add Drill" path) with sane
      drill defaults instead of a forced turning insert
    - _Requirements: 6.1_

- [ ] 9. (Later phase) Rigid tapping stub
  - [ ]* 9.1 Document the G33.1 tapping path
    - Note the tap Tool_Type, pitch field, and G33.1 output plan in the design; do not implement the
      cycle in this phase
    - _Requirements: 6.1, 6.4_

- [ ] 10. Final checkpoint — all tests pass, integration smoke
  - Generate a program with a drilling block (no G8x/G80 present); load a `.tbl` with a drill and
    confirm the Q9 drill graphic renders. Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional/test tasks and can be skipped for a faster MVP.
- Each task references specific requirements for traceability.
- Drilling emits explicit peck moves (G0/G1/G4) — the pivotal output-format decision — so no canned
  cycle (G81/G83/G80) appears anywhere, avoiding the G18-plane drill-axis pitfall.
- The planner (tasks 2–3) is pure Python with zero Qt and can be tested independently.
- File locations follow current conventions: `tools/` for the tool-card data/IO modules (note: the
  tool-tab-rebuild tasks referenced `pipeline/`, but these modules now live under `tools/`),
  `gui/components/` for widgets, `planners/` for the planner, `tests/properties/` and `tests/unit/`.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3"] },
    { "id": 1, "tasks": ["2.1", "2.2"] },
    { "id": 2, "tasks": ["3.1", "3.2"] },
    { "id": 3, "tasks": ["5.1"] },
    { "id": 4, "tasks": ["5.2", "6.1"] },
    { "id": 5, "tasks": ["6.2", "6.3", "6.4", "6.5"] },
    { "id": 6, "tasks": ["7.1"] },
    { "id": 7, "tasks": ["7.2", "7.3"] },
    { "id": 8, "tasks": ["8.1", "8.2", "8.3"] },
    { "id": 9, "tasks": ["9.1"] }
  ]
}
```
