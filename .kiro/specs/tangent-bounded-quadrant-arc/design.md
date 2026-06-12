# Tangent-Bounded Quadrant Arc — Design

## Overview

Replace the polyline approximation in `zone_builder.py` with proper Build123d geometric primitives for quadrant arc segments ("Q" and "-Q"). The kernel constructs exact conic edges which flow through the existing wire extraction pipeline. The finish planner decomposes non-circular edges into multi-arc G2/G3 sequences during edge-to-move conversion. Preview rendering remains unchanged (hand-math for performance).

## Architecture

```
User Input ("Q"/"-Q")
    → model_builder.py: ProfileMove(quadrant=True, quadrant_sign=+1/-1)
    → zone_builder.py: Build123d EllipticalCenterArc or Spline edge
    → Zone faces (exact conic geometry)
    → Finish planner: wire extraction → edge decomposition → ToolMoves (G2/G3)
    → G-code writer: standard G2/G3 output
```

## Data Model Changes

### `models/profile.py` — ProfileMove

Add `quadrant_sign` field:
```python
@dataclass(frozen=True)
class ProfileMove:
    segment_type: SegmentType
    x: float
    z: float
    radius: float = 0.0
    quadrant: bool = False
    quadrant_sign: int = 1  # +1 = convex (Q), -1 = concave (-Q)
```

### `pipeline/model_builder.py`

Detect "Q" and "-Q" strings:
- "Q" → `ProfileMove(quadrant=True, quadrant_sign=1, radius=0.0)`
- "-Q" → `ProfileMove(quadrant=True, quadrant_sign=-1, radius=0.0)`

### `gui/components/segment_list.py`

- `_read_row()`: detect "Q" and "-Q" in radius field
- `_validate_arc_radius()`: accept both as valid
- Wizard hint: suggest "Q" and "-Q" options

## Zone Builder Construction

### Axis-Aligned Detection

A quadrant arc is axis-aligned when:
- `|x_start_r - x_end_r| < TOLERANCE` (same X → vertical chord), OR
- `|z_start - z_end| < TOLERANCE` (same Z → horizontal chord)

Axis-aligned means the arc is a true quarter-circle (single radius = the non-shared delta). Off-axis means it's elliptical.

### Axis-Aligned Case: EllipticalCenterArc

For +Q (convex):
- Center at the bounding box corner where tangent lines meet: `(x_start_r, z_end)` or `(x_end_r, z_start)` depending on direction
- This is a circular arc (radius = delta) since one axis is zero

For -Q (concave):
- Center at the opposite bounding box corner: `(x_end_r, z_start)` or `(x_start_r, z_end)`

Build123d construction:
```python
from build123d import RadiusArc
# Axis-aligned is actually a circular arc with known radius
radius = abs(delta)  # the non-zero delta
# Sign convention maps to Build123d sign
RadiusArc(start, end, signed_radius)
```

### Off-Axis Case: Rational Quadratic Bézier Spline

For +Q (convex):
- Control point P1 = intersection of tangent lines = bounding box corner `(x_start_r, z_end)`
- Weight w = cos(π/4) ≈ 0.7071 for exact quarter-ellipse

For -Q (concave):
- Control point P1 = opposite bounding box corner `(x_end_r, z_start)`
- Same weight

Build123d construction:
```python
from OCP.Geom2dAPI import Geom2dAPI_PointsToBSpline
from OCP.TColgp import TColgp_Array1OfPnt2d
from OCP.TColStd import TColStd_Array1OfReal
# Or use build123d Spline with tangent constraints
from build123d import Spline
Spline(start, end, tangents=[entry_tangent, exit_tangent])
```

## Finish Planner Edge Decomposition

### Current Flow

`_moves_from_edges()` already handles LINE and ARC edge types from wire extraction. It needs a third path for ELLIPSE/BSPLINE edges.

### Decomposition Algorithm

For non-circular edges (elliptical arcs, splines):
1. Sample the curve parametrically at uniform intervals
2. At each sample point, compute the local curvature
3. Fit a circular arc between consecutive sample points
4. Check chord error — if exceeds tolerance, subdivide
5. Output sequence of ToolMoves with arc center (I, K) for each sub-arc

Use OCCT's `GCPnts_AbscissaPoint` and `BRepAdaptor_Curve` for parametric sampling and curvature queries.

### Chord-Error Tolerance

Default: `0.0001"` (0.1 thou) — matches typical lathe finishing accuracy.
Configurable via a constant in `models/constants.py`.

## Preview Rendering

Uses the kernel — `program_tab.py` constructs the quadrant arc edge via Build123d (same code path as zone builder) and extracts sample points from the OCCT edge for display. This eliminates `interpolate_quadrant_arc()` as a separate code path. Performance cost is ~1.3ms per quadrant arc (well within the 16ms frame budget for profiles with up to 10 segments).

## Affected Files

| File | Change |
|------|--------|
| `models/profile.py` | Add `quadrant_sign` field to ProfileMove |
| `models/constants.py` | Add `QUADRANT_CHORD_ERROR` constant |
| `pipeline/model_builder.py` | Parse "-Q", set `quadrant_sign` |
| `gui/components/segment_list.py` | Accept "-Q" in R field |
| `geometry/zone_builder.py` | Replace polyline with EllipticalCenterArc/Spline |
| `geometry/arc_helpers.py` | Remove `interpolate_quadrant_arc` (no longer needed) |
| `gui/program_tab.py` | Use kernel for preview (replace hand-math interpolation) |
| `planners/finish_planner.py` | Add edge decomposition for non-circular edges |
