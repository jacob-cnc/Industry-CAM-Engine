"""Arc geometry helpers for Industry CAM Engine.

Provides functions for computing valid arc alternatives when user input
is geometrically invalid. Used by the segment list validation tooltip
to suggest fixes.

All computations use RADIUS for X (internal convention). Callers convert
from diameter as needed.

Why this module exists:
    When a user enters an arc with endpoints and radius that don't form a
    valid circle (radius < chord/2), they need actionable guidance — not
    just "invalid." This module computes what valid options exist:
    - What's the minimum radius for these endpoints?
    - If I keep this radius, what Z can I reach at this X?
    - If I keep this radius, what X can I reach at this Z?

These are the questions a machinist asks when their mental model doesn't
match the geometry constraints.
"""

import math
from typing import Optional, Tuple


def compute_arc_x_extremum(
    center_x: float, center_z: float, radius: float,
    x1_r: float, z1: float, x2_r: float, z2: float,
    is_cw: bool
) -> tuple:
    """Compute the minimum and maximum X values an arc reaches.

    The X extremum of a circular arc occurs either at the endpoints or
    where the tangent is vertical — i.e., at center_x ± radius if that
    angle is within the arc sweep.

    Algorithm:
        1. Compute start and end angles relative to center
        2. Compute sweep angle matching CW/CCW direction
        3. Check if angle 0 (rightmost point, x = center_x + radius)
           is within the sweep → if so, x_max = center_x + radius
        4. Check if angle π (leftmost point, x = center_x - radius)
           is within the sweep → if so, x_min = center_x - radius
        5. Otherwise, x_min and x_max are just the endpoint X values

    Handles edge cases: quarter circle, semicircle, shallow arc, full sweep.

    Args:
        center_x: Arc center X coordinate (radius units)
        center_z: Arc center Z coordinate (inches)
        radius: Arc radius (absolute value, inches)
        x1_r: Start point X (radius units)
        z1: Start point Z (inches)
        x2_r: End point X (radius units)
        z2: End point Z (inches)
        is_cw: True for clockwise arc, False for counter-clockwise

    Returns:
        (x_min, x_max) — the minimum and maximum X values the arc reaches.
    """
    # Compute start and end angles relative to center
    angle_start = math.atan2(z1 - center_z, x1_r - center_x)
    angle_end = math.atan2(z2 - center_z, x2_r - center_x)

    # Compute sweep angle matching CW/CCW direction
    diff = angle_end - angle_start
    if is_cw:
        # CW on screen = negative angular sweep
        if diff > 0:
            diff -= 2 * math.pi
    else:
        # CCW on screen = positive angular sweep
        if diff < 0:
            diff += 2 * math.pi

    # Start with endpoint X values as baseline
    x_min = min(x1_r, x2_r)
    x_max = max(x1_r, x2_r)

    def _angle_in_sweep(target_angle: float) -> bool:
        """Check if target_angle is within the arc sweep from angle_start.

        For CW arcs (negative sweep), checks if the target falls within
        the clockwise traversal. For CCW arcs (positive sweep), checks
        if the target falls within the counter-clockwise traversal.
        """
        rel = target_angle - angle_start
        if is_cw:
            # Normalize rel to (-2π, 0]
            while rel > 0:
                rel -= 2 * math.pi
            while rel < -2 * math.pi:
                rel += 2 * math.pi
            return diff <= rel <= 0
        else:
            # Normalize rel to [0, 2π)
            while rel < 0:
                rel += 2 * math.pi
            while rel > 2 * math.pi:
                rel -= 2 * math.pi
            return 0 <= rel <= diff

    # Check rightmost point: angle = 0, x = center_x + radius
    if _angle_in_sweep(0.0):
        x_max = max(x_max, center_x + radius)

    # Check leftmost point: angle = π, x = center_x - radius
    if _angle_in_sweep(math.pi):
        x_min = min(x_min, center_x - radius)

    return (x_min, x_max)


def is_arc_within_x_bounds(
    center_x: float, center_z: float, radius: float,
    x1_r: float, z1: float, x2_r: float, z2: float,
    is_cw: bool, tolerance: float = 1e-9
) -> bool:
    """Check whether an arc stays within the X bounds of its endpoints.

    Computes the arc X extremum via compute_arc_x_extremum() and returns
    whether the arc stays within [min(x1_r, x2_r), max(x1_r, x2_r)]
    within the given tolerance.

    Args:
        center_x: Arc center X coordinate (radius units)
        center_z: Arc center Z coordinate (inches)
        radius: Arc radius (absolute value, inches)
        x1_r: Start point X (radius units)
        z1: Start point Z (inches)
        x2_r: End point X (radius units)
        z2: End point Z (inches)
        is_cw: True for clockwise arc, False for counter-clockwise
        tolerance: Numerical tolerance for bounds comparison (default 1e-9)

    Returns:
        True if the arc stays within [min(x1_r, x2_r) - tolerance,
        max(x1_r, x2_r) + tolerance], False otherwise.
    """
    x_min_arc, x_max_arc = compute_arc_x_extremum(
        center_x, center_z, radius, x1_r, z1, x2_r, z2, is_cw
    )

    x_min_bound = min(x1_r, x2_r)
    x_max_bound = max(x1_r, x2_r)

    if x_min_arc < x_min_bound - tolerance:
        return False
    if x_max_arc > x_max_bound + tolerance:
        return False
    return True


def compute_min_radius(
    x_start_r: float, z_start: float,
    x_end_r: float, z_end: float,
) -> float:
    """Compute the minimum valid radius for an arc between two points.

    The minimum radius equals chord_length / 2 (a semicircle).

    Args:
        x_start_r: Start X in radius
        z_start: Start Z in inches
        x_end_r: End X in radius
        z_end: End Z in inches

    Returns:
        Minimum valid radius (inches). Any radius >= this value is valid.
    """
    dx = x_end_r - x_start_r
    dz = z_end - z_start
    chord = math.sqrt(dx * dx + dz * dz)
    return chord / 2.0


def _select_center(
    x1_r: float, z1: float, x2_r: float, z2: float,
    radius: float, is_cw: bool
) -> Optional[Tuple[float, float]]:
    """Select arc center using cross-product convention.

    Replicates the center selection logic used in finish_planner.py and
    program_tab.py. Uses cross product sign to pick the center that
    produces the correct CW/CCW direction on screen.

    Args:
        x1_r, z1: Start point (radius, inches)
        x2_r, z2: End point (radius, inches)
        radius: Arc radius (absolute value, must be >= chord/2)
        is_cw: True for CW on screen (+R), False for CCW (-R)

    Returns:
        (center_x, center_z) or None if no valid solution.
    """
    mx = (x1_r + x2_r) / 2.0
    mz = (z1 + z2) / 2.0

    dx = x2_r - x1_r
    dz = z2 - z1
    d = math.sqrt(dx * dx + dz * dz)

    if d < 1e-10:
        return None

    h_sq = radius * radius - (d / 2.0) ** 2
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


def compute_min_bounded_radius(
    x_start_r: float, z_start: float,
    x_end_r: float, z_end: float,
    is_cw: bool,
    tolerance: float = 1e-9,
) -> float:
    """Compute the minimum radius that produces a bounded arc.

    The geometric minimum radius is chord/2 (a semicircle), but that
    semicircle may exceed the X bounds [min(X_start, X_end), max(X_start, X_end)].
    This function finds the smallest radius >= chord/2 such that the
    resulting arc stays within the X bounds of the endpoints.

    Uses binary search: as radius increases from chord/2, the arc becomes
    shallower and eventually stays within bounds.

    Args:
        x_start_r: Start X in radius
        z_start: Start Z in inches
        x_end_r: End X in radius
        z_end: End Z in inches
        is_cw: True for CW arc, False for CCW arc
        tolerance: Numerical tolerance for bounds comparison

    Returns:
        Minimum radius (inches) that produces a bounded arc.
        This is >= chord/2 and may be larger if chord/2 would produce
        an out-of-bounds semicircle.
    """
    dx = x_end_r - x_start_r
    dz = z_end - z_start
    chord = math.sqrt(dx * dx + dz * dz)
    min_r = chord / 2.0

    if chord < 1e-10:
        return min_r

    # Check if chord/2 already produces a bounded arc
    center = _select_center(x_start_r, z_start, x_end_r, z_end, min_r, is_cw)
    if center is None:
        return min_r

    if is_arc_within_x_bounds(
        center[0], center[1], min_r,
        x_start_r, z_start, x_end_r, z_end,
        is_cw, tolerance
    ):
        return min_r

    # Binary search for the minimum bounded radius.
    # Upper bound: a very large radius produces a nearly-straight arc
    # that is always within bounds.
    lo = min_r
    hi = min_r * 100.0  # Start with 100x chord/2

    # Verify that hi is actually bounded; if not, keep doubling
    for _ in range(20):
        center_hi = _select_center(x_start_r, z_start, x_end_r, z_end, hi, is_cw)
        if center_hi is not None and is_arc_within_x_bounds(
            center_hi[0], center_hi[1], hi,
            x_start_r, z_start, x_end_r, z_end,
            is_cw, tolerance
        ):
            break
        hi *= 2.0
    else:
        # If we can't find a bounded radius, return the geometric minimum
        return min_r

    # Binary search between lo and hi
    for _ in range(64):  # 64 iterations gives ~1e-19 precision
        mid = (lo + hi) / 2.0
        center_mid = _select_center(x_start_r, z_start, x_end_r, z_end, mid, is_cw)
        if center_mid is not None and is_arc_within_x_bounds(
            center_mid[0], center_mid[1], mid,
            x_start_r, z_start, x_end_r, z_end,
            is_cw, tolerance
        ):
            hi = mid
        else:
            lo = mid

    return hi


def compute_tangent_radius(
    x_start_r: float, z_start: float,
    x_end_r: float, z_end: float,
    prev_dir_x: float, prev_dir_z: float,
) -> Optional[float]:
    """Compute the radius that makes an arc tangent to the previous segment.

    For tangency at the start point, the arc center must lie on the line
    perpendicular to the incoming direction (the normal at the start point).
    The center must also be equidistant from start and end (on the
    perpendicular bisector of the chord). The intersection of these two
    lines gives the unique center, and the distance from center to start
    is the tangent radius.

    Algorithm:
        1. Compute the normal to the previous segment direction at start
        2. Compute the perpendicular bisector of the chord (start → end)
        3. Intersect these two lines to find the center
        4. Radius = distance from center to start

    Args:
        x_start_r: Start X in radius (from previous segment endpoint)
        z_start: Start Z in inches
        x_end_r: End X in radius
        z_end: End Z in inches
        prev_dir_x: X component of previous segment direction (unit or unnormalized)
        prev_dir_z: Z component of previous segment direction

    Returns:
        The radius that produces a tangent arc, or None if:
        - Previous direction is zero-length
        - The end point is collinear with the incoming direction (no arc exists)
        - The two lines are parallel (degenerate geometry)
    """
    # Normalize previous direction
    dir_len = math.sqrt(prev_dir_x * prev_dir_x + prev_dir_z * prev_dir_z)
    if dir_len < 1e-10:
        return None

    # Normal to previous direction (perpendicular, pointing to one side)
    # The center lies on the line: start + t * normal
    norm_x = -prev_dir_z / dir_len
    norm_z = prev_dir_x / dir_len

    # Perpendicular bisector of chord (start → end)
    # Midpoint of chord
    mid_x = (x_start_r + x_end_r) / 2.0
    mid_z = (z_start + z_end) / 2.0

    # Chord direction
    chord_dx = x_end_r - x_start_r
    chord_dz = z_end - z_start
    chord_len = math.sqrt(chord_dx * chord_dx + chord_dz * chord_dz)
    if chord_len < 1e-10:
        return None

    # Perpendicular bisector direction (perpendicular to chord)
    bisect_dx = -chord_dz / chord_len
    bisect_dz = chord_dx / chord_len

    # Intersect: start + t * normal = mid + s * bisect
    # x_start_r + t * norm_x = mid_x + s * bisect_dx
    # z_start + t * norm_z = mid_z + s * bisect_dz
    #
    # Solve for t:
    # t * norm_x - s * bisect_dx = mid_x - x_start_r
    # t * norm_z - s * bisect_dz = mid_z - z_start
    #
    # Using Cramer's rule:
    det = norm_x * (-bisect_dz) - norm_z * (-bisect_dx)
    if abs(det) < 1e-12:
        # Lines are parallel — end point is collinear with incoming direction
        return None

    rhs_x = mid_x - x_start_r
    rhs_z = mid_z - z_start

    t = (rhs_x * (-bisect_dz) - rhs_z * (-bisect_dx)) / det

    # Center coordinates
    cx = x_start_r + t * norm_x
    cz = z_start + t * norm_z

    # Radius = distance from center to start
    dx = cx - x_start_r
    dz = cz - z_start
    radius = math.sqrt(dx * dx + dz * dz)

    if radius < 1e-10:
        return None

    return radius


def compute_tangent_z(
    x_start_r: float, z_start: float,
    x_end_r: float, radius: float,
    exit_horizontal: bool = True,
) -> Optional[float]:
    """Compute the Z endpoint where the arc exits tangent to a standard direction.

    For a lathe, the standard exit directions are:
    - Horizontal (along Z): the arc exits traveling in ±Z (tangent to OD)
    - Vertical (along X): the arc exits traveling in ±X (tangent to face)

    When exit_horizontal=True (default), the arc exits tangent to the Z axis.
    This means the tangent at the endpoint is horizontal, which means the
    endpoint is at the top or bottom of the circle (directly above/below center).
    So the center must be at x = x_end_r, and the endpoint is a quadrant point.

    Given the start point and radius, with the constraint that the endpoint
    has x = x_end_r and the center has x = x_end_r, we find the Z.

    Args:
        x_start_r: Start X in radius
        z_start: Start Z in inches
        x_end_r: End X in radius
        radius: Arc radius (absolute value)
        exit_horizontal: If True, arc exits along Z (horizontal tangent at end).
                        If False, arc exits along X (vertical tangent at end).

    Returns:
        Z coordinate of the tangent endpoint, or None if unreachable.
    """
    if exit_horizontal:
        # Arc exits horizontal → endpoint is a quadrant point where tangent is horizontal
        # This means the center is directly above or below the endpoint: center_x = x_end_r
        # The center must also be at distance R from the start:
        # (x_end_r - x_start_r)² + (cz - z_start)² = R²
        dx = x_end_r - x_start_r
        dz_sq = radius * radius - dx * dx
        if dz_sq < 0:
            return None

        dz = math.sqrt(dz_sq)
        # Center is at (x_end_r, z_start ± dz)
        # Endpoint is at (x_end_r, center_z + R) or (x_end_r, center_z - R)
        # Two candidate centers and two candidate endpoints per center.
        # For a standard lathe arc going from face into part (negative Z):
        # Center below start: cz = z_start - dz, endpoint = cz + R or cz - R
        cz_below = z_start - dz
        z_end_1 = cz_below + radius  # This would be above start (unlikely for lathe)
        z_end_2 = cz_below - radius  # This goes further negative (into part)

        # Center above start: cz = z_start + dz
        cz_above = z_start + dz
        z_end_3 = cz_above + radius
        z_end_4 = cz_above - radius

        # For lathe work, we want the Z that's most negative (into the part)
        # and different from z_start
        candidates = []
        for z in [z_end_1, z_end_2, z_end_3, z_end_4]:
            if abs(z - z_start) > 1e-9:
                candidates.append(z)

        if not candidates:
            return None

        # For lathe work, prefer the Z that goes into the part (more negative)
        # When distances are equal, pick the more negative Z
        candidates.sort(key=lambda z: (abs(z - z_start), z))
        return candidates[0]
    else:
        # Arc exits vertical → endpoint is where tangent is vertical
        # This means center_z = z_end (center directly beside endpoint)
        # Center at distance R from start: (cx - x_start_r)² + (z_end - z_start)² = R²
        # And endpoint at (center_x ± R, z_end)
        # Since we don't know z_end yet (that's what we're computing), this case
        # requires knowing the endpoint X. For the "X blank" case, use compute_tangent_x instead.
        return None


def compute_tangent_x(
    x_start_r: float, z_start: float,
    z_end: float, radius: float,
) -> Optional[float]:
    """Compute the X endpoint where the arc exits tangent to a vertical direction.

    For a lathe, exiting tangent to X (vertical tangent at endpoint) means
    the arc arrives at the endpoint traveling along X (toward/away from centerline).
    This means the center is directly beside the endpoint: center_z = z_end.

    Given the start point, end Z, and radius, with the constraint that
    center_z = z_end, we find the endpoint X.

    Args:
        x_start_r: Start X in radius
        z_start: Start Z in inches
        z_end: End Z in inches
        radius: Arc radius (absolute value)

    Returns:
        X coordinate (radius) of the tangent endpoint, or None if unreachable.
    """
    # Center_z = z_end (constraint for vertical tangent at endpoint)
    # Center at distance R from start: (cx - x_start_r)² + (z_end - z_start)² = R²
    dz = z_end - z_start
    dx_sq = radius * radius - dz * dz
    if dx_sq < 0:
        return None

    dx = math.sqrt(dx_sq)
    # Center candidates: cx = x_start_r + dx or cx = x_start_r - dx
    cx_right = x_start_r + dx
    cx_left = x_start_r - dx

    # Endpoint is at (center_x ± R, z_end)
    # For vertical tangent: endpoint.x = center_x + R or center_x - R
    candidates = []

    # From center_right
    x_end_1 = cx_right + radius
    x_end_2 = cx_right - radius
    # From center_left
    x_end_3 = cx_left + radius
    x_end_4 = cx_left - radius

    for x in [x_end_1, x_end_2, x_end_3, x_end_4]:
        if abs(x - x_start_r) > 1e-9 and x >= 0:
            candidates.append(x)

    if not candidates:
        return None

    # Return the candidate closest to start (most natural arc)
    candidates.sort(key=lambda x: abs(x - x_start_r))
    return candidates[0]


def compute_fillet_quadrant_radius(
    seg1_start_x_r: float, seg1_start_z: float,
    junction_x_r: float, junction_z: float,
    seg2_end_x_r: float, seg2_end_z: float,
) -> Optional[float]:
    """Compute the maximum fillet radius for a corner break between two segments.

    For a fillet between two straight segments meeting at a junction point,
    the maximum radius is limited by the shorter segment length and the
    corner angle. The fillet "backs off" from the corner by R * tan(θ/2)
    along each segment, where θ is the angle between the segments.

    This computes the radius that just fits — the arc is tangent to both
    segments and the setback doesn't exceed either segment's length.

    Args:
        seg1_start_x_r: Start X of segment 1 (radius units)
        seg1_start_z: Start Z of segment 1
        junction_x_r: Junction point X (radius units) — end of seg1, start of seg2
        junction_z: Junction point Z
        seg2_end_x_r: End X of segment 2 (radius units)
        seg2_end_z: End Z of segment 2

    Returns:
        Maximum fillet radius in inches, or None if:
        - Either segment has zero length
        - The segments are collinear (no corner to fillet)
        - The geometry is degenerate
    """
    # Direction vectors of each segment at the junction
    # Seg1 arrives at junction: direction = junction - seg1_start
    d1_x = junction_x_r - seg1_start_x_r
    d1_z = junction_z - seg1_start_z
    len1 = math.sqrt(d1_x * d1_x + d1_z * d1_z)

    # Seg2 departs from junction: direction = seg2_end - junction
    d2_x = seg2_end_x_r - junction_x_r
    d2_z = seg2_end_z - junction_z
    len2 = math.sqrt(d2_x * d2_x + d2_z * d2_z)

    if len1 < 1e-10 or len2 < 1e-10:
        return None

    # Normalize
    d1_x /= len1
    d1_z /= len1
    d2_x /= len2
    d2_z /= len2

    # Angle between segments: cos(θ) = -d1 · d2
    # (negative because d1 arrives and d2 departs — the angle is the exterior angle)
    cos_theta = -(d1_x * d2_x + d1_z * d2_z)

    # Clamp for numerical safety
    cos_theta = max(-1.0, min(1.0, cos_theta))

    # If segments are nearly collinear (θ ≈ 180° → cos_theta ≈ -1), no fillet needed
    if cos_theta < -0.9999:
        return None

    # If segments are nearly parallel same-direction (θ ≈ 0° → cos_theta ≈ 1), no fillet
    if cos_theta > 0.9999:
        return None

    # Half-angle: θ/2
    theta = math.acos(cos_theta)
    half_angle = theta / 2.0

    # Setback distance = R * tan(half_angle)
    # But we need tan(half_angle) to compute max R from segment lengths
    tan_half = math.tan(half_angle)

    if tan_half < 1e-10:
        return None

    # Maximum R limited by each segment's length:
    # setback = R * tan(half_angle) <= segment_length
    # R <= segment_length / tan(half_angle)
    max_r_from_seg1 = len1 / tan_half
    max_r_from_seg2 = len2 / tan_half

    # The fillet radius is limited by the shorter constraint
    max_r = min(max_r_from_seg1, max_r_from_seg2)

    if max_r < 1e-10:
        return None

    return max_r


def interpolate_quadrant_arc(
    x_start_r: float, z_start: float,
    x_end_r: float, z_end: float,
    num_points: int = 32,
) -> list:
    """Interpolate a tangent-bounded quadrant arc (quarter ellipse).

    Generates points along a quarter ellipse inscribed in the bounding box
    defined by the start and end points. The curve is tangent to the
    horizontal at one endpoint and tangent to the vertical at the other
    (quadrant points of the ellipse).

    The ellipse has semi-axes:
        a = |z_end - z_start| (along Z)
        b = |x_end_r - x_start_r| (along X)

    The center of the ellipse is at (x_end_r, z_start) or (x_start_r, z_end)
    depending on the quadrant. The curve goes from start to end along one
    quarter of this ellipse.

    Args:
        x_start_r: Start X in radius units
        z_start: Start Z in inches
        x_end_r: End X in radius units
        z_end: End Z in inches
        num_points: Number of interpolation points (default 32)

    Returns:
        List of (x_r, z) tuples along the quarter ellipse from start to end.
        First point is (x_start_r, z_start), last is (x_end_r, z_end).
    """
    dx = x_end_r - x_start_r
    dz = z_end - z_start

    if abs(dx) < 1e-10 or abs(dz) < 1e-10:
        # Degenerate — just return a straight line
        return [(x_start_r, z_start), (x_end_r, z_end)]

    # Semi-axes of the ellipse
    b = abs(dx)  # semi-axis along X
    a = abs(dz)  # semi-axis along Z

    # Determine which quadrant we're traversing based on direction of travel.
    # The ellipse center is placed so that:
    # - Start point is a quadrant point (horizontal tangent)
    # - End point is a quadrant point (vertical tangent)
    #
    # Start has horizontal tangent → start is at the top or bottom of the ellipse
    # (where dx/dt = 0 at t=0 or t=π). This means:
    #   center_x = x_start_r (same X as start, offset in Z)
    #   center_z = z_end (same Z as end, offset in X)
    #
    # So center = (x_start_r, z_end) and parametrize as:
    #   x(t) = center_x + b * sin(t)  (or -sin depending on direction)
    #   z(t) = center_z + a * cos(t)  (or -cos depending on direction)
    #
    # At t=0: x = center_x = x_start_r, z = center_z + a → should equal z_start
    # So: center_z + a = z_start → center_z = z_start - a = z_start - |dz|
    # But center_z should = z_end. Check: z_start - |dz| = z_end when dz < 0 (z_end < z_start)
    # That works for one case. Let's handle all quadrants.

    # Place center at (x_start_r, z_end)
    cx = x_start_r
    cz = z_end

    # Determine sign multipliers for the parametric curve
    # x(t) = cx + sign_x * b * sin(t)
    # z(t) = cz + sign_z * a * cos(t)
    # At t=0: x(0) = cx = x_start_r ✓, z(0) = cz + sign_z * a = z_start
    # → sign_z * a = z_start - cz = z_start - z_end = -dz
    # → sign_z = -dz / a = -dz / |dz| = -sign(dz)
    sign_z = -1.0 if dz > 0 else 1.0

    # At t=π/2: x(π/2) = cx + sign_x * b = x_end_r
    # → sign_x * b = x_end_r - cx = x_end_r - x_start_r = dx
    # → sign_x = dx / b = dx / |dx| = sign(dx)
    sign_x = 1.0 if dx > 0 else -1.0

    points = []
    for i in range(num_points + 1):
        t = (math.pi / 2.0) * i / num_points
        x = cx + sign_x * b * math.sin(t)
        z = cz + sign_z * a * math.cos(t)
        points.append((x, z))

    return points


def compute_max_z_for_radius(
    x_start_r: float, z_start: float,
    x_end_r: float, radius: float,
) -> Optional[float]:
    """Compute the Z endpoint for a tangent-preserving arc at a given X.

    Assumes the arc starts tangent to the face (horizontal at the start point),
    meaning the center is directly below the start at (x_start, z_start - R).
    This is the standard case for arcs beginning at the part face.

    Given that constraint, computes the Z where the circle intersects the
    vertical line at x_end_r.

    This answers: "If I want R=0.25 starting tangent at Z=0, and ending at
    X=0.125r, what Z does the arc reach?"

    Args:
        x_start_r: Start X in radius
        z_start: Start Z in inches
        x_end_r: End X in radius
        radius: Arc radius in inches (absolute value)

    Returns:
        Z endpoint for the tangent-preserving arc, or None if X distance
        exceeds the radius (endpoint unreachable from this center).
    """
    # Center is directly below start for tangent-at-face constraint
    cx = x_start_r
    cz = z_start - radius

    # Find where the circle (centered at cx, cz with radius R) intersects x = x_end_r
    # Circle equation: (x - cx)² + (z - cz)² = R²
    # At x = x_end_r: (x_end_r - cx)² + (z - cz)² = R²
    # (z - cz)² = R² - (x_end_r - cx)²
    dx = x_end_r - cx
    dz_sq = radius * radius - dx * dx
    if dz_sq < 0:
        # X distance exceeds radius — endpoint unreachable
        return None

    # Two solutions: z = cz ± sqrt(dz_sq)
    # We want the one below the start (more negative Z)
    dz = math.sqrt(dz_sq)
    z_lower = cz - dz
    z_upper = cz + dz

    # Return the solution that's below z_start (the arc goes downward)
    # z_upper = cz + dz = (z_start - R) + dz — this is the start point (or above)
    # z_lower = cz - dz = (z_start - R) - dz — this is below
    return z_lower


def compute_max_x_for_radius(
    x_start_r: float, z_start: float,
    z_end: float, radius: float,
) -> Optional[float]:
    """Compute the maximum X (radius) reachable at a given Z with a given radius.

    Given a start point, an end Z, and a radius, finds the X value where
    the chord equals 2*radius (the maximum reach — a semicircle).

    This answers: "If I want R=0.25 and end at Z=-0.5, what's the max X I can reach?"

    Args:
        x_start_r: Start X in radius
        z_start: Start Z in inches
        z_end: End Z in inches
        radius: Arc radius in inches

    Returns:
        Maximum X (radius) reachable, or None if Z distance alone exceeds diameter.
    """
    dz = z_end - z_start
    max_chord = 2.0 * radius
    dx_sq = max_chord * max_chord - dz * dz
    if dx_sq < 0:
        # Z distance alone exceeds the diameter — no valid X exists
        return None
    max_dx = math.sqrt(dx_sq)
    # X increases (OD turning: arc bulges outward)
    return x_start_r + max_dx


def format_validation_message(
    x_start_dia: float, z_start: float,
    x_end_dia: float, z_end: float,
    radius: float,
    is_cw: Optional[bool] = None,
) -> str:
    """Format a detailed validation error message with alternatives.

    Called when abs(radius) < chord/2. Computes and presents:
    1. The minimum radius needed for these endpoints
    2. The maximum Z reachable at this X with this radius
    3. The maximum X reachable at this Z with this radius

    When is_cw is provided, the function also checks whether the minimum
    radius (chord/2) would produce an out-of-bounds arc. If so, it suggests
    a larger bounded minimum radius instead.

    All user-facing values are in DIAMETER for X, INCHES for Z and R.

    Args:
        x_start_dia: Start X in diameter
        z_start: Start Z in inches
        x_end_dia: End X in diameter
        z_end: End Z in inches
        radius: User's entered radius (absolute value)
        is_cw: Arc direction (True=CW, False=CCW). When provided,
               enables bounds-aware radius suggestions.

    Returns:
        Multi-line string suitable for a tooltip.
    """
    # Convert to radius for computation
    x_start_r = x_start_dia / 2.0
    x_end_r = x_end_dia / 2.0
    r = abs(radius)

    # Chord info
    dx = x_end_r - x_start_r
    dz = z_end - z_start
    chord = math.sqrt(dx * dx + dz * dz)
    min_r = chord / 2.0

    lines = []
    lines.append(f"Radius {r:.4f} is too small for these endpoints.")
    lines.append(f"")
    lines.append(f"Chord between points: {chord:.4f}")
    lines.append(f"Minimum radius: {min_r:.4f}")
    lines.append(f"")

    # Determine the bounded minimum radius if direction is known
    bounded_min_r = min_r
    if is_cw is not None:
        bounded_min_r = compute_min_bounded_radius(
            x_start_r, z_start, x_end_r, z_end, is_cw
        )

    # Alternative 1: increase radius
    lines.append(f"Options:")
    if bounded_min_r > min_r + 1e-9:
        # chord/2 would produce an out-of-bounds arc; suggest bounded minimum
        lines.append(f"  • Increase R to at least {bounded_min_r:.4f} (bounded)")
    else:
        lines.append(f"  • Increase R to at least {min_r:.4f}")

    # Alternative 2: adjust Z (keep X and R)
    max_z = compute_max_z_for_radius(x_start_r, z_start, x_end_r, r)
    if max_z is not None and abs(max_z - z_start) > 1e-6:
        lines.append(f"  • Keep R={r:.4f}, X={x_end_dia:.4f}: max Z = {max_z:.4f}")

    # Alternative 3: adjust X (keep Z and R)
    max_x_r = compute_max_x_for_radius(x_start_r, z_start, z_end, r)
    if max_x_r is not None and max_x_r > x_start_r + 1e-6:
        max_x_dia = max_x_r * 2.0
        lines.append(f"  • Keep R={r:.4f}, Z={z_end:.4f}: max X = {max_x_dia:.4f} dia")

    return "\n".join(lines)
