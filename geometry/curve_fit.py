"""Fit circular arcs to a non-circular kernel edge (ellipse, B-spline).

Moved verbatim from planners/finish_planner.py on 2026-11-12 (structure
cleanup, step 4c) so the kernel's curve evaluation (OCP BRepAdaptor_Curve)
lives in geometry/. The finish planner turns the returned spans into G2/G3
moves; this module only answers "which three points on the curve define each
arc piece within chord_error".

Reachability (2026-11-12): CURVE edges come from non-circular geometry. With
quadrant arcs made true circles (owner 2026-11-11, "ellipses are retired")
the zone builder produces only lines and circles, so no Generate path reaches
this today; tests/unit/test_edge_decomposition.py exercises it with real OCCT
ellipse and B-spline edges. Kept for future spline input.

DEBT (hand-math branch): the 3-point circumcentre and deviation checks are
hand math; OCCT has arc-approximation tools worth comparing against.
"""
from __future__ import annotations

import math
from typing import List, Optional, Tuple

from OCP.BRepAdaptor import BRepAdaptor_Curve

Point = Tuple[float, float]


def circumcenter(x1: float, z1: float, x2: float, z2: float, x3: float, z3: float) -> Optional[tuple]:
    """Circumcentre (cx, cz) of three points, or None if they are collinear.

    Uses the determinant formula for numerical stability.
    """
    ax, az = x1, z1
    bx, bz = x2, z2
    cx, cz = x3, z3

    D = 2.0 * (ax * (bz - cz) + bx * (cz - az) + cx * (az - bz))

    if abs(D) < 1e-12:
        return None  # Collinear

    ux = ((ax ** 2 + az ** 2) * (bz - cz) + (bx ** 2 + bz ** 2) * (cz - az) + (cx ** 2 + cz ** 2) * (az - bz)) / D
    uz = ((ax ** 2 + az ** 2) * (cx - bx) + (bx ** 2 + bz ** 2) * (ax - cx) + (cx ** 2 + cz ** 2) * (bx - ax)) / D

    return (ux, uz)


def max_line_deviation(curve, u_a: float, u_b: float,
                       ax_r: float, az: float, bx_r: float, bz: float) -> float:
    """Maximum deviation of the curve from the straight line between the endpoints."""
    dx = bx_r - ax_r
    dz = bz - az
    line_len = math.sqrt(dx ** 2 + dz ** 2)

    if line_len < 1e-12:
        return 0.0

    max_dev = 0.0
    n_check = 5
    for j in range(1, n_check + 1):
        t = j / (n_check + 1)
        u_sample = u_a + t * (u_b - u_a)
        p_sample = curve.Value(u_sample)
        sx_r, sz = p_sample.X(), p_sample.Y()

        # Perpendicular distance from point to line
        # Using cross product formula: |cross| / |line_vec|
        cross = abs((sx_r - ax_r) * dz - (sz - az) * dx)
        dev = cross / line_len
        if dev > max_dev:
            max_dev = dev

    return max_dev


def subdivide_curve_spans(curve, u_start: float, u_end: float, chord_error: float,
                          max_depth: int = 12) -> List[tuple]:
    """Adaptively subdivide a curve into spans where a circular arc fit is within tolerance.

    Uses a stack-based approach to avoid deep recursion. For each candidate span,
    computes the maximum deviation between the fitted arc and the true curve at
    several sample points. If deviation exceeds chord_error, the span is split.

    Returns:
        List of (u_a, u_b) parameter pairs in traversal order.
    """
    result = []
    # Stack of (u_a, u_b, depth)
    stack = [(u_start, u_end, 0)]

    while stack:
        u_a, u_b, depth = stack.pop()

        # If we've hit max depth, accept this span as-is
        if depth >= max_depth:
            result.append((u_a, u_b))
            continue

        # Sample three points for arc fitting
        u_mid = (u_a + u_b) / 2.0
        p_a = curve.Value(u_a)
        p_mid = curve.Value(u_mid)
        p_b = curve.Value(u_b)

        ax_r, az = p_a.X(), p_a.Y()
        mx_r, mz = p_mid.X(), p_mid.Y()
        bx_r, bz = p_b.X(), p_b.Y()

        # Fit circumscribed circle through three points
        center = circumcenter(ax_r, az, mx_r, mz, bx_r, bz)

        if center is None:
            # Collinear points — check if the actual curve deviates from the line
            # Sample additional points and check deviation from the line
            max_dev = max_line_deviation(curve, u_a, u_b, ax_r, az, bx_r, bz)
            if max_dev <= chord_error:
                result.append((u_a, u_b))
            else:
                # Subdivide (push right first so left is processed first)
                stack.append((u_mid, u_b, depth + 1))
                stack.append((u_a, u_mid, depth + 1))
            continue

        cx_r, cz = center
        radius = math.sqrt((ax_r - cx_r) ** 2 + (az - cz) ** 2)

        # Check deviation at several interior sample points
        max_dev = 0.0
        n_check = 5
        for j in range(1, n_check + 1):
            t = j / (n_check + 1)
            u_sample = u_a + t * (u_b - u_a)
            p_sample = curve.Value(u_sample)
            sx_r, sz = p_sample.X(), p_sample.Y()
            # Distance from sample point to fitted arc center
            dist = math.sqrt((sx_r - cx_r) ** 2 + (sz - cz) ** 2)
            dev = abs(dist - radius)
            if dev > max_dev:
                max_dev = dev

        if max_dev <= chord_error:
            # This span is within tolerance
            result.append((u_a, u_b))
        else:
            # Subdivide (push right first so left is processed first)
            stack.append((u_mid, u_b, depth + 1))
            stack.append((u_a, u_mid, depth + 1))

    # Sort result by parameter order
    if u_start < u_end:
        result.sort(key=lambda span: span[0])
    else:
        result.sort(key=lambda span: span[0], reverse=True)

    return result


def curve_arc_spans(ocp_edge, start_dia: Point, end_dia: Point,
                    chord_error: float) -> List[Tuple[Point, Point, Point]]:
    """Arc pieces approximating a non-circular edge from start_dia to end_dia.

    Returns, in cutting order, (start, mid, end) points of each piece in
    DIAMETER (x_dia, z). The first piece starts exactly at start_dia and the
    last ends exactly at end_dia (no drift). The curve's parametric direction
    is matched to start_dia (within .001).
    """
    curve = BRepAdaptor_Curve(ocp_edge)

    u_first = curve.FirstParameter()
    u_last = curve.LastParameter()

    # Determine parametric direction: does u_first correspond to edge.start or edge.end?
    # Edge start/end are in diameter, curve points are in radius
    p_first = curve.Value(u_first)
    start_x_r = start_dia[0] / 2.0
    start_z = start_dia[1]

    dist_to_start = math.sqrt(
        (p_first.X() - start_x_r) ** 2 + (p_first.Y() - start_z) ** 2
    )

    if dist_to_start < 0.001:
        # Parametric direction matches edge direction
        u_start = u_first
        u_end = u_last
    else:
        # Parametric direction is reversed
        u_start = u_last
        u_end = u_first

    spans = subdivide_curve_spans(curve, u_start, u_end, chord_error)

    pieces = []
    for i, (u_a, u_b) in enumerate(spans):
        u_mid = (u_a + u_b) / 2.0
        p_a = curve.Value(u_a)
        p_mid = curve.Value(u_mid)
        p_b = curve.Value(u_b)

        ax_dia, az = p_a.X() * 2.0, p_a.Y()
        mx_dia, mz = p_mid.X() * 2.0, p_mid.Y()
        bx_dia, bz = p_b.X() * 2.0, p_b.Y()

        # Use exact edge endpoints for first and last spans (no drift)
        if i == 0:
            ax_dia, az = start_dia[0], start_dia[1]
        if i == len(spans) - 1:
            bx_dia, bz = end_dia[0], end_dia[1]

        pieces.append(((ax_dia, az), (mx_dia, mz), (bx_dia, bz)))
    return pieces
