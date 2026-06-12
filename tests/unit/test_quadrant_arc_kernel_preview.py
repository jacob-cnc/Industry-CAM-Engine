"""Tests for quadrant arc kernel-based preview rendering.

Validates that _quadrant_arc_kernel_points() from program_tab.py produces
correct display points using Build123d geometry (RadiusArc for axis-aligned,
Spline for off-axis) and parametric sampling from the OCCT edge.

Validates: Requirements 9.1, 9.2, 9.3, 9.4
"""

import math
import time
import pytest

from gui.program_tab import _quadrant_arc_kernel_points


class TestQuadrantArcKernelPoints:
    """Test the kernel-based quadrant arc display point extraction."""

    # --- Basic correctness tests ---

    def test_axis_aligned_convex_same_x(self):
        """Axis-aligned +Q arc (same X) produces correct quarter-circle."""
        # Start and end share same X (vertical chord) → true circular arc
        points = _quadrant_arc_kernel_points(
            x_start_r=0.5, z_start=0.0,
            x_end_r=0.5, z_end=-0.5,
            quadrant_sign=1, num_points=32,
        )
        # Should have 33 points (32 + 1 for start)
        assert len(points) == 33
        # Start and end points match
        assert points[0] == (0.5, 0.0)
        assert points[-1] == (0.5, -0.5)

    def test_axis_aligned_convex_same_z(self):
        """Axis-aligned +Q arc (same Z) produces correct quarter-circle."""
        # Start and end share same Z (horizontal chord)
        points = _quadrant_arc_kernel_points(
            x_start_r=0.25, z_start=-1.0,
            x_end_r=0.5, z_end=-1.0,
            quadrant_sign=1, num_points=32,
        )
        assert len(points) == 33
        assert points[0] == (0.25, -1.0)
        assert points[-1] == (0.5, -1.0)

    def test_off_axis_convex(self):
        """Off-axis +Q arc produces smooth elliptical curve."""
        points = _quadrant_arc_kernel_points(
            x_start_r=0.25, z_start=0.0,
            x_end_r=0.5, z_end=-0.75,
            quadrant_sign=1, num_points=48,
        )
        assert len(points) == 49
        # Exact endpoints
        assert points[0] == (0.25, 0.0)
        assert points[-1] == (0.5, -0.75)

    def test_off_axis_concave(self):
        """Off-axis -Q arc produces concave (scooped) curve."""
        points = _quadrant_arc_kernel_points(
            x_start_r=0.25, z_start=0.0,
            x_end_r=0.5, z_end=-0.75,
            quadrant_sign=-1, num_points=48,
        )
        assert len(points) == 49
        # Exact endpoints
        assert points[0] == (0.25, 0.0)
        assert points[-1] == (0.5, -0.75)

    def test_concave_vs_convex_differ(self):
        """Q and -Q produce different curves for same endpoints."""
        pts_convex = _quadrant_arc_kernel_points(
            x_start_r=0.25, z_start=0.0,
            x_end_r=0.5, z_end=-0.75,
            quadrant_sign=1, num_points=32,
        )
        pts_concave = _quadrant_arc_kernel_points(
            x_start_r=0.25, z_start=0.0,
            x_end_r=0.5, z_end=-0.75,
            quadrant_sign=-1, num_points=32,
        )
        # Endpoints match
        assert pts_convex[0] == pts_concave[0]
        assert pts_convex[-1] == pts_concave[-1]
        # Midpoints differ significantly
        mid_convex = pts_convex[len(pts_convex) // 2]
        mid_concave = pts_concave[len(pts_concave) // 2]
        dist = math.sqrt(
            (mid_convex[0] - mid_concave[0])**2 +
            (mid_convex[1] - mid_concave[1])**2
        )
        assert dist > 0.01, "Convex and concave midpoints should differ"

    # --- Curve smoothness ---

    def test_curve_is_smooth(self):
        """Points should form a smooth curve (no large jumps between consecutive points)."""
        points = _quadrant_arc_kernel_points(
            x_start_r=0.25, z_start=0.0,
            x_end_r=0.5, z_end=-0.75,
            quadrant_sign=1, num_points=48,
        )
        max_step = 0
        for i in range(1, len(points)):
            dx = points[i][0] - points[i - 1][0]
            dz = points[i][1] - points[i - 1][1]
            step = math.sqrt(dx * dx + dz * dz)
            max_step = max(max_step, step)
        # For a curve spanning ~0.25 X and 0.75 Z with 48 segments,
        # each step should be well under 0.05"
        assert max_step < 0.05

    def test_monotonic_for_standard_profile(self):
        """For a typical lathe quadrant arc, X increases and Z decreases monotonically."""
        # Standard convex Q going from face (small X, Z=0) to OD
        points = _quadrant_arc_kernel_points(
            x_start_r=0.25, z_start=0.0,
            x_end_r=0.5, z_end=-0.5,
            quadrant_sign=1, num_points=32,
        )
        # X should be monotonically non-decreasing
        for i in range(1, len(points)):
            assert points[i][0] >= points[i - 1][0] - 1e-9
        # Z should be monotonically non-increasing
        for i in range(1, len(points)):
            assert points[i][1] <= points[i - 1][1] + 1e-9

    # --- Degenerate cases ---

    def test_degenerate_same_point(self):
        """When start == end, returns a two-point line."""
        points = _quadrant_arc_kernel_points(
            x_start_r=0.5, z_start=-1.0,
            x_end_r=0.5, z_end=-1.0,
            quadrant_sign=1,
        )
        assert len(points) == 2
        assert points[0] == (0.5, -1.0)
        assert points[-1] == (0.5, -1.0)

    # --- Performance test ---

    def test_performance_under_16ms(self):
        """Preview rendering for 10 quadrant arcs stays under 16ms total.

        Validates Requirement 9.4: rendering time < 16ms for typical profiles.
        """
        # Warm up (first call may have import overhead)
        _quadrant_arc_kernel_points(0.25, 0.0, 0.5, -0.5, 1, 48)

        start = time.perf_counter()
        for i in range(10):
            _quadrant_arc_kernel_points(
                x_start_r=0.1 * (i + 1), z_start=0.0,
                x_end_r=0.1 * (i + 2), z_end=-0.1 * (i + 1),
                quadrant_sign=1 if i % 2 == 0 else -1,
                num_points=48,
            )
        elapsed_ms = (time.perf_counter() - start) * 1000

        # Budget: 16ms for up to 10 quadrant arcs
        assert elapsed_ms < 16.0, (
            f"10 quadrant arcs took {elapsed_ms:.1f}ms (budget: 16ms)"
        )
