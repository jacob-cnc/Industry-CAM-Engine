---
inclusion: auto
---

# LinuxCNC G/M Code Reference for Lathe Operations

## Lathe-Specific Modes

- **G7** — Diameter Mode: X axis values represent diameter (X1.0 = 0.5" from center = 1.0" diameter part). This is our default.
- **G8** — Radius Mode: X axis values represent radius (X0.5 = 0.5" from center). G8 is default at power-up but we always program G7.
- **G18** — XZ Plane: Required for lathe arcs. G2/G3 use I (X offset) and K (Z offset).
- **G96** — Constant Surface Speed (CSS): S = surface feet/min. Requires D for max RPM. Not affected by diameter/radius mode.
- **G97** — RPM Mode: S = spindle RPM directly.
- **G95** — Feed Per Revolution: F = inches/rev. Requires spindle encoder feedback.
- **G94** — Feed Per Minute: F = inches/min (default).

## Arc Moves (G2/G3) — Critical for This Engine

### Format (XZ Plane, G18)
```
G2 X- Z- I- K- F-   (CW arc)
G3 X- Z- I- K- F-   (CCW arc)
G2 X- Z- R- F-      (radius format — less accurate, avoid for > 180°)
```

### Conventions
- **G2 = CW** as viewed from +Y (the operator's perspective on a lathe)
- **G3 = CCW** as viewed from +Y
- **I** = incremental X offset from arc start to center (in diameter mode: I is diameter offset)
- **K** = incremental Z offset from arc start to center
- **R** = radius (positive < 180°, negative > 180°)

### Tolerance Rules (from LinuxCNC source `interp_arc.cc`)
- `RADIUS_TOLERANCE_INCH = 0.00005"` — for R-format arcs
- `CENTER_ARC_RADIUS_TOLERANCE_INCH ≈ 0.00283"` — for IJK-format arcs
- Error condition: "distance from start to center differs from distance from end to center by more than 0.05" OR (0.0005" AND 0.1% of radius)"
- Our engine uses 0.0005" as conservative threshold (well within LinuxCNC's window)

### Arc Direction on Our Lathe (Hump Test Profile)
- Profile arc is CCW in UI convention → G02 (CW in G-code) → positive R in engine
- The arc dips TOWARD centerline (smaller diameter)
- On the graph: green profile line goes UPWARD (toward X=0) at the arc

## Threading (G76)

```
G76 P- Z- I- J- R- K- Q- H- E- L-
```
- P = pitch (distance per revolution)
- Z = final Z position
- I = thread peak offset from drive line (negative = external, positive = internal)
- J = initial cut depth
- K = full thread depth
- R = depth degression (1.0 = constant depth, 2.0 = constant area)
- Q = compound slide angle (typically 29-30°)
- H = spring passes
- E = taper distance
- L = taper end (0=none, 1=entry, 2=exit, 3=both)

## Cutter Compensation (G41/G42)

```
G41 D-   (comp left of programmed path)
G42 D-   (comp right of programmed path)
G41.1 D- L-  (dynamic comp, D=diameter, L=orientation 0-9)
G40      (cancel compensation)
```

### Rules
- Lead-in move must be >= tool radius length
- Lead-in can be a rapid move
- After G40, next move must be linear and longer than tool diameter
- Cannot program G2/G3 immediately after G40
- XZ plane (G18) is supported for lathe cutter comp
- L word (orientation) is required for lathe tools in G41.1/G42.1

### Tool Orientation (Q word in tool table, L word in G41.1)
```
Q/L value | Tool position relative to workpiece
0         | Tool tip (no comp applied)
1         | Front, right (typical OD right-hand tool)
2         | Front, left
3         | Rear, right
4         | Rear, left
5         | Front, center (boring bar)
6         | Rear, center
7         | Right, center
8         | Left, center
9         | Center (round insert)
```

## Motion Modes

- **G0** — Rapid: coordinated move at max rate. Path may be rounded at direction changes.
- **G1** — Linear feed: coordinated move at programmed feed rate.
- **G33** — Spindle-synchronized motion: for single-point threading. K = distance per rev.
- **G61** — Exact path mode: moves exactly as programmed, slows at corners.
- **G64 P- Q-** — Path blending: P = tolerance, Q = naive CAM tolerance. Blends corners for speed.

## Units and Coordinates

- **G20** — Inch mode (our default)
- **G21** — Metric mode
- **G90** — Absolute distance mode
- **G91** — Incremental distance mode
- **G90.1** — Absolute arc distance mode (I/K are absolute positions)
- **G91.1** — Incremental arc distance mode (I/K are offsets from start — our default)

## M-Codes (Lathe-Relevant)

- M3 S- — Spindle CW at S rpm
- M4 S- — Spindle CCW at S rpm
- M5 — Spindle stop
- M6 — Tool change
- M8 — Coolant on
- M9 — Coolant off
- M2/M30 — Program end

## Our G-Code Output Conventions

1. Always emit G7 (diameter mode) in preamble
2. Always emit G18 (XZ plane) in preamble
3. Always emit G20 (inch) in preamble
4. Use G91.1 (incremental arc distance) — I/K are offsets from start to center
5. Prefer IJK format over R format for arcs (more accurate)
6. X values are always DIAMETER (per G7)
7. Feed rate (F) is in inches/min (G94) unless CSS mode active
8. Coordinates to 4 decimal places (0.0001" resolution)
9. Arc radius validated against LinuxCNC tolerance before output
