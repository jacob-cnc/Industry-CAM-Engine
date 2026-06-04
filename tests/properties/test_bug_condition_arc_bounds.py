"""Bug Condition Exploration Test — Property 1: Arc X Bounds Violation.

This test verifies the fix for arc segments that exceed X bounds.

Validates: Requirements 1.1, 1.2, 1.3, 2.1, 2.2, 2.3

Bug Condition:
    The cross-product center selection logic picks the center that satisfies
    CW/CCW direction but does NOT verify the resulting arc stays within the
    X bounds [min(X_start, X_end), max(X_start, X_end)]. When chord ≈ 2×radius
    (near-semicircle), the wrong center produces the major arc (>180°) which
    exceeds X bounds.

Test Strategy:
    Generate arc segments where chord ≈ 2×radius (near-semicircle cases) with
    varying CW/CCW directions. Filter using assume() to only test cases where
    the UNFIXED selectCenter() produces an arc exceeding X bounds (the bug
    condition). Then verify that the fix resolves the issue:
    - compute_min_bounded_radius() provides a valid bounded radius
    - Using that radius with _select_center() produces an arc within bounds

Expected Outcome:
    Test PASSES on fixed code — confirms the fix works correctly.
    Test FAILS on unfixed code — proves the bug exists.
"""

import math
import sys
import os

import pytest
from hypothesis import given, settings, assume, note, HealthCheck
from hypothesis import strategies as st

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Tolerance for floating-point comparisons
TOLERANCE = 1e-9


# ---------------------------------------------------------------------------
# Core geometry functions — UNFIXED logic for bug condition detection
# ---------------------------------------------------------------------------

def select_center_unfixed(
    x1_r: float, z1: float, x2_r: float, z2: float,
    radius: float, is_cw: bool
) -> tuple:
    """Find arc center using cross-product selection (UNFIXED logic).

    Replicates the ORIGINAL logic from finish_planner.py _find_arc_center()
    BEFORE the bounds-aware fix. Used by is_bug_condition() to identify
    inputs that WOULD have triggered the bug.
    """
    mx = (x1_r + x2_r) / 2.0
    mz = (z1 + z2) / 2.0

    dx = x2_r - x1_r
    dz = z2 - z1
    d = math.sqrt(dx**2 + dz**2)

    if d < 1e-10:
        return None

    h_sq = radius**2 - (d / 2.0)**2
    if h_sq < 0:
        h_sq = 0
    h = math.sqrt(h_sq)

    px = -dz / d
    pz = dx / d

    c1_x = mx + h * px
    c1_z = mz + h * pz
    c2_x = mx - h * px
    c2_z = mz - h * pz

    # Cross product: (start-center) x (end-center)
    ax = x1_r - c1_x
    az = z1 - c1_z
    bx = x2_r - c1_x
    bz = z2 - c1_z
    cr1 = ax * bz - az * bx

    # CW -> negative cross, CCW -> positive cross
    if is_cw:
        return (c1_x, c1_z) if cr1 < 0 else (c2_x, c2_z)
    else:
        return (c1_x, c1_z) if cr1 > 0 else (c2_x, c2_z)


def compute_arc_x_extremum(
    cx_r: float, cz: float, radius: float,
    x1_r: float, z1: float, x2_r: float, z2: float,
    is_cw: bool
) -> tuple:
    """Compute the min and max X values the arc reaches.

    The X extremum of a circular arc occurs either at the endpoints or
    where the tangent is vertical (at center_x ± radius if that angle
    is within the arc sweep).

    Returns:
        (x_min, x_max) of the arc path.
    """
    angle_start = math.atan2(z1 - cz, x1_r - cx_r)
    angle_end = math.atan2(z2 - cz, x2_r - cx_r)
    diff = angle_end - angle_start

    # Normalize sweep
    if is_cw:
        if diff > 0:
            diff -= 2 * math.pi
    else:
        if diff < 0:
            diff += 2 * math.pi

    # Start with endpoint X values
    x_min = min(x1_r, x2_r)
    x_max = max(x1_r, x2_r)

    def angle_in_sweep(target_angle):
        """Check if target_angle is within the arc sweep from angle_start."""
        rel = target_angle - angle_start
        if is_cw:
            while rel > 0:
                rel -= 2 * math.pi
            while rel < -2 * math.pi:
                rel += 2 * math.pi
            return diff <= rel <= 0
        else:
            while rel < 0:
                rel += 2 * math.pi
            while rel > 2 * math.pi:
                rel -= 2 * math.pi
            return 0 <= rel <= diff

    # Rightmost point: angle = 0, x = cx + radius
    if angle_in_sweep(0.0):
        x_max = max(x_max, cx_r + radius)

    # Leftmost point: angle = pi, x = cx - radius
    if angle_in_sweep(math.pi):
        x_min = min(x_min, cx_r - radius)

    return (x_min, x_max)


def interpolate_arc(
    cx_r: float, cz: float, radius: float,
    x1_r: float, z1: float, x2_r: float, z2: float,
    is_cw: bool, n_pts: int = 100
) -> list:
    """Interpolate arc points from start to end around center."""
    angle_start = math.atan2(z1 - cz, x1_r - cx_r)
    angle_end = math.atan2(z2 - cz, x2_r - cx_r)
    diff = angle_end - angle_start

    if is_cw:
        if diff > 0:
            diff -= 2 * math.pi
    else:
        if diff < 0:
            diff += 2 * math.pi

    points = []
    for i in range(n_pts + 1):
        t = i / float(n_pts)
        angle = angle_start + diff * t
        x = cx_r + radius * math.cos(angle)
        z = cz + radius * math.sin(angle)
        points.append((x, z))

    return points


def is_bug_condition(
    x_start_r: float, z_start: float,
    x_end_r: float, z_end: float,
    radius: float, is_cw: bool
) -> bool:
    """Check if the ORIGINAL (unfixed) center selection produces an arc exceeding X bounds.

    This is the formal bug condition from the spec. Uses the UNFIXED logic
    to identify inputs that WOULD have triggered the bug.
    """
    center = select_center_unfixed(x_start_r, z_start, x_end_r, z_end, radius, is_cw)
    if center is None:
        return False

    cx_r, cz = center
    x_min_bound = min(x_start_r, x_end_r)
    x_max_bound = max(x_start_r, x_end_r)

    arc_x_min, arc_x_max = compute_arc_x_extremum(
        cx_r, cz, radius, x_start_r, z_start, x_end_r, z_end, is_cw
    )

    return arc_x_max > x_max_bound + TOLERANCE or arc_x_min < x_min_bound - TOLERANCE


# ---------------------------------------------------------------------------
# Property-Based Test: Bug Condition Exploration
# ---------------------------------------------------------------------------

class TestBugConditionArcXBounds:
    """Property 1: Arc X Bounds Enforcement.

    For arc segments where the bug condition holds (unfixed center selection
    produces an arc exceeding X bounds), verify that the fix resolves the
    issue: compute_min_bounded_radius() provides a radius that produces
    an arc staying within [min(X_start_r, X_end_r), max(X_start_r, X_end_r)].
    """

    @given(
        x_start_r=st.floats(min_value=0.3, max_value=1.5),
        x_end_r=st.floats(min_value=0.3, max_value=1.5),
        z_start=st.floats(min_value=-1.0, max_value=0.5),
        z_end=st.floats(min_value=-1.0, max_value=0.5),
        radius_epsilon=st.floats(min_value=0.001, max_value=0.5),
        is_cw=st.booleans(),
    )
    @settings(max_examples=500, suppress_health_check=[HealthCheck.filter_too_much], deadline=None)
    def test_arc_points_within_x_bounds(
        self, x_start_r, x_end_r, z_start, z_end, radius_epsilon, is_cw
    ):
        """**Validates: Requirements 1.1, 1.2, 1.3, 2.1, 2.2, 2.3**

        Generate near-semicircle arcs (radius ≈ chord/2 + epsilon) where the
        bug condition holds, then verify that the FIXED system resolves the
        issue: using the bounded minimum radius produces an arc that stays
        within X bounds.

        The fix works as follows:
        1. The validator (task 3.6) detects arcs where the computed path
           exceeds X bounds and rejects them with an actionable message.
        2. The bounded radius suggestion (task 3.7) computes the minimum
           radius that produces a bounded arc.
        3. When the user applies the suggested radius, the resulting arc
           stays within [min(X_start, X_end), max(X_start, X_end)].

        This test verifies: for any bug-condition input, using the
        compute_min_bounded_radius() suggestion with _select_center()
        produces a valid bounded arc with all points within X bounds.
        """
        # Ensure endpoints are different (non-degenerate arc)
        assume(abs(x_start_r - x_end_r) > 0.01)
        assume(abs(z_start - z_end) > 0.01)

        # Compute chord and radius (near-semicircle: radius = chord/2 + epsilon)
        dx = x_end_r - x_start_r
        dz = z_end - z_start
        chord = math.sqrt(dx * dx + dz * dz)

        # Skip degenerate cases
        assume(chord > 0.02)

        # Radius is just slightly larger than chord/2 (near-semicircle)
        radius = chord / 2.0 + radius_epsilon

        # Filter: only test cases where the bug condition holds
        # (unfixed selectCenter produces an arc exceeding X bounds)
        assume(is_bug_condition(x_start_r, z_start, x_end_r, z_end, radius, is_cw))

        # Import the FIXED functions from the actual codebase
        from geometry.arc_helpers import (
            compute_min_bounded_radius,
            _select_center,
            is_arc_within_x_bounds,
            compute_arc_x_extremum as real_extremum,
        )

        # THE FIX: compute the bounded minimum radius.
        # This is what the validator suggests and what the user would apply.
        bounded_radius = compute_min_bounded_radius(
            x_start_r, z_start, x_end_r, z_end, is_cw
        )

        # The bounded radius must be >= chord/2 (geometric minimum)
        assert bounded_radius >= chord / 2.0 - TOLERANCE, (
            f"Bounded radius {bounded_radius} should be >= chord/2 {chord/2}"
        )

        # Use _select_center (from the codebase) with the bounded radius
        center = _select_center(x_start_r, z_start, x_end_r, z_end, bounded_radius, is_cw)
        assert center is not None, "Center should exist for bounded radius"
        cx_r, cz = center

        # Verify the arc with bounded radius is within X bounds using
        # the codebase's is_arc_within_x_bounds function
        assert is_arc_within_x_bounds(
            cx_r, cz, bounded_radius, x_start_r, z_start, x_end_r, z_end, is_cw
        ), (
            f"Arc with bounded radius {bounded_radius:.6f} should be within X bounds "
            f"but is_arc_within_x_bounds returned False. "
            f"Center=({cx_r:.6f}, {cz:.6f})"
        )

        # Interpolate arc points with the bounded radius
        points = interpolate_arc(
            cx_r, cz, bounded_radius,
            x_start_r, z_start, x_end_r, z_end,
            is_cw, n_pts=100
        )

        # Expected bounds (with slightly relaxed tolerance for interpolation)
        x_min_bound = min(x_start_r, x_end_r)
        x_max_bound = max(x_start_r, x_end_r)
        # Use a slightly larger tolerance for interpolated points since
        # discrete sampling can introduce small numerical errors
        INTERP_TOLERANCE = 1e-6

        note(f"Arc: X_start={x_start_r:.4f}, X_end={x_end_r:.4f}, "
             f"Z_start={z_start:.4f}, Z_end={z_end:.4f}")
        note(f"Original radius={radius:.4f}, bounded_radius={bounded_radius:.4f}")
        note(f"chord={chord:.4f}, chord/2={chord/2:.4f}")
        note(f"is_cw={is_cw}, center=({cx_r:.4f}, {cz:.4f})")
        note(f"X bounds: [{x_min_bound:.4f}, {x_max_bound:.4f}]")

        # Find the arc X range
        max_x = max(p[0] for p in points)
        min_x = min(p[0] for p in points)
        note(f"Arc X range: [{min_x:.4f}, {max_x:.4f}]")

        # ASSERT EXPECTED BEHAVIOR: all arc points within X bounds
        # With the bounded radius from the fix, the arc MUST stay within bounds.
        for i, (px, pz) in enumerate(points):
            assert px >= x_min_bound - INTERP_TOLERANCE, (
                f"Arc point {i} at X={px:.6f} is below X_min_bound={x_min_bound:.6f} "
                f"(violation: {x_min_bound - px:.6f}). "
                f"Arc from ({x_start_r:.4f}, {z_start:.4f}) to ({x_end_r:.4f}, {z_end:.4f}), "
                f"bounded_radius={bounded_radius:.4f}, is_cw={is_cw}, center=({cx_r:.4f}, {cz:.4f})"
            )
            assert px <= x_max_bound + INTERP_TOLERANCE, (
                f"Arc point {i} at X={px:.6f} exceeds X_max_bound={x_max_bound:.6f} "
                f"(violation: {px - x_max_bound:.6f}). "
                f"Arc from ({x_start_r:.4f}, {z_start:.4f}) to ({x_end_r:.4f}, {z_end:.4f}), "
                f"bounded_radius={bounded_radius:.4f}, is_cw={is_cw}, center=({cx_r:.4f}, {cz:.4f})"
            )
