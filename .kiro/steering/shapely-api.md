---
inclusion: auto
---

# Shapely API Reference (Runtime Validation)

## Overview

Shapely is a Python package for manipulation and analysis of planar geometric objects, built on the GEOS library. We use it as a RUNTIME dependency for fast safety validation of planned toolpaths.

Documentation: https://shapely.readthedocs.io/en/stable/
PyPI: https://pypi.org/project/Shapely/

## Our Usage: Fast Polygon-Based Safety Checks

Shapely validates that planned moves don't violate zone boundaries. It does NOT produce toolpath coordinates — Build123d does that. Shapely confirms they're safe.

## Core Types We Use

### Polygon
A closed region defined by an exterior ring of (x, y) coordinates.
```python
from shapely.geometry import Polygon

# Build keep_zone polygon from boundary coordinates
# Coordinates are (x_radius, z) — same as Build123d sketch plane
coords = [(0.0, 0.0), (0.501, 0.001), (0.501, -0.501), ...]
keep_zone_poly = Polygon(coords)

# Properties
keep_zone_poly.area        # Area in square inches
keep_zone_poly.boundary    # The exterior ring as a LineString
keep_zone_poly.exterior    # The exterior ring (LinearRing)
keep_zone_poly.is_valid    # True if geometry is valid
```

### Point
A single (x, y) coordinate for containment testing.
```python
from shapely.geometry import Point

# Test if a pass endpoint is inside the keep zone
pt = Point(0.501, -0.590)  # (x_radius, z)
is_inside = keep_zone_poly.contains(pt)  # True = GOUGE
```

### LineString
A sequence of (x, y) coordinates forming a line for intersection testing.
```python
from shapely.geometry import LineString

# Test if a rapid move crosses the keep zone boundary
rapid_line = LineString([(0.625, -0.5), (0.501, -0.5)])  # start → end
crosses = rapid_line.intersects(keep_zone_poly.boundary)  # True = UNSAFE
```

## Key Operations for Validation

### contains(point) — Point-in-Zone Test
```python
# Is this pass endpoint inside the keep zone? (gouge check)
keep_zone_poly.contains(Point(x_radius, z))  # ~2 microseconds

# IMPORTANT: contains() returns False for points ON the boundary
# Use covers() if boundary points should count as "inside"
keep_zone_poly.covers(Point(x_radius, z))
```

### intersects(geometry) — Line-Zone Crossing
```python
# Does this rapid move cross the keep zone boundary?
line = LineString([(x1_r, z1), (x2_r, z2)])
line.intersects(keep_zone_poly.boundary)  # True = rapid crosses boundary

# Does this feed move enter the finished part?
line.intersects(finished_part_poly)  # True = gouge
```

### intersection(geometry) — Get Crossing Points
```python
# Where exactly does the rapid cross the boundary?
crossings = line.intersection(keep_zone_poly.boundary)
# Returns Point, MultiPoint, or GeometryCollection
```

### difference(geometry) — Material Remaining
```python
# How much material is left after all passes?
remaining = material_to_remove_poly.difference(tool_swept_poly)
remaining.area  # Should be < TOLERANCE_SQ for full coverage
```

### buffer(distance) — Offset/Expand Polygon
```python
# Expand finished_part by fin_allowance to get keep_zone
# (Used in oracle for independent verification, NOT in production zone construction)
keep_zone_poly = finished_part_poly.buffer(fin_allowance)

# buffer() parameters:
# distance > 0 = expand (dilation)
# distance < 0 = shrink (erosion)
# quad_segs = number of segments per quarter circle (default 8)
# join_style = 'round' (default), 'mitre', 'bevel'
```

### unary_union(geometries) — Merge Multiple Polygons
```python
from shapely.ops import unary_union

# Union all swept rectangles into one region
tool_swept = unary_union(swept_polygons)
```

## Performance Characteristics

| Operation | Typical Time | Notes |
|-----------|-------------|-------|
| Polygon construction (50 vertices) | ~0.01ms | One-time |
| Point.contains() | ~2µs | Per check |
| LineString.intersects(boundary) | ~5µs | Per rapid |
| Polygon.difference() | ~5-50ms | Full coverage check |
| unary_union(100 polygons) | ~20ms | Swept area merge |

## Polygon Construction from Build123d Boundary

```python
from shapely.geometry import Polygon

def build_validation_polygon(edges, cos_limit=0.9999):
    """Convert Build123d boundary edges to Shapely Polygon.
    
    Args:
        edges: List from ZoneQueryAPI.boundary_wire_extraction()
               Each edge: {"type": "LINE"|"ARC", "start": (x_dia, z), 
                          "end": (x_dia, z), ...}
        cos_limit: Adaptive densification threshold (0.9999 = max error ~R×0.0001)
    
    Returns:
        Shapely Polygon in (x_radius, z) coordinates
    """
    coords = []
    for edge in edges:
        start_x_r = edge["start"][0] / 2.0  # diameter → radius
        start_z = edge["start"][1]
        end_x_r = edge["end"][0] / 2.0
        end_z = edge["end"][1]
        
        if not coords:
            coords.append((start_x_r, start_z))
        
        if edge["type"] == "LINE":
            coords.append((end_x_r, end_z))
        elif edge["type"] == "ARC":
            # Adaptive densification
            arc_points = densify_arc_adaptive(
                start=(start_x_r, start_z),
                end=(end_x_r, end_z),
                center=(edge["center"][0] / 2.0, edge["center"][1]),
                radius=edge["radius"],
                direction=edge["direction"],
                cos_limit=cos_limit,
            )
            coords.extend(arc_points)
    
    return Polygon(coords)
```

## Adaptive Arc Densification

```python
import math

def densify_arc_adaptive(start, end, center, radius, direction, cos_limit=0.9999, depth=0, max_depth=12):
    """Recursively bisect arc until cosine-limit flatness predicate satisfied.
    
    Maximum chord error = R × (1 - cos_limit) = R × 0.0001 for cos_limit=0.9999
    For R=0.251" (hump test): max error = 0.0000251" (50× tighter than TOLERANCE)
    """
    if depth >= max_depth:
        return [end]
    
    # Compute arc midpoint
    mid = arc_midpoint(start, end, center, radius, direction)
    
    # Flatness predicate: are start→mid→end collinear enough?
    v1 = normalize((mid[0] - start[0], mid[1] - start[1]))
    v2 = normalize((end[0] - mid[0], end[1] - mid[1]))
    dot_product = v1[0] * v2[0] + v1[1] * v2[1]
    
    if dot_product >= cos_limit:
        return [end]  # Flat enough — single chord acceptable
    
    # Not flat — bisect
    left = densify_arc_adaptive(start, mid, center, radius, direction, cos_limit, depth + 1, max_depth)
    right = densify_arc_adaptive(mid, end, center, radius, direction, cos_limit, depth + 1, max_depth)
    return left + right
```

## Important Notes

1. **Shapely works in (x, y) coordinates** — we map (x_radius, z_lathe) to Shapely's (x, y)
2. **All X values must be in RADIUS** when building Shapely polygons (divide diameter by 2)
3. **Polygon must be valid** — use `polygon.is_valid` to check, `make_valid(polygon)` to fix
4. **contains() excludes boundary** — a point exactly ON the boundary returns False
5. **Inscribed chord property** — polygon chords are inside the true arc, making containment checks conservative (safe)
6. **Thread safety** — Shapely operations are NOT thread-safe. Validation runs in the main thread.
