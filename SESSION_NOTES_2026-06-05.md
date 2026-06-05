# Session Notes — 2026-06-05: Arc Radius Sign Convention Fix

## Problem Statement

An AI agent kept confusing arc direction (CW/CCW), arc selection (major/minor),
and signed radius conventions. This caused a "1 step forward, 2 steps back"
pattern when working on arc-related bugs. The root bug: Seg 8 (a CCW arc) was
being output as G02 (CW) with the wrong center.

## What Was Changed

### 1. Created steering file: `.kiro/steering/arc-geometry.md`

Definitive reference documenting:
- The three independent arc concepts (direction, selection, magnitude)
- This codebase's sign conventions (ProfileMove.radius sign = direction)
- Cross product rule for center selection
- Build123d RadiusArc API mapping
- Common mistakes to avoid

### 2. Zone builder (`geometry/zone_builder.py`)

**User-defined arc segments:**
- Changed `b3d_radius = -target["radius"]` → `b3d_radius = target["radius"]`
- Removed incorrect comment ("Our convention: +R = minor, -R = major")
- Added correct comment explaining the conventions align

**Corner break fillets:**
- Inverted the cross-product → sign mapping:
  - Was: `cross > 0 → +fillet_r`, `cross < 0 → -fillet_r`
  - Now: `cross > 0 → -fillet_r`, `cross < 0 → +fillet_r`
- This was needed because fillets were calibrated for the old downstream
  negation. With no downstream flip, the fillet sign logic had to be inverted
  at the source.

### 3. Cleanup planner (`planners/cleanup_planner.py`) — 2 sites

- Changed `b3d_radius = -target["radius"]` → `b3d_radius = target["radius"]`
- Both the OD face builder and ID face builder sections

### 4. Contour roughing planner (`planners/contour_roughing_planner.py`)

- **REVERTED** back to `-t["radius"]` (the sign flip)
- This planner builds its own independent face, offsets it concentrically,
  and clips to stock boundaries. The negated center (inside the stock) keeps
  offset arcs from exceeding stock OD during progressive offsetting.
- ⚠️ **Still has issues** — the offset contour roughing arcs are not rendering
  correctly. Tabled for later investigation.

## What Works Now

| Component | Status |
|-----------|--------|
| Staircase roughing | ✅ Correct |
| Cleanup pass (semi-finish) | ✅ Correct |
| Finish pass (profile contour) | ✅ Correct |
| Corner break fillets (all types) | ✅ Correct |
| Offset contour roughing | ❌ Still broken — tabled |

## Root Cause Explanation

The zone builder had a comment claiming the engine's radius sign meant
major/minor arc. It actually means direction (CW/CCW). The blind sign flip
`-target["radius"]` coincidentally worked for vertical chords and tiny fillets
but placed the arc center on the wrong side for diagonal chords, causing the
finish planner to extract wrong geometry and output wrong G-code direction.

## Key Empirical Finding

Build123d's `RadiusArc(start, end, radius)` sign convention:
- Positive → arc bulges LEFT of the start→end vector (90° CCW rotation of chord)
- Negative → arc bulges RIGHT of the start→end vector (90° CW rotation of chord)

For user-defined arc segments, the engine's ProfileMove.radius sign (+CW/-CCW)
happens to align with Build123d's side-of-chord convention — pass directly.

For corner break fillets, the zone builder computes the correct Build123d sign
from the cross product of arrival × departure directions.

## Remaining Work (Offset Contour)

The contour roughing planner needs a different approach. It builds its own face,
offsets inward, and clips to stock. The correct geometric center (from
`_select_center`) causes the arc to exceed stock OD at larger offsets, producing
a major arc after clipping. The old (negated) center stays inside stock bounds
but produces wrong direction.

Possible approaches for the fix:
1. Keep the negated center but fix `_to_moves` to force correct direction
2. Use the correct center but cap the offset arc at stock OD without clipping
3. Detect when an offset arc exceeds stock and split it into line + arc segments
4. Use a different offset strategy that avoids the arc entirely at large offsets
   (polyline approximation for the arc region)

## Files Modified

- `.kiro/steering/arc-geometry.md` (new)
- `geometry/zone_builder.py`
- `planners/cleanup_planner.py`
- `planners/contour_roughing_planner.py`

## Tests

250 unit tests pass. No regressions.
