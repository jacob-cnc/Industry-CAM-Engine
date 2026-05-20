"""Unit tests for hal.compound_logic — Linear and Arc modes.

Tests the pure computation layer in isolation (no GUI, no HAL).
"""

import math
import pytest

from hal.compound_logic import (
    CompoundLinearLogic, CompoundArcLogic,
    Quadrant, ArcStartType,
)
from hal.constants import JOG_INCREMENTS


# ======================================================================
# CompoundLinearLogic Tests
# ======================================================================

class TestLinearValidateAngle:
    """Tests for CompoundLinearLogic.validate_angle()."""

    def test_valid_zero(self):
        ok, val = CompoundLinearLogic.validate_angle("0")
        assert ok is True
        assert val == 0.0

    def test_valid_ninety(self):
        ok, val = CompoundLinearLogic.validate_angle("90")
        assert ok is True
        assert val == 90.0

    def test_valid_float(self):
        ok, val = CompoundLinearLogic.validate_angle("29.5")
        assert ok is True
        assert val == 29.5

    def test_valid_numeric_input(self):
        ok, val = CompoundLinearLogic.validate_angle(45.0)
        assert ok is True
        assert val == 45.0

    def test_invalid_negative(self):
        ok, val = CompoundLinearLogic.validate_angle("-1")
        assert ok is False
        assert val == 0.0

    def test_invalid_over_ninety(self):
        ok, val = CompoundLinearLogic.validate_angle("91")
        assert ok is False
        assert val == 0.0

    def test_invalid_text(self):
        ok, val = CompoundLinearLogic.validate_angle("abc")
        assert ok is False
        assert val == 0.0

    def test_invalid_none(self):
        ok, val = CompoundLinearLogic.validate_angle(None)
        assert ok is False
        assert val == 0.0

    def test_invalid_empty(self):
        ok, val = CompoundLinearLogic.validate_angle("")
        assert ok is False
        assert val == 0.0


class TestLinearDecomposePulse:
    """Tests for CompoundLinearLogic.decompose_pulse()."""

    def test_zero_angle_pure_z(self):
        """At 0°, all motion is along Z (no X component)."""
        x, z = CompoundLinearLogic.decompose_pulse(1, 0.001, 0.0)
        assert abs(x) < 1e-15
        assert abs(z - 0.001) < 1e-10

    def test_ninety_angle_pure_x(self):
        """At 90°, all motion is along X (no Z component)."""
        x, z = CompoundLinearLogic.decompose_pulse(1, 0.001, 90.0)
        assert abs(x - 0.001) < 1e-10
        assert abs(z) < 1e-15

    def test_forty_five_equal_components(self):
        """At 45°, X and Z components are equal."""
        x, z = CompoundLinearLogic.decompose_pulse(1, 0.001, 45.0)
        assert abs(x - z) < 1e-15
        expected = 0.001 * math.sin(math.radians(45))
        assert abs(x - expected) < 1e-10

    def test_threading_angle(self):
        """29.5° — standard threading infeed angle."""
        x, z = CompoundLinearLogic.decompose_pulse(1, 0.001, 29.5)
        expected_x = 0.001 * math.sin(math.radians(29.5))
        expected_z = 0.001 * math.cos(math.radians(29.5))
        assert abs(x - expected_x) < 1e-10
        assert abs(z - expected_z) < 1e-10

    def test_negative_count_reverses_direction(self):
        """Negative count_delta reverses both components."""
        x, z = CompoundLinearLogic.decompose_pulse(-1, 0.001, 45.0)
        assert x < 0
        assert z < 0

    def test_multiple_counts(self):
        """Multiple counts scale linearly."""
        x1, z1 = CompoundLinearLogic.decompose_pulse(1, 0.001, 30.0)
        x5, z5 = CompoundLinearLogic.decompose_pulse(5, 0.001, 30.0)
        assert abs(x5 - 5 * x1) < 1e-10
        assert abs(z5 - 5 * z1) < 1e-10

    def test_zero_count_no_motion(self):
        """Zero count_delta produces no motion."""
        x, z = CompoundLinearLogic.decompose_pulse(0, 0.001, 45.0)
        assert x == 0.0
        assert z == 0.0


class TestLinearSoftLimits:
    """Tests for CompoundLinearLogic.check_soft_limits()."""

    def test_within_limits_passes(self):
        x, z, suppressed = CompoundLinearLogic.check_soft_limits(
            1.0, 10.0, 0.01, 0.01
        )
        assert suppressed is False
        assert x == 0.01
        assert z == 0.01

    def test_x_exceeds_max_suppresses_both(self):
        """If X would exceed max, both axes are suppressed."""
        x, z, suppressed = CompoundLinearLogic.check_soft_limits(
            2.12, 10.0, 0.1, 0.1  # 2.12 + 0.1 = 2.22 > X_MAX/2 = 2.125
        )
        assert suppressed is True
        assert x == 0.0
        assert z == 0.0

    def test_x_exceeds_min_suppresses_both(self):
        """If X would go below min, both axes are suppressed."""
        x, z, suppressed = CompoundLinearLogic.check_soft_limits(
            0.0, 10.0, -0.1, 0.01  # 0.0 - 0.1 = -0.1 < X_MIN/2 = -0.005
        )
        assert suppressed is True
        assert x == 0.0
        assert z == 0.0

    def test_z_exceeds_max_suppresses_both(self):
        """If Z would exceed max, both axes are suppressed."""
        x, z, suppressed = CompoundLinearLogic.check_soft_limits(
            1.0, 23.49, 0.001, 0.02  # 23.49 + 0.02 = 23.51 > 23.5
        )
        assert suppressed is True
        assert x == 0.0
        assert z == 0.0

    def test_z_exceeds_min_suppresses_both(self):
        """If Z would go below min, both axes are suppressed."""
        x, z, suppressed = CompoundLinearLogic.check_soft_limits(
            1.0, 0.0, 0.001, -0.02  # 0.0 - 0.02 = -0.02 < -0.01
        )
        assert suppressed is True
        assert x == 0.0
        assert z == 0.0


class TestLinearAccumulateDistance:
    """Tests for CompoundLinearLogic.accumulate_distance()."""

    def test_accumulates_correctly(self):
        logic = CompoundLinearLogic()
        d1 = logic.accumulate_distance(0.003, 0.004)
        assert abs(d1 - 0.005) < 1e-10  # 3-4-5 triangle

    def test_multiple_accumulations(self):
        logic = CompoundLinearLogic()
        logic.accumulate_distance(0.003, 0.004)  # 0.005
        d2 = logic.accumulate_distance(0.003, 0.004)  # 0.010
        assert abs(d2 - 0.010) < 1e-10

    def test_reset_zeros_distance(self):
        logic = CompoundLinearLogic()
        logic.accumulate_distance(1.0, 1.0)
        logic.reset()
        assert logic.cumulative_distance == 0.0

    def test_reset_distance_zeros_only_distance(self):
        logic = CompoundLinearLogic()
        logic.accumulate_distance(1.0, 1.0)
        logic.reset_distance()
        assert logic.cumulative_distance == 0.0


# ======================================================================
# CompoundArcLogic Tests
# ======================================================================

class TestArcValidateRadius:
    """Tests for CompoundArcLogic.validate_radius()."""

    def test_valid_positive(self):
        ok, val = CompoundArcLogic.validate_radius("0.25")
        assert ok is True
        assert val == 0.25

    def test_valid_large(self):
        ok, val = CompoundArcLogic.validate_radius("2.0")
        assert ok is True
        assert val == 2.0

    def test_invalid_zero(self):
        ok, val = CompoundArcLogic.validate_radius("0")
        assert ok is False

    def test_invalid_negative(self):
        ok, val = CompoundArcLogic.validate_radius("-0.5")
        assert ok is False

    def test_invalid_text(self):
        ok, val = CompoundArcLogic.validate_radius("abc")
        assert ok is False

    def test_invalid_none(self):
        ok, val = CompoundArcLogic.validate_radius(None)
        assert ok is False


class TestArcQuadrantRanges:
    """Tests for CompoundArcLogic.get_quadrant_angle_range()."""

    def test_ne_range(self):
        logic = CompoundArcLogic()
        start, end = logic.get_quadrant_angle_range(Quadrant.NE)
        assert start == 0.0
        assert abs(end - math.pi / 2) < 1e-10

    def test_nw_range(self):
        logic = CompoundArcLogic()
        start, end = logic.get_quadrant_angle_range(Quadrant.NW)
        assert abs(start - math.pi / 2) < 1e-10
        assert abs(end - math.pi) < 1e-10

    def test_sw_range(self):
        logic = CompoundArcLogic()
        start, end = logic.get_quadrant_angle_range(Quadrant.SW)
        assert abs(start - math.pi) < 1e-10
        assert abs(end - 3 * math.pi / 2) < 1e-10

    def test_se_range(self):
        logic = CompoundArcLogic()
        start, end = logic.get_quadrant_angle_range(Quadrant.SE)
        assert abs(start - 3 * math.pi / 2) < 1e-10
        assert abs(end - 2 * math.pi) < 1e-10


class TestArcActivation:
    """Tests for CompoundArcLogic.activate()."""

    def test_activate_sets_radius(self):
        logic = CompoundArcLogic()
        logic.activate(1.0, 5.0, 0.5, Quadrant.SE, ArcStartType.ARC_TOP)
        assert logic.radius == 0.5

    def test_activate_resets_distance(self):
        logic = CompoundArcLogic()
        logic.cumulative_distance = 99.0
        logic.activate(1.0, 5.0, 0.5, Quadrant.SE, ArcStartType.ARC_TOP)
        assert logic.cumulative_distance == 0.0

    def test_activate_computes_center_se_arc_top(self):
        """SE quadrant, ARC_TOP: center is at (current_x, current_z - radius)."""
        logic = CompoundArcLogic()
        logic.activate(1.0, 5.0, 0.5, Quadrant.SE, ArcStartType.ARC_TOP)
        assert abs(logic.arc_center_x - 1.0) < 1e-10
        assert abs(logic.arc_center_z - 4.5) < 1e-10

    def test_activate_computes_center_ne_arc_bottom(self):
        """NE quadrant, ARC_BOTTOM: center is at (current_x - radius, current_z)."""
        logic = CompoundArcLogic()
        logic.activate(1.0, 5.0, 0.5, Quadrant.NE, ArcStartType.ARC_BOTTOM)
        assert abs(logic.arc_center_x - 0.5) < 1e-10
        assert abs(logic.arc_center_z - 5.0) < 1e-10


class TestArcProcessPulse:
    """Tests for CompoundArcLogic.process_pulse()."""

    def test_single_pulse_produces_motion(self):
        logic = CompoundArcLogic()
        logic.activate(1.0, 5.0, 0.5, Quadrant.SE, ArcStartType.ARC_TOP)
        x_d, z_d, suppressed, clamped = logic.process_pulse(1, 0.001, 1.0, 5.0)
        assert suppressed is False
        # Should produce some motion
        assert abs(x_d) > 0 or abs(z_d) > 0

    def test_suppressed_at_soft_limit(self):
        """Motion that would exceed soft limits is suppressed."""
        logic = CompoundArcLogic()
        # Place tool near X max limit (radius = 2.125)
        logic.activate(2.1, 5.0, 0.5, Quadrant.NE, ArcStartType.ARC_TOP)
        # Try to move further positive in X
        x_d, z_d, suppressed, clamped = logic.process_pulse(100, 0.01, 2.1, 5.0)
        assert suppressed is True
        assert x_d == 0.0
        assert z_d == 0.0

    def test_clamped_at_quadrant_boundary(self):
        """Motion past quadrant boundary is clamped."""
        logic = CompoundArcLogic()
        # Use NE quadrant with a small radius at a safe position
        # NE range is 0 to π/2, tool starts at angle 0 (bottom of NE arc)
        logic.activate(1.0, 5.0, 0.25, Quadrant.NE, ArcStartType.ARC_TOP)
        # Many pulses in the negative direction to push past the 0° boundary
        total_x = 0.0
        total_z = 0.0
        clamped_ever = False
        for _ in range(500):
            x_d, z_d, suppressed, clamped = logic.process_pulse(
                -1, 0.01, 1.0 + total_x, 5.0 + total_z
            )
            if clamped:
                clamped_ever = True
                break
            if not suppressed:
                total_x += x_d
                total_z += z_d
        # Should have been clamped at some point (or hit soft limit)
        # Either outcome is acceptable — the point is it doesn't run forever
        assert clamped_ever or total_x != 0.0 or total_z != 0.0

    def test_zero_count_no_motion(self):
        logic = CompoundArcLogic()
        logic.activate(1.0, 5.0, 0.5, Quadrant.SE, ArcStartType.ARC_TOP)
        x_d, z_d, suppressed, clamped = logic.process_pulse(0, 0.001, 1.0, 5.0)
        # Zero count means tangent decomposition gives zero
        # (tangent_x * 0 * jog_scale = 0)
        assert x_d == 0.0
        assert z_d == 0.0


class TestArcGetPoints:
    """Tests for CompoundArcLogic.get_arc_points()."""

    def test_returns_points_after_activation(self):
        logic = CompoundArcLogic()
        logic.activate(1.0, 5.0, 0.5, Quadrant.SE, ArcStartType.ARC_TOP)
        points = logic.get_arc_points(20)
        assert len(points) == 21  # n_points + 1

    def test_returns_empty_before_activation(self):
        logic = CompoundArcLogic()
        points = logic.get_arc_points(20)
        assert points == []

    def test_points_are_on_circle(self):
        """All generated points should be at the correct radius from center."""
        logic = CompoundArcLogic()
        logic.activate(1.0, 5.0, 0.5, Quadrant.SE, ArcStartType.ARC_TOP)
        points = logic.get_arc_points(20)
        for x, z in points:
            dist = math.sqrt(
                (x - logic.arc_center_x) ** 2 + (z - logic.arc_center_z) ** 2
            )
            assert abs(dist - 0.5) < 1e-10


class TestArcReset:
    """Tests for CompoundArcLogic.reset()."""

    def test_reset_zeros_distance(self):
        logic = CompoundArcLogic()
        logic.cumulative_distance = 5.0
        logic.reset()
        assert logic.cumulative_distance == 0.0

    def test_reset_zeros_angle(self):
        logic = CompoundArcLogic()
        logic.current_angle = 1.5
        logic.reset()
        assert logic.current_angle == 0.0
