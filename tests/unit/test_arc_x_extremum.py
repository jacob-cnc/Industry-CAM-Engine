"""Unit tests for compute_arc_x_extremum() in geometry/arc_helpers.py.

Tests known geometric configurations to verify the function correctly
computes the minimum and maximum X values an arc reaches.

Validates: Requirements 2.1, 2.2, 2.3, 2.5
"""

import math
import sys
import os

import pytest

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from geometry.arc_helpers import compute_arc_x_extremum

TOLERANCE = 1e-9


class TestComputeArcXExtremum:
    """Unit tests for compute_arc_x_extremum with known geometric configurations."""

    def test_quarter_circle_cw_top_to_right(self):
        """Quarter circle CW from top (0, 1) to right (1, 0), center at origin.

        Arc sweeps from 90° to 0° (CW = negative sweep).
        Rightmost point (angle=0) IS the endpoint → x_max = 1.0.
        Leftmost point (angle=π) is NOT in sweep → x_min = min(0, 1) = 0.
        """
        center_x, center_z = 0.0, 0.0
        radius = 1.0
        x1_r, z1 = 0.0, 1.0   # top of circle (angle = π/2)
        x2_r, z2 = 1.0, 0.0   # right of circle (angle = 0)
        is_cw = True

        x_min, x_max = compute_arc_x_extremum(
            center_x, center_z, radius, x1_r, z1, x2_r, z2, is_cw
        )

        assert abs(x_max - 1.0) < TOLERANCE, f"Expected x_max=1.0, got {x_max}"
        assert abs(x_min - 0.0) < TOLERANCE, f"Expected x_min=0.0, got {x_min}"

    def test_quarter_circle_ccw_right_to_top(self):
        """Quarter circle CCW from right (1, 0) to top (0, 1), center at origin.

        Arc sweeps from 0° to 90° (CCW = positive sweep).
        Rightmost point (angle=0) IS the start → x_max = 1.0.
        Leftmost point (angle=π) is NOT in sweep → x_min = min(1, 0) = 0.
        """
        center_x, center_z = 0.0, 0.0
        radius = 1.0
        x1_r, z1 = 1.0, 0.0   # right of circle (angle = 0)
        x2_r, z2 = 0.0, 1.0   # top of circle (angle = π/2)
        is_cw = False

        x_min, x_max = compute_arc_x_extremum(
            center_x, center_z, radius, x1_r, z1, x2_r, z2, is_cw
        )

        assert abs(x_max - 1.0) < TOLERANCE, f"Expected x_max=1.0, got {x_max}"
        assert abs(x_min - 0.0) < TOLERANCE, f"Expected x_min=0.0, got {x_min}"

    def test_semicircle_cw_top_to_bottom(self):
        """Semicircle CW from top (0, 1) to bottom (0, -1), center at origin.

        Arc sweeps from 90° to -90° going CW (through 0°).
        Rightmost point (angle=0) IS in sweep → x_max = 1.0.
        Leftmost point (angle=π) is NOT in sweep → x_min = min(0, 0) = 0.
        """
        center_x, center_z = 0.0, 0.0
        radius = 1.0
        x1_r, z1 = 0.0, 1.0    # top (angle = π/2)
        x2_r, z2 = 0.0, -1.0   # bottom (angle = -π/2)
        is_cw = True

        x_min, x_max = compute_arc_x_extremum(
            center_x, center_z, radius, x1_r, z1, x2_r, z2, is_cw
        )

        assert abs(x_max - 1.0) < TOLERANCE, f"Expected x_max=1.0, got {x_max}"
        assert abs(x_min - 0.0) < TOLERANCE, f"Expected x_min=0.0, got {x_min}"

    def test_semicircle_ccw_top_to_bottom(self):
        """Semicircle CCW from top (0, 1) to bottom (0, -1), center at origin.

        Arc sweeps from 90° to -90° going CCW (through 180°).
        Rightmost point (angle=0) is NOT in sweep → x_max = max(0, 0) = 0.
        Leftmost point (angle=π) IS in sweep → x_min = -1.0.
        """
        center_x, center_z = 0.0, 0.0
        radius = 1.0
        x1_r, z1 = 0.0, 1.0    # top (angle = π/2)
        x2_r, z2 = 0.0, -1.0   # bottom (angle = -π/2)
        is_cw = False

        x_min, x_max = compute_arc_x_extremum(
            center_x, center_z, radius, x1_r, z1, x2_r, z2, is_cw
        )

        assert abs(x_max - 0.0) < TOLERANCE, f"Expected x_max=0.0, got {x_max}"
        assert abs(x_min - (-1.0)) < TOLERANCE, f"Expected x_min=-1.0, got {x_min}"

    def test_full_circle_cw(self):
        """Full circle (nearly) CW — should reach both extremes.

        Start and end nearly the same point, CW sweep ≈ 2π.
        Both angle=0 and angle=π are in sweep.
        x_max = center_x + radius, x_min = center_x - radius.
        """
        center_x, center_z = 0.5, 0.0
        radius = 0.5
        # Start at top, end just slightly past top (nearly full circle CW)
        angle_start = math.pi / 2
        angle_end = math.pi / 2 + 0.001  # tiny bit past start in CCW direction
        x1_r = center_x + radius * math.cos(angle_start)
        z1 = center_z + radius * math.sin(angle_start)
        x2_r = center_x + radius * math.cos(angle_end)
        z2 = center_z + radius * math.sin(angle_end)
        is_cw = True  # CW sweep goes the long way around

        x_min, x_max = compute_arc_x_extremum(
            center_x, center_z, radius, x1_r, z1, x2_r, z2, is_cw
        )

        # Full circle should reach both extremes
        assert abs(x_max - (center_x + radius)) < TOLERANCE, \
            f"Expected x_max={center_x + radius}, got {x_max}"
        assert abs(x_min - (center_x - radius)) < TOLERANCE, \
            f"Expected x_min={center_x - radius}, got {x_min}"

    def test_shallow_arc_stays_within_endpoints(self):
        """Shallow arc (large radius) stays well within endpoint X values.

        A very shallow arc (radius >> chord) barely deviates from a straight
        line. The extremum should be very close to the endpoint X values.

        CCW from angle (π/2 - 0.05) to (π/2 + 0.05) is a short arc near the
        top of the circle. It does NOT cross angle=0 or angle=π.
        """
        center_x, center_z = 0.5, -10.0  # Center far below (large radius)
        radius = 10.0
        # Two points on the circle, close together (shallow arc)
        x1_r = center_x + radius * math.cos(math.pi / 2 - 0.05)
        z1 = center_z + radius * math.sin(math.pi / 2 - 0.05)
        x2_r = center_x + radius * math.cos(math.pi / 2 + 0.05)
        z2 = center_z + radius * math.sin(math.pi / 2 + 0.05)
        # CCW from (π/2 - 0.05) to (π/2 + 0.05) is the SHORT arc
        is_cw = False

        x_min, x_max = compute_arc_x_extremum(
            center_x, center_z, radius, x1_r, z1, x2_r, z2, is_cw
        )

        # Shallow arc: extremum should be within endpoint X values
        assert x_min >= min(x1_r, x2_r) - TOLERANCE
        assert x_max <= max(x1_r, x2_r) + TOLERANCE

    def test_quarter_circle_cw_right_to_bottom(self):
        """Quarter circle CW from right (1, 0) to bottom (0, -1), center at origin.

        Arc sweeps from 0° to -90° (CW = negative sweep).
        Rightmost point (angle=0) IS the start → x_max = 1.0.
        Leftmost point (angle=π) is NOT in sweep → x_min = min(1, 0) = 0.
        """
        center_x, center_z = 0.0, 0.0
        radius = 1.0
        x1_r, z1 = 1.0, 0.0    # right (angle = 0)
        x2_r, z2 = 0.0, -1.0   # bottom (angle = -π/2)
        is_cw = True

        x_min, x_max = compute_arc_x_extremum(
            center_x, center_z, radius, x1_r, z1, x2_r, z2, is_cw
        )

        assert abs(x_max - 1.0) < TOLERANCE, f"Expected x_max=1.0, got {x_max}"
        assert abs(x_min - 0.0) < TOLERANCE, f"Expected x_min=0.0, got {x_min}"

    def test_arc_crossing_leftmost_point(self):
        """Arc that crosses the leftmost point (angle=π).

        CW arc from angle=3π/4 to angle=-3π/4 (i.e., from top-left to
        bottom-left), going CW through angle=π (the leftmost point).

        Center at (1, 0), radius=1. Leftmost point is at x=0.
        CW from 3π/4 sweeps negatively: 3π/4 → π/2 → ... NO, that's wrong.
        CW sweep is negative. From 3π/4, going CW means decreasing angle...
        that goes through π/2, 0, -π/2 — NOT through π.

        Instead: CCW from 3π/4 to -3π/4 (= 5π/4). CCW sweep from 3π/4
        goes through π to 5π/4 (-3π/4). This crosses angle=π.
        """
        center_x, center_z = 1.0, 0.0
        radius = 1.0
        # Start at angle = 3π/4 (top-left quadrant)
        x1_r = center_x + radius * math.cos(3 * math.pi / 4)
        z1 = center_z + radius * math.sin(3 * math.pi / 4)
        # End at angle = -3π/4 (= 5π/4, bottom-left quadrant)
        x2_r = center_x + radius * math.cos(-3 * math.pi / 4)
        z2 = center_z + radius * math.sin(-3 * math.pi / 4)
        # CCW from 3π/4 to -3π/4: sweep goes 3π/4 → π → -3π/4
        is_cw = False

        x_min, x_max = compute_arc_x_extremum(
            center_x, center_z, radius, x1_r, z1, x2_r, z2, is_cw
        )

        # The arc crosses angle=π, so x_min should be center_x - radius = 0.0
        assert abs(x_min - 0.0) < TOLERANCE, f"Expected x_min=0.0, got {x_min}"

    def test_arc_crossing_rightmost_point(self):
        """Arc that crosses the rightmost point (angle=0).

        CCW arc from angle=-π/4 to angle=π/4, center at (0.5, 0), radius=0.5.
        This crosses angle=0 (rightmost at x=1.0).
        """
        center_x, center_z = 0.5, 0.0
        radius = 0.5
        # Start at angle = -π/4
        x1_r = center_x + radius * math.cos(-math.pi / 4)
        z1 = center_z + radius * math.sin(-math.pi / 4)
        # End at angle = π/4
        x2_r = center_x + radius * math.cos(math.pi / 4)
        z2 = center_z + radius * math.sin(math.pi / 4)
        is_cw = False  # CCW from -π/4 to π/4 crosses 0

        x_min, x_max = compute_arc_x_extremum(
            center_x, center_z, radius, x1_r, z1, x2_r, z2, is_cw
        )

        # The arc crosses angle=0, so x_max should be center_x + radius = 1.0
        assert abs(x_max - 1.0) < TOLERANCE, f"Expected x_max=1.0, got {x_max}"

    def test_vertical_chord_arc(self):
        """Arc with vertical chord (same X start and end).

        Both endpoints at X=0.5, arc bulges outward. The arc is inherently
        bounded since start and end X are equal.
        """
        center_x, center_z = 0.0, 0.0
        radius = 1.0
        # Both endpoints at X=0.5 (different Z)
        # angle where cos(a) = 0.5 → a = ±π/3
        x1_r = 0.5
        z1 = math.sqrt(1.0 - 0.25)   # ≈ 0.866
        x2_r = 0.5
        z2 = -math.sqrt(1.0 - 0.25)  # ≈ -0.866
        is_cw = True  # CW from top to bottom through right side

        x_min, x_max = compute_arc_x_extremum(
            center_x, center_z, radius, x1_r, z1, x2_r, z2, is_cw
        )

        # CW from π/3 to -π/3 passes through angle=0 (rightmost)
        assert abs(x_max - 1.0) < TOLERANCE, f"Expected x_max=1.0, got {x_max}"
        # x_min should be the endpoint X value (0.5)
        assert abs(x_min - 0.5) < TOLERANCE, f"Expected x_min=0.5, got {x_min}"

    def test_does_not_affect_compute_min_radius(self):
        """Verify compute_min_radius still works correctly (preservation)."""
        from geometry.arc_helpers import compute_min_radius

        # Simple case: horizontal chord of length 1
        min_r = compute_min_radius(0.0, 0.0, 1.0, 0.0)
        assert abs(min_r - 0.5) < TOLERANCE

        # Diagonal chord
        min_r = compute_min_radius(0.0, 0.0, 0.3, -0.4)
        chord = math.sqrt(0.3**2 + 0.4**2)
        assert abs(min_r - chord / 2.0) < TOLERANCE

        # Zero-length chord
        min_r = compute_min_radius(0.5, -0.3, 0.5, -0.3)
        assert abs(min_r - 0.0) < TOLERANCE
