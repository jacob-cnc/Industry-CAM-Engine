# Design Document: Drilling Cycles

## Overview

This design adds on-center axial drilling to the Industry CAM Engine as a new conversational
operation. It spans the same layers as the existing threading and grooving operations and reuses
their established patterns:

1. **Models** — a `DrillingParams` frozen dataclass, an `is_drilling` property on `ProgramBlock`,
   and a `ToolType.DRILLING` enum member.
2. **Planner** — a `DrillingPlanner` that turns params + drill `ToolDef` into an ordered
   `List[ToolMove]` (the peck schedule), with plan-time geometric validation.
3. **Outputs** — a `write_drilling_block(...)` method that formats those moves into G-code lines.
4. **GUI (Program tab)** — a `DrillingPanel`, the block-type registry entries, the generate-loop
   dispatch, and save/restore wiring.
5. **GUI (Tools tab)** — drill tool types, drill fields on `ToolCardData`, conditional card fields,
   `.tbl` metadata round-trip, and a `_drill()` tool outline.

The feature deliberately follows the **grooving** path, not the threading path, for G-code: drilling
emits explicit `ToolMove`s (rapids / feeds / dwells) rather than a literal canned-cycle word. A
drilling block is generated on the block-writer path and bypasses `pipeline.execute()` and the three
Shapely gates, exactly as grooving and threading do, so the planner validates its own geometry.

### Design Decisions

- **Explicit peck moves, not G81/G83.** On a LinuxCNC lathe in G18 (XZ), a G8x canned cycle's hole
  axis is Y, not Z — wrong for a lathe, and the reason `linuxcnc-gcode-reference.md` lists no drill
  canned cycles. Explicit G0/G1/G4 moves drill unambiguously along Z, round-trip through the simple
  parser (`outputs/gcode_parser.py`) and the non-controller preview (`parse_gcode_for_sim`), and let
  the machinist see every move on the graph. This also keeps one implementation shared by the lathe
  PC and the dev box.
- **Planner returns `ToolMove`s.** Grooving's `.plan()` already returns `List[ToolMove]`; drilling
  does the same so the move list can feed both the writer and (optionally) the preview, and no new
  `MoveType` is needed. `PassType.DRILLING` is added only for sim/graph colouring.
- **`DrillingParams` is a sibling of `GroovingParams`.** A frozen dataclass in `models/program.py`
  keeps the operation self-contained and serialisable into `ProgramBlock.params_data`, consistent
  with the other operations. No change to `pipeline/model_builder.py` (profile-only) is required.
- **Drill diameter maps to the `.tbl` D column.** LinuxCNC's `D` is the tool diameter; mapping the
  drill diameter there (with `nose_radius = D/2`) reuses the existing serialize/deserialize
  convention with no special case, and keeps the drill a first-class LinuxCNC tool.
- **Separate drill fields over reusing insert fields.** Point angle, flute length, and max peck have
  no home in `ToolCardData`, `ToolDef`, or `InsertSpec` today. Adding explicit fields (rather than
  overloading `tip_angle` / `nose_radius` / `ic`) keeps the drill semantics clear and the turning
  tools untouched.
- **Decouple panel visibility from the legacy block-type combo.** Today section visibility is derived
  from a fixed 4-item combo index in two places. Drilling switches that logic to read
  `block.is_profile / is_threading / is_grooving / is_drilling` directly, removing the structural snag
  rather than widening the combo.

---

## Architecture

```
Program tab (gui/program_tab.py)
  Add menu ──> ProgramBlock(block_type="drilling")           [gui/components/block_list.py]
  _on_block_selected / _on_block_type_changed                (switch on block.is_drilling)
      └─> show DrillingPanel section, hide others
  _save_active_block_data / _restore_block_data              (<-> block.params_data)
  _on_generate_clicked
      └─ elif block.is_drilling:
             _generate_drilling_block(block, writer, prev_tool_number)
                 tool = _resolve_tool_for_block(block)       [drill ToolDef]
                 params = DrillingParams(**block.params_data)
                 moves  = DrillingPlanner().plan(params, tool, stock)
                 lines  = writer.write_drilling_block(params, moves, tool, unit_mode)
      └─ _combine_gcode_sections(...)  ── inject before PROGRAM END

Models (models/)
  program.py :  DrillingParams (frozen), ProgramBlock.is_drilling, display label
  moves.py   :  PassType.DRILLING (optional)
  tool.py    :  ToolType.DRILLING, INSERT_SHAPES += "drill"

Planner (planners/drilling_planner.py)
  DrillingPlanner.plan(params, tool, stock) -> List[ToolMove]
      _validate(params, tool, stock)   (depth / diameter / travel / feed)
      _peck_schedule(...)              (full-retract or chip-break)
      tip_length(dia, point_angle)

Outputs (outputs/gcode_writer.py)
  write_drilling_block(params, moves, tool, unit_mode) -> List[str]

Tools tab (gui/ + tools/)
  tools/tool_card_data.py  :  TOOL_TYPES, TYPE_ORIENTATIONS, TYPE_INSERTS,
                              ToolCardData drill fields, insert_spec drill branch, maps
  tools/tool_table_io.py   :  serialize/deserialize drill metadata, type keys
  gui/components/tool_geometry_row.py : drill-conditional fields, hide insert/angles
  geometry/tool_outline.py :  _drill() branch
```

### Dependency direction

All new code respects the strict import chain
`models → tools → geometry → … → planners → … → outputs → … → gui`
(`.kiro/steering/architecture-rules.md`). `DrillingPlanner` imports only `models`; the writer imports
only `models`; the GUI imports planner, writer, and models.

---

## Components and Interfaces

### DrillingParams (`models/program.py`)

```python
@dataclass(frozen=True)
class DrillingParams:
    """One on-center axial drilling operation. Zero external dependencies.

    Coordinates (inches, Z negative toward the tailstock):
        z_start:        part face Z (rapid-to plane reference)
        depth:          commanded hole depth (positive, along -Z from z_start)
        depth_to_tip:   True = depth is to the drill tip; False = to the full-dia shoulder
        through_hole:   True = extend final depth by tip_length to break through
        r_plane:        clearance Z above the face where feed begins / pecks retract to
        peck_enabled:   True = peck; False = single feed
        peck_increment: per-peck axial feed (positive)
        full_retract:   True = retract to r_plane (G83 style); False = chip-break (G73 style)
        dwell:          bottom dwell seconds (0 = none)
    """
    operation: str          # "center", "spot", "drill", "ream" (tap: later phase)
    z_start: float
    depth: float
    depth_to_tip: bool
    through_hole: bool
    r_plane: float
    peck_enabled: bool
    peck_increment: float
    full_retract: bool
    dwell: float
    feed: float             # inch/rev (G95)
    spindle_rpm: float      # advisory (manual spindle)
    tool_number: int
```

`ProgramBlock` gains `is_drilling` (true for `"drilling"`), a `type_labels` entry (`"Drilling"`),
and the `"drilling"` string in its `block_type` doc comment. `BLOCK_TYPE_INFO`,
`ADDABLE_BLOCK_TYPES`, and `_default_tool_for_type` in `gui/components/block_list.py` gain the type.

### DrillingPlanner (`planners/drilling_planner.py`)

```python
class DrillingPlanner:
    def plan(self, params: DrillingParams, tool: ToolDef,
             stock: StockDef) -> List[ToolMove]: ...

    def _validate(self, params, tool, stock) -> None: ...   # Requirement 4
    def _peck_schedule(self, z_start_feed: float, z_final: float,
                       params: DrillingParams) -> List[ToolMove]: ...

def tip_length(drill_diameter: float, point_angle: float) -> float:
    """(D/2) / tan(point_angle/2); 0 for a 180° (flat) point."""
```

**Final depth** (as a signed Z, feeds go negative):

```
z_tip     = z_start - depth                   if depth_to_tip
          = z_start - depth - tip_length      if depth to full-dia shoulder
z_final   = z_tip - tip_length                if through_hole else z_tip
```

**Move sequence** (positions are (X=0, Z)):

1. `RAPID (0, r_plane)` — to centreline at the clearance plane.
2. Peck loop from `z_cur = r_plane` down to `z_final`:
   - `FEED (0, z_next)` where `z_next = max(z_cur - peck_increment, z_final)` at `params.feed`.
   - if `z_next > z_final` (more to go):
     - full-retract: `RAPID (0, r_plane)` then `RAPID (0, z_next + small_clearance)`
     - chip-break:  `RAPID (0, z_next + small_clearance)`
   - `z_cur = z_next`
3. if `dwell > 0`: `DWELL` at `z_final`.
4. `RAPID (0, r_plane)`.

When `peck_enabled` is false, step 2 is a single `FEED (0, z_final)`. `small_clearance` is a module
constant (e.g. 0.02"). All moves carry `pass_type = PassType.DRILLING`.

### write_drilling_block (`outputs/gcode_writer.py`)

Modeled on `write_grooving_block`. Signature:

```python
def write_drilling_block(self, params: DrillingParams, moves: List[ToolMove],
                         tool: ToolDef, unit_mode: str = "inch") -> List[str]:
```

- compute local `conv` / `fmt` / `n()` from `unit_mode` (as threading/grooving do);
- emit section header comment, `self._optional_stop(...)`, `self._line("G7", ...)`,
  `self._line(f"S{params.spindle_rpm:.0f} M3", ...)`;
- iterate `moves`, dispatching to `self._rapid`, `self._feed_line`, `self._dwell` and tagging each
  with a human comment (e.g. "Peck 2: feed to depth", "Retract to clearance plane");
- the helpers already update `self._x / self._z`, so no manual position fix-up is needed (unlike the
  threading G76 path);
- return the list of lines.

The `_generate_drilling_block` generator in `gui/program_tab.py` (modeled on
`_generate_grooving_block`) resolves the tool via `_resolve_tool_for_block`, emits a
`write_tool_change` when `prev_tool_number != block.tool_number`, builds `DrillingParams` from
`block.params_data`, calls `DrillingPlanner().plan(...)`, then `writer.write_drilling_block(...)`, and
returns the lines. The generate loop gains `elif block.is_drilling:` alongside the grooving branch,
and sections merge through the existing `_combine_gcode_sections`.

### DrillingPanel (`gui/components/drilling_panel.py`)

A `QWidget` mirroring `GroovingPanel`'s contract: `params_changed = pyqtSignal()`,
`get_values() -> dict`, `set_values(data)`, `get_tool_number()`. Fields map 1:1 to `DrillingParams`.
Center/spot operations expose a target chamfer-diameter entry that computes depth from the tool's
point angle. The panel lives in a new hidden `self._section_drilling = CollapsibleSection(...)` built
in `_build_left_panel`, wired in `_connect_signals` (`params_changed → _on_field_changed`), and shown
/ hidden by the visibility logic in `_on_block_selected` and `_on_block_type_changed` (now switching
on `block.is_*`). `_save_active_block_data` / `_restore_block_data` gain `elif block.is_drilling:`
branches calling `get_values()` / `set_values()`.

### Tools-tab drill support

- **`tools/tool_card_data.py`**: add `"Center Drill"`, `"Spot Drill"`, `"Twist Drill"`, `"Reamer"`,
  `"Tap"` to `TOOL_TYPES`; map each to `[9]` in `TYPE_ORIENTATIONS` and to a `["N/A"]` sentinel in
  `TYPE_INSERTS`; add `drill_diameter`, `point_angle`, `flute_length`, `max_peck` (and `pitch` for
  tap) fields to `ToolCardData` (defaults 0.0); extend `_CARD_TYPE_TO_TOOL_TYPE`,
  `_CARD_TYPE_TO_DIRECTION` (NEUTRAL), the reverse map, `tool_def_to_tool_card`, and add a `"drill"`
  branch to `insert_spec()`.
- **`models/tool.py`**: add `ToolType.DRILLING` (and optionally TAP/REAMER); add `"drill"` to
  `INSERT_SHAPES`. `InsertSpec` grows an optional point-angle field, or the drill spec reuses
  `front_angle` as half-angle — decided in task 1; the drill outline reads whichever is chosen.
- **`tools/tool_table_io.py`**: register the drill type keys in `_TYPE_TO_KEY` / `_KEY_TO_TYPE`; in
  `serialize_tool`, write `D = drill_diameter` (so `nose_radius = D/2`) and append
  `pointangle|flute|maxpeck|pitch` to the comment metadata; in `deserialize_tool`, parse them back.
  Respect the 200-byte comment / 255-byte line budget.
- **`gui/components/tool_geometry_row.py`**: add a drill-conditional field group (drill diameter,
  point angle, flute length, max peck) mirroring the blade-width visibility pattern, and hide the
  insert dropdown + front/back angle rows for drilling types; `_update_orientation_graphic` builds a
  drill `InsertSpec`.
- **`geometry/tool_outline.py`**: add `_drill()` to the dispatch, drawing a cylinder of the drill
  diameter with a conical point symmetric about the centreline at Q9, avoiding the `I0 J0` raise.

---

## Data Models

### ProgramBlock params_data for a drilling block

`block.params_data` is the dict returned by `DrillingPanel.get_values()` — the `DrillingParams`
fields minus `tool_number` (which `ProgramBlock` tracks separately and the generator re-injects),
consistent with how grooving/threading store their panel dicts.

### .tbl line for a drill

```
T3 P3 X+0.000000 Z-0.500000 D0.250000 I0.0 J0.0 Q9 ;ice=2|xwear=0|zwear=0|type=twist_drill|pointangle=118.0|flute=2.500|maxpeck=0.150|desc=1/4 twist drill
```

`D` = drill diameter (0.2500"), `Q` = 9, `I`/`J` = 0 (no insert edges), drill specifics in metadata.

---

## Correctness Properties

### Property 1: Feeds are monotone and bounded

*For any* valid `DrillingParams`, each FEED move in the planner output advances Z toward the part
(more negative) relative to the previous in-hole position, and no FEED move passes the final planned
depth. **Validates: Requirements 3.3–3.5, 9.1.**

### Property 2: Peck increments sum to the final depth

*For any* valid pecking `DrillingParams`, the planned feed increments sum to exactly the depth from
the feed-start plane to the final depth, and no single peck feed exceeds `peck_increment`.
**Validates: Requirements 3.4, 3.5, 9.2.**

### Property 3: Through-hole tip extension

*For any* valid through-hole `DrillingParams`, the deepest planned Z equals the commanded tip depth
minus `tip_length(drill_diameter, point_angle)`. **Validates: Requirements 3.8, 9.3.**

### Property 4: Drill tool-table round-trip

*For any* valid drill `ToolCardData`, serialising to a .tbl line and deserialising back yields an
equivalent drill (tool number, drill diameter, point angle, flute length, max peck, orientation,
Tool_Type, description) within 6 decimals for lengths and 1 decimal for angles.
**Validates: Requirements 7.4, 9.4.**

### Property 5: Depth-reference consistency

*For any* valid `DrillingParams`, choosing `depth_to_tip=False` (shoulder reference) produces a final
tip Z exactly `tip_length` deeper than choosing `depth_to_tip=True` with the same commanded depth,
all else equal. **Validates: Requirement 3.9.**

---

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Blind-hole depth exceeds stock length | `DrillingPlanner` raises with depth and stock length |
| Drill diameter larger than bore/stock allows on center | `DrillingPlanner` raises |
| Depth or peck motion exceeds Z travel limit | `DrillingPlanner` raises |
| Non-positive feed, or non-positive peck while pecking | `DrillingPlanner` raises |
| Resolved tool is not a drilling type | `program_tab` reports a clear block/tool error (Req 4.5) |
| Drill tool with zero front/back angle reaches insert outline | `_drill()` branch handles it; no `I0 J0` raise |
| .tbl comment exceeds budget with drill metadata | Serializer raises the existing length error; fields trimmed per existing policy |

---

## Testing Strategy

### Property-Based Tests (Hypothesis)

`tests/properties/test_drilling_properties.py`, min 100 examples each, tag
`# Feature: drilling-cycles, Property N: <text>`:

1. Feeds monotone and bounded (Property 1)
2. Peck increments sum to depth (Property 2)
3. Through-hole tip extension (Property 3)
4. Drill .tbl round-trip (Property 4)
5. Depth-reference consistency (Property 5)

### Unit Tests (pytest)

- `tests/unit/test_drilling_planner.py` — single-feed vs peck, full-retract vs chip-break, dwell,
  through vs blind, each validation error path.
- `tests/unit/test_write_drilling_block.py` — emitted lines for a known params/moves pair (golden),
  unit scaling, tool-change injection.
- `tests/unit/test_drill_tool_card.py` — drill fields, cascade (Q9, no insert), card-to-ToolDef map.
- `tests/unit/test_tool_table_io_drill.py` — drill serialize/deserialize, D-column mapping, metadata.
- `tests/unit/test_drilling_block_restore.py` — program save/load with a drilling block.

### Integration Tests

- Add a drilling block in the program tab, generate, and assert the combined program contains the
  drilling section with correct G0/G1/G4 lines and no G8x/G80.
- Load a `.tbl` containing a drill, confirm the Tools tab shows drill fields and the Q9 graphic.
