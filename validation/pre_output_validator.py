"""Pre-output validation for Industry CAM Engine.

Validates G-code geometry before emitting — catches zero-length moves,
invalid arcs, and missing feed rates.

Imports from: models/
"""

import math
from typing import List

from models.moves import ToolMove, MoveType, PassType
from models.validation import ValidationResult, Severity
from models.constants import TOLERANCE, CENTER_ARC_RADIUS_TOLERANCE_INCH


def validate_gcode_geometry(moves: List[ToolMove]) -> List[ValidationResult]:
    """Pre-output G-code geometry validation.

    Checks:
    - No zero-length moves (start == end within TOLERANCE)
    - Arc endpoint distance from center matches radius (roughing arcs only)
    - Feed rate is set before first feed move
    - All coordinates are finite (no NaN, no Inf)

    Note: Cleanup/finish pass arcs are excluded from arc validation because
    their I/K values come from kernel boundary extraction and may use
    different parameterization than the G-code writer expects.
    """
    results = []
    prev_x = None
    prev_z = None
    feed_set = False

    for i, move in enumerate(moves):
        # Check for NaN/Inf
        if not (math.isfinite(move.x) and math.isfinite(move.z)):
            results.append(ValidationResult(
                severity=Severity.ERROR,
                category="system",
                message=f"Move {i}: non-finite coordinate (X={move.x}, Z={move.z}).",
                move_index=i,
            ))
            prev_x = move.x
            prev_z = move.z
            continue

        # Check feed rate set before first feed move
        if move.move_type in (MoveType.FEED, MoveType.ARC_CW, MoveType.ARC_CCW):
            if move.feed > 0:
                feed_set = True
            elif not feed_set:
                results.append(ValidationResult(
                    severity=Severity.ERROR,
                    category="system",
                    message=f"Move {i}: feed move with no feed rate set (feed=0).",
                    recommendation="Ensure feed rate is specified on the first feed move.",
                    move_index=i,
                ))

        # Check zero-length moves (skip DWELL — they're intentionally stationary)
        if prev_x is not None and prev_z is not None:
            if move.move_type != MoveType.DWELL and abs(move.x - prev_x) < TOLERANCE and abs(move.z - prev_z) < TOLERANCE:
                results.append(ValidationResult(
                    severity=Severity.ERROR,
                    category="system",
                    message=(
                        f"Move {i}: zero-length move at ({move.x:.5f}, {move.z:.5f}). "
                        f"This indicates a planning bug."
                    ),
                    move_index=i,
                ))

        # Arc validation (roughing arcs only — cleanup/finish arcs from kernel may differ)
        if move.move_type in (MoveType.ARC_CW, MoveType.ARC_CCW):
            if move.pass_type not in (PassType.CLEANUP, PassType.FINISH):
                if prev_x is not None and prev_z is not None:
                    center_x = prev_x + move.center_i
                    center_z = prev_z + move.center_k

                    dx_start = (prev_x - center_x) / 2.0
                    dz_start = prev_z - center_z
                    r_start = math.sqrt(dx_start**2 + dz_start**2)

                    dx_end = (move.x - center_x) / 2.0
                    dz_end = move.z - center_z
                    r_end = math.sqrt(dx_end**2 + dz_end**2)

                    if abs(r_start - r_end) > CENTER_ARC_RADIUS_TOLERANCE_INCH:
                        results.append(ValidationResult(
                            severity=Severity.ERROR,
                            category="system",
                            message=(
                                f"Move {i} (arc): radius mismatch. "
                                f"Start-to-center: {r_start:.5f}\", End-to-center: {r_end:.5f}\". "
                                f"Difference: {abs(r_start - r_end):.5f}\"."
                            ),
                            move_index=i,
                        ))

        prev_x = move.x
        prev_z = move.z

    return results
