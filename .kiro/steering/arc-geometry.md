# Arc Geometry — Definitive Reference

This steering file is the single source of truth for circular arc concepts in Industry CAM Engine.
Consult this BEFORE writing or modifying any arc-related code.

## The Three Independent Concepts

There are three orthogonal decisions when specifying a circular arc. They are INDEPENDENT of each other.
Confusing them is the #1 source of bugs in this codebase.

| Concept | What it controls | How it's encoded |
|---------|-----------------|------------------|
| **Direction** (CW/CCW) | Which way you traverse the arc | G02 = CW, G03 = CCW |
| **Arc selection** (major/minor) | Which of the two possible arcs between two points | R sign: +R = minor (≤180°), -R = major (>180°) |
| **Radius magnitude** | How big the circle is | abs(R) — always positive in geometry calculations |

### CRITICAL RULES — memorize these

```
Direction ≠ Arc selection
G2/G3 ≠ major/minor
CW/CCW ≠ R sign

R sign selects WHICH arc (major vs minor).
G2/G3 selects WHICH WAY to traverse it.
These are two separate, orthogonal choices.
```

## Convention in THIS Codebase

### ProfileMove.radius (models/profile.py)
- **Positive** → CW on screen → G02
- **Negative** → CCW on screen → G03
- Magnitude = the arc radius (always the minor arc in this engine's profile definition)
- This is a **direction** encoding, NOT a major/minor encoding

### ToolMove.radius (models/moves.py)  
- **Positive** → CW → G02 (MoveType.ARC_CW)
- **Negative** → CCW → G03 (MoveType.ARC_CCW)
- Same convention as ProfileMove: sign = direction

### ToolMove.center_i / center_k
- **Incremental** offsets from the arc start point to the arc center
- center_i is in **DIAMETER** (matches X axis convention)
- center_k is in inches (Z axis)
- When center_i/center_k are provided, they are preferred over R-format in G-code output

### G-code output (gcode_writer.py)
- `G02` = clockwise arc
- `G03` = counter-clockwise arc
- R-format: `R{abs(radius)}` — always positive (magnitude only), direction is from G02/G03
- IJK-format: `I{center_i} K{center_k}` — used when center is known (preferred)

## Direction Determination — The Cross Product Rule

Throughout the engine, arc direction is determined by the cross product of vectors from center to start and center to end:

```python
# Vectors from center to start and center to end
ax = x1_r - cx    # start - center
az = z1 - cz
bx = x2_r - cx    # end - center  
bz = z2 - cz

cross = ax * bz - az * bx

# Cross product sign determines direction ON SCREEN (XZ plane, +X right, +Z up)
# Negative cross → CW on screen → G02
# Positive cross → CCW on screen → G03
```

This is used in:
- `finish_planner.py` — determining direction when decomposing edges into arcs
- `arc_helpers._select_center()` — choosing which of two candidate centers matches is_cw
- `pre_planning_validator.py` — validating arc geometry

## Center Selection — Two Candidates

Given two points and a radius, there are always **two** possible circle centers (one on each side of the chord). The correct center is chosen by:

1. Compute both candidate centers (perpendicular bisector ± offset)
2. Use cross product to determine which produces the desired CW/CCW direction
3. Validate with `is_arc_within_x_bounds()` as a secondary check

```python
# From arc_helpers._select_center():
if is_cw:
    return (c1_x, c1_z) if cr1 < 0 else (c2_x, c2_z)  # pick negative cross
else:
    return (c1_x, c1_z) if cr1 > 0 else (c2_x, c2_z)  # pick positive cross
```

## Sweep Angle Convention

```python
# From finish_planner.py:
# Negative sweep = CW = G02
# Positive sweep = CCW = G03
sweep = end_angle - start_angle  # (after normalization)
is_cw = sweep < 0
```

## Coordinate Spaces — Don't Mix Them

| Context | X meaning | Notes |
|---------|-----------|-------|
| User-facing (ProfileMove.x, ToolMove.x, G-code X) | DIAMETER | Always |
| Geometry calculations (arc center, radius, bounds) | RADIUS | Divide diameter by 2 |
| center_i (ToolMove) | DIAMETER | Incremental offset, matches X axis |
| ProfileMove.radius magnitude | RADIUS | The actual geometric radius |

## Common Mistakes This Engine Has Encountered

### ❌ "Use G03 because it's the major arc"
WRONG. G02/G03 is direction. Major/minor is selected by R sign (not used in this engine's internal representation — we always use center-point form or minor arcs).

### ❌ "Negative radius means counter-clockwise"
CONTEXT-DEPENDENT. In raw G-code R-word format, negative R = major arc. In THIS codebase's ProfileMove/ToolMove, negative radius = CCW direction. Know which context you're in.

### ❌ "Flip the radius sign to change the arc size"
WRONG in this codebase. Flipping the sign changes DIRECTION (CW↔CCW), not arc size. The magnitude determines size.

### ❌ "CW/CCW determines which of the two centers to pick"
PARTIALLY RIGHT but incomplete. CW/CCW determines center via cross-product rule (see above). It does NOT determine major/minor — that's implicit from the center+endpoints geometry.

### ❌ "Swap center_i sign to fix the direction"
WRONG. Changing the center changes the circle. Direction comes from G02/G03 (MoveType). If the arc is going the wrong way, change the MoveType, not the center.

### ❌ "Convert center_i to radius for geometry"
RIGHT — and mandatory. center_i is in DIAMETER. Divide by 2 before doing any distance/angle calculations.

## Decision Flowchart

When creating an arc ToolMove:

```
1. Do I have center coordinates?
   YES → compute center_i (DIAMETER, incremental from start)
       → compute center_k (inches, incremental from start)  
       → determine direction via cross product → set MoveType.ARC_CW or ARC_CCW
       → set radius = distance_from_center_to_start (positive if CW, negative if CCW)
   
   NO → use ProfileMove.radius sign directly
      → positive → MoveType.ARC_CW, radius = +abs(r)
      → negative → MoveType.ARC_CCW, radius = -abs(r)

2. The G-code writer will:
   - Use IJK format if center_i or center_k are non-zero
   - Otherwise use R format with abs(radius)
   - G02/G03 comes from move_type, NEVER from radius sign at output time
```

## Build123d RadiusArc — External API Mapping

Build123d's `RadiusArc(start, end, radius)` uses the radius sign to control
**which side of the chord** the arc center is placed on:

```
Build123d RadiusArc sign convention:
  Positive radius → center on LEFT side of start→end vector (90° CCW from chord)
  Negative radius → center on RIGHT side of start→end vector (90° CW from chord)
```

### The mapping used throughout this codebase

There are TWO different mappings depending on the planner:

**Zone builder + cleanup planner** (shared face for finish/cleanup passes):
```python
b3d_radius = target["radius"]    # Pass directly — NO sign flip
```
These build the OCCT face that the finish planner later extracts edges from.
The finish planner determines arc direction from the extracted geometry using
cross product, so the face center must be geometrically correct.

**Contour roughing planner** (independent face for offset contour roughing):
```python
b3d_radius = -t["radius"]        # Sign flip — inverted
```
The contour roughing planner builds its OWN face, offsets it concentrically,
clips to stock boundaries, and extracts arcs from the clipped wire. The
negated sign places the center on the side that keeps the arc WITHIN stock
bounds during progressive offsetting. The planner's `_to_moves()` uses cross
product to detect direction from whatever geometry comes out, so it's
self-consistent regardless of which center it uses.

**Why they differ:** The zone_builder face feeds the finish planner which
needs the geometrically correct center to compute proper sweep direction.
The contour roughing planner needs the arc to stay within stock bounds
during offset/clip operations — the "inside" center (closer to part centerline)
produces offset arcs that progressively shrink rather than grow past stock OD.

### Quadrant arcs — separate convention

For quadrant arcs, the formula is:
```python
signed_radius = -arc_radius * quadrant_sign
```
- `quadrant_sign = +1` (convex) → negative b3d radius → right-side center → arc curves inward
- `quadrant_sign = -1` (concave) → positive b3d radius → left-side center → arc curves outward

This is correct for quadrant arcs because convex/concave directly maps to which side
of the chord the center belongs on.

## Quick Reference Table

| ProfileMove.radius | ToolMove.move_type | ToolMove.radius | G-code |
|---|---|---|---|
| +0.25 | ARC_CW | +0.25 | G02 ... R0.2500 (or I/K) |
| -0.25 | ARC_CCW | -0.25 | G03 ... R0.2500 (or I/K) |

Note: G-code R is ALWAYS positive (absolute value). The sign information is carried by G02/G03.

## End-to-End Pipeline Summary

```
User defines ProfileMove.radius = ±R (sign = direction, magnitude = radius)
        ↓
zone_builder converts to Build123d RadiusArc → OCCT face
        ↓  ⚠️  This mapping (b3d_radius = -target["radius"]) may place center wrong
        ↓
finish_planner extracts edges from OCCT face → reads center from geometry
        ↓
finish_planner computes sweep via cross product → determines MoveType (ARC_CW/CCW)
        ↓
ToolMove(move_type, x, z, radius=±R, center_i, center_k)
        ↓
gcode_writer emits G02/G03 from move_type, R from abs(radius), I/K from center
```

The zone builder is the SOURCE OF TRUTH for the OCCT geometry. If it places the
center wrong, the finish planner will faithfully extract that wrong center and
produce wrong G-code. Fix bugs at the zone builder level first.
