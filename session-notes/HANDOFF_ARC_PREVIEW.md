# Handoff: Fix Arc Preview in Program Tab Segment Builder

## Problem
When the user enters an ARC segment in the Program tab's Profile Segments table, the preview graph renders a full circle (or multiple quadrants) instead of just the short arc between the two endpoints. The arc interpolation logic in `_update_preview()` is computing the wrong sweep angle.

## Where the bug lives
`gui/program_tab.py` → `_update_preview()` method, specifically the arc interpolation block starting around line 990.

## How the segment data works
- The segment table stores: `{"type": "arc", "x": 1.0, "z": -1.5, "radius": -1.0}`
- `x` is in DIAMETER (inches)
- `z` is in inches
- `radius` is SIGNED: positive = CW (G02), negative = CCW (G03)
- The arc goes FROM the previous segment's endpoint TO this segment's endpoint
- The radius magnitude is in the same mixed coordinate space as the profile (X=diameter, Z=inches)

## Known-good reference
The engine's pipeline handles arcs correctly. See `_visual_test_arc.py` for the proven test case:
```
segments = [
    ProfileMove(SegmentType.LINE, 0.000, 0.000),
    ProfileMove(SegmentType.LINE, 1.000, 0.000),
    ProfileMove(SegmentType.LINE, 1.000, -0.500),
    ProfileMove(SegmentType.ARC, 1.000, -1.500, radius=-1.000),  # CCW arc
    ProfileMove(SegmentType.LINE, 1.000, -2.000),
]
```
This arc goes from (1.0 dia, -0.5) to (1.0 dia, -1.5) with R=1.0 CCW. It's a convex bulge outward. The center is at approximately (-0.732 dia, -1.0) — computed by Build123d in the zone builder.

## The coordinate space issue
The preview works in RADIUS for X (÷2 from diameter) but the arc radius is specified in the profile's native space where X is diameter. The center-finding math must account for this:

1. Compute chord and find center in DIAMETER+Z space (where the radius value lives)
2. Convert center to radius space for display
3. Compute angles and interpolate in radius space using the DISPLAY radius (distance from center to start point in radius coords)

## The sweep angle issue (THE ACTUAL BUG)
The current code computes `angle_start` and `angle_end` using `atan2`, then adjusts `diff` based on CW/CCW direction. But it's producing a sweep > π when it should be < π (or vice versa). The logic for choosing the short arc vs long arc based on the sign of radius is wrong.

For a CW arc (positive radius): the tool sweeps clockwise, so `diff` should be negative (decreasing angle). If `diff > 0`, subtract 2π.
For a CCW arc (negative radius): the tool sweeps counter-clockwise, so `diff` should be positive (increasing angle). If `diff < 0`, add 2π.

But this alone doesn't guarantee the SHORT arc. The issue is that after the center is found, there are always two possible arcs (short and long). The sign convention in our engine means:
- The center is placed on the side determined by the sign
- The arc ALWAYS takes the short path (< π) around that center

So after computing `diff`, if `abs(diff) > π`, the center is on the wrong side or the direction logic is inverted.

## What needs to happen
1. Fix the center computation to correctly place it based on CW/CCW convention
2. Ensure the sweep angle produces only the SHORT arc between the two endpoints
3. Test with the known-good Arc OD case: from (1.0 dia, -0.5) to (1.0 dia, -1.5), R=-1.0 (CCW), which should produce a ~60° convex bulge to the right

## Files to modify
- `gui/program_tab.py` — `_update_preview()` method, arc interpolation block

## How to test
1. Launch GUI: `python -m gui.main_window` from the project root
2. In Program tab, add segments matching the Arc OD test case
3. The preview should show a small convex arc between Z=-0.5 and Z=-1.5, bulging outward (toward larger X)
4. It should NOT show a full circle or a large sweeping arc

## Related: the engine's arc handling
The engine uses Build123d to compute the actual arc geometry from the signed radius. The preview doesn't use Build123d — it's a pure-math approximation for real-time display. The math needs to match the engine's interpretation of signed radius.

In LinuxCNC/G-code convention:
- G02 (CW) with positive R: center is on the "inside" of the arc (shorter path)
- G03 (CCW) with negative R in our convention: same — short arc

The preview should always render the SHORT arc (< 180°) for the given radius magnitude.
