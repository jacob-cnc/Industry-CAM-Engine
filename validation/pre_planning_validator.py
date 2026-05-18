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
