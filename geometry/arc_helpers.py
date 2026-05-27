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
) -> str:
    """Format a detailed validation error message with alternatives.

    Called when abs(radius) < chord/2. Computes and presents:
    1. The minimum radius needed for these endpoints
    2. The maximum Z reachable at this X with this radius
    3. The maximum X reachable at this Z with this radius

    All user-facing values are in DIAMETER for X, INCHES for Z and R.

    Args:
        x_start_dia: Start X in diameter
        z_start: Start Z in inches
        x_end_dia: End X in diameter
        z_end: End Z in inches
        radius: User's entered radius (absolute value)

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

    # Alternative 1: increase radius
    lines.append(f"Options:")
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
