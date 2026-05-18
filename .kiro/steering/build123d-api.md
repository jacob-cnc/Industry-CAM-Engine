---
inclusion: auto
---

# Build123d API Reference (2D Sketch Operations)

## Overview

Build123d is a Python parametric CAD framework built on OpenCascade (OCCT). We use it exclusively for 2D Face construction and boolean operations in the XY sketch plane (where X = radius, Y = lathe Z coordinate).

Documentation: https://build123d.readthedocs.io/en/latest/
PyPI: https://pypi.org/project/build123d/

## Core Pattern: BuildSketch + BuildLine + make_face

All zone construction follows this pattern:

```python
from build123d import BuildSketch, BuildLine, Line, RadiusArc, make_face, offset

with BuildSketch() as sketch:
    with BuildLine():
        # Trace a closed contour using Line and RadiusArc
        Line((0.0, 0.0), (0.5, 0.0))       # face line
        Line((0.5, 0.0), (0.5, -0.5))       # OD straight
        RadiusArc((0.5, -0.5), (0.5, -1.0), -0.25)  # arc segment
        Line((0.5, -1.0), (0.5, -2.0))      # OD straight
        Line((0.5, -2.0), (0.0, -2.0))      # closure to centerline
        Line((0.0, -2.0), (0.0, 0.0))       # centerline back to start
    make_face()  # Convert closed wire to Face

face = sketch.sketch.face()  # Extract the Face object
```

## Key Operations

### Line(start, end)
Creates a straight edge between two 2D points.
```python
Line((x1, y1), (x2, y2))
```

### RadiusArc(start, end, radius)
Creates a circular arc between two points with given radius.
- **Positive radius** = shorter arc (center on LEFT of start→end direction)
- **Negative radius** = longer arc (center on RIGHT of start→end direction)

**CRITICAL for lathe work:**
- Profile CW (G02, positive profile radius) → Build123d **NEGATIVE** RadiusArc radius
- Profile CCW (G03, negative profile radius) → Build123d **POSITIVE** RadiusArc radius

```python
# Hump test arc: CW in lathe convention, dips toward centerline
# Profile radius = +0.25 (CW) → Build123d radius = -0.25
RadiusArc((0.5, -0.5), (0.5, -1.0), -0.25)
```

### make_face()
Converts the closed wire (from BuildLine) into a 2D Face. Must be called inside BuildSketch after BuildLine completes. The wire MUST be closed (last point = first point within tolerance).

### offset(face_or_sketch, amount, kind=Kind.ARC)
Equidistant offset of a Face or Sketch.
- **amount > 0** = expand outward (face grows)
- **amount < 0** = shrink inward (face contracts)
- **kind=Kind.ARC** = round corners (default)
- **kind=Kind.INTERSECTION** = extend edges to meet at corners (sharp, no fillets)

```python
from build123d import offset, Kind

# Offset finished_part outward by fin_allowance
keep_zone_offset = offset(finished_part_face, amount=0.001)
keep_zone_face = keep_zone_offset.face()
```

**For our engine:** We use `Kind.INTERSECTION` for open wire offsets (cleanup pass) and default `Kind.ARC` for closed face offsets (zone construction).

### Boolean Operations (Face arithmetic)
```python
# Subtraction: material_to_remove = stock - keep_zone
result = stock_face - keep_zone_face

# Intersection: face_zone = material & clip_rectangle
result = material_face & clip_face

# Union (fuse): combined = face_a.fuse(face_b)
result = face_a.fuse(face_b)
```

**Return types:**
- Boolean operations may return a `Face` or a `ShapeList` (multiple faces)
- Always check: `if isinstance(result, ShapeList): face = max(result, key=lambda f: f.area)`
- Check for None and degenerate results: `if result is None or result.area < 1e-10: raise`

### Face Properties
```python
face.area          # Area in square units
face.wrapped       # The underlying OCP TopoDS_Face (for direct OCCT operations)
```

## OCP (OpenCascade) Operations We Use Directly

These are used in `ZoneQueryAPI` for geometric queries against the Faces:

### BRepAlgoAPI_Section(face, edge)
Intersects a Face with an Edge. Returns edges/vertices where they cross.
Used for: `boundary_at_x()`, `intervals_at_x()`, `intervals_at_z()`

### BRepClass_FaceClassifier(face, uv_point, tolerance)
Classifies a point as IN, ON, OUT, or UNKNOWN relative to a Face.
Used for: `point_in_zone()`

### BRepTools.OuterWire_s(face)
Extracts the outer boundary wire of a Face.
Used for: `boundary_wire_extraction()`, `line_zone_intersection()`

### BRepTools_WireExplorer(wire)
Iterates edges in wire traversal order.
Used for: `boundary_wire_extraction()` (extracting edge descriptors)

### BRepAdaptor_Curve(edge)
Adapts an edge for geometric queries (type, circle parameters, etc.)
Used for: classifying edges as LINE or ARC in boundary extraction

## Coordinate System in Build123d Sketches

Build123d sketches live in the XY plane of 3D space:
- **Sketch X** = our radius coordinate (lathe X/2)
- **Sketch Y** = our Z coordinate (lathe Z)
- **Sketch Z** = always 0 (planar)

When constructing 3D points for OCP operations:
```python
from OCP.gp import gp_Pnt
# Point at radius=0.5, Z=-1.0
pt = gp_Pnt(0.5, -1.0, 0.0)  # (x_radius, z_lathe, 0)
```

## Common Pitfalls

1. **Zero-length edges crash OCCT** — always filter duplicate points before Line()
2. **Unclosed wires fail make_face()** — ensure last point matches first point
3. **ShapeList from booleans** — always handle the multi-face case
4. **offset() can fail on degenerate geometry** — always check result is not None
5. **RadiusArc sign is opposite to G-code convention** — see conversion rule above
