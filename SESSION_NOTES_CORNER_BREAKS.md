# Session Notes: Corner Break (Chamfer/Arc) Feature Integration

## Date: 2026-06-01

## Summary

Fully integrated the chamfer/arc corner break feature from data model through
G-code generation, validation, and display rendering. The feature was previously
data-model-only (P1.5 placeholder) — now it generates correct toolpath geometry.

## Problem Statement

Corner breaks (chamfers and fillets between profile segments) were stored in the
data model but never applied to:
1. The real-time contour preview during segment building
2. The finished part zone geometry (Build123d face)
3. The finish pass G-code
4. The cleanup pass G-code
5. The toolpath simulation/display rendering

## Key Discovery: Arc Direction Determination

The central challenge was determining the correct G02/G03 direction for fillet
arcs at segment junctions. We explored multiple approaches before finding the
correct one:

### Approaches That Failed

1. **Cross product of (start-center) × (end-center)**: Unreliable because the
   sign depends on which side of the chord the center is on, not on the cutting
   direction.

2. **"Minor arc" sweep heuristic** (normalize sweep to [-π, π]): Works for the
   original profile fillets but FAILS for offset arcs (cleanup pass). The offset
   operation can produce arcs where the correct cutting direction follows the
   MAJOR arc path.

3. **ThreePointArc with explicit center**: Correctly builds the face geometry
   but doesn't solve the downstream direction problem — the finish planner still
   needs to determine G02/G03 from the extracted edges.

4. **Midpoint heuristics** (farther from centerline, between Z endpoints, closer
   to chord): All fail for some corner geometries because the relationship between
   arc midpoint position and cutting direction varies by corner type.

### The Correct Solution: Signed Radius via Cross Product of Segment Directions

The solution mirrors how user-defined arc segments work: a **signed radius**
determines which side of the chord the center is on.

For corner break fillets, the sign is auto-detected from the geometry:

```python
cross = arr_ux * dep_uz - arr_uz * dep_ux
if cross > 0:  # inside corner (left turn)
    signed_fillet_r = +fillet_r
else:           # outside corner (right turn)
    signed_fillet_r = -fillet_r
```

This signed radius flows through `RadiusArc` (the same proven pipeline as
user-defined arcs), Build123d places the center on the correct side, OCCT
reports the correct center in boundary extraction, and the sweep angle
calculation gives the correct G02/G03 downstream.

### Why This Works

- The cross product of arrival × departure directions is **deterministic** —
  it unambiguously identifies inside vs outside corners
- The signed radius → `RadiusArc` pipeline is **proven** (same as segment arcs)
- Build123d/OCCT is the **single source of truth** for geometry
- The finish planner extracts edges from OCCT (no dual computation)
- The cleanup planner's offset face inherits correct geometry from the
  correctly-built finished part face

## Architecture

```
User Input (segment list + corner breaks)
    ↓
_profile_to_radius_coords (auto-detect sign via cross product)
    ↓
_build_face_from_coords (RadiusArc with signed radius → Build123d)
    ↓
Build123d/OCCT (constructs face with correct arc geometry)
    ↓
┌─────────────────────────────────────────────────────────┐
│ ZoneQueryAPI.boundary_wire_extraction("finished_part")  │
│ → EdgeData with correct centers from OCCT               │
└─────────────────────────────────────────────────────────┘
    ↓                                    ↓
Finish Planner                    Cleanup Planner
(extract edges, compute           (offset face, extract edges,
 sweep → G02/G03)                  compute sweep → G02/G03)
    ↓                                    ↓
G-code Writer (I/K from OCCT centers)
    ↓
Display Renderer (pure G-code interpretation:
  G02 = negative sweep, G03 = positive sweep)
```

## Files Modified

- `geometry/zone_builder.py` — Corner break fillet sign detection, face construction
- `geometry/adaptive_sampling.py` — Added `is_cw` parameter for direction-aware densification
- `planners/finish_planner.py` — Rewritten to extract edges from OCCT boundary
- `planners/cleanup_planner.py` — Sweep-based direction from offset face edges
- `gui/program_tab.py` — Connected corner_breaks_changed signal, preview rendering
- `gui/components/sim_viewer.py` — Pure G-code arc direction interpretation
- `gui/components/segment_list.py` — Corner break data emission (existing, unchanged)
- `outputs/graph_adapter.py` — Direction-aware arc densification for display
- `validation/post_planning_validator.py` — Buffer for finish/cleanup boundary tracing

## Key Lessons

1. **Don't infer direction from geometry when it's ambiguous** — use explicit
   signed values that flow through the pipeline.

2. **Build123d/OCCT should be the single source of geometric truth** — don't
   compute arc centers independently in multiple places.

3. **The display should interpret G-code directly** — no heuristics, no
   "pick shorter arc", just render what the G-code says.

4. **Offset operations change geometric relationships** — heuristics that work
   on the original profile may fail on offset geometry. The signed radius
   approach avoids this because the offset inherits correct geometry from the
   correctly-built source face.

5. **Inside vs outside corners are deterministic from segment directions** —
   the cross product of arrival × departure gives an unambiguous answer.
