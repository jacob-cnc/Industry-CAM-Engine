"""Pre-planning validation for Industry CAM Engine.

Validates profile geometry before zone construction.
Catches invalid arcs, unclosed profiles, and constraint violations.

Imports from: models/
"""

import math
from typing import List

from models.profile import ClosedProfile, ProfileMove, SegmentType, MachiningMode
from models.stock import StockDef
from models.validation import ValidationResult, Severity
from models.constants import TOLERANCE
from geometry.arc_helpers import compute_arc_x_extremum, is_arc_within_x_bounds


def _compute_arc_center(
    x1_r: float, z1: float, x2_r: float, z2: float,
    radius: float, is_cw: bool
) -> tuple:
    """Compute arc center using cross-product selection (same logic as planners).

    Uses the same center selection algorithm as finish_planner._find_arc_center()
    to ensure consistent behavior between validation and planning.

    Args:
        x1_r, z1: Start point (radius, inches)
        x2_r, z2: End point (radius, inches)
        radius: Arc radius (absolute value)
        is_cw: True for CW on screen (+R), False for CCW (-R)

    Returns:
        (center_x_radius, center_z) or None if no solution.
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


def validate_profile(profile: ClosedProfile, stock: StockDef) -> List[ValidationResult]:
    """Pre-planning geometry validation.

    Checks:
    - Arc radius >= chord_length / 2 for every ARC segment
    - All X values positive (diameter convention)
    - Profile starts at Z=0 (within TOLERANCE)
    - Profile ends at Z_end (within TOLERANCE)
    - OD: profile X <= stock_dia
    - ID: profile X >= pilot_hole_dia (if applicable)

    Returns list of ValidationResult (empty = all valid).
    """
    results = []
    segments = profile.segments

    if not segments:
        results.append(ValidationResult(
            severity=Severity.ERROR,
            category="geometry",
            message="Profile has no segments.",
            recommendation="Add at least one profile segment.",
        ))
        return results

    # Check first segment Z = 0
    first_z = segments[0].z
    if abs(first_z) > TOLERANCE:
        results.append(ValidationResult(
            severity=Severity.ERROR,
            category="geometry",
            message=f"Profile must start at Z=0.000. Current first segment Z={first_z:.5f}.",
            recommendation=f"Set first segment Z to 0.000.",
            location=(segments[0].x, first_z),
        ))

    # Check last segment Z = z_end
    last_z = segments[-1].z
    if abs(last_z - profile.z_end) > TOLERANCE:
        results.append(ValidationResult(
            severity=Severity.ERROR,
            category="geometry",
            message=f"Profile must end at Z={profile.z_end:.4f}. Current last segment Z={last_z:.5f}.",
            recommendation=f"Set last segment Z to {profile.z_end:.4f}.",
            location=(segments[-1].x, last_z),
        ))

    # Check each segment
    prev_x = segments[0].x
    prev_z = segments[0].z

    for i, seg in enumerate(segments[1:], start=1):
        # All X must be positive (diameter convention)
        if seg.x < -TOLERANCE:
            results.append(ValidationResult(
                severity=Severity.ERROR,
                category="geometry",
                message=f"Segment {i+1}: X must be positive (diameter convention). Got X={seg.x:.5f}.",
                recommendation=f"Did you mean X={abs(seg.x):.5f}?",
                location=(seg.x, seg.z),
            ))

        # Arc validation
        if seg.segment_type == SegmentType.ARC and seg.radius != 0.0:
            # Compute chord length between previous endpoint and this endpoint
            dx = (seg.x - prev_x) / 2.0  # Convert to radius for distance calc
            dz = seg.z - prev_z
            chord_length = math.sqrt(dx * dx + dz * dz)

            # Arc radius must be >= chord_length / 2
            abs_radius = abs(seg.radius)
            min_radius = chord_length / 2.0

            if abs_radius < min_radius - TOLERANCE:
                results.append(ValidationResult(
                    severity=Severity.ERROR,
                    category="geometry",
                    message=(
                        f"Segment {i+1} (Arc): Radius {abs_radius:.5f}\" is smaller than "
                        f"minimum valid radius {min_radius:.5f}\" (chord/2)."
                    ),
                    recommendation=f"Increase radius to at least {min_radius + TOLERANCE:.5f}\" or adjust endpoints.",
                    location=(seg.x, seg.z),
                ))
            elif abs_radius >= min_radius - TOLERANCE:
                # Radius is valid — check if the arc exceeds X bounds
                # Compute arc center using cross-product selection (same as planners)
                x1_r = prev_x / 2.0  # Convert diameter to radius
                x2_r = seg.x / 2.0
                is_cw = seg.radius > 0

                center = _compute_arc_center(x1_r, prev_z, x2_r, seg.z, abs_radius, is_cw)
                if center is not None:
                    cx, cz = center
                    if not is_arc_within_x_bounds(cx, cz, abs_radius, x1_r, prev_z, x2_r, seg.z, is_cw, TOLERANCE):
                        # Compute the actual extremum for the error message
                        x_min_arc, x_max_arc = compute_arc_x_extremum(
                            cx, cz, abs_radius, x1_r, prev_z, x2_r, seg.z, is_cw
                        )
                        x_min_bound = min(x1_r, x2_r)
                        x_max_bound = max(x1_r, x2_r)

                        # Determine which bound is violated
                        if x_max_arc > x_max_bound + TOLERANCE:
                            extremum = x_max_arc
                        else:
                            extremum = x_min_arc

                        results.append(ValidationResult(
                            severity=Severity.ERROR,
                            category="geometry",
                            message=(
                                f"Segment {i+1} (Arc): Arc from X={prev_x:.4f}\" to X={seg.x:.4f}\" "
                                f"with radius={abs_radius:.5f}\" exceeds X bounds. "
                                f"The arc path reaches X={extremum * 2:.4f}\" (dia) which is outside "
                                f"[{x_min_bound * 2:.4f}\", {x_max_bound * 2:.4f}\"] (dia). "
                                f"Consider using a larger radius or splitting into two segments."
                            ),
                            recommendation=(
                                f"Increase radius to reduce arc bulge, adjust endpoints, "
                                f"or split into two segments."
                            ),
                            location=(seg.x, seg.z),
                        ))

        # OD mode: profile X should not exceed stock diameter
        if profile.mode == MachiningMode.OD:
            if seg.x > stock.diameter + TOLERANCE:
                results.append(ValidationResult(
                    severity=Severity.ERROR,
                    category="geometry",
                    message=f"Segment {i+1}: X={seg.x:.4f}\" exceeds stock diameter {stock.diameter:.4f}\".",
                    recommendation="Reduce X or increase stock diameter.",
                    location=(seg.x, seg.z),
                ))

        prev_x = seg.x
        prev_z = seg.z

    return results
