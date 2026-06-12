# Implementation Plan

## Overview

Replace polyline approximation of quadrant arcs with Build123d geometric primitives. Add "-Q" support for concave arcs. Implement edge decomposition in the finish planner for non-circular edges. Output as standard G2/G3 moves.

## Tasks

- [x] 1. Data model: Add quadrant_sign to ProfileMove
  - Add `quadrant_sign: int = 1` field to `ProfileMove` dataclass in `models/profile.py`
  - +1 = convex (Q), -1 = concave (-Q)
  - Add `QUADRANT_CHORD_ERROR = 0.0001` to `models/constants.py`
  - _Requirements: 10.1, 10.2, 7.2_

- [x] 2. Input parsing: Handle "-Q" through the pipeline
  - Update `pipeline/model_builder.py` to detect "-Q" string → `ProfileMove(quadrant=True, quadrant_sign=-1)`
  - Update `gui/components/segment_list.py` `_read_row()` to detect "-Q"
  - Update `_validate_arc_radius()` to accept "-Q" as valid
  - Update wizard hint to mention "-Q" option
  - _Requirements: 10.1, 10.2, 10.3_

- [x] 3. Zone builder: Axis-aligned detection
  - In `geometry/zone_builder.py`, add detection logic in `_build_face_from_coords()`
  - Axis-aligned: `|x_start - x_end| < TOLERANCE` OR `|z_start - z_end| < TOLERANCE`
  - Off-axis: both differ beyond tolerance
  - _Requirements: 1.1, 1.2, 1.3_

- [x] 4. Zone builder: Axis-aligned arc construction (EllipticalCenterArc or RadiusArc)
  - For axis-aligned quadrant arcs, use Build123d `RadiusArc` (since one axis is zero, it's a true circular quarter-arc)
  - Compute center at the bounding box corner based on `quadrant_sign`
  - +Q: center at tangent-line intersection corner
  - -Q: center at opposite corner (mirrored)
  - Derive the signed radius for Build123d convention
  - Remove the polyline `Line()` loop for axis-aligned cases
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 4.1, 4.2, 5.1_

- [x] 5. Zone builder: Off-axis arc construction (Spline)
  - For off-axis quadrant arcs, use Build123d `Spline` with tangent constraints at endpoints
  - Entry tangent: direction of previous segment (horizontal or vertical for standard cases)
  - Exit tangent: direction of next segment
  - Control point at bounding box corner (+Q) or opposite corner (-Q)
  - Remove the polyline `Line()` loop for off-axis cases
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 4.3, 5.1, 5.2, 5.3_

- [x] 6. Finish planner: Edge decomposition for non-circular edges
  - In `planners/finish_planner.py` `_moves_from_edges()`, add handling for elliptical/spline edge types
  - Use OCCT `BRepAdaptor_Curve` to parametrically sample the edge
  - Decompose into circular arc segments using biarc or chord-error-based subdivision
  - Each sub-arc becomes a ToolMove with computed center (I, K)
  - Ensure endpoint continuity (no drift between consecutive arcs)
  - Use `QUADRANT_CHORD_ERROR` from constants
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 7.1, 7.3, 7.4_

- [x] 7. G-code writer: Verify standard output
  - Confirm the G-code writer emits decomposed quadrant arc moves as standard G2/G3
  - No changes expected — decomposed moves are already ToolMoves with arc type
  - Verify endpoint + I/K format matches existing arc output
  - _Requirements: 8.1, 8.2, 8.3_

- [x] 8. Preview rendering: Use kernel for display
  - Replace `interpolate_quadrant_arc()` call in `program_tab.py` with Build123d Spline/RadiusArc construction
  - Extract display points from the OCCT edge using parametric sampling
  - Handle both Q and -Q via the same kernel path
  - Remove `interpolate_quadrant_arc()` from `geometry/arc_helpers.py` (no longer needed)
  - Verify preview performance stays under 16ms for profiles with multiple quadrant arcs
  - _Requirements: 9.1, 9.2, 9.3, 9.4_

- [x] 9. Integration test: Full pipeline with Q arc
  - Define a profile with a Q segment, generate toolpath, verify:
    - No gouge errors from Shapely validator
    - Finish pass traces the correct elliptical contour
    - G-code contains multiple G2/G3 moves approximating the ellipse
  - Test with -Q segment as well
  - Test axis-aligned case (same X or same Z)
  - Test off-axis case (different X and Z)

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1"] },
    { "id": 1, "tasks": ["2", "8"] },
    { "id": 2, "tasks": ["3"] },
    { "id": 3, "tasks": ["4", "5"] },
    { "id": 4, "tasks": ["6"] },
    { "id": 5, "tasks": ["7"] },
    { "id": 6, "tasks": ["9"] }
  ]
}
```

## Notes

- The preview renderer uses the kernel (Build123d) for quadrant arcs — single source of truth, ~1.3ms per arc (within 16ms budget)
- The zone builder constructs exact geometry; the planner decomposes it for G-code
- Axis-aligned detection is based on endpoint coordinates, not adjacent segment directions
- `interpolate_quadrant_arc()` in `arc_helpers.py` will be removed once preview uses the kernel
- Chord-error tolerance default: 0.0001" (can be tuned per job if needed later)
- Build123d `Spline` with tangent constraints is the preferred approach for off-axis cases — avoids manual OCCT NURBS construction
