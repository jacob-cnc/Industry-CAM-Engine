# Checkpoint 6 — ContourIntersect, Cleanup Offset, Finish Pass Fixed
## Date: 2026-05-16
## Status: Staircase Z-boundaries fixed, cleanup pass offset implemented, finish pass corrected

## Major Accomplishments This Session

### ContourIntersect Module (NEW)
- `geometry/contour_intersect.py` — decouples toolpath planning from zone face queries
- Intersects horizontal line against zone boundary WIRE (not face) using `BRepAlgoAPI_Section`
- Classifies segments via `BRepClass_FaceClassifier` with `gp_Pnt` (3D, not 2D UV)
- Extracts `TopoDS_Face` from Compound shapes (boolean cut results wrap in Compounds)
- Caches faces, shapes, and wires per zone for performance
- Staircase planner now uses ContourIntersect — matches NX ground truth at all X levels

### Staircase Planner Z-Boundary Fix
- At X levels where the MTR arc is crossed: correctly returns 2 intervals (split by arc)
- At X levels above arc extent: correctly returns 1 interval (arc doesn't reach)
- Verified against NX staircase DXF — merged intervals match exactly at every X level
- Only remaining difference: NX has sub-segment markers at offset arc intersections (informational, not functional)

### Cleanup Pass Rewritten (Kernel Offset + Clip)
- **Definition**: Finished Part offset equidistant by fin_allowance, clipped at Z0+fin, Z_end, X_start+fin
- Offsets the finished part face using Build123d `offset()` (kernel operation, no hand math)
- Clips to turning region using `BRepAlgoAPI_Common` with a clip rectangle
- Extracts turning edges from clipped wire, orders top-to-bottom, converts to ToolMoves
- Approach: rapid to stock OD at Z0+fin → rapid X to X_start+fin → feed along face to offset X → follow offset contour
- Arc at offset coordinates: X=1.002 dia, R=1.001, center=(-0.732 dia, -1.000)
- Matches NX cleanup pass reference DXF

### Finish Pass Fixed
- Traces exact profile contour (not offset) — distinct from cleanup
- Approach: rapid to (X_start, Z0+fin), feed to (X_start, Z0), then trace all profile segments
- Arc I/K computed correctly from endpoints and radius using `_find_arc_center`
- Full profile sequence: face segment → straight down → arc → straight down

### G-Code Writer Improvements
- Cleanup approach: rapid to stock OD at Z0+fin, rapid to X_start+fin, then pass moves
- Finish approach: rapid to stock OD at Z0+fin, rapid to X_start, then pass moves
- Zero-length move suppression in `_emit_move`
- Zero-length move filtering in `_assemble_moves` (pipeline)

### Transition Planner Updated
- Cleanup/finish transitions target the pass's actual start position (x_level, z_start)
- No more rapiding to centerline then feeding diagonally through the part

### DXF Export Fixed
- Arc rendering: always use `start_angle=ea, end_angle=sa` for both G02/G03
- Guard against zero I/K (invalid center) — skip arc, draw line
- Removed zone boundary layers (clutter), clean toolpath-only output
- Colors: rough=green(3), cleanup=dark green(94), finish=blue(5), face=yellow(14), rapid=red(1)

## NX Ground Truth Delta (Final)

### Staircase Roughing
| X dia range | NX intervals | Our intervals | Status |
|-------------|-------------|---------------|--------|
| 1.450–1.300 | 1 continuous | 1 continuous | ✅ Match |
| 1.250–1.050 | 2 (split at MTR arc) | 2 (split at MTR arc) | ✅ Match |
| 1.002 | 2 (roughing boundary) | 2 (roughing boundary) | ✅ Exact |

### Cleanup Pass
- X = 1.002 dia (offset) ✅
- Arc R = 1.001 (offset) ✅
- Arc center = (-0.732 dia, -1.000) ✅
- Z boundaries: 0.001, -0.4997, -1.5003, -2.000 ✅

### Finish Pass
- X = 1.000 dia (profile) ✅
- Arc R = 1.000 (profile) ✅
- I/K = (-1.7321, -0.5000) ✅
- Full contour from Z=0 to Z=-2.000 ✅

## Big Lessons Learned

### 1. Zone building and toolpath planning are different jobs
Zones = boolean ops on faces (working). Toolpath planning = intersect lines against boundary wires, classify with face. ContourIntersect bridges this gap.

### 2. The CAD kernel does the geometry — never hand math
Every hand-math attempt (arc centers, coordinate offsets, tolerance filters) was wrong or fragile. The kernel handles offsets, intersections, clipping, and classification. Ask it the right question.

### 3. Cleanup pass ≠ Finish pass
- Cleanup: offset coordinates (X+fin, R+fin). Removes bulk of fin_allowance.
- Finish: profile coordinates. Final surface.
- G41/G42 handles TNR separately for both.

### 4. Always validate against NX ground truth DXFs
Parse reference DXFs, compare coordinates. Round-trip (generate → parse → DXF → overlay) is the only reliable validation. Code review means nothing until the DXF matches.

### 5. Approach sequence matters as much as the contour
Half the bugs were in how the tool gets TO the contour. Must be safe (no rapids through material) and land at the correct start point.

## Files Modified This Session
- `geometry/contour_intersect.py` — NEW (wire intersection + face classification)
- `geometry/__init__.py` — added ContourIntersect export
- `geometry/zone_query.py` — unchanged (ContourIntersect is separate module)
- `planners/staircase_planner.py` — uses ContourIntersect, updated terminology
- `planners/cleanup_planner.py` — REWRITTEN (kernel offset + clip)
- `planners/finish_planner.py` — REWRITTEN (full profile trace, I/K computation)
- `pipeline/pipeline.py` — creates ContourIntersect, passes to staircase, zero-length filtering
- `outputs/gcode_writer.py` — cleanup/finish approach sequences, zero-length suppression
- `transitions/transition_planner.py` — cleanup/finish target actual start position
- `.kiro/steering/ground-truth-fixtures.md` — lessons learned, engine output tracking
- `.kiro/steering/zone-mental-model.md` — cleanup/finish pass definitions
- `reference/CAD Reference/GROUND_TRUTH_NOTES.md` — updated delta table, NX staircase analysis
- `reference/CAD Reference/Engine Output/Arc OD/` — Arc_OD_Staircase.ngc + .dxf
- `_export_arc_od_dump.py` — updated DXF export (colors, arc rendering)

## Next Steps (Priority Order)
1. Fix validator arc chord check (false positive on cleanup/finish arcs)
2. Run full pipeline validation on arc OD (currently blocked by validator)
3. Verify stepped OD still passes full pipeline (confirmed working without validation)
4. Fix ID bore mode (staircase planner generates passes beyond bore wall)
5. Wire offset-contour/waterfall roughing strategy
6. Wire Debug tab Export buttons to actual exporters
