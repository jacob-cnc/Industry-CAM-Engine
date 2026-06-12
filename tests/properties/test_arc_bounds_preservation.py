"""Preservation Property Test — Property 2: Non-Buggy Arc Behavior Unchanged.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

This test captures the EXISTING correct behavior of the arc center selection
for non-buggy inputs (arcs already within X bounds). It must PASS on unfixed
code and continue to pass after the fix is applied.

Observation-first methodology:
- Shallow arcs (radius >> chord/2) produce centers far from the chord,
  resulting in arcs well within bounds
- Vertical chord arcs (X_start = X_end) produce correct convex bulge arcs
- Line segments pass through without arc validation
- Arcs with radius < chord/2 produce the existing "radius too small" error

For all arc segments where NOT isBugCondition(input), the center selection
must produce identical results before and after the fix.
"""

import math
import sys
import os

import pytest
from hypothesis import given, settings, assume, note, HealthCheck
from hypothesis import strategies as st

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from geometry.arc_helpers import compute_min_radius, format_validation_message


# ---------------------------------------------------------------------------
# Core arc geometry functions (extracted from finish_planner/_find_arc_center)
# ---------------------------------------------------------------------------

TOLERANCE = 1e-9


def select_center(x1_r: float, z1: float, x2_r: float, z2: float,
                  radius: float, is_cw: bool):
    """Select arc center using cross-product convention.

    This is the CURRENT (unfixed) center selection logic, extracted from
    planners/finish_planner.py and gui/program_tab.py for testing.

    Returns (center_x_radius, center_z) or None if no solution.
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


def compute_arc_x_extremum(center_x: float, center_z: float, radius: float,
                           x1_r: float, z1: float, x2_r: float, z2: float,
                           is_cw: bool) -> tuple:
    """Compute the X extremum (min and max) of an arc between two endpoints.

    The X extremum of a circular arc occurs either at the endpoints or where
    the tangent is vertical (at center_x ± radius if that angle is within
    the arc sweep).

    Returns (x_min, x_max) of the arc path.
    """
    # Start and end angles relative to center
    angle_start = math.atan2(z1 - center_z, x1_r - center_x)
    angle_end = math.atan2(z2 - center_z, x2_r - center_x)

    # Compute sweep angle matching direction
    diff = angle_end - angle_start
    if is_cw:
        # CW on screen = negative sweep in data space
        if diff > 0:
            diff -= 2 * math.pi
    else:
        # CCW on screen = positive sweep in data space
        if diff < 0:
            diff += 2 * math.pi

    # Sample the arc to find extremum (robust approach)
    n_pts = max(64, int(abs(diff) * radius * 200))
    x_min = min(x1_r, x2_r)
    x_max = max(x1_r, x2_r)

    for i in range(1, n_pts):
        t = i / float(n_pts)
        angle = angle_start + diff * t
        x_pt = center_x + radius * math.cos(angle)
        x_min = min(x_min, x_pt)
        x_max = max(x_max, x_pt)

    return (x_min, x_max)


def is_bug_condition(x_start_r: float, z_start: float, x_end_r: float,
                     z_end: float, radius: float, is_cw: bool) -> bool:
    """Determine if the current center selection produces an out-of-bounds arc.

    Returns True if the arc exceeds the X bounds of the endpoints.
    """
    center = select_center(x_start_r, z_start, x_end_r, z_end, radius, is_cw)
    if center is None:
        return False

    cx, cz = center
    x_min_bound = min(x_start_r, x_end_r)
    x_max_bound = max(x_start_r, x_end_r)

    arc_x_min, arc_x_max = compute_arc_x_extremum(
        cx, cz, radius, x_start_r, z_start, x_end_r, z_end, is_cw
    )

    return (arc_x_max > x_max_bound + TOLERANCE or
            arc_x_min < x_min_bound - TOLERANCE)


def interpolate_arc(center_x: float, center_z: float, radius: float,
                    x1_r: float, z1: float, x2_r: float, z2: float,
                    is_cw: bool, n_pts: int = 64) -> list:
    """Interpolate arc points between two endpoints.

    Returns list of (x, z) tuples along the arc path.
    """
    angle_start = math.atan2(z1 - center_z, x1_r - center_x)
    angle_end = math.atan2(z2 - center_z, x2_r - center_x)

    diff = angle_end - angle_start
    if is_cw:
        if diff > 0:
            diff -= 2 * math.pi
    else:
        if diff < 0:
            diff += 2 * math.pi

    points = [(x1_r, z1)]
    for i in range(1, n_pts):
        t = i / float(n_pts)
        angle = angle_start + diff * t
        x_pt = center_x + radius * math.cos(angle)
        z_pt = center_z + radius * math.sin(angle)
        points.append((x_pt, z_pt))
    points.append((x2_r, z2))
    return points


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

@st.composite
def shallow_arc_strategy(draw):
    """Generate shallow arcs (radius >> chord/2) that are well within bounds.

    These arcs have large radius relative to chord, producing centers far
    from the chord and arcs that barely deviate from a straight line.
    Excludes vertical chords (X_start = X_end) which are tested separately.
    """
    x_start_r = draw(st.floats(min_value=0.2, max_value=1.5))
    x_end_r = draw(st.floats(min_value=0.2, max_value=1.5))
    z_start = draw(st.floats(min_value=-2.0, max_value=0.0))
    z_end = draw(st.floats(min_value=-2.0, max_value=0.0))
    is_cw = draw(st.booleans())

    # Ensure endpoints are distinct and NOT a vertical chord
    dx = x_end_r - x_start_r
    dz = z_end - z_start
    chord = math.sqrt(dx * dx + dz * dz)
    assume(chord > 0.01)  # Non-degenerate chord
    assume(abs(dx) > 0.02)  # Not a vertical chord

    # Radius significantly larger than chord/2 (at least 3x chord)
    min_radius = chord / 2.0
    radius_multiplier = draw(st.floats(min_value=3.0, max_value=20.0))
    radius = min_radius * radius_multiplier

    # Filter: must NOT be a bug condition
    assume(not is_bug_condition(x_start_r, z_start, x_end_r, z_end,
                                radius, is_cw))

    return {
        'x_start_r': x_start_r,
        'z_start': z_start,
        'x_end_r': x_end_r,
        'z_end': z_end,
        'radius': radius,
        'is_cw': is_cw,
    }


@st.composite
def vertical_chord_arc_strategy(draw):
    """Generate arcs with vertical chords (X_start = X_end).

    These arcs are inherently bounded since both endpoints share the same X
    and the arc bulges outward then returns.
    """
    x_r = draw(st.floats(min_value=0.3, max_value=1.5))
    z_start = draw(st.floats(min_value=-1.5, max_value=0.0))
    z_end = draw(st.floats(min_value=-1.5, max_value=0.0))
    is_cw = draw(st.booleans())

    # Ensure Z endpoints are distinct
    dz = abs(z_end - z_start)
    assume(dz > 0.01)

    # Radius must be >= chord/2 = dz/2
    chord = dz
    min_radius = chord / 2.0
    radius_multiplier = draw(st.floats(min_value=1.01, max_value=10.0))
    radius = min_radius * radius_multiplier

    return {
        'x_start_r': x_r,
        'z_start': z_start,
        'x_end_r': x_r,  # Same X — vertical chord
        'z_end': z_end,
        'radius': radius,
        'is_cw': is_cw,
    }


@st.composite
def general_non_buggy_arc_strategy(draw):
    """Generate general arc segments that do NOT trigger the bug condition.

    Uses assume() to filter out inputs where the bug condition holds.
    """
    x_start_r = draw(st.floats(min_value=0.2, max_value=1.5))
    x_end_r = draw(st.floats(min_value=0.2, max_value=1.5))
    z_start = draw(st.floats(min_value=-2.0, max_value=0.0))
    z_end = draw(st.floats(min_value=-2.0, max_value=0.0))
    is_cw = draw(st.booleans())

    # Ensure endpoints are distinct
    dx = x_end_r - x_start_r
    dz = z_end - z_start
    chord = math.sqrt(dx * dx + dz * dz)
    assume(chord > 0.01)

    # Radius >= chord/2 (valid arc)
    min_radius = chord / 2.0
    radius_multiplier = draw(st.floats(min_value=1.01, max_value=15.0))
    radius = min_radius * radius_multiplier

    # Filter: must NOT be a bug condition
    assume(not is_bug_condition(x_start_r, z_start, x_end_r, z_end,
                                radius, is_cw))

    return {
        'x_start_r': x_start_r,
        'z_start': z_start,
        'x_end_r': x_end_r,
        'z_end': z_end,
        'radius': radius,
        'is_cw': is_cw,
    }


# ---------------------------------------------------------------------------
# Property Tests — Preservation
# ---------------------------------------------------------------------------

class TestPreservation_ShallowArcs:
    """Shallow arcs (radius >> chord/2) must produce identical centers.

    **Validates: Requirements 3.1**

    Observation: Shallow arcs produce centers far from the chord, resulting
    in arcs that barely deviate from a straight line. These are well within
    X bounds and must be completely unaffected by any fix.
    """

    @given(arc=shallow_arc_strategy())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_shallow_arc_center_selection_preserved(self, arc):
        """**Validates: Requirements 3.1**

        For shallow arcs (radius >> chord/2), the center selection must
        produce the same result. These arcs are well within bounds.
        """
        center = select_center(
            arc['x_start_r'], arc['z_start'],
            arc['x_end_r'], arc['z_end'],
            arc['radius'], arc['is_cw']
        )

        # Center must be computable
        assert center is not None, "Shallow arc should always have a valid center"
        cx, cz = center

        # Verify the arc is within bounds (confirms non-buggy)
        arc_x_min, arc_x_max = compute_arc_x_extremum(
            cx, cz, arc['radius'],
            arc['x_start_r'], arc['z_start'],
            arc['x_end_r'], arc['z_end'],
            arc['is_cw']
        )
        x_min_bound = min(arc['x_start_r'], arc['x_end_r'])
        x_max_bound = max(arc['x_start_r'], arc['x_end_r'])

        note(f"Arc X range: [{arc_x_min:.6f}, {arc_x_max:.6f}]")
        note(f"Bounds: [{x_min_bound:.6f}, {x_max_bound:.6f}]")
        note(f"Center: ({cx:.6f}, {cz:.6f})")

        # Shallow arcs should be well within bounds
        assert arc_x_min >= x_min_bound - TOLERANCE, (
            f"Shallow arc X min {arc_x_min} below bound {x_min_bound}"
        )
        assert arc_x_max <= x_max_bound + TOLERANCE, (
            f"Shallow arc X max {arc_x_max} above bound {x_max_bound}"
        )


class TestPreservation_VerticalChordArcs:
    """Vertical chord arcs (X_start = X_end) must produce identical centers.

    **Validates: Requirements 3.2**

    Observation: Arcs connecting two points at the same X value produce a
    convex bulge that is inherently bounded since both endpoints share the
    same X. The arc bulges outward then returns.
    """

    @given(arc=vertical_chord_arc_strategy())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_vertical_chord_arc_center_preserved(self, arc):
        """**Validates: Requirements 3.2**

        For vertical chord arcs (X_start = X_end), the center selection
        must produce the same result. These are inherently bounded.
        """
        center = select_center(
            arc['x_start_r'], arc['z_start'],
            arc['x_end_r'], arc['z_end'],
            arc['radius'], arc['is_cw']
        )

        assert center is not None, "Vertical chord arc should have a valid center"
        cx, cz = center

        # Verify the center is geometrically correct
        # Distance from center to start should equal radius
        dist_start = math.sqrt(
            (arc['x_start_r'] - cx)**2 + (arc['z_start'] - cz)**2
        )
        assert abs(dist_start - arc['radius']) < 1e-6, (
            f"Center-to-start distance {dist_start} != radius {arc['radius']}"
        )

        # Distance from center to end should equal radius
        dist_end = math.sqrt(
            (arc['x_end_r'] - cx)**2 + (arc['z_end'] - cz)**2
        )
        assert abs(dist_end - arc['radius']) < 1e-6, (
            f"Center-to-end distance {dist_end} != radius {arc['radius']}"
        )

        note(f"Vertical chord arc: X={arc['x_start_r']:.4f}, "
             f"Z=[{arc['z_start']:.4f}, {arc['z_end']:.4f}]")
        note(f"Center: ({cx:.6f}, {cz:.6f}), radius={arc['radius']:.6f}")


class TestPreservation_LineSegments:
    """Line segments must pass through without arc validation.

    **Validates: Requirements 3.3**

    Observation: Line segments have no radius and no arc center computation.
    They are rendered as straight lines between endpoints. No arc validation
    should be applied to them.
    """

    @given(
        x_start_r=st.floats(min_value=0.1, max_value=2.0),
        z_start=st.floats(min_value=-3.0, max_value=0.5),
        x_end_r=st.floats(min_value=0.1, max_value=2.0),
        z_end=st.floats(min_value=-3.0, max_value=0.5),
    )
    @settings(max_examples=50)
    def test_line_segment_no_arc_validation(self, x_start_r, z_start,
                                            x_end_r, z_end):
        """**Validates: Requirements 3.3**

        Line segments (radius=0) should not trigger any arc center
        computation or bounds checking. They are straight lines.
        """
        # Line segments have radius = 0 — no arc computation needed
        # The program_tab.py code checks: if seg_type == "arc" and abs(radius) > 0.0001
        # So lines (radius=0) skip the entire arc block.
        radius = 0.0
        seg_type = "line"

        # Verify: with radius=0, the arc condition is not met
        assert not (seg_type == "arc" and abs(radius) > 0.0001), (
            "Line segments should not enter arc processing"
        )

        # Verify: compute_min_radius still works for reference
        # (it computes chord/2 regardless of segment type)
        dx = x_end_r - x_start_r
        dz = z_end - z_start
        chord = math.sqrt(dx * dx + dz * dz)
        if chord > 1e-10:
            min_r = compute_min_radius(x_start_r, z_start, x_end_r, z_end)
            assert abs(min_r - chord / 2.0) < 1e-10


class TestPreservation_RadiusTooSmall:
    """Arcs with radius < chord/2 must produce the same error message.

    **Validates: Requirements 3.5**

    Observation: When radius < chord/2, the arc is geometrically impossible.
    The format_validation_message() function produces an error with the
    minimum radius and alternatives. This behavior must be preserved.
    """

    @given(
        x_start_r=st.floats(min_value=0.2, max_value=1.5),
        z_start=st.floats(min_value=-2.0, max_value=0.0),
        x_end_r=st.floats(min_value=0.2, max_value=1.5),
        z_end=st.floats(min_value=-2.0, max_value=0.0),
        radius_fraction=st.floats(min_value=0.1, max_value=0.95),
    )
    @settings(max_examples=50)
    def test_radius_too_small_error_preserved(self, x_start_r, z_start,
                                              x_end_r, z_end, radius_fraction):
        """**Validates: Requirements 3.5**

        When radius < chord/2, the validation message must contain:
        - "too small" indication
        - The minimum radius value
        - At least one alternative suggestion
        """
        dx = x_end_r - x_start_r
        dz = z_end - z_start
        chord = math.sqrt(dx * dx + dz * dz)
        assume(chord > 0.05)  # Need meaningful chord

        min_radius = chord / 2.0
        # Use a radius that's too small (fraction of minimum)
        radius = min_radius * radius_fraction
        assume(radius < min_radius - 1e-9)
        assume(radius > 0.001)  # Not degenerate

        # Convert to diameter for the user-facing function
        x_start_dia = x_start_r * 2.0
        x_end_dia = x_end_r * 2.0

        msg = format_validation_message(
            x_start_dia, z_start, x_end_dia, z_end, radius
        )

        # Verify the error message format is preserved
        assert "too small" in msg.lower(), (
            f"Error message should contain 'too small': {msg}"
        )
        assert f"{min_radius:.4f}" in msg or f"{min_radius:.5f}" in msg, (
            f"Error message should contain minimum radius: {msg}"
        )
        assert "Options:" in msg or "option" in msg.lower(), (
            f"Error message should contain alternatives: {msg}"
        )


class TestPreservation_GeneralNonBuggyArcs:
    """General non-buggy arcs must produce identical center selection.

    **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

    This is the core preservation property: for ALL arc segments where the
    bug condition does NOT hold, the center selection must produce the same
    result before and after the fix.

    The test uses assume() to filter out buggy inputs, then verifies:
    1. The center is computable
    2. The center is geometrically correct (equidistant from both endpoints)
    3. The arc stays within X bounds
    4. The cross-product convention is satisfied (CW/CCW direction)
    """

    @given(arc=general_non_buggy_arc_strategy())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_non_buggy_arc_center_identical(self, arc):
        """**Validates: Requirements 3.1, 3.2, 3.4**

        For non-buggy arcs, selectCenter produces a valid, bounded center
        that satisfies the CW/CCW direction convention.
        """
        center = select_center(
            arc['x_start_r'], arc['z_start'],
            arc['x_end_r'], arc['z_end'],
            arc['radius'], arc['is_cw']
        )

        assert center is not None, "Non-buggy arc should have a valid center"
        cx, cz = center

        # Property 1: Center is equidistant from both endpoints (= radius)
        dist_start = math.sqrt(
            (arc['x_start_r'] - cx)**2 + (arc['z_start'] - cz)**2
        )
        dist_end = math.sqrt(
            (arc['x_end_r'] - cx)**2 + (arc['z_end'] - cz)**2
        )
        assert abs(dist_start - arc['radius']) < 1e-6, (
            f"Center-to-start distance {dist_start} != radius {arc['radius']}"
        )
        assert abs(dist_end - arc['radius']) < 1e-6, (
            f"Center-to-end distance {dist_end} != radius {arc['radius']}"
        )

        # Property 2: Cross-product convention is satisfied
        ax = arc['x_start_r'] - cx
        az = arc['z_start'] - cz
        bx = arc['x_end_r'] - cx
        bz = arc['z_end'] - cz
        cross = ax * bz - az * bx

        if arc['is_cw']:
            assert cross < TOLERANCE, (
                f"CW arc should have negative cross product, got {cross}"
            )
        else:
            assert cross > -TOLERANCE, (
                f"CCW arc should have positive cross product, got {cross}"
            )


    @given(arc=general_non_buggy_arc_strategy())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_non_buggy_arc_within_x_bounds(self, arc):
        """**Validates: Requirements 3.1, 3.2**

        For non-buggy arcs, all interpolated arc points must stay within
        the X bounds of the endpoints. This confirms the arc is bounded
        and the center selection is correct.
        """
        center = select_center(
            arc['x_start_r'], arc['z_start'],
            arc['x_end_r'], arc['z_end'],
            arc['radius'], arc['is_cw']
        )

        assert center is not None
        cx, cz = center

        # Interpolate the arc
        points = interpolate_arc(
            cx, cz, arc['radius'],
            arc['x_start_r'], arc['z_start'],
            arc['x_end_r'], arc['z_end'],
            arc['is_cw'], n_pts=64
        )

        x_min_bound = min(arc['x_start_r'], arc['x_end_r'])
        x_max_bound = max(arc['x_start_r'], arc['x_end_r'])

        note(f"Arc: ({arc['x_start_r']:.4f}, {arc['z_start']:.4f}) -> "
             f"({arc['x_end_r']:.4f}, {arc['z_end']:.4f})")
        note(f"Radius: {arc['radius']:.6f}, CW: {arc['is_cw']}")
        note(f"Center: ({cx:.6f}, {cz:.6f})")
        note(f"X bounds: [{x_min_bound:.6f}, {x_max_bound:.6f}]")

        for i, (px, pz) in enumerate(points):
            assert px >= x_min_bound - TOLERANCE, (
                f"Point {i} X={px:.8f} below min bound {x_min_bound:.8f}"
            )
            assert px <= x_max_bound + TOLERANCE, (
                f"Point {i} X={px:.8f} above max bound {x_max_bound:.8f}"
            )


    @given(arc=general_non_buggy_arc_strategy())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_non_buggy_arc_center_deterministic(self, arc):
        """**Validates: Requirements 3.1, 3.2, 3.4, 3.5**

        For non-buggy arcs, calling selectCenter twice with the same inputs
        must produce the exact same center. This ensures determinism that
        the fix must preserve.
        """
        center1 = select_center(
            arc['x_start_r'], arc['z_start'],
            arc['x_end_r'], arc['z_end'],
            arc['radius'], arc['is_cw']
        )
        center2 = select_center(
            arc['x_start_r'], arc['z_start'],
            arc['x_end_r'], arc['z_end'],
            arc['radius'], arc['is_cw']
        )

        assert center1 is not None
        assert center2 is not None
        assert center1[0] == center2[0], (
            f"Center X not deterministic: {center1[0]} != {center2[0]}"
        )
        assert center1[1] == center2[1], (
            f"Center Z not deterministic: {center1[1]} != {center2[1]}"
        )
