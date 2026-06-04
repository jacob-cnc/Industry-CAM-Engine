# Arc Bounds Fix — Bugfix Design

## Overview

Arc segments in the Profile Segments table produce geometry that exceeds the X bounds defined by the start and end points. The cross-product center selection logic picks the center that satisfies the CW/CCW direction convention but does not verify that the resulting arc stays within the X bounds of the endpoints. Additionally, the arc helper (`compute_min_radius`) suggests radius values without bounds checking, and the pre-planning validator only checks `radius >= chord/2` without verifying the arc extremum stays within bounds.

The fix targets three locations: (1) the center selection logic in `program_tab.py` and `finish_planner.py` to prefer the bounded center, (2) the `arc_helpers.py` module to reject or clamp radius suggestions that produce out-of-bounds arcs, and (3) the `pre_planning_validator.py` to reject arc configurations whose computed X extremum exceeds the endpoint bounds.

## Glossary

- **Bug_Condition (C)**: The condition where the selected arc center produces an arc path whose X extremum exceeds `[min(X_start, X_end), max(X_start, X_end)]`
- **Property (P)**: The desired behavior — all arc points stay within the X bounds of the endpoints (within tolerance)
- **Preservation**: Existing behavior for arcs that are already within bounds, line segments, and the "radius too small" error must remain unchanged
- **selectCenter()**: The function in `finish_planner.py` (and duplicated in `program_tab.py`, `cleanup_planner.py`) that uses cross-product sign to pick between two candidate arc centers based on CW/CCW direction
- **compute_min_radius()**: The function in `geometry/arc_helpers.py` that computes `chord/2` as the minimum valid radius without bounds checking
- **X bounds**: The interval `[min(X_start_r, X_end_r), max(X_start_r, X_end_r)]` — the arc must not exceed these values in the X (radius) direction
- **Major arc**: An arc subtending > 180° — always exceeds the X bounds of its endpoints
- **Minor arc**: An arc subtending ≤ 180° — may or may not stay within X bounds depending on center placement

## Bug Details

### Bug Condition

The bug manifests when an arc segment is defined with endpoints and a signed radius, and the cross-product center selection picks the center that produces an arc path exceeding the X bounds of the endpoints. This happens because the selection logic only considers CW/CCW direction (cross-product sign) without checking whether the resulting arc stays geometrically bounded.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type ArcSegment {x_start_r, z_start, x_end_r, z_end, radius, is_cw}
  OUTPUT: boolean

  // Compute the arc center using the current cross-product selection
  center ← selectCenter(input.x_start_r, input.z_start, input.x_end_r, input.z_end, |input.radius|, input.is_cw)

  // Compute the arc extremum in X (the peak/valley of the arc path)
  x_min_bound ← min(input.x_start_r, input.x_end_r)
  x_max_bound ← max(input.x_start_r, input.x_end_r)
  arc_x_extremum ← computeArcExtremumX(center, |input.radius|, input.x_start_r, input.z_start, input.x_end_r, input.z_end)

  // Bug triggers when the arc exceeds the X bounds of the endpoints
  RETURN arc_x_extremum > x_max_bound + TOLERANCE OR arc_x_extremum < x_min_bound - TOLERANCE
END FUNCTION
```

### Examples

- **CW arc, X=0.5r to X=0.75r, radius ≈ chord/2**: Cross-product selects center on far side of chord → major arc peaks at X ≈ 1.0r (exceeds X_end=0.75r by 0.25r). Expected: arc stays within [0.5r, 0.75r].
- **CCW arc, X=0.5r to X=0.75r, radius ≈ chord/2**: Cross-product selects center on far side → arc dips below X=0.5r. Expected: arc stays within [0.5r, 0.75r].
- **CW arc, large radius (shallow arc)**: Center is far from chord, arc barely deviates from straight line → stays well within bounds. This case is NOT buggy and must be preserved.
- **Arc with same X start/end (vertical chord)**: Arc bulges outward then returns — inherently bounded since both endpoints share the same X. This case is NOT buggy.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Arcs with radius significantly larger than chord/2 (shallow arcs well within bounds) must continue to compute and render identically
- Arcs connecting two points at the same X value (vertical chord) must continue to render the convex bulge correctly
- LINE segments must continue to render as straight lines without any arc validation applied
- Semicircular arcs (radius = chord/2) that stay within X bounds must continue to be accepted
- The existing "radius too small" error (radius < chord/2) must continue to report with the same message format and alternatives

**Scope:**
All inputs where the current center selection already produces an arc within X bounds should be completely unaffected by this fix. This includes:
- Shallow arcs (large radius relative to chord)
- Vertical-chord arcs (same X start and end)
- Line segments (no arc validation)
- Arcs where both candidate centers produce bounded paths (the cross-product selection is already correct)

## Hypothesized Root Cause

Based on the bug description and code analysis, the most likely issues are:

1. **Cross-product selection ignores bounds**: The `selectCenter()` function in `finish_planner.py` (line ~215) and `program_tab.py` (line ~1175) picks the center purely based on CW/CCW direction (cross-product sign). When the chord is nearly equal to the diameter (2×radius), both candidate centers are close to the chord midpoint but on opposite sides — one produces the minor arc (bounded) and the other produces the major arc (unbounded). The cross-product criterion can pick the wrong one.

2. **No bounds validation after center selection**: After selecting the center, neither `program_tab.py` nor `finish_planner.py` computes the arc's X extremum to verify it stays within `[min(X_start, X_end), max(X_start, X_end)]`. The arc is rendered/planned without any bounds check.

3. **`compute_min_radius()` lacks bounds awareness**: The function in `geometry/arc_helpers.py` returns `chord/2` as the minimum radius. This is geometrically correct (minimum for a valid circle through both points) but does not account for whether the resulting arc stays within X bounds. A radius of `chord/2` produces a semicircle which may exceed bounds depending on chord orientation.

4. **Pre-planning validator only checks `radius >= chord/2`**: The validator in `validation/pre_planning_validator.py` (line ~87) only rejects arcs where the radius is too small to form a valid circle. It does not compute the arc extremum or reject arcs that would exceed X bounds.

## Correctness Properties

Property 1: Bug Condition - Arc X Bounds Enforcement

_For any_ arc segment where the bug condition holds (the current center selection produces an arc exceeding X bounds), the fixed center selection and validation SHALL produce an arc whose X values stay within `[min(X_start_r, X_end_r) - TOLERANCE, max(X_start_r, X_end_r) + TOLERANCE]` for all interpolated points along the arc path.

**Validates: Requirements 2.1, 2.2, 2.3**

Property 2: Preservation - Non-Buggy Arc Behavior Unchanged

_For any_ arc segment where the bug condition does NOT hold (the current center selection already produces a bounded arc), the fixed function SHALL produce the same center coordinates, the same interpolated arc points, and the same rendered/planned geometry as the original function, preserving all existing correct behavior.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `geometry/arc_helpers.py`

**Function**: `compute_min_radius()` and new `compute_arc_x_extremum()`

**Specific Changes**:
1. **Add `compute_arc_x_extremum()` utility**: New function that, given a center and radius, computes the maximum and minimum X values the arc reaches between two endpoints. This is the geometric core — the X extremum of a circular arc occurs either at the endpoints or where the tangent is vertical (i.e., at `center_x ± radius` if that angle is within the sweep).

2. **Add `is_arc_within_x_bounds()` utility**: New function that takes endpoints, center, and radius, computes the arc X extremum, and returns whether it stays within `[min(X_start, X_end), max(X_start, X_end)]`.

3. **Modify `compute_min_radius()` or add `compute_min_bounded_radius()`**: Either modify the existing function or add a new one that computes the minimum radius that produces a bounded arc (not just a geometrically valid circle). This may be larger than `chord/2`.

---

**File**: `gui/program_tab.py` (around line 1172)

**Function**: Arc center selection in `_update_profile_graph()`

**Specific Changes**:
4. **Add bounds check after center selection**: After the cross-product picks a center, compute the arc X extremum. If it exceeds bounds, swap to the other candidate center. If both exceed bounds, flag the arc as invalid (degenerate case).

---

**File**: `planners/finish_planner.py` (around line 174)

**Function**: `_find_arc_center()` (or equivalent method)

**Specific Changes**:
5. **Add bounds-aware center selection**: Same logic as program_tab.py — after cross-product selection, verify the arc stays within X bounds. If not, swap centers. This ensures the finish planner generates bounded toolpaths.

---

**File**: `planners/cleanup_planner.py` (around line 845)

**Function**: Arc center selection (duplicated from finish_planner)

**Specific Changes**:
6. **Apply same bounds-aware center selection**: Mirror the fix from finish_planner.py to maintain consistency.

---

**File**: `validation/pre_planning_validator.py`

**Function**: `validate_profile()`

**Specific Changes**:
7. **Add X bounds validation for arcs**: After the existing `radius >= chord/2` check, compute the arc center and X extremum. If the extremum exceeds `[min(X_start, X_end), max(X_start, X_end)]`, emit an ERROR-level `ValidationResult` with an actionable message explaining the bounds violation and suggesting alternatives.

---

**File**: `geometry/arc_helpers.py`

**Function**: `format_validation_message()`

**Specific Changes**:
8. **Add bounds-aware suggestions**: When suggesting alternative radii, verify that the suggested radius produces a bounded arc. If `chord/2` would produce an out-of-bounds semicircle, suggest a larger minimum radius that keeps the arc within bounds.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write tests that construct arc segments with endpoints where the chord is nearly equal to the diameter, invoke the center selection logic, interpolate the arc, and assert that the X extremum stays within bounds. Run these tests on the UNFIXED code to observe failures and understand the root cause.

**Test Cases**:
1. **CW arc near-semicircle overshoot**: Define arc from (0.5r, 0.0) to (0.75r, -0.3) with radius ≈ chord/2 + epsilon, CW. Assert arc X ≤ 0.75r. (will fail on unfixed code)
2. **CCW arc near-semicircle undershoot**: Define arc from (0.5r, 0.0) to (0.75r, -0.3) with radius ≈ chord/2 + epsilon, CCW. Assert arc X ≥ 0.5r. (will fail on unfixed code)
3. **Exact semicircle bounds violation**: Define arc with radius = chord/2 exactly where the semicircle exceeds X bounds. (will fail on unfixed code)
4. **Helper suggestion produces out-of-bounds arc**: Call `compute_min_radius()`, use the result as radius, verify the resulting arc stays within bounds. (may fail on unfixed code)

**Expected Counterexamples**:
- Arc interpolation produces points with X > max(X_start, X_end) or X < min(X_start, X_end)
- Possible causes: cross-product selects the far-side center, producing the major arc path

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  center' ← selectCenter_fixed(input.x_start_r, input.z_start, input.x_end_r, input.z_end, |input.radius|, input.is_cw)
  arc_points ← interpolateArc(center', |input.radius|, input.x_start_r, input.z_start, input.x_end_r, input.z_end)

  x_min_bound ← min(input.x_start_r, input.x_end_r)
  x_max_bound ← max(input.x_start_r, input.x_end_r)

  FOR EACH point IN arc_points DO
    ASSERT point.x >= x_min_bound - TOLERANCE
    ASSERT point.x <= x_max_bound + TOLERANCE
  END FOR
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT selectCenter_original(input) = selectCenter_fixed(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many arc configurations automatically across the input domain (varying X_start, X_end, Z_start, Z_end, radius, direction)
- It catches edge cases that manual unit tests might miss (e.g., vertical chords, near-zero chords, very large radii)
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs

**Test Plan**: Observe behavior on UNFIXED code first for arcs that are already within bounds, then write property-based tests capturing that behavior.

**Test Cases**:
1. **Shallow arc preservation**: Generate arcs with radius >> chord/2 (well within bounds), verify center selection is identical before and after fix
2. **Vertical chord preservation**: Generate arcs with X_start = X_end (different Z), verify rendering is identical
3. **Line segment preservation**: Verify line segments pass through without arc validation
4. **Radius-too-small error preservation**: Generate arcs with radius < chord/2, verify the same error message is produced

### Unit Tests

- Test `compute_arc_x_extremum()` with known geometric configurations (quarter circle, semicircle, shallow arc)
- Test `is_arc_within_x_bounds()` for boundary cases (extremum exactly at bound, just inside, just outside)
- Test center selection swap logic: when cross-product picks the wrong center, verify the fix swaps to the bounded center
- Test pre-planning validator rejects out-of-bounds arcs with correct error message
- Test `compute_min_radius()` / bounded radius suggestion for arcs where chord/2 would exceed bounds

### Property-Based Tests

- Generate random arc segments (varying endpoints, radius, direction) and verify: if the arc is within bounds, the fixed code produces the same center as the original code (preservation)
- Generate random arc segments that trigger the bug condition and verify: the fixed code produces an arc within X bounds (fix checking)
- Generate random non-arc segments and verify: no arc validation is applied (line segment preservation)
- Generate random arcs with radius < chord/2 and verify: the "radius too small" error is unchanged

### Integration Tests

- Test full finish planner pipeline with a profile containing a near-semicircle arc that previously exceeded bounds — verify the generated toolpath stays within bounds
- Test the profile preview graph rendering with the same arc — verify visual output matches expected bounded arc
- Test the pre-planning validator catches an out-of-bounds arc before it reaches the planner
- Test the arc helper suggestions for a configuration where chord/2 would exceed bounds — verify the suggestion is bounded
