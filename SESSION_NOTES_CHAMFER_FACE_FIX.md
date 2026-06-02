# Session Notes: Chamfer at Face/Turning Junction Fix

## Date: 2026-06-02

## Summary

Fixed the cleanup planner losing chamfer edges at the face/turning junction
during the offset + clip + filter pipeline. The chamfer diagonal was being
incorrectly classified as a clip boundary edge and filtered out.

## Problem Statement

When a chamfer corner break exists at the face/shoulder junction (e.g., the
90° corner where the face segment meets the first turning shoulder), the
cleanup planner's edge filter incorrectly removes the chamfer edge from the
offset wire after clipping.

The cleanup pass would trace only the vertical shoulder, skipping the chamfer
entirely. The finish pass was unaffected (it extracts edges from OCCT boundary
directly without the clip/filter pipeline).

## Root Cause

Two compounding issues:

### 1. Bloated tolerance from arbitrary x_max_r

The clip region used `x_max_r = 10.0` (an arbitrary large value). The tolerance
for boundary detection was computed as:

```python
tol = max(1e-3, z_range * 0.001, x_range * 0.001)
```

With `x_range = (10.0 - 0.0025) * 2 = ~20`, this gave `tol = 0.02"` — larger
than most chamfer sizes (typically 0.015").

### 2. Non-directional boundary filter

The filter logic was:
```python
if abs(sz - z_top) < tol and abs(ez - z_top) < tol:
    continue  # Kill edge
```

A chamfer edge from `(0.505, -0.014)` to `(0.477, 0.0)` has:
- End Z = 0.0 (exactly at z_top)
- Start Z = -0.014 (within tol=0.02 of z_top)

Both endpoints appeared to be "at z_top" so the chamfer was filtered as if
it were a horizontal boundary edge. But it's actually diagonal — a profile
feature, not a clip artifact.

## Diagnostic Approach

Added temporary logging at 4 stages:
1. Input profile corner breaks
2. Coords after `_profile_to_radius_coords` (corner break trimming)
3. All edges from the offset face (pre-clip)
4. All edges after clipping + filter decisions

This confirmed:
- The chamfer geometry IS correctly created by `_profile_to_radius_coords`
- The offset operation correctly produces the chamfer edge (shifted by fin_allowance)
- The Boolean clip correctly preserves the chamfer in the clipped wire
- The edge FILTER is where it's lost — both endpoints fall within the bloated tolerance of z_top

## Fix (Two-Part)

### Part 1: Cap x_max_r at actual stock radius

```python
# Before:
x_max_r = 10.0  # Well beyond any stock

# After:
stock_r = stock.diameter / 2.0 if stock else 0.5
x_max_r = stock_r + 0.1  # Small margin beyond stock OD
```

For 1" stock, tolerance drops from 0.02 to ~0.001.

### Part 2: Directionality check for Z boundary filter

```python
# Before:
if abs(sz - z_top) < tol and abs(ez - z_top) < tol:
    continue

# After:
if abs(sz - z_top) < tol and abs(ez - z_top) < tol:
    x_span = abs(sx - ex)
    z_span = abs(sz - ez)
    if x_span > z_span * 2.0 or x_span < tol:
        continue  # Truly horizontal edge along z_top
```

A true clip boundary edge at Z=z_top is horizontal (large X span, near-zero
Z span). A chamfer diagonal has comparable X and Z spans, so it passes through.

Same logic applied to Z=z_bot boundary.

### Tolerance formula also tightened:

```python
# Before:
tol = max(1e-3, z_range * 0.001, x_range * 0.001)

# After:
tol = max(1e-4, min(z_range * 0.001, x_range * 0.001))
```

Uses `min` instead of `max` to prevent one large dimension from inflating
tolerance beyond what small features can tolerate.

## Verification

- Diagnostic script with chamfer at junction 1 (face/shoulder): chamfer edge
  now survives the filter and appears in the cleanup pass output
- Corner Break Test.json (chamfer + 3 fillets): all 8 turning edges preserved,
  10 cleanup moves with correct arc directions
- Full test suite: 205 tests pass, no regressions

## Files Modified

- `planners/cleanup_planner.py` — x_max_r cap, tolerance formula, directional filter

## Key Lesson

When using tolerance-based boundary detection to separate "clip edges" from
"profile edges," the tolerance must be smaller than the smallest profile
feature. And the filter should check edge directionality, not just endpoint
proximity — a diagonal edge touching a boundary is not the same as an edge
running along it.
