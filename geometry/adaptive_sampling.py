"""Adaptive arc densification for Industry CAM Engine.

Implements the OpenCamLib cosine-limit flatness predicate for converting
arcs into point sequences with guaranteed maximum chord error.

Used by:
- validation/polygon_builder.py (Shapely polygon construction, cos_limit=0.9999)
- outputs/graph_adapter.py (display densification, cos_limit=0.999)

Imports from: models/ (constants only)
"""

import math
from typing import List, Tuple

from models.constants import SHAPELY_COS_LIMIT, MAX_DENSIFICATION_DEPTH


def flatness_predicate(
    start: Tuple[float, float],
    mid: Tuple[float, float],
    end: Tuple[float, float],
    cos_limit: float,
) -> bool:
    """OpenCamLib-style cosine-limit flatness test.

    Returns True if the three points are 'flat enough' (no further bisection needed).
    The test: dot(normalize(mid-start), normalize(end-mid)) > cos_limit

    When the dot product is close to 1.0, the points are nearly collinear.
    """
    # Vector from start to mid
    v1x = mid[0] - start[0]
    v1y = mid[1] - start[1]
    len1 = math.sqrt(v1x * v1x + v1y * v1y)

    # Vector from mid to end
    v2x = end[0] - mid[0]
    v2y = end[1] - mid[1]
    len2 = math.sqrt(v2x * v2x + v2y * v2y)

    # Avoid division by zero for degenerate cases
    if len1 < 1e-12 or len2 < 1e-12:
        return True  # Degenerate — treat as flat

    # Normalize and dot product
    dot = (v1x * v2x + v1y * v2y) / (len1 * len2)
    return dot >= cos_limit


def arc_midpoint(
    start: Tuple[float, float],
    end: Tuple[float, float],
    center: Tuple[float, float],
    radius: float,
) -> Tuple[float, float]:
    """Compute the point on the arc halfway between start and end (angle bisection).

    The midpoint is found by bisecting the angle from center to start and center to end,
    then projecting outward by radius from center.
    """
    angle_start = math.atan2(start[1] - center[1], start[0] - center[0])
    angle_end = math.atan2(end[1] - center[1], end[0] - center[0])

    # Handle angle wrapping — choose the shorter arc
    diff = angle_end - angle_start
    if diff > math.pi:
        diff -= 2 * math.pi
    elif diff < -math.pi:
        diff += 2 * math.pi

    angle_mid = angle_start + diff / 2.0

    return (
        center[0] + radius * math.cos(angle_mid),
        center[1] + radius * math.sin(angle_mid),
    )


def adaptive_densify_arc(
    start: Tuple[float, float],
    end: Tuple[float, float],
    center: Tuple[float, float],
    radius: float,
    cos_limit: float = SHAPELY_COS_LIMIT,
    max_depth: int = MAX_DENSIFICATION_DEPTH,
) -> List[Tuple[float, float]]:
    """Recursively bisect an arc until the cosine-limit flatness predicate is satisfied.

    Returns a densified point list INCLUDING start and end.

    Properties:
    - Straight regions: minimal intermediate points
    - Tight arcs: many intermediate points (high curvature)
    - Max chord error: R × (1 - cos(arccos(cos_limit)/2^depth))
    - For cos_limit=0.9999, R=0.251": max error < 0.000025"
    - Inscribed-chord guarantee: all chords are INSIDE the true arc

    Args:
        start: Arc start point (x, y)
        end: Arc end point (x, y)
        center: Arc center point (x, y)
        radius: Arc radius (positive, absolute value)
        cos_limit: Flatness threshold (higher = more points, tighter tolerance)
        max_depth: Maximum recursion depth (safety limit)

    Returns:
        List of (x, y) points from start to end (inclusive).
    """
    result = [start]
    _densify_recursive(start, end, center, radius, cos_limit, max_depth, 0, result)
    result.append(end)
    return result


def _densify_recursive(
    start: Tuple[float, float],
    end: Tuple[float, float],
    center: Tuple[float, float],
    radius: float,
    cos_limit: float,
    max_depth: int,
    depth: int,
    result: List[Tuple[float, float]],
) -> None:
    """Internal recursive densification. Appends intermediate points to result."""
    mid = arc_midpoint(start, end, center, radius)

    if depth >= max_depth:
        # Force at least one bisection at max depth
        result.append(mid)
        return

    if flatness_predicate(start, mid, end, cos_limit):
        # Flat enough — no intermediate point needed between start and end
        return

    # Not flat — bisect both halves
    _densify_recursive(start, mid, center, radius, cos_limit, max_depth, depth + 1, result)
    result.append(mid)
    _densify_recursive(mid, end, center, radius, cos_limit, max_depth, depth + 1, result)
