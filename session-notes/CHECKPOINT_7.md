# Checkpoint 7 — ID Bore Mode, Contour Roughing, Visualizer Fixes
## Date: 2026-05-16
## Status: All roughing strategies working (OD staircase, OD contour, ID staircase). Visualizer renders arcs smoothly.

## Major Accomplishments This Session

### 1. Validator Arc Chord Fix
- `validation/post_planning_validator.py` — arc moves now densified before crossing checks
- Uses `adaptive_densify_arc` (same as polygon construction) for accurate arc path validation
- Eliminates false positives where arc chord crosses finished part but actual arc curves away

### 2. ID Bore Mode (Full Implementation)
- **Zone builder** (`geometry/zone_builder.py`): offset direction fixed (always positive), MTR Z_end clipped by fin_allowance for ID
- **Staircase planner**: Z_begin = Z_start for ID, passes build outward from pilot hole
- **Cleanup planner**: separate `_compute_offset_profile_id()` method — kernel-driven, handles arcs
- **Finish planner**: Z_start approach for ID when no TFZ
- **G-code writer**: `safe_x = pilot_hole_dia` for ID (approach/retract from bore center)
- **Pipeline**: TFZ collapse detection (X_start = first segment X → no face passes)
- **Validated against NX ground truth** — all 13 roughing passes, cleanup contour, finish contour match exactly

### 3. Contour/Offset Roughing (OD)
- **New file**: `planners/contour_roughing_planner.py` — `ContourRoughingPlanner`
- Algorithm: offset finished part face at DOC intervals, clip to stock rectangle, extract turning edges
- Same `b3d_offset` + `BRepAlgoAPI_Common` pattern as cleanup planner, in a loop
- Handles split passes (arc exceeds stock OD → single face with concave boundary, stock OD connector kept)
- 9 passes generated matching NX ground truth structure
- Passes reversed for cutting order (outermost first, working inward)

### 4. Arc Peak Retract Logic
- `_compute_pass_max_x()` in G-code writer computes true max X including arc peaks
- Arc peak = `(center_x_r + radius_r) * 2` when arc bulges outward
- Capped at stock OD (no retract beyond stock)
- Universal: works for staircase, contour, and future tapers

### 5. Visualizer Fixes
- **Graph adapter** (`outputs/graph_adapter.py`): arc moves densified for smooth curve rendering
- **SimMove parser**: now extracts I/K words from G-code
- **Smooth playback**: pre-computed interpolated path with arc interpolation, ~60fps timer
- Rapids move fast, feeds move slow, arcs trace the actual curve

## Files Modified/Created This Session
- `validation/post_planning_validator.py` — arc densification for crossing checks
- `geometry/zone_builder.py` — ID offset direction, MTR Z_end clip
- `planners/staircase_planner.py` — z_begin logic for ID
- `planners/cleanup_planner.py` — ID-specific offset method, zone boundary fallback removed
- `planners/finish_planner.py` — ID Z_start approach
- `planners/contour_roughing_planner.py` — NEW (contour roughing)
- `pipeline/pipeline.py` — TFZ collapse, contour planner wiring
- `outputs/gcode_writer.py` — safe_x for ID, arc peak retract
- `outputs/graph_adapter.py` — arc densification for display
- `_visual_test_arc.py` — SimMove I/K parsing, smooth interpolated playback
- `_visual_test_contour.py` — contour roughing visualizer
- `_visual_test_id_bore.py` — ID bore visualizer
- `_export_contour_od.py` — contour roughing DXF/G-code export
- `_export_id_bore.py` — ID bore DXF/G-code export
- `.kiro/steering/id-program-rules.md` — NEW (ID rules and lessons)
- `.kiro/steering/contour-roughing-rules.md` — NEW (contour roughing rules)
- `.kiro/steering/zone-mental-model.md` — updated with ID rules, retract logic, validator future work
- `.kiro/steering/ground-truth-fixtures.md` — updated with contour roughing lessons
- `tests/ground_truth/stepped_id.json` — DOC corrected to 0.050 (from DXF)

## NX Ground Truth Status

| Profile | Staircase | Contour | Cleanup | Finish |
|---------|-----------|---------|---------|--------|
| Arc OD | ✅ Match | ✅ Match (9 passes) | ✅ Match | ✅ Match |
| Stepped OD | ✅ Match | N/A | ✅ Match | ✅ Match |
| Stepped ID | ✅ Match (13 passes) | Not yet (need DXF) | ✅ Match | ✅ Match |

## Known Issues / Future Work

1. **Uncut material validator** — current validator only checks Finished Part/Finish Allowance. Does NOT detect rapids through uncut stock within MTR zone. Needs swept region tracking per pass execution order.
2. **ID contour roughing** — architecture ready, needs NX ground truth DXF with arcs to validate
3. **Debug tab Export buttons** — not wired to actual exporters yet
4. **GUI polish** — many tabs need work (next session focus)
5. **Contour roughing approach logic** — currently feeds along stock OD between split sections. May want retract to stock OD + 0.005" for safety margin (discussed, deferred).

## Key Lessons This Session

1. Always start from NX ground truth — parse DXFs first, then make engine match
2. ID is the mirror of OD — same architecture, inverted geometry parameters
3. Don't abandon proven architecture — adapt it (cleanup offset+clip → contour roughing loop)
4. Decouple OD and ID code paths completely — no shared logic that could regress
5. Contour roughing = cleanup planner in a loop (same offset+clip at DOC intervals)
6. Single face with concave boundary, not multiple faces (OCCT clip behavior)
7. Retract X must account for arc peaks, not just endpoint X values
8. Wire traversal direction ≠ cutting direction (reverse + chain for correct order)
