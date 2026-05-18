---
inclusion: auto
---

# Contour/Offset Roughing Rules

## NX Ground Truth Reference

Contour roughing toolpath DXF:
`reference/CAD Reference/Arc Reference/175934-001_01-Arc Contour Roughing Toolpath.dxf`

This DXF includes the finish pass, cleanup pass, and all contour roughing passes for the Arc OD profile.

## Algorithm (OD Mode)

### Pass Generation (inside-out offset)

1. Start with the **roughing boundary** (profile offset outward by fin_allowance = 0.001r). This is the cleanup pass contour.
2. Offset outward by DOC(radius) to get the first contour roughing pass (offset = fin_allowance + DOC = 0.001 + 0.025 = 0.026r from profile).
3. Continue offsetting outward by DOC(radius) for each subsequent pass.
4. Stop when the offset exceeds stock OD everywhere.

### Clipping Against MTR Zone

Each offset contour is clipped against the MTR zone boundary (stock OD at X=0.750r for this profile):
- If the arc at a given offset doesn't reach stock OD → full arc, no clipping needed
- If the arc exceeds stock OD → clip at X=0.750r, producing two partial arcs with a vertical line at stock OD between them

### Cutting Order (outside-in)

Passes execute in REVERSE order — outermost pass (closest to stock OD) cuts first, working inward toward the profile. This ensures each pass has cleared material behind it for safe retract.

### Pass Structure

**Full pass (arc doesn't reach stock OD):**
```
1. Vertical line: (X_offset, Z_face_cleared) → (X_offset, Z_arc_start)
2. Arc: (X_offset, Z_arc_start) → (X_offset, Z_arc_end) [full arc, same X both ends]
3. Vertical line: (X_offset, Z_arc_end) → (X_offset, Z_end)
```

**Clipped pass (arc exceeds stock OD):**
```
1. Vertical line: (X_offset, Z_face_cleared) → (X_offset, Z_upper_arc_start)
2. Arc (upper partial): (X_offset, Z_upper_arc_start) → (stock_OD_r, Z_clip_upper)
3. Vertical at stock OD: (stock_OD_r, Z_clip_upper) → (stock_OD_r, Z_clip_lower)
4. Arc (lower partial): (stock_OD_r, Z_clip_lower) → (X_offset, Z_lower_arc_end)
5. Vertical line: (X_offset, Z_lower_arc_end) → (X_offset, Z_end)
```

## NX Ground Truth Data (Arc OD Profile)

Profile: Arc center (-0.366r, -1.000), R=1.000
Stock OD: 0.750r
DOC: 0.025r (0.050 dia)
Fin allowance: 0.001r (0.002 dia)
Z_face_cleared: 0.001 (fin_allowance)
Z_end: -2.000

### Passes (10 contour roughing + 1 cleanup + 1 finish)

| Pass | Offset (r) | Arc Radius | Clipped? | X at straight sections |
|------|-----------|------------|----------|----------------------|
| Finish | 0.000 | 1.000 | No | 0.500r |
| Cleanup | 0.001 | 1.001 | No | 0.501r |
| Contour 1 | 0.026 | 1.026 | No | 0.526r |
| Contour 2 | 0.051 | 1.051 | No | 0.551r |
| Contour 3 | 0.076 | 1.076 | No | 0.576r |
| Contour 4 | 0.101 | 1.101 | No | 0.601r |
| Contour 5 | 0.126 | 1.126 | Yes (X=0.750r) | 0.626r |
| Contour 6 | 0.151 | 1.151 | Yes | 0.651r |
| Contour 7 | 0.176 | 1.176 | Yes | 0.676r |
| Contour 8 | 0.201 | 1.201 | Yes | 0.701r |
| Contour 9 | 0.226 | 1.226 | Yes | 0.726r |

Note: The vertical line X values are at the offset X (profile_x + offset), NOT at stock OD. The straight sections above and below the arc are at the same X as the arc endpoints.

## Key Implementation Rules

1. **Kernel-driven offsets** — use Build123d `offset()` for equidistant offset. Never hand-compute arc centers or radii.
2. **Kernel-driven clipping** — use `BRepAlgoAPI_Common` with the MTR zone face to clip passes that exceed stock boundary.
3. **Arc center is constant** — all offset arcs share the same center as the profile arc. Only the radius changes (R_profile + offset_distance).
4. **No cleanup pass needed** — for offset-contour strategy, the last roughing pass IS at the roughing boundary. The cleanup pass from staircase strategy is not generated.
5. **Finish pass is unchanged** — same profile trace regardless of roughing strategy.
6. **Face passes are unchanged** — same TFZ removal regardless of roughing strategy.

## Relationship to Staircase

| Aspect | Staircase | Offset-Contour |
|--------|-----------|----------------|
| Pass shape | Constant X (horizontal) | Profile-following (arcs + lines) |
| Material left | Stair-step pattern | Uniform fin_allowance band |
| Cleanup needed | Yes (removes stair-steps) | No (last pass = roughing boundary) |
| Arc handling | Passes split at arc intersections | Passes follow arc at offset radius |
| Cutting order | Stock OD → profile (outside-in) | Stock OD → profile (outside-in) |

## Implementation Lessons (2026-05-16)

### The algorithm is cleanup planner in a loop
Same `b3d_offset()` + `BRepAlgoAPI_Common` clip pattern as cleanup, repeated at DOC intervals. Each iteration increases the offset distance by DOC(radius).

### Clip produces single face with concave boundary
When arc exceeds stock OD, OCCT produces ONE face — the stock OD edge connects upper and lower arc sections within the boundary wire. It does NOT produce multiple disconnected faces.

### Edge filter must keep partial stock OD edges
Only filter stock OD edges spanning the full Z range (true boundary). Partial verticals at stock OD are connectors between split arc sections — real traversal edges.

### Compute inside-out, cut outside-in
Offsets computed from smallest to largest. Pass list reversed for cutting (outermost first).

### File: `planners/contour_roughing_planner.py`
- `ContourRoughingPlanner.plan()` — main entry, loops offset+clip
- `_build_face()` — finished part face (profile + closure)
- `_do_offset()` — `b3d_offset` wrapper
- `_clip_and_extract()` — clip + multi-face handling + edge extraction
- `_wire_to_edges()` — OCCT wire → edge tuples with filter
- `_order()` — chain edges top-to-bottom
- `_to_moves()` — edges → ToolMoves (LINE/ARC/RAPID/FEED_IN)
- `_x_level()` — min X of vertical segments

### Retract Logic for Contour Passes
The G-code writer uses `_compute_pass_max_x()` to determine safe retract X:
- Computes the true maximum X the pass reached, including arc peaks
- Arc peak = `(center_x_r + radius_r) * 2` when arc bulges outward (peak > both endpoints)
- Capped at stock OD (split passes have peak at stock OD already)
- Replaces the old `x_level`-based retract which missed arc humps
- Universal: works for staircase (no change), contour, tapers
