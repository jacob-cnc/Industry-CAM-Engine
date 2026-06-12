"""Unit tests for tangent arc helper functions in geometry/arc_helpers.py.

Tests compute_tangent_radius(), compute_tangent_z(), and compute_tangent_x()
with known geometric configurations.
"""

import math
import os
import sys
import unittest

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from geometry.arc_helpers import (
    compute_tangent_radius,
    compute_tangent_z,
    compute_tangent_x,
)

TOLERANCE = 1e-6


class TestComputeTangentRadius(unittest.TestCase):
    """Test compute_tangent_radius() with known geometric cases."""

    def test_horizontal_line_to_vertical_drop(self):
        """Line going in -Z, arc ending at lower X (nose radius case).

        Previous segment travels in -Z (horizontal on lathe).
        Arc goes from (0.5r, 0.0) to (0.25r, -0.25).
        For a perfect quarter circle: R = 0.25, center at (0.5r, -0.25).
        """
        # Previous direction: along -Z (horizontal)
        prev_dir_x = 0.0
        prev_dir_z = -1.0

        # Start at (0.5r, 0.0), end at (0.25r, -0.25)
        x_start_r = 0.5
        z_start = 0.0
        x_end_r = 0.25
        z_end = -0.25

        result = compute_tangent_radius(
            x_start_r, z_start, x_end_r, z_end,
            prev_dir_x, prev_dir_z
        )

        self.assertIsNotNone(result)
        self.assertAlmostEqual(result, 0.25, places=6)

    def test_horizontal_line_to_diagonal_drop(self):
        """Line going in -Z, arc ending at a 45-degree diagonal point.

        Start at (1.0r, 0.0), end at (0.5r, -0.5).
        Previous direction is horizontal (-Z).
        For tangency: center must be directly below start (on the normal).
        Center = (1.0r, 0.0 - R), and R = distance to end.
        (0.5 - 1.0)^2 + (-0.5 - (-R))^2 = R^2
        0.25 + (R - 0.5)^2 = R^2
        0.25 + R^2 - R + 0.25 = R^2
        0.5 - R = 0  → R = 0.5
        """
        result = compute_tangent_radius(
            1.0, 0.0, 0.5, -0.5,
            0.0, -1.0
        )
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result, 0.5, places=6)

    def test_vertical_line_to_horizontal_exit(self):
        """Line going in -X (facing toward center), arc to a horizontal exit.

        Previous direction: along -X (toward centerline).
        Start at (0.5r, 0.0), end at (0.25r, -0.25).
        Normal to -X direction is along ±Z.
        Center on normal from start: (0.5r, 0.0 + t) for some t.
        """
        result = compute_tangent_radius(
            0.5, 0.0, 0.25, -0.25,
            -1.0, 0.0
        )
        self.assertIsNotNone(result)
        # Verify it's a positive radius
        self.assertGreater(result, 0.0)

    def test_collinear_endpoint_returns_none(self):
        """End point on the same line as the previous direction → no arc."""
        # Previous direction: along -Z. End point is directly along -Z from start.
        result = compute_tangent_radius(
            0.5, 0.0, 0.5, -1.0,
            0.0, -1.0
        )
        # End point is collinear with direction → no tangent arc exists
        self.assertIsNone(result)

    def test_zero_direction_returns_none(self):
        """Zero-length direction vector → no computation possible."""
        result = compute_tangent_radius(
            0.5, 0.0, 0.25, -0.25,
            0.0, 0.0
        )
        self.assertIsNone(result)

    def test_same_endpoints_returns_none(self):
        """Start and end at the same point → no chord, no arc."""
        result = compute_tangent_radius(
            0.5, 0.0, 0.5, 0.0,
            0.0, -1.0
        )
        self.assertIsNone(result)


class TestComputeTangentZ(unittest.TestCase):
    """Test compute_tangent_z() — where arc exits tangent to Z axis."""

    def test_quarter_circle_nose_radius(self):
        """Standard nose radius: from OD, arc exits horizontal at bottom.

        Start at (0.5r, 0.0), end X = 0.25r, R = 0.25.
        For the arc to exit horizontal at end, center_x must equal x_end.
        Center at (0.25r, cz) with distance R from start:
        (0.25 - 0.5)^2 + (cz - 0.0)^2 = 0.25^2
        0.0625 + cz^2 = 0.0625 → cz = 0
        Endpoint = (0.25r, cz - R) = (0.25r, -0.25) or (0.25r, cz + R) = (0.25r, 0.25)
        Closest to start that's different: -0.25
        """
        result = compute_tangent_z(0.5, 0.0, 0.25, 0.25, exit_horizontal=True)
        self.assertIsNotNone(result)
        # Should be -0.25 (into the part)
        self.assertAlmostEqual(result, -0.25, places=6)

    def test_x_distance_exceeds_radius(self):
        """When delta-X > R, no tangent point exists."""
        result = compute_tangent_z(0.5, 0.0, 0.1, 0.1, exit_horizontal=True)
        # dx = 0.1 - 0.5 = -0.4, |dx| = 0.4 > R=0.1
        self.assertIsNone(result)

    def test_same_x_zero_dz(self):
        """Same X start and end → dz=0, center at start, endpoint at ±R."""
        result = compute_tangent_z(0.5, 0.0, 0.5, 0.5, exit_horizontal=True)
        self.assertIsNotNone(result)


class TestComputeTangentX(unittest.TestCase):
    """Test compute_tangent_x() — where arc exits tangent to X axis."""

    def test_quarter_circle_from_face(self):
        """Arc from face exit tangent to X (vertical at endpoint).

        Start at (0.5r, 0.0), end Z = -0.25, R = 0.25.
        For vertical tangent at end: center_z = z_end = -0.25.
        Distance from start: (cx - 0.5)^2 + (-0.25 - 0)^2 = 0.25^2
        (cx - 0.5)^2 = 0.0625 - 0.0625 = 0 → cx = 0.5
        Endpoint = (cx ± R, z_end) = (0.75r, -0.25) or (0.25r, -0.25)
        Closest to start: 0.25r (diff = 0.25) vs 0.75r (diff = 0.25) — tie.
        """
        result = compute_tangent_x(0.5, 0.0, -0.25, 0.25)
        self.assertIsNotNone(result)
        # Both candidates are equidistant, should get one of them
        self.assertTrue(
            abs(result - 0.25) < TOLERANCE or abs(result - 0.75) < TOLERANCE
        )

    def test_z_distance_exceeds_radius(self):
        """When |dz| > R, no tangent point exists."""
        result = compute_tangent_x(0.5, 0.0, -1.0, 0.25)
        # dz = -1.0, R = 0.25. dz^2 = 1.0 > R^2 = 0.0625
        self.assertIsNone(result)

    def test_negative_x_filtered_out(self):
        """Endpoints with negative X (past centerline) should be excluded."""
        # Start near centerline, large Z drop, small radius
        result = compute_tangent_x(0.1, 0.0, -0.05, 0.15)
        # Should either return a valid positive X or None
        if result is not None:
            self.assertGreaterEqual(result, 0.0)


if __name__ == "__main__":
    unittest.main()


from geometry.arc_helpers import compute_fillet_quadrant_radius


class TestComputeFilletQuadrantRadius(unittest.TestCase):
    """Test compute_fillet_quadrant_radius() for corner break suggestions."""

    def test_90_degree_corner_equal_segments(self):
        """Two equal-length perpendicular segments at a 90° corner.

        Seg1: (0.5r, 0.0) → (0.5r, -1.0) — straight down Z, length 1.0
        Seg2: (0.5r, -1.0) → (0.0r, -1.0) — straight toward center, length 0.5

        Corner angle = 90°, half-angle = 45°, tan(45°) = 1.0
        Max R from seg1 = 1.0 / 1.0 = 1.0
        Max R from seg2 = 0.5 / 1.0 = 0.5
        Result = min(1.0, 0.5) = 0.5
        """
        result = compute_fillet_quadrant_radius(
            0.5, 0.0,      # seg1 start
            0.5, -1.0,     # junction
            0.0, -1.0,     # seg2 end
        )
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result, 0.5, places=6)

    def test_90_degree_corner_short_first_segment(self):
        """90° corner where the first segment is shorter.

        Seg1: (0.5r, -0.8) → (0.5r, -1.0) — length 0.2
        Seg2: (0.5r, -1.0) → (0.0r, -1.0) — length 0.5

        Max R from seg1 = 0.2 / tan(45°) = 0.2
        Max R from seg2 = 0.5 / tan(45°) = 0.5
        Result = 0.2
        """
        result = compute_fillet_quadrant_radius(
            0.5, -0.8,     # seg1 start
            0.5, -1.0,     # junction
            0.0, -1.0,     # seg2 end
        )
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result, 0.2, places=6)

    def test_collinear_segments_returns_none(self):
        """Segments going in same direction — no corner to fillet."""
        result = compute_fillet_quadrant_radius(
            0.5, 0.0,
            0.5, -1.0,
            0.5, -2.0,
        )
        self.assertIsNone(result)

    def test_zero_length_segment_returns_none(self):
        """Zero-length segment — can't compute direction."""
        result = compute_fillet_quadrant_radius(
            0.5, -1.0,    # same as junction
            0.5, -1.0,    # junction
            0.0, -1.0,
        )
        self.assertIsNone(result)

    def test_obtuse_corner(self):
        """Obtuse corner (135°) — larger fillet possible.

        Seg1: (0.5r, 0.0) → (0.5r, -1.0) — along -Z, length 1.0
        Seg2: (0.5r, -1.0) → (0.5r + 0.707, -1.707) — 45° diagonal, length 1.0

        Angle between: 135° (obtuse), half = 67.5°, tan(67.5°) ≈ 2.414
        Max R ≈ 1.0 / 2.414 ≈ 0.414
        """
        import math
        d = 1.0 / math.sqrt(2)
        result = compute_fillet_quadrant_radius(
            0.5, 0.0,
            0.5, -1.0,
            0.5 + d, -1.0 - d,
        )
        self.assertIsNotNone(result)
        # For 135° corner: tan(67.5°) ≈ 2.4142
        expected = 1.0 / math.tan(math.radians(67.5))
        self.assertAlmostEqual(result, expected, places=4)


if __name__ == "__main__":
    unittest.main()
