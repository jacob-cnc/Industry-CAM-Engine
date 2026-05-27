# Session Notes — 2026-05-27

## Changes Made

### 1. Generation Error Dialog (`gui/components/error_dialog.py`) — NEW
- Modal dialog showing detailed error info when toolpath generation fails
- Categorizes errors by pipeline stage (model_build, pipeline, zone_construction, gcode_write, graph_convert)
- Shows validation results with locations, recommendations, and consequences
- Collapsible traceback section for debugging
- Actionable fix suggestions based on error type

### 2. Program Tab Error Handling (`gui/program_tab.py`)
- `_on_generate_clicked()` now tracks pipeline stage and shows the error dialog on failure
- Validation errors display full list with locations and recommendations
- Exceptions show categorized error + full traceback in dialog
- Status label includes stage name for quick identification

### 3. Post-Planning Validator Fix (`validation/post_planning_validator.py`)
- **Bug:** Finish pass arcs tracing the profile boundary triggered false gouge detection
- **Cause:** Independent densification of the same arc (polygon boundary vs validator arc) produces different inscribed chord samples that briefly cross each other
- **Fix:** Finish pass arc moves check against a 0.001" inward-buffered polygon, matching the existing cleanup pass pattern

### 4. Graph Widget 1:1 Aspect (`gui/components/graph_widget.py`)
- Locked aspect ratio to 1:1 — arcs now display as true circles
- Removed free-scale mode (inaccurate display serves no purpose)
- User can still pan/zoom freely; double-click auto-fits

### 5. Cleanup Pass for Contour Roughing (`pipeline/pipeline.py`)
- **Bug:** Finish pass was cutting 10x its prescribed DOC with contour roughing
- **Cause:** Contour roughing's innermost pass leaves `fin_allowance + DOC` of material (not just `fin_allowance`). Without cleanup, the finish pass had to remove the extra DOC.
- **Fix:** Cleanup pass now runs for both staircase and contour roughing strategies

### 6. Program Tab UI Fields (`gui/program_tab.py`)
- Added X Park / Z Park fields (defaults: 2.0" dia, 2.0" Z)
- Added Finish RPM field (default: 1200)
- Changed default roughing feed to 0.006 ipr
- All new fields: saved/loaded in JSON, validated, wired to signals

### 7. Contour Roughing Arc Fix (`planners/contour_roughing_planner.py`)
- **Bug:** Arc radius mismatch errors (I/K relative to wrong start point)
- **Cause:** Passes started with bare arc moves — no positioning move to establish the correct start point for I/K computation
- **Fix:** Added feed move to arc's geometric start as first move of each pass

### 8. Contour Roughing Stock OD Re-cut Elimination (`planners/contour_roughing_planner.py`)
- **Bug:** Passes whose arc exits at stock OD had a trailing feed move down the stock wall to Z_end (cutting air)
- **Cause:** Clip operation produces vertical edges at stock OD boundary; old filter only removed full-span edges
- **Fix:** Remove any stock-OD edge where either endpoint touches Z_top or Z_bot (clip boundary artifact). Keep only true connectors between split arc sections.

## Discussion Notes

### RPM / Feed Per Rev on Manual Spindle
- G95 (feed per revolution) uses the spindle encoder for real-time RPM measurement
- S word + M3 enables encoder feedback — doesn't control spindle speed (manual)
- If spindle isn't turning, axes won't move (0 RPM × F = 0 IPM) — safe stall, no error
- RPM field kept in UI as operator reference for target speed setting

### 9. Retract Clearance (`outputs/gcode_writer.py`, `transitions/transition_planner.py`)
- Retract rapids now go to stock_dia + 0.010" (0.005" per side) instead of exactly stock_dia
- Prevents tool from dragging along stock surface during retract moves
- Applied in both the G-code writer (safe_x) and the transition planner

### 10. Sim Playback Finish Pass Visibility (`gui/components/sim_viewer.py`)
- **Bug:** Finish pass didn't display during sim playback (Play), but showed on "Show All"
- **Cause:** `reveal_toolpath_up_to()` was called with `sim_moves` index (G-code lines) directly as index into `toolpath_items` (pipeline moves). Different list lengths meant finish pass segments were never reached.
- **Fix:** Use the `_sim_to_toolmoves` mapping to translate sim playback position to the correct toolpath segment index. Falls back to highest mapped index for unmapped sim moves.

## Commits (branch: fix/contour-roughing-and-ui-improvements)

1. `87e2d0e` — fix(contour-roughing): arc I/K positioning, stock OD re-cut, cleanup pass
2. `250d6dd` — fix(retract): add 0.005in per-side clearance above stock surface
3. `83379cb` — fix(sim): use sim-to-toolmoves mapping for toolpath reveal during playback
