# Checkpoint 4 — Full Pipeline Verified Against Ground Truth
## Date: 2026-05-15
## Status: Engine Core COMPLETE, Zones Match Ground Truth, Visual Display Correct

## Major Accomplishments This Session

### Wire Extraction Fixed
- `boundary_wire_extraction()` now uses `CurrentVertex()` for correct edge orientation
- All edges chain with zero gaps
- Finished Part and Material to Rough zones match ground truth DXF EXACTLY (vertex-for-vertex)

### Hand Math Eliminated
- `_build_display_polygons()` DELETED — no longer exists
- `_display_polys.py` DELETED
- All zone coordinates come from Build123d wire extraction exclusively
- No try/except fallbacks remain in zone_builder

### Zone Builder Fixed
- `Kind.INTERSECTION` on offset → sharp corners (no fillets)
- MTR stock starts at Z=fin_allowance → excludes True Face Zone
- Finish Allowance = keep_zone - finished_part (proper thin band)
- Keep zone clipped to stock boundaries (no Z < Z_end)
- All fallback patterns removed — raises on failure

### Round-Trip Testing Codified
- Requirement 33 added to spec (3 checkpoints + ground truth comparison)
- Steering file `round-trip-testing.md` created (no-fallback enforcement)
- Ground truth comparison validates zone vertices before pipeline proceeds

### G-Code Writer Improved
- Always outputs both X and Z (operator readability)
- Descriptive comments on every line
- Same-tool optimization (no park between cleanup and finish)
- Safe retract/approach (Z traverse at stock OD, X feed to DOC level)
- No diagonal rapids through part

### Visual Display Working
- All 4 zones correctly shaded (Finished Part=steel blue, MTR=red, TFZ=red, Fin Allowance=amber)
- Zones match ground truth geometry
- Toolpath visible with correct color coding
- Crosshair with coordinate readout

### DXF Round-Trip Verified
- Engine DXF: zones from wire extraction + toolpath from PlanResult
- G-code DXF: toolpath from parsed G-code (what machine will execute)
- Shapely validation on parsed G-code: ZERO gouges

## Files Modified/Created This Session
- geometry/zone_builder.py — fixed offset (Kind.INTERSECTION), MTR construction, clipping
- geometry/zone_query.py — fixed boundary_wire_extraction (CurrentVertex orientation)
- outputs/gcode_writer.py — full rewrite (comments, both axes, same-tool)
- outputs/graph_adapter.py — zone shading from wire extraction
- pipeline/pipeline.py — _extract_zone_boundary (no hand math), removed _build_display_polygons
- gui/colors.py — background color, crosshair color
- gui/components/graph_widget.py — zone polygon rendering, clipping
- .kiro/steering/round-trip-testing.md — NEW (testing chain + no-fallback rules)
- .kiro/specs/.../requirements.md — Requirement 33 added

## Ground Truth Validation Results
- Finished Part: ✓ 6 vertices match exactly
- Material to Rough: ✓ 6 vertices match exactly
- Shapely round-trip (G-code): ✓ Zero gouges

## Known Remaining Items
- Retract behavior could be more efficient (not dangerous, just extra air time)
- Finish allowance zone display has minor overlap at profile boundary (acceptable)
- Arc OD profile not yet tested through pipeline
- ID profile not yet tested through pipeline
- GUI tabs (Program, Edit, Tools, Debug) not yet built
- Offset-contour planner not yet implemented
