---
inclusion: auto
---

# Coordinate Conventions

## Axis System (2-Axis Lathe)

- **X axis** — radial (perpendicular to spindle axis). Positive = away from centerline.
- **Z axis** — longitudinal (along spindle axis). Negative = into the workpiece (toward chuck).
- **Centerline** — X = 0. The spindle axis.
- **Stock face** — Z = 0 (or Z = z_start if stock face is offset). The front face of the workpiece.

## Diameter vs Radius

| Context | Convention | Example |
|---------|-----------|---------|
| G-code output (X words) | DIAMETER | X1.0000 = 0.5" from center |
| G-code output (I words) | DIAMETER offset | I0.5000 = 0.25" radial offset to center |
| G-code output (K words) | INCHES (Z offset) | K-0.2500 |
| G-code output (R words) | RADIUS (arc radius) | R0.2500 |
| UI fields (Stock Dia, X End) | DIAMETER | "1.250" = 1.250" diameter |
| UI fields (DOC) | DIAMETER | "0.050" = 0.025" on radius per pass |
| ProfileMove.x | DIAMETER | x=1.0 means 0.5" radius |
| ProfileMove.radius | RADIUS (geometric) | radius=0.25 means R=0.25" |
| Build123d sketch plane | RADIUS for X, INCHES for Z | Point(0.5, -1.0) = X=0.5 radius, Z=-1.0 |
| Shapely polygons | RADIUS for X, INCHES for Z | Same as Build123d |
| ZoneQueryAPI inputs | DIAMETER for X | boundary_at_x(1.0) queries at 0.5" radius |
| ZoneQueryAPI outputs | INCHES (Z values) | Returns Z crossings in inches |
| Interval/Fiber | DIAMETER for X level | Fiber at x_dia=1.0 |
| ToolMove.x | DIAMETER | x=1.002 means 0.501" radius |
| ToolMove.z | INCHES | z=-0.5010 |
| ToolMove.radius | RADIUS (arc radius) | radius=0.249 (signed: +CW, -CCW) |

## Sign Conventions

| Value | Positive | Negative |
|-------|----------|----------|
| X (diameter) | Away from centerline | N/A (always >= 0) |
| Z | Toward tailstock / away from chuck | Into workpiece / toward chuck |
| Arc radius (ProfileMove) | CW (G02) | CCW (G03) |
| Arc radius (ToolMove) | CW (G02) | CCW (G03) |
| Feed rate | Always positive | N/A |
| DOC | Always positive (on radius) | N/A |
| Fin allowance | Always positive (on radius) | N/A |

## Tolerance Constants

| Constant | Value | Usage |
|----------|-------|-------|
| TOLERANCE | 0.0005" | System operating tolerance — closure gaps, interval merging, point comparisons |
| TOLERANCE_SQ | 0.00000025 sq in | Area threshold for oracle coverage/gouge checks |
| CENTER_ARC_RADIUS_TOLERANCE | 0.00283" | LinuxCNC's IJK arc acceptance window |
| RADIUS_TOLERANCE | 0.00005" | LinuxCNC's R-format arc tolerance |
| DISPLAY_TOLERANCE | 0.001" | Zone shading tessellation maximum chord error |
| DENSIFICATION_ERROR | 0.000025" | Shapely polygon maximum chord error (cos_limit=0.9999) |

## Allowed Arithmetic on Coordinates

ONLY these operations are permitted on coordinate values:

```python
# Diameter <-> Radius conversion
x_radius = x_diameter / 2.0
x_diameter = x_radius * 2.0

# Tolerance comparison
if abs(a - b) < TOLERANCE:

# Pass level computation (uniform stepping)
x_level = stock_dia - n * doc_dia

# Safe position computation (stock boundary + clearance)
safe_x = stock_dia + retract_dist
```

NEVER do:
```python
# Manual offset (use kernel offset instead)
offset_x = profile_x + fin_allowance  # WRONG

# Manual arc center (use kernel edge extraction instead)
cx = mx + h * perp_x  # WRONG

# Manual circle intersection (use boundary_at_x instead)
z = cz + sqrt(r**2 - dx**2)  # WRONG
```

## OD vs ID Direction Table

| Operation | OD Mode | ID Mode |
|-----------|---------|---------|
| Pass stepping | Stock OD → profile (decreasing X) | Pilot hole → bore wall (increasing X) |
| Safe retract X | Stock OD (larger X) | Pilot hole (smaller X) |
| Offset direction (keep zone) | Away from centerline (+X) | Toward centerline (-X) |
| Stock boundary | Stock OD diameter | Pilot hole diameter |
| Face pass direction | Stock OD → centerline (-X feed) | Pilot hole → x_start (+X feed) |
| "Toward material" | Decreasing X | Increasing X |
| "Away from material" | Increasing X | Decreasing X |
