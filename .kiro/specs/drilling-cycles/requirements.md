# Requirements Document

## Introduction

Add on-center axial **drilling cycles** to the Industry CAM Engine as a new conversational
operation type in the Program tab, with the supporting **drill tool** definitions in the Tools
tab. This machine has a manual quick-change toolpost with no tailstock, no live tooling, and no
C-axis (see `.kiro/steering/machine-hardware.md`), so the feature is deliberately bounded to
holes on the spindle centreline (X0) fed along Z — a drill, reamer, or tap held in a QCTP holder.
Cross-drilling, bolt circles, and radial holes are out of scope.

A spindle encoder is present, so feed-per-revolution (G95) output works and rigid tapping
(G33.1) is physically possible. The spindle is manual (no VFD), so spindle RPM is **advisory**
(displayed, never commanded) exactly as it is for the existing turning, threading, and grooving
operations.

Drilling G-code is emitted as **explicit peck moves** — rapids, feeds, and dwells
(G0 / G1 / G4) — not as plane-tied canned cycles (G81 / G83). This mirrors the grooving peck
implementation, round-trips through the simple G-code parser and the non-controller preview, and
avoids the LinuxCNC pitfall that a G8x canned cycle in the G18 (XZ) plane drills along Y rather
than Z. It is the reason `.kiro/steering/linuxcnc-gcode-reference.md` documents G76 but no G81/G83.

A drilling block is generated on the same block-writer path as threading and grooving: it bypasses
`pipeline.execute()` and the three Shapely validation gates, so the planner performs its own
geometric sanity checks (depth, diameter, travel) at plan time.

## Glossary

- **Drilling_Block**: A `ProgramBlock` whose `block_type` is `"drilling"`, representing one
  on-center axial hole-making operation in the multi-block program.
- **Drilling_Operation**: The hole-making mode of a Drilling_Block — one of Center Drill, Spot
  Drill, Twist Drill, or Reamer (Tap is a later phase).
- **Drilling_Panel**: The PyQt5 parameter panel for a Drilling_Block, exposing the same
  `params_changed` / `get_values()` / `set_values()` contract as `GroovingPanel`.
- **DrillingParams**: The frozen dataclass in `models/program.py` holding one drilling
  operation's field state (depths, R-plane, peck, dwell, feed, rpm, tool).
- **DrillingPlanner**: The planner in `planners/drilling_planner.py` that turns DrillingParams and
  the drill ToolDef into an ordered list of `ToolMove` objects (the peck schedule).
- **R_Plane**: The Z clearance position above the part face where rapids stop and feed begins, and
  to which the drill retracts between pecks.
- **Peck_Increment**: The axial depth of each feed step before a retract, for chip evacuation.
- **Full_Retract_Peck**: A peck strategy where the drill rapids all the way to the R_Plane between
  pecks (deep-hole / G83 style).
- **Chip_Break_Peck**: A peck strategy where the drill retracts only a small clearance between
  pecks (G73 style), staying in the hole.
- **Point_Angle**: The included angle of a drill point (e.g. 118° or 135°).
- **Tip_Length**: The axial length of the conical drill point, `(drill_diameter / 2) / tan(Point_Angle / 2)`,
  added to Z-final for through-holes so the full diameter clears the back face.
- **Drill_Depth**: The commanded hole depth, measured either to the full-diameter shoulder or to
  the drill tip, as selected by the user.
- **Through_Hole**: A hole that exits the far face; its planned depth is extended by Tip_Length.
- **Drill_Tool**: A Tools-tab tool whose Tool_Type is a drilling type (Center Drill, Spot Drill,
  Twist Drill, Reamer, Tap), stored at orientation Q9 (CENTER), carrying drill diameter, point
  angle, flute length, and max peck.
- **Tool_Type**: The GUI tool category string in `ToolCardData.tool_type` (one of `TOOL_TYPES`)
  that drives the orientation and insert dropdown cascade and conditional field visibility.
- **Drill_Graphic**: The true-scale tool outline for a drill — a cylindrical body with a conical
  point drawn symmetric about the spindle centreline — produced by a new `_drill()` branch in
  `geometry/tool_outline.py`.

## Requirements

### Requirement 1: Drilling Block Type

**User Story:** As a CNC operator, I want to add a drilling operation to my program, so that I can
produce an on-center hole as one block in the conversational program alongside turning, threading,
and grooving.

#### Acceptance Criteria

1. THE block-type registry SHALL include a `"drilling"` block type with a display label and colour
   in `BLOCK_TYPE_INFO`, and SHALL list it in `ADDABLE_BLOCK_TYPES` so it appears in the Add menu.
2. WHEN the user selects the drilling entry from the Add menu, THE block list SHALL create a
   `ProgramBlock` with `block_type = "drilling"` and a sensible default tool number from
   `_default_tool_for_type`.
3. THE `ProgramBlock` model SHALL expose an `is_drilling` property that is true exactly for the
   `"drilling"` block type, and SHALL provide a default display label for it.
4. WHEN a program file containing a drilling block is saved and reloaded, THE program SHALL restore
   the drilling block and its parameters without loss, and THE load validation SHALL accept the
   `"drilling"` block type.

### Requirement 2: Drilling Parameter Panel

**User Story:** As a CNC operator, I want a parameter panel for the drilling operation, so that I
can enter the hole geometry and cutting parameters in familiar conversational fields.

#### Acceptance Criteria

1. THE Drilling_Panel SHALL expose a `params_changed` signal, a `get_values() -> dict` method, and a
   `set_values(data)` method, matching the panel contract used by `GroovingPanel` and `ThreadingPanel`.
2. THE Drilling_Panel SHALL provide fields for Drilling_Operation, Z start (face), Drill_Depth,
   depth reference (tip or full-diameter shoulder), Through_Hole toggle, R_Plane clearance,
   peck enable, Peck_Increment, peck strategy (Full_Retract_Peck or Chip_Break_Peck), bottom dwell,
   feed (inch/rev), spindle RPM, and tool number.
3. WHEN the Through_Hole toggle is on, THE Drilling_Panel SHALL present the planned depth as
   extended by Tip_Length and SHALL make clear that the extra travel is the drill point breaking
   through.
4. WHEN the Drilling_Operation is Center Drill or Spot Drill, THE Drilling_Panel SHALL allow entry
   of a target chamfer diameter as an alternative to an explicit depth, computing the depth from the
   point angle.
5. WHEN any field changes, THE Drilling_Panel SHALL emit `params_changed`.
6. WHEN the program-tab active block changes to or from a drilling block, THE program tab SHALL show
   the Drilling_Panel section and hide the profile, threading, grooving, and parting sections (and
   vice versa), driven by `block.is_drilling` rather than the legacy 4-item block-type combo index.

### Requirement 3: Peck Schedule Generation

**User Story:** As a CNC operator, I want the engine to generate a correct peck sequence, so that
chips evacuate and the hole reaches the intended depth.

#### Acceptance Criteria

1. THE DrillingPlanner SHALL return an ordered `List[ToolMove]` using only RAPID, FEED, and DWELL
   move types, with no new `MoveType` required.
2. THE DrillingPlanner SHALL begin each operation with a rapid to X0 at the R_Plane.
3. WHEN pecking is disabled, THE DrillingPlanner SHALL feed from the R_Plane to the final depth in a
   single feed move.
4. WHEN pecking is enabled with Full_Retract_Peck, THE DrillingPlanner SHALL, for each peck, feed
   down one Peck_Increment, rapid to the R_Plane, then rapid back to a small clearance above the
   last depth before the next feed.
5. WHEN pecking is enabled with Chip_Break_Peck, THE DrillingPlanner SHALL, for each peck, feed down
   one Peck_Increment then retract a small clearance without leaving the hole.
6. WHEN a bottom dwell is specified, THE DrillingPlanner SHALL emit a DWELL at the final depth before
   retracting.
7. THE DrillingPlanner SHALL end each operation with a rapid from the final depth to the R_Plane.
8. WHEN the operation is a Through_Hole, THE DrillingPlanner SHALL extend the final feed depth by
   Tip_Length so the full drill diameter clears the back face.
9. WHEN the depth reference is the full-diameter shoulder, THE DrillingPlanner SHALL add Tip_Length
   to the commanded Drill_Depth to position the drill tip; WHEN the reference is the tip, THE
   DrillingPlanner SHALL use the commanded Drill_Depth directly.

### Requirement 4: Plan-Time Validation

**User Story:** As a CNC operator, I want the drilling planner to catch unsafe input, so that a bad
hole is rejected before any G-code is produced, even though drilling bypasses the Shapely gates.

#### Acceptance Criteria

1. IF the final drill depth exceeds the stock length along Z, THEN THE DrillingPlanner SHALL raise a
   clear error naming the depth and the stock length, unless the operation is an explicit Through_Hole.
2. IF the drill diameter exceeds the available bore or stock diameter such that the on-center hole is
   geometrically impossible, THEN THE DrillingPlanner SHALL raise a clear error.
3. IF the commanded depth or the between-peck motion would exceed the machine Z travel limits, THEN
   THE DrillingPlanner SHALL raise a clear error.
4. IF the feed is not positive, or the Peck_Increment is not positive while pecking is enabled, THEN
   THE DrillingPlanner SHALL raise a clear error.
5. WHEN the resolved tool for a drilling block is not a drilling Tool_Type, THE program tab SHALL
   report a clear error naming the block and the tool rather than silently drilling with a turning tool.

### Requirement 5: G-code Output

**User Story:** As a CNC operator, I want the drilling block to emit standard LinuxCNC G-code
consistent with the rest of the program, so that it runs on my machine and previews correctly.

#### Acceptance Criteria

1. THE G-code writer SHALL provide a `write_drilling_block(...)` method that returns a
   `List[str]` of G-code lines, built from the DrillingPlanner move list using the existing
   `_rapid`, `_feed_line`, `_dwell`, and `_line` helpers.
2. THE drilling block SHALL emit only G0, G1, and G4 motion (plus its local `G7` and spindle
   `S.. M3`), and SHALL NOT emit a G8x canned cycle or a G80 cancel.
3. THE drilling block SHALL emit feed in the inherited G95 (inch-per-rev) mode and SHALL NOT change
   the feed mode.
4. WHEN a tool change is required relative to the previous block, THE drilling generator SHALL emit a
   tool change via `write_tool_change` before the cycle, consistent with the grooving generator.
5. THE drilling block SHALL honour the active unit mode, scaling coordinates and formatting exactly
   as the threading and grooving block writers do.
6. THE combined program SHALL inject the drilling section like the threading and grooving sections,
   relying on the first profile block's header/preamble for units, plane, and feed mode.

### Requirement 6: Drill Tool Type in the Tools Tab

**User Story:** As a CNC operator, I want to define drills in the Tools tab, so that a drilling
block can reference a real tool with the geometry the cycle needs.

#### Acceptance Criteria

1. THE Tools tab Tool_Type list SHALL include drilling types: Center Drill, Spot Drill, Twist Drill,
   Reamer, and Tap.
2. THE type-to-orientation cascade SHALL map every drilling Tool_Type to orientation Q9 (CENTER).
3. THE type-to-insert cascade SHALL map every drilling Tool_Type to a no-insert sentinel, and THE
   Tool_Card SHALL hide the insert-code dropdown and the front/back angle fields for drilling types.
4. THE `ToolCardData` dataclass SHALL carry drill fields: drill diameter, point angle, flute length,
   and max peck, with tap additionally carrying thread pitch.
5. WHEN the Tool_Type is a drilling type, THE Tool_Card SHALL display the drill fields (drill
   diameter, point angle, flute length, max peck) using the conditional-visibility pattern already
   used for the grooving blade-width field; otherwise THE Tool_Card SHALL hide them.
6. THE pipeline `ToolType` enum SHALL include a `DRILLING` member (and may include TAP/REAMER), and
   the card-to-ToolDef mapping SHALL map drilling cards to it with `ToolDirection.NEUTRAL`.

### Requirement 7: Drill Tool Persistence

**User Story:** As a CNC operator, I want drills saved in the LinuxCNC .tbl file, so that they
survive restarts and remain compatible with LinuxCNC.

#### Acceptance Criteria

1. THE tool-table serializer SHALL map a drill's diameter to the `D` column (the LinuxCNC tool
   diameter) and SHALL set `nose_radius = drill_diameter / 2` so the existing `D = nose_radius * 2`
   convention holds without special-casing.
2. THE tool-table serializer SHALL encode point angle, flute length, max peck, and (for taps) pitch
   as pipe-delimited key=value pairs in the comment metadata, within the existing comment-length budget.
3. THE tool-table serializer SHALL register the drilling Tool_Type keys in the type/key maps, and THE
   deserializer SHALL restore a drill's Tool_Type, drill fields, and orientation from the metadata.
4. FOR ALL valid drill `ToolCardData` instances, serialising to .tbl and deserialising back SHALL
   produce an equivalent drill tool with matching tool number, drill diameter, point angle, flute
   length, max peck, orientation, Tool_Type, and description, preserving 6 decimal places for
   lengths and 1 decimal place for angles.
5. THE orientation validation SHALL accept Q9 for drilling tools (as it already does for the master
   tool) on both save and load.

### Requirement 8: Drill Tool Graphic

**User Story:** As a CNC operator, I want a correct drill drawing in the tool card and screen
graphics, so that I can visually confirm the drill geometry.

#### Acceptance Criteria

1. THE tool-outline builder SHALL provide a `_drill()` branch that draws a cylindrical body of the
   drill diameter with a conical point of the given point angle, symmetric about the spindle
   centreline at orientation Q9.
2. THE `INSERT_SHAPES` set SHALL include a `"drill"` shape, and `insert_spec()` SHALL produce a drill
   spec (point angle and drill diameter) for drilling Tool_Types.
3. WHEN a drill tool is displayed, THE orientation graphic and the screen tool graphic SHALL render
   the Drill_Graphic and SHALL NOT raise the "edge angles unknown (I0 J0)" error that the insert
   path raises for zero front/back angles.

### Requirement 9: Correctness Properties

**User Story:** As a developer, I want the drilling math and tool round-trip covered by property
tests, so that the feature holds across the whole input space, consistent with project discipline.

#### Acceptance Criteria

1. FOR ALL valid DrillingParams, THE DrillingPlanner move list SHALL be monotonic in Z toward the
   part during feeds and SHALL never feed below the final planned depth.
2. FOR ALL valid pecking DrillingParams, THE sum of the feed increments SHALL reach exactly the final
   planned depth and no peck feed SHALL exceed the Peck_Increment.
3. FOR ALL valid Through_Hole DrillingParams, THE final feed depth SHALL equal the commanded depth
   plus Tip_Length, computed from the drill diameter and point angle.
4. FOR ALL valid drill `ToolCardData`, THE .tbl serialize/deserialize round-trip SHALL be an
   identity within the stated precision (Requirement 7.4).
