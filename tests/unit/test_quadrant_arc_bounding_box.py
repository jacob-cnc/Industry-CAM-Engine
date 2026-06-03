"""Tests for quadrant arc bounding box constraint.

The fundamental property of a tangent-bounded quadrant arc is that ALL points
on the curve must lie within (or on) the bounding box defined by the start
and end points. The curve is inscribed in the rectangle:
  x ∈ [min(x_start, x_end), max(x_start, x_end)]
  z ∈ [min(z_start, z_end), max(z_start, z_end)]

This test verifies this property for the kernel-based preview renderer
(_quadrant_arc_kernel_points) across multiple endpoint configurations.

If any test here fails, the Spline/RadiusArc construction is producing
geometry that violates the bounding box constraint — the tangent directions
or radius sign are wrong.
"""

import pytest
from gui.program_tab import _quadrant_arc_kernel_points


# Tolerance for floating point comparison (allow tiny overshoot from sampling)
BBOX_TOL = 1e-6


def assert_all_points_in_bounding_box(points, x_start_r, z_start, x_end_r, z_end, label=""):
    """Assert every point lies within the bounding box of start and end."""
    x_min = min(x_start_r, x_end_r) - BBOX_TOL
    x_max = max(x_start_r, x_end_r) + BBOX_TOL
    z_min = min(z_start, z_end) - BBOX_TOL
    z_max = max(z_start, z_end) + BBOX_TOL

    for i, (px, pz) in enumerate(points):
        assert x_min <= px <= x_max, (
            f"{label} Point {i}/{len(points)}: x={px:.6f} outside "
            f"[{x_min:.6f}, {x_max:.6f}] (start=({x_start_r}, {z_start}), "
            f"end=({x_end_r}, {z_end}))"
        )
        assert z_min <= pz <= z_max, (
            f"{label} Point {i}/{len(points)}: z={pz:.6f} outside "
            f"[{z_min:.6f}, {z_max:.6f}] (start=({x_start_r}, {z_start}), "
            f"end=({x_end_r}, {z_end}))"
        )


class TestConvexQBoundingBox:
    """All +Q (convex) arcs must stay within the bounding box."""

    # --- Off-axis cases (the problematic ones) ---

    def test_off_axis_increasing_x_decreasing_z(self):
        """Profile going right and down: X increases, Z decreases."""
        # This is the exact case from the user's screenshot:
        # From (0.375r, -0.75) to (0.5r, -1.25) with +Q
        x_start_r, z_start = 0.375, -0.75
        x_end_r, z_end = 0.5, -1.25
        points = _quadrant_arc_kernel_points(x_start_r, z_start, x_end_r, z_end, 1)
        assert_all_points_in_bounding_box(
            points, x_start_r, z_start, x_end_r, z_end,
            label="+Q increasing_x decreasing_z"
        )

    def test_off_axis_increasing_x_increasing_z(self):
        """Profile going right and up: X increases, Z increases."""
        x_start_r, z_start = 0.25, -1.0
        x_end_r, z_end = 0.5, -0.5
        points = _quadrant_arc_kernel_points(x_start_r, z_start, x_end_r, z_end, 1)
        assert_all_points_in_bounding_box(
            points, x_start_r, z_start, x_end_r, z_end,
            label="+Q increasing_x increasing_z"
        )

    def test_off_axis_decreasing_x_decreasing_z(self):
        """Profile going left and down: X decreases, Z decreases."""
        x_start_r, z_start = 0.5, 0.0
        x_end_r, z_end = 0.25, -0.75
        points = _quadrant_arc_kernel_points(x_start_r, z_start, x_end_r, z_end, 1)
        assert_all_points_in_bounding_box(
            points, x_start_r, z_start, x_end_r, z_end,
            label="+Q decreasing_x decreasing_z"
        )

    def test_off_axis_decreasing_x_increasing_z(self):
        """Profile going left and up: X decreases, Z increases."""
        x_start_r, z_start = 0.5, -1.0
        x_end_r, z_end = 0.25, -0.5
        points = _quadrant_arc_kernel_points(x_start_r, z_start, x_end_r, z_end, 1)
        assert_all_points_in_bounding_box(
            points, x_start_r, z_start, x_end_r, z_end,
            label="+Q decreasing_x increasing_z"
        )

    def test_off_axis_large_aspect_ratio(self):
        """Large difference between X and Z deltas."""
        # Small X change, large Z change
        x_start_r, z_start = 0.4, 0.0
        x_end_r, z_end = 0.5, -1.0
        points = _quadrant_arc_kernel_points(x_start_r, z_start, x_end_r, z_end, 1)
        assert_all_points_in_bounding_box(
            points, x_start_r, z_start, x_end_r, z_end,
            label="+Q large_aspect_ratio"
        )

    # --- Axis-aligned cases (should also pass) ---

    def test_axis_aligned_same_x(self):
        """Same X (vertical chord) — RadiusArc should stay in bounds."""
        x_start_r, z_start = 0.5, 0.0
        x_end_r, z_end = 0.5, -0.5
        points = _quadrant_arc_kernel_points(x_start_r, z_start, x_end_r, z_end, 1)
        assert_all_points_in_bounding_box(
            points, x_start_r, z_start, x_end_r, z_end,
            label="+Q axis_aligned_same_x"
        )

    def test_axis_aligned_same_z(self):
        """Same Z (horizontal chord) — RadiusArc should stay in bounds."""
        x_start_r, z_start = 0.25, -1.0
        x_end_r, z_end = 0.5, -1.0
        points = _quadrant_arc_kernel_points(x_start_r, z_start, x_end_r, z_end, 1)
        assert_all_points_in_bounding_box(
            points, x_start_r, z_start, x_end_r, z_end,
            label="+Q axis_aligned_same_z"
        )


class TestConcaveQBoundingBox:
    """All -Q (concave) arcs must stay within the bounding box."""

    def test_off_axis_increasing_x_decreasing_z(self):
        """Concave arc going right and down."""
        x_start_r, z_start = 0.375, -0.75
        x_end_r, z_end = 0.5, -1.25
        points = _quadrant_arc_kernel_points(x_start_r, z_start, x_end_r, z_end, -1)
        assert_all_points_in_bounding_box(
            points, x_start_r, z_start, x_end_r, z_end,
            label="-Q increasing_x decreasing_z"
        )

    def test_off_axis_increasing_x_increasing_z(self):
        """Concave arc going right and up."""
        x_start_r, z_start = 0.25, -1.0
        x_end_r, z_end = 0.5, -0.5
        points = _quadrant_arc_kernel_points(x_start_r, z_start, x_end_r, z_end, -1)
        assert_all_points_in_bounding_box(
            points, x_start_r, z_start, x_end_r, z_end,
            label="-Q increasing_x increasing_z"
        )

    def test_off_axis_decreasing_x_decreasing_z(self):
        """Concave arc going left and down."""
        x_start_r, z_start = 0.5, 0.0
        x_end_r, z_end = 0.25, -0.75
        points = _quadrant_arc_kernel_points(x_start_r, z_start, x_end_r, z_end, -1)
        assert_all_points_in_bounding_box(
            points, x_start_r, z_start, x_end_r, z_end,
            label="-Q decreasing_x decreasing_z"
        )

    def test_off_axis_decreasing_x_increasing_z(self):
        """Concave arc going left and up."""
        x_start_r, z_start = 0.5, -1.0
        x_end_r, z_end = 0.25, -0.5
        points = _quadrant_arc_kernel_points(x_start_r, z_start, x_end_r, z_end, -1)
        assert_all_points_in_bounding_box(
            points, x_start_r, z_start, x_end_r, z_end,
            label="-Q decreasing_x increasing_z"
        )

    def test_axis_aligned_same_x(self):
        """Concave, same X (vertical chord)."""
        x_start_r, z_start = 0.5, 0.0
        x_end_r, z_end = 0.5, -0.5
        points = _quadrant_arc_kernel_points(x_start_r, z_start, x_end_r, z_end, -1)
        assert_all_points_in_bounding_box(
            points, x_start_r, z_start, x_end_r, z_end,
            label="-Q axis_aligned_same_x"
        )

    def test_axis_aligned_same_z(self):
        """Concave, same Z (horizontal chord)."""
        x_start_r, z_start = 0.25, -1.0
        x_end_r, z_end = 0.5, -1.0
        points = _quadrant_arc_kernel_points(x_start_r, z_start, x_end_r, z_end, -1)
        assert_all_points_in_bounding_box(
            points, x_start_r, z_start, x_end_r, z_end,
            label="-Q axis_aligned_same_z"
        )
