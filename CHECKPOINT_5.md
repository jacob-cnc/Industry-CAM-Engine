# Checkpoint 5 — Validator Fixed, Arc Staircase Z-Boundary Bug Identified
## Date: 2026-05-15
## Status: Cleanup planner fixed, validator tightened, staircase arc query bug identified but not yet fixed

## Major Accomplishments This Session

### G-Code Writer Retract Logic Improved
- Retract to previous pass X level (not stock OD) — saves air time
- Diagonal retract at shoulders — clears corner without tool drag
- Approach: traverse Z at prev level → feed X to DOC

### All Spec Tasks Completed (95/95)
- GUI tabs: Program, Edit, Tools, Debug all implemented
- MainWindow with signal wiring
- Missing files created: dxf_exporter, svg_exporter, sim_adapter, offset_contour_planner

### Cleanup Planner Rewritten (CRITICAL FIX)
- OLD: Hand math (`x_r + fin_r`) producing straight G01 through arc boundaries — GOUGE
- NEW: Uses `boundary_wire_extraction("material_to_rough")` — emits G02/G03 for arc edges
- Cleanup pass now correctly outputs: `['feed', 'arc_cw', 'feed']` for arc profiles

### Validator Tightened
- Removed blanket skip of cleanup/finish moves
- All moves checked against finished_part_poly (endpoint + segment)
- Cleanup moves additionally checked against finish_allowance_poly
- Uses `crosses()` for segment checks (boundary contact OK, crossing = gouge)
- Uses distance-to-boundary check for endpoints (on boundary OK, inside = gouge)
- Pass type transitions reset prev_x/prev_z (G-code writer handles inter-phase approach)
- Arc moves: chord check is valid because arcs curve AWAY from finished part

### Segment List Widget Updated
- User sees CW/CCW dropdown instead of signed radius
- Backend converts: CW → positive radius, CCW → negative radius
- More intuitive for operators

### Ground Truth Analysis Complete
- NX Staircase Toolpath DXF provided and analyzed
- NX uses offset arcs at each DOC level for Z boundaries
- Our engine uses MTR zone section (correct for the zone shape, wrong for staircase strategy)

## The Remaining Bug: Staircase Arc Z-Boundaries

### What's Wrong
At X levels where the offset arc extends beyond the roughing boundary arc:
- **Our engine**: `boundary_at_x(1.45)` returns `Z[0.001, -2.0]` (one big interval)
- **NX ground truth**: Z[0, -0.4427] + Z[-1.5573, -2.0] (two intervals split by offset arc)

### Root Cause
The MTR zone Face has the roughing boundary arc (R=1.001) as its inner edge. This arc only extends to X=0.501r. At X levels above 0.501r (e.g., X=0.725r), the horizontal section doesn't cross the arc — so it returns one big interval.

NX's staircase uses the **offset arc at each DOC level** (R = profile_R + DOC_offset + fin_allowance). At X=0.725r, the offset arc has R=1.226 which DOES extend to that X level, giving Z boundaries of -0.4427 and -1.5573.

### What Needs to Happen
The staircase planner needs to compute Z boundaries using offset arcs at each DOC level, not from the MTR zone section. Two approaches:
1. Compute the offset arc geometry at each X level and find its Z intersection
2. Build intermediate offset zones at each DOC level and section those

This is essentially what the offset-contour planner does — compute offset boundaries at each DOC level. The staircase planner needs the same offset computation but only uses the Z intersections (not the full contour).

### Verified Working
- `boundary_at_x()` at X=0.501r correctly returns 4 Z values (arc crossings found)
- Cleanup planner correctly emits arc moves from wire extraction
- Finish planner correctly emits arc moves from profile segments
- Validator catches straight-line-through-arc gouges
- Stepped OD still passes all tests

## Files Modified This Session
- `outputs/gcode_writer.py` — retract to prev X level, diagonal at shoulders
- `planners/cleanup_planner.py` — REWRITTEN (wire extraction, no hand math)
- `validation/post_planning_validator.py` — REWRITTEN (tight rules, no blanket skips)
- `gui/components/segment_list.py` — CW/CCW direction column
- `gui/components/graph_widget.py` — expanded zoom limits
- `pipeline/pipeline.py` — finish_allowance extraction made optional for ID mode
- `outputs/dxf_exporter.py` — NEW
- `outputs/svg_exporter.py` — NEW
- `outputs/sim_adapter.py` — NEW
- `planners/offset_contour_planner.py` — NEW (stub, not yet wired)
- `gui/edit_tab.py` — ExtraSelection fix
- `_visual_test_arc.py` — sim viewer with G-code sync
- `_export_arc_od.py` — Arc OD round-trip test
- `_export_id.py` — ID bore test (still failing)
- `reference/CAD Reference/GROUND_TRUTH_NOTES.md` — NEW
- `.kiro/steering/zone-mental-model.md` — face pass Z=0.001 rule added
- `.kiro/steering/qtpyvcp-reference.md` — NEW (manual inclusion)
- `Ship to LinuxPC/` — deployment package

## Next Steps (Priority Order)
1. Fix staircase planner arc Z-boundaries (compute offset arc intersections at each DOC level)
2. Implement offset-contour/waterfall roughing strategy (wire to pipeline)
3. Fix ID bore mode (staircase planner generates passes beyond bore wall)
4. Wire Debug tab Export buttons to actual exporters
5. Wire Tools tab selection → Program tab tool usage
