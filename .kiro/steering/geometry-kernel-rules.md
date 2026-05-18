---
inclusion: auto
---

# Geometry Kernel Rules — Build123d as Single Source of Truth

## The One Rule

ALL geometric answers come from Build123d/OCCT. No exceptions. No fallbacks. No hand math.

## What the Kernel Provides

| Query | Method | Returns |
|-------|--------|---------|
| Where does material exist at X level? | `ZoneQueryAPI.boundary_at_x(x_dia, zone)` | List of Z crossings |
| Where does material exist at Z level? | `geometry.intervals_at_z(zones, z_level)` | List of (x_outer, x_inner) |
| Is this point inside a zone? | `ZoneQueryAPI.point_in_zone(x_dia, z, zone)` | bool |
| Does this line cross a zone boundary? | `ZoneQueryAPI.line_zone_intersection(...)` | List of (x_dia, z) crossings |
| What is the Roughing Boundary contour? | `ZoneQueryAPI.boundary_wire_extraction("roughing_boundary")` | List of edge descriptors |
| What is the offset profile? | `geometry.build_zones()` (offset operation) | ZoneSet with zone Faces |

## What the Kernel Does NOT Provide (Use Shapely Instead)

| Query | Why Not Kernel | Use Instead |
|-------|---------------|-------------|
| Fast point-in-zone for 360 checks | Too slow (~0.5ms each) | Shapely polygon.contains() |
| Fast line-intersection for rapid safety | Too slow for every rapid | Shapely line.intersects(boundary) |
| Area-based coverage verification | Not implemented in production | Shapely difference().area |

## Zone Construction Flow

```
ClosedProfile + RoughingParams + mode
    → build_zones()
        1. Build Finished Part Face (profile + centerline/stock closure)
        2. Offset Profile Boundary by fin_allowance → Roughing Boundary
        3. Build Stock Boundary rectangle Face
        4. Derive zones:
           - Finish Allowance Zone = area between Roughing Boundary and Profile Boundary
           - Material to Rough Out = area between Stock Boundary and Roughing Boundary
        5. Split Material to Rough Out: True Face Zone (Z >= Z_start to Z=0) and Turning Zone (Z < Z_start)
    → ZoneSet (all Faces stored)
```

## Offset Rules

- Offset is ALWAYS via the kernel's `offset()` operation on a Face
- For OD: offset AWAY from centerline (positive amount expands the face)
- For ID: offset TOWARD centerline (positive amount on the finished_part face expands it toward pilot hole)
- The kernel handles arc radius adjustment automatically (convex arcs shrink, concave arcs grow)
- NEVER manually compute `R - fin_allowance` or `R + fin_allowance`

## Arc Direction in Build123d

Profile convention → Build123d RadiusArc:
- Profile CW (positive radius) → RadiusArc NEGATIVE radius
- Profile CCW (negative radius) → RadiusArc POSITIVE radius

This is because:
- Profile CW = center on right of travel direction
- Build123d positive RadiusArc = center on left of travel direction
- They're opposite conventions

## Query Caching

ZoneQueryAPI queries are expensive (~0.5ms each). The Fiber/Interval layer caches results:
- Each Fiber caches its intervals after first query
- The turning planner queries each X level exactly ONCE
- The interval chart is built from cached Fibers

## Error Policy

```python
# If the kernel fails, RAISE. Never fall back.
section = BRepAlgoAPI_Section(face, line_edge)
section.Build()
if not section.IsDone():
    raise RuntimeError(f"boundary_at_x failed at x_dia={x_dia}")

# If the result is empty, that's information (no material at this level).
# Empty result is NOT an error — it means the pass level is beyond the profile.
if not z_values:
    return []  # Valid: no material here
```

## Adding New Queries

If you need a geometric answer the kernel doesn't currently provide:

1. Add a new method to `ZoneQueryAPI` (e.g., `tangent_at_boundary(x_dia, zone)`)
2. Implement it using OCCT operations (BRepAdaptor, BRepAlgoAPI, etc.)
3. The method accepts X in DIAMETER, converts internally to radius
4. The method raises RuntimeError on kernel failure
5. The method logs at DEBUG level

NEVER work around a missing query with hand math. Add the query.

## ContourIntersect — Wire-Based Interval Finding

For toolpath planning (finding Z intervals at each X level), use `ContourIntersect` instead of `boundary_at_x`:

```python
from geometry.contour_intersect import ContourIntersect
ci = ContourIntersect(zone_set)
intervals = ci.intervals_at_x(x_dia, "material_to_rough")
```

How it works:
1. Extracts ALL wires from the zone's raw shape (Compound from boolean ops)
2. Builds a horizontal line edge at the given X level
3. Intersects line against wires using `BRepAlgoAPI_Section(wire, line_edge)`
4. Sorts intersection Z values, forms candidate segments
5. Classifies each segment midpoint against the zone face using `BRepClass_FaceClassifier`
6. Returns segments classified as IN (material)

Key implementation details:
- The face classifier requires a `TopoDS_Face`, not a `TopoDS_Compound` — extract it
- Use `gp_Pnt` (3D point), NOT `gp_Pnt2d` (UV parametric) for face classification
- Wire extraction uses the raw shape (may be Compound); face classification uses the extracted Face

## Cleanup Pass Offset — Kernel Only

The cleanup pass contour is computed by:
1. Building the Finished Part face from profile segments + closure (same as zone_builder)
2. Offsetting it by fin_allowance using `Build123d offset(face, amount, kind=Kind.INTERSECTION)`
3. Clipping to the turning region using `BRepAlgoAPI_Common(offset_face, clip_rectangle)`
4. Extracting turning edges from the clipped wire (skip edges on clip boundaries)
5. Ordering edges top-to-bottom and converting to ToolMoves

NEVER compute offset coordinates by adding fin_allowance to X values or radius values manually.
