# LinuxCNC Source Reference

This is a sparse checkout of the [LinuxCNC](https://github.com/LinuxCNC/linuxcnc) repository, acquired as a **read-only reference** to understand how the downstream G-code execution environment constrains the toolpaths produced by our roughing engine.

This is NOT a runtime or test dependency. It informs correctness properties and edge case rules.

## Checked-Out Directories

```
src/emc/rs274ngc/   — G-code interpreter (arc validation, tolerance definitions)
src/emc/motion/     — Trajectory planner (motion control, blending)
src/libnml/posemath/ — Arc interpolation math (sin/cos based)
```

## Key Files and Their Relevance

### Arc Tolerance and Validation

| File | Purpose | Relevance |
|------|---------|-----------|
| `src/emc/rs274ngc/interp_internal.hh` | Tolerance constants | Defines `RADIUS_TOLERANCE_INCH = 0.00005` and `CENTER_ARC_RADIUS_TOLERANCE_INCH = 2 * 0.001 * √2 ≈ 0.00283"`. Our G-code arcs must have start/end radii within this tolerance of the commanded radius, or LinuxCNC rejects them. |
| `src/emc/rs274ngc/interp_arc.cc` | Arc G-code interpretation | How LinuxCNC validates G2/G3 arc commands — center computation from IJK or R format, endpoint validation, spiral tolerance checking. |
| `src/emc/rs274ngc/interp_convert.cc` | G-code conversion | `convert_arc()` — the main arc processing function that applies tolerances and validates geometry before queuing motion. |

### Trajectory Planner Behavior

| File | Purpose | Relevance |
|------|---------|-----------|
| `src/emc/motion/motion.c` | Main motion controller | Core trajectory planning loop — how moves are queued and executed. |
| `src/emc/motion/control.c` | Motion control logic | Velocity/acceleration planning, path blending decisions. When `G64` is active, corners may be blended (cut short). |
| `src/emc/motion/simple_tp.c` | Simple trajectory planner | Exact-stop mode (`G61`) behavior — how rapid-to-feed transitions work without blending. |

### Arc Interpolation

| File | Purpose | Relevance |
|------|---------|-----------|
| `src/libnml/posemath/posemath.cc` | Pose math library | `pmCirclePoint()` — arc interpolation uses sin/cos (not DDA), so points on circles are computed exactly with no accumulated error. |
| `src/libnml/posemath/gomath.c` | Geometric operations | Circle/arc math primitives used by the motion controller. |

## What This Tells Us About Correctness

1. **Arc endpoint tolerance**: LinuxCNC rejects arcs where start/end radii deviate from the commanded radius by more than `CENTER_ARC_RADIUS_TOLERANCE_INCH` (~0.00283"). Our offset geometry must produce arcs satisfying this, or we fall back to linear interpolation. We use a conservative tolerance of **0.0005"** as our design threshold.

2. **Arc interpolation is exact**: LinuxCNC uses `sin/cos` for arc point computation (not incremental DDA), so there's no accumulated interpolation error. Our correctness properties can assume the machine follows the commanded arc exactly.

3. **Trajectory blending**: When `G64` path blending is active, LinuxCNC may cut corners at segment junctions. Our no-gouge property should account for the blending tolerance (`G64 P0.001` is typical for finishing).

4. **Rapid behavior**: Rapids (`G0`) use the trajectory planner's maximum velocity and may overshoot slightly due to deceleration. Our rapid-clearance property should include a small margin.

## Integration Constraints for Edge Case Rules

When an edge case rule modifies geometry (e.g., replacing a degenerate arc with a line), the resulting G-code must still satisfy LinuxCNC's constraints:

- Arc radius must produce endpoints within `CENTER_ARC_RADIUS_TOLERANCE_INCH` of the circle
- Arc moves must have non-zero length (checked by motion controller)
- Consecutive moves should be continuous (no gaps > machine resolution)
- Minimum arc radius is bounded by the tolerance — arcs smaller than ~0.001" radius are unreliable

## Usage

This directory is gitignored from the main project. To refresh:

```bash
cd linuxcnc-reference
git pull
```

To check what's included:

```bash
git sparse-checkout list
```
