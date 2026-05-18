"""Verification tests for CompoundSlideLogic pure computation class.

Exercises all key methods to confirm correctness:
- validate_angle: range checking and type handling
- decompose_pulse: trigonometric decomposition
- check_soft_limits: all-or-nothing suppression
- accumulate_distance: Euclidean distance tracking
- reset: zeroing cumulative distance
"""

import math
import pytest
import sys
import os

# Add parent directory to path so we can import compound_slide_logic
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from compound_slide_logic import CompoundSlideLogic


class TestValidateAngle:
    """Test angle validation accepts only [0.0, 90.0] range."""

    def test_valid_zero(self):
        valid, val = CompoundSlideLogic.validate_angle(0.0)
        assert valid is True
        assert val == 0.0

    def test_valid_ninety(self):
        valid, val = CompoundSlideLogic.validate_angle(90.0)
        assert valid is True
        assert val == 90.0

    def test_valid_midrange(self):
        valid, val = CompoundSlideLogic.validate_angle(45.0)
        assert valid is True
        assert val == 45.0

    def test_valid_thirty(self):
        """30 degrees is a common threading infeed angle."""
        valid, val = CompoundSlideLogic.validate_angle(30.0)
        assert valid is True
        assert val == 30.0

    def test_valid_string_input(self):
        valid, val = CompoundSlideLogic.validate_angle("45.0")
        assert valid is True
        assert val == 45.0

    def test_invalid_negative(self):
        valid, val = CompoundSlideLogic.validate_angle(-1.0)
        assert valid is False
        assert val == 0.0

    def test_invalid_over_ninety(self):
        valid, val = CompoundSlideLogic.validate_angle(90.1)
        assert valid is False
        assert val == 0.0

    def test_invalid_string(self):
        valid, val = CompoundSlideLogic.validate_angle("abc")
        assert valid is False
        assert val == 0.0

    def test_invalid_none(self):
        valid, val = CompoundSlideLogic.validate_angle(None)
        assert valid is False
        assert val == 0.0

    def test_invalid_empty_string(self):
        valid, val = CompoundSlideLogic.validate_angle("")
        assert valid is False
        assert val == 0.0


class TestDecomposePulse:
    """Test motion decomposition matches trig formula."""

    def setup_method(self):
        self.logic = CompoundSlideLogic(
            x_min=-0.01, x_max=4.25, z_min=-0.01, z_max=23.5
        )

    def test_zero_angle_pure_z(self):
        """Angle=0 degrees should produce pure Z motion (x_dist == 0)."""
        x, z = self.logic.decompose_pulse(1, 0.001, 0.0)
        assert x == pytest.approx(0.0, abs=1e-10)
        assert z == pytest.approx(0.001, abs=1e-10)

    def test_ninety_angle_pure_x(self):
        """Angle=90 degrees should produce pure X motion (z_dist == 0)."""
        x, z = self.logic.decompose_pulse(1, 0.001, 90.0)
        assert x == pytest.approx(0.001, abs=1e-10)
        assert z == pytest.approx(0.0, abs=1e-10)

    def test_forty_five_equal_components(self):
        """Angle=45 degrees should produce equal X and Z magnitudes."""
        x, z = self.logic.decompose_pulse(1, 0.001, 45.0)
        assert abs(x) == pytest.approx(abs(z), rel=1e-10)

    def test_thirty_degrees_threading(self):
        """Angle=30 degrees (threading infeed) produces correct ratio."""
        x, z = self.logic.decompose_pulse(1, 0.001, 30.0)
        expected_x = 0.001 * math.sin(math.radians(30.0))
        expected_z = 0.001 * math.cos(math.radians(30.0))
        assert x == pytest.approx(expected_x, rel=1e-10)
        assert z == pytest.approx(expected_z, rel=1e-10)

    def test_negative_count_reverses_direction(self):
        """Negative count_delta should reverse both components."""
        x_pos, z_pos = self.logic.decompose_pulse(1, 0.001, 45.0)
        x_neg, z_neg = self.logic.decompose_pulse(-1, 0.001, 45.0)
        assert x_neg == pytest.approx(-x_pos, rel=1e-10)
        assert z_neg == pytest.approx(-z_pos, rel=1e-10)

    def test_zero_count_zero_motion(self):
        """count_delta=0 should produce zero motion."""
        x, z = self.logic.decompose_pulse(0, 0.001, 45.0)
        assert x == 0.0
        assert z == 0.0

    def test_multiple_counts(self):
        """Multiple counts should scale linearly."""
        x1, z1 = self.logic.decompose_pulse(1, 0.001, 45.0)
        x5, z5 = self.logic.decompose_pulse(5, 0.001, 45.0)
        assert x5 == pytest.approx(5 * x1, rel=1e-10)
        assert z5 == pytest.approx(5 * z1, rel=1e-10)

    def test_jog_scale_scaling(self):
        """Different jog scales should scale proportionally."""
        x_small, z_small = self.logic.decompose_pulse(1, 0.0001, 45.0)
        x_large, z_large = self.logic.decompose_pulse(1, 0.001, 45.0)
        assert x_large == pytest.approx(10 * x_small, rel=1e-10)
        assert z_large == pytest.approx(10 * z_small, rel=1e-10)


class TestCheckSoftLimits:
    """Test soft limit suppression is all-or-nothing."""

    def setup_method(self):
        self.logic = CompoundSlideLogic(
            x_min=-0.01, x_max=4.25, z_min=-0.01, z_max=23.5
        )

    def test_within_limits_passes(self):
        """Motion within limits should pass through unchanged."""
        x, z, suppressed = self.logic.check_soft_limits(2.0, 10.0, 0.001, 0.001)
        assert x == 0.001
        assert z == 0.001
        assert suppressed is False

    def test_x_exceeds_max_suppresses_both(self):
        """X exceeding max should suppress BOTH axes."""
        x, z, suppressed = self.logic.check_soft_limits(4.24, 10.0, 0.02, 0.001)
        assert x == 0.0
        assert z == 0.0
        assert suppressed is True

    def test_x_exceeds_min_suppresses_both(self):
        """X below min should suppress BOTH axes."""
        x, z, suppressed = self.logic.check_soft_limits(0.0, 10.0, -0.02, 0.001)
        assert x == 0.0
        assert z == 0.0
        assert suppressed is True

    def test_z_exceeds_max_suppresses_both(self):
        """Z exceeding max should suppress BOTH axes."""
        x, z, suppressed = self.logic.check_soft_limits(2.0, 23.49, 0.001, 0.02)
        assert x == 0.0
        assert z == 0.0
        assert suppressed is True

    def test_z_exceeds_min_suppresses_both(self):
        """Z below min should suppress BOTH axes."""
        x, z, suppressed = self.logic.check_soft_limits(2.0, 0.0, 0.001, -0.02)
        assert x == 0.0
        assert z == 0.0
        assert suppressed is True

    def test_exactly_at_limit_boundary_allowed(self):
        """Position exactly at soft limit boundary should be allowed."""
        # Moving to exactly x_max
        x, z, suppressed = self.logic.check_soft_limits(4.24, 10.0, 0.01, 0.0)
        assert suppressed is False
        assert x == 0.01
        assert z == 0.0

    def test_exactly_at_min_boundary_allowed(self):
        """Position exactly at min boundary should be allowed."""
        x, z, suppressed = self.logic.check_soft_limits(0.0, 0.0, -0.01, -0.01)
        assert suppressed is False


class TestAccumulateDistance:
    """Test cumulative distance equals sum of Euclidean pulse magnitudes."""

    def setup_method(self):
        self.logic = CompoundSlideLogic(
            x_min=-0.01, x_max=4.25, z_min=-0.01, z_max=23.5
        )

    def test_single_pulse(self):
        """Single pulse distance should be sqrt(x^2 + z^2)."""
        dist = self.logic.accumulate_distance(0.003, 0.004)
        assert dist == pytest.approx(0.005, rel=1e-10)

    def test_cumulative_multiple_pulses(self):
        """Multiple pulses should accumulate."""
        self.logic.accumulate_distance(0.003, 0.004)  # 0.005
        dist = self.logic.accumulate_distance(0.003, 0.004)  # 0.005
        assert dist == pytest.approx(0.010, rel=1e-10)

    def test_zero_motion_no_accumulation(self):
        """Zero motion should not add to distance."""
        self.logic.accumulate_distance(0.003, 0.004)  # 0.005
        dist = self.logic.accumulate_distance(0.0, 0.0)
        assert dist == pytest.approx(0.005, rel=1e-10)

    def test_negative_deltas_still_positive_distance(self):
        """Negative deltas should still produce positive distance."""
        dist = self.logic.accumulate_distance(-0.003, -0.004)
        assert dist == pytest.approx(0.005, rel=1e-10)


class TestReset:
    """Test reset zeros cumulative distance."""

    def test_reset_zeros_distance(self):
        logic = CompoundSlideLogic(
            x_min=-0.01, x_max=4.25, z_min=-0.01, z_max=23.5
        )
        logic.accumulate_distance(0.003, 0.004)
        assert logic.cumulative_distance > 0
        logic.reset()
        assert logic.cumulative_distance == 0.0

    def test_reset_allows_fresh_accumulation(self):
        logic = CompoundSlideLogic(
            x_min=-0.01, x_max=4.25, z_min=-0.01, z_max=23.5
        )
        logic.accumulate_distance(0.003, 0.004)
        logic.reset()
        dist = logic.accumulate_distance(0.006, 0.008)
        assert dist == pytest.approx(0.01, rel=1e-10)
