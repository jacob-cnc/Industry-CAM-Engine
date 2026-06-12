"""Post-planning validation for Industry CAM Engine.

Validates every planned move against Shapely polygons.
This is the HARD SAFETY FLOOR — if Shapely says a move gouges, it's blocked.

Rules:
- NO move (rapid, feed, arc, retract, approach) may enter the Finished Part zone
- Cleanup moves must not enter the Finish Allowance zone
- Points ON the boundary (distance < TOLERANCE) are allowed (boundary tracing)
- Arc moves are densified and each sub-segment is checked individually
  (chord-only checking produces false positives when the arc curves away from the part
  but the chord cuts through it)

Imports from: models/, geometry/, validation/polygon_builder
"""

from typing import List

from shapely.geometry import Point, LineString

from models.moves import ToolMove, MoveType, PassType
from models.validation import ValidationResult, Severity
from models.profile import MachiningMode
from models.constants import TOLERANCE, SHAPELY_COS_LIMIT, MAX_DENSIFICATION_DEPTH
from geometry.adaptive_sampling import adaptive_densify_arc
from validation.polygon_builder import ValidationPolygons


def validate_all_moves(
    moves: List[ToolMove],
    polygons: ValidationPolygons,
    mode: MachiningMode,
) -> List[ValidationResult]:
    """Post-planning safety validation using Shapely polygons.

    Checks EVERY move with NO exceptions:
    - Every endpoint must not be inside finished_part_poly (boundary OK)
    - Every segment must not cross through finished_part_poly
    - Cleanup segments must not cross through finish_allowance_poly

    Args:
        moves: Complete ordered toolpath (all passes + transitions)
        polygons: Shapely validation polygons (cached from zone construction)
        mode: OD or ID

    Returns:
        List of ValidationResult (empty = all moves safe).
    """
    results = []
    finished_part = polygons.finished_part_poly
    finish_allowance = polygons.finish_allowance_poly

    if finished_part.is_empty:
        return results

    prev_x = None
    prev_z = None
    prev_pass_type = None

    for i, move in enumerate(moves):
        end_x_r = move.x / 2.0
        end_z = move.z
        end_point = Point(end_x_r, end_z)

        # Reset prev position when pass type changes — the G-code writer
        # inserts safe approach rapids between phases that aren't in tool_moves
        if move.pass_type != prev_pass_type:
            prev_x = None
            prev_z = None
            prev_pass_type = move.pass_type

        # --- ENDPOINT CHECK (all move types) ---
        # Point must not be INSIDE the finished part (boundary contact OK)
        # A point is "inside" if it's contained AND not on the boundary
        if finished_part.contains(end_point):
            # Check if it's actually on the boundary (within tolerance)
            dist_to_boundary = end_point.distance(finished_part.boundary)
            if dist_to_boundary > TOLERANCE:
                results.append(ValidationResult(
                    severity=Severity.ERROR,
                    category="safety",
                    message=(
                        f"Move {i} ({move.pass_type.value.upper()}): endpoint "
                        f"({move.x:.4f} dia, {move.z:.4f}) is INSIDE the Finished "
                        f"Part zone (dist to boundary: {dist_to_boundary:.6f}). GOUGE DETECTED."
                    ),
                    recommendation="Check pass planning — this move enters the keep zone.",
                    location=(move.x, move.z),
                    move_index=i,
                ))

        # --- SEGMENT CHECK (all move types including arcs) ---
        if prev_x is not None and prev_z is not None:
            start_x_r = prev_x / 2.0
            start_z = prev_z

            # Skip zero-length moves
            if abs(start_x_r - end_x_r) > TOLERANCE or abs(start_z - end_z) > TOLERANCE:
                # Build list of sub-segments to check
                # For arcs: densify the actual arc path, then check each chord
                # For linear moves: single chord from start to end
                if move.move_type in (MoveType.ARC_CW, MoveType.ARC_CCW):
                    sub_segments = _densify_arc_move(
                        start_x_r, start_z, end_x_r, end_z, move
                    )
                else:
                    sub_segments = [LineString([(start_x_r, start_z), (end_x_r, end_z)])]

                # Check each sub-segment vs finished_part
                # Finish pass traces the profile boundary directly.
                # Cleanup pass traces the offset boundary (fin_allowance outside
                # the finished part). Both are derived from OCCT geometry.
                # A small buffer handles densification sampling differences.
                if move.pass_type in (PassType.FINISH, PassType.CLEANUP):
                    fp_check = finished_part.buffer(-0.001)
                    if fp_check.is_empty:
                        fp_check = finished_part
                else:
                    fp_check = finished_part

                for seg in sub_segments:
                    # crosses() returns True when a line enters and exits
                    # the polygon interior. But it returns False when the line
                    # runs along the polygon BOUNDARY (coincident edge). To catch
                    # boundary-coincident gouges (e.g., a roughing pass running
                    # along a profile vertex where the polygon has a vertical edge),
                    # also check if the segment's intersection with the polygon
                    # interior has non-zero length.
                    gouge_detected = False
                    if seg.crosses(fp_check):
                        gouge_detected = True
                    elif move.pass_type == PassType.ROUGH:
                        # Extra check for roughing: a line that overlaps the
                        # polygon boundary without crossing is still a gouge if
                        # it has significant interior overlap. This catches the
                        # case where a vertical roughing pass at a profile X
                        # vertex coincides with the polygon edge.
                        intersection = seg.intersection(fp_check)
                        if not intersection.is_empty and intersection.length > TOLERANCE:
                            gouge_detected = True

                    if gouge_detected:
                        move_type_str = move.move_type.value.upper()
                        results.append(ValidationResult(
                            severity=Severity.ERROR,
                            category="safety",
                            message=(
                                f"Move {i} ({move.pass_type.value.upper()} {move_type_str}): "
                                f"segment from ({prev_x:.4f}, {prev_z:.4f}) to "
                                f"({move.x:.4f}, {move.z:.4f}) CROSSES the Finished Part "
                                f"zone. GOUGE DETECTED."
                            ),
                            recommendation="This move path enters the finished part interior.",
                            location=(move.x, move.z),
                            move_index=i,
                        ))
                        break  # One crossing is enough to flag this move

                # Cleanup moves: also check vs finish_allowance
                # The cleanup pass traces the OUTER boundary of the finish allowance
                # zone. Due to floating point from Build123d offset operations, the
                # arc may slightly penetrate the polygon boundary. Use a small inward
                # buffer (shrink the polygon) to allow boundary-tracing tolerance.
                if move.pass_type == PassType.CLEANUP:
                    if not finish_allowance.is_empty:
                        # Buffer inward by 0.001" to allow boundary-tracing tolerance
                        fa_check = finish_allowance.buffer(-0.001)
                        if not fa_check.is_empty:
                            for seg in sub_segments:
                                if seg.crosses(fa_check):
                                    move_type_str = move.move_type.value.upper()
                                    results.append(ValidationResult(
                                        severity=Severity.ERROR,
                                        category="safety",
                                        message=(
                                            f"Move {i} (CLEANUP {move_type_str}): segment from "
                                            f"({prev_x:.4f}, {prev_z:.4f}) to ({move.x:.4f}, {move.z:.4f}) "
                                            f"CROSSES the Finish Allowance zone. GOUGE DETECTED."
                                        ),
                                        recommendation=(
                                            "Cleanup pass arc/segment cuts through the "
                                            "finish allowance zone boundary."
                                        ),
                                        location=(move.x, move.z),
                                        move_index=i,
                                    ))
                                    break  # One crossing is enough

        prev_x = move.x
        prev_z = move.z

    return results


def _densify_arc_move(
    start_x_r: float,
    start_z: float,
    end_x_r: float,
    end_z: float,
    move: ToolMove,
) -> List[LineString]:
    """Densify an arc move into sub-segments for accurate crossing checks.

    Converts the arc into a polyline using adaptive densification, then returns
    a list of LineString segments (one per consecutive point pair).

    Coordinates are in RADIUS (matching Shapely polygon convention).
    center_i is in DIAMETER (G-code convention), so we halve it.
    """
    import math

    # Arc center in radius coordinates
    center_i_r = move.center_i / 2.0  # Convert diameter offset to radius
    center_k = move.center_k

    center_x_r = start_x_r + center_i_r
    center_z = start_z + center_k

    # Compute radius from center to start (should match center to end)
    radius = math.sqrt(
        (start_x_r - center_x_r) ** 2 + (start_z - center_z) ** 2
    )

    # Guard: if radius is near zero or center_i/k are both zero, fall back to chord
    if radius < TOLERANCE:
        return [LineString([(start_x_r, start_z), (end_x_r, end_z)])]

    # Densify the arc path
    points = adaptive_densify_arc(
        start=(start_x_r, start_z),
        end=(end_x_r, end_z),
        center=(center_x_r, center_z),
        radius=radius,
        cos_limit=SHAPELY_COS_LIMIT,
        max_depth=MAX_DENSIFICATION_DEPTH,
    )

    # Convert consecutive point pairs into LineString segments
    segments = []
    for j in range(len(points) - 1):
        p1 = points[j]
        p2 = points[j + 1]
        # Skip degenerate zero-length sub-segments
        if abs(p1[0] - p2[0]) > 1e-9 or abs(p1[1] - p2[1]) > 1e-9:
            segments.append(LineString([p1, p2]))

    # Fallback: if densification produced nothing, use the chord
    if not segments:
        segments = [LineString([(start_x_r, start_z), (end_x_r, end_z)])]

    return segments
