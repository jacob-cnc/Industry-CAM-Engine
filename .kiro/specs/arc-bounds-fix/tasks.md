# Implementation Plan

## Overview

Fix arc segments that exceed X bounds by implementing bounds-aware center selection, adding X extremum validation, and providing bounds-aware radius suggestions. The fix targets `geometry/arc_helpers.py`, `gui/program_tab.py`, `planners/finish_planner.py`, `planners/cleanup_planner.py`, and `validation/pre_planning_validator.py`.

## Tasks

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - Arc X Bounds Violation
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the arc exceeds X bounds when the cross-product center selection picks the wrong center
  - **Scoped PBT Approach**: Generate arc segments where chord ≈ 2×radius (near-semicircle cases) with varying CW/CCW directions and endpoint configurations that trigger the bug condition
  - Test that for arc segments where `isBugCondition(input)` holds, all interpolated arc points satisfy `x_min_bound - TOLERANCE <= point.x <= x_max_bound + TOLERANCE` where bounds are `[min(X_start_r, X_end_r), max(X_start_r, X_end_r)]`
  - Use Hypothesis to generate arc segments with: x_start_r in [0.3, 1.5], x_end_r in [0.3, 1.5] (different from x_start_r), z_start/z_end varying, radius near chord/2 + small epsilon, both CW and CCW
  - Filter inputs using `assume()` to only test cases where the current `selectCenter()` produces an arc exceeding X bounds (the bug condition)
  - Assert expected behavior: all arc interpolation points stay within `[min(X_start_r, X_end_r) - 1e-9, max(X_start_r, X_end_r) + 1e-9]`
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS (this is correct - it proves the bug exists by showing counterexamples where arc points exceed X bounds)
  - Document counterexamples found (e.g., "CW arc from X=0.5r to X=0.75r with radius≈chord/2 produces points at X≈1.0r, exceeding X_end by 0.25r")
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 2.3_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Non-Buggy Arc Behavior Unchanged
  - **IMPORTANT**: Follow observation-first methodology
  - **IMPORTANT**: Write this test BEFORE implementing the fix
  - Observe: Run the UNFIXED `selectCenter()` on arc segments that are already within X bounds (where `isBugCondition` returns false) and record the center coordinates produced
  - Observe: Shallow arcs (radius >> chord/2) produce centers far from the chord, resulting in arcs well within bounds
  - Observe: Vertical chord arcs (X_start = X_end) produce correct convex bulge arcs
  - Observe: Line segments pass through without arc validation
  - Observe: Arcs with radius < chord/2 produce the existing "radius too small" error
  - Write property-based test using Hypothesis: for all arc segments where `NOT isBugCondition(input)` (non-buggy inputs), assert `selectCenter_original(input) == selectCenter_fixed(input)` — the center coordinates must be identical
  - Generate random arc segments with: radius significantly larger than chord/2 (e.g., radius > 2×chord), same-X endpoints (vertical chords), and various endpoint/direction combinations that do NOT trigger the bug condition
  - Use `assume()` to filter out inputs where the bug condition holds
  - Verify test passes on UNFIXED code (confirms baseline behavior is captured correctly)
  - **EXPECTED OUTCOME**: Tests PASS (this confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 3. Fix for arc X bounds violation

  - [x] 3.1 Add `compute_arc_x_extremum()` utility to `geometry/arc_helpers.py`
    - Implement function that computes the maximum and minimum X values an arc reaches between two endpoints given a center and radius
    - The X extremum of a circular arc occurs either at the endpoints or where the tangent is vertical (at `center_x ± radius` if that angle is within the arc sweep)
    - Handle edge cases: quarter circle, semicircle, shallow arc, full sweep
    - _Bug_Condition: isBugCondition(input) where arc_x_extremum exceeds [min(X_start, X_end), max(X_start, X_end)]_
    - _Expected_Behavior: compute correct extremum for any arc configuration_
    - _Preservation: Must not affect existing compute_min_radius() behavior_
    - _Requirements: 2.1, 2.2, 2.3, 2.5_

  - [x] 3.2 Add `is_arc_within_x_bounds()` utility to `geometry/arc_helpers.py`
    - Implement function that takes endpoints, center, and radius, computes the arc X extremum via `compute_arc_x_extremum()`, and returns whether it stays within `[min(X_start, X_end), max(X_start, X_end)]` within TOLERANCE
    - Return boolean indicating bounded status
    - _Bug_Condition: isBugCondition(input) where this function would return False for the current center_
    - _Expected_Behavior: correctly identify out-of-bounds arcs_
    - _Preservation: New function, no existing behavior affected_
    - _Requirements: 2.1, 2.2, 2.3_

  - [x] 3.3 Add bounds-aware center selection to `gui/program_tab.py`
    - After the cross-product center selection (around line 1172), compute the arc X extremum using `is_arc_within_x_bounds()`
    - If the selected center produces an out-of-bounds arc, swap to the other candidate center
    - If both candidate centers produce out-of-bounds arcs, flag the arc as invalid (degenerate case)
    - _Bug_Condition: isBugCondition(input) where cross-product picks the far-side center producing major arc_
    - _Expected_Behavior: select the center that keeps arc within [min(X_start, X_end), max(X_start, X_end)]_
    - _Preservation: For non-buggy arcs, cross-product selection is already correct — no change in behavior_
    - _Requirements: 1.1, 2.1, 2.2, 2.3, 3.1, 3.2_

  - [x] 3.4 Add bounds-aware center selection to `planners/finish_planner.py`
    - Apply same bounds-aware center selection logic as program_tab.py (around line 174 in `_find_arc_center()`)
    - After cross-product selection, verify arc stays within X bounds; if not, swap centers
    - _Bug_Condition: isBugCondition(input) where finish planner generates out-of-bounds toolpath_
    - _Expected_Behavior: finish planner generates bounded toolpaths for all arc segments_
    - _Preservation: Non-buggy arcs produce identical toolpaths_
    - _Requirements: 1.1, 2.1, 2.2, 2.3, 3.1_

  - [x] 3.5 Add bounds-aware center selection to `planners/cleanup_planner.py`
    - Mirror the fix from finish_planner.py to maintain consistency (around line 845)
    - Same bounds check and center swap logic
    - _Bug_Condition: isBugCondition(input) where cleanup planner generates out-of-bounds toolpath_
    - _Expected_Behavior: cleanup planner generates bounded toolpaths for all arc segments_
    - _Preservation: Non-buggy arcs produce identical toolpaths_
    - _Requirements: 1.1, 2.1, 2.2, 2.3, 3.1_

  - [x] 3.6 Add X bounds validation to `validation/pre_planning_validator.py`
    - After the existing `radius >= chord/2` check in `validate_profile()`, compute the arc center and X extremum
    - If the extremum exceeds `[min(X_start, X_end), max(X_start, X_end)]`, emit an ERROR-level `ValidationResult` with an actionable message explaining the bounds violation and suggesting alternatives
    - Preserve the existing "radius too small" error message format and behavior
    - _Bug_Condition: isBugCondition(input) where validator currently allows out-of-bounds arcs_
    - _Expected_Behavior: reject arc configurations whose computed X extremum exceeds endpoint bounds_
    - _Preservation: Existing "radius too small" error unchanged; non-buggy arcs pass validation as before_
    - _Requirements: 1.5, 2.5, 3.5_

  - [x] 3.7 Add bounds-aware radius suggestions to `geometry/arc_helpers.py`
    - Modify `compute_min_radius()` or add `compute_min_bounded_radius()` that computes the minimum radius producing a bounded arc
    - When suggesting alternative radii in `format_validation_message()`, verify that the suggested radius produces a bounded arc using `is_arc_within_x_bounds()`
    - If `chord/2` would produce an out-of-bounds semicircle, suggest a larger minimum radius that keeps the arc within bounds
    - _Bug_Condition: isBugCondition(input) where compute_min_radius() suggests radius that produces out-of-bounds arc_
    - _Expected_Behavior: only suggest radii that produce arcs bounded within [min(X_start, X_end), max(X_start, X_end)]_
    - _Preservation: For arcs where chord/2 is already bounded, suggestions remain unchanged_
    - _Requirements: 1.4, 2.4, 3.1_

  - [x] 3.8 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - Arc X Bounds Enforcement
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior (all arc points within X bounds)
    - When this test passes, it confirms the expected behavior is satisfied for all buggy inputs
    - Run bug condition exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed — arcs now stay within X bounds)
    - _Requirements: 2.1, 2.2, 2.3_

  - [x] 3.9 Verify preservation tests still pass
    - **Property 2: Preservation** - Non-Buggy Arc Behavior Unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions — non-buggy arcs produce identical results)
    - Confirm all tests still pass after fix (no regressions introduced)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 4. Checkpoint - Ensure all tests pass
  - Run the full test suite to verify no regressions
  - Verify bug condition exploration test (Property 1) passes
  - Verify preservation property tests (Property 2) pass
  - Verify any existing unit tests in the project still pass
  - Ensure all tests pass, ask the user if questions arise


## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1", "2"] },
    { "id": 1, "tasks": ["3.1"] },
    { "id": 2, "tasks": ["3.2"] },
    { "id": 3, "tasks": ["3.3", "3.4", "3.5", "3.6", "3.7"] },
    { "id": 4, "tasks": ["3.8"] },
    { "id": 5, "tasks": ["3.9"] },
    { "id": 6, "tasks": ["4"] }
  ]
}
```

## Notes

- Tasks 1 and 2 must be completed BEFORE any implementation work begins (tasks 3.x)
- Task 1 is expected to FAIL on unfixed code — this confirms the bug exists
- Task 2 is expected to PASS on unfixed code — this captures baseline behavior
- Tasks 3.3, 3.4, 3.5 can be done in parallel once 3.1 and 3.2 are complete
- The fix uses Hypothesis for property-based testing (already present in the project as `.hypothesis/` directory exists)
- TOLERANCE for bounds checking should match the project's existing geometric tolerance (likely 1e-9 or similar)
