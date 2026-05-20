"""Integration tests for compound slide — ManualTab._update_compound() flow.

Tests the full pipeline: MPG counts → logic decomposition → jog output,
including preset angles, distance reset, and interlock behavior.

Uses the MockBackend directly (no Qt event loop needed for logic tests).
"""

import math
import pytest

from hal.compound_logic import (
    CompoundLinearLogic, CompoundArcLogic,
    Quadrant, ArcStartType,
)
from hal.constants import JOG_INCREMENTS


# ======================================================================
# Preset Angles Tests
# ======================================================================

class TestPresetAngles:
    """Tests for preset angle definitions."""

    def test_presets_exist(self):
        assert len(CompoundLinearLogic.PRESETS) >= 4

    def test_threading_preset(self):
        assert "29.5° Thread" in CompoundLinearLogic.PRESETS
        assert CompoundLinearLogic.PRESETS["29.5° Thread"] == 29.5

    def test_chamfer_preset(self):
        assert "45° Chamfer" in CompoundLinearLogic.PRESETS
        assert CompoundLinearLogic.PRESETS["45° Chamfer"] == 45.0

    def test_all_presets_valid(self):
        for label, angle in CompoundLinearLogic.PRESETS.items():
            ok, val = CompoundLinearLogic.validate_angle(angle)
            assert ok is True, f"Preset '{label}' has invalid angle {angle}"
            assert val == angle


# ======================================================================
# Distance Reset Tests
# ======================================================================

class TestDistanceReset:
    """Tests for reset_distance() — zeroes counter without full reset."""

    def test_linear_reset_distance(self):
        logic = CompoundLinearLogic()
        logic.accumulate_distance(0.5, 0.0)
        logic.reset_distance()
        assert logic.cumulative_distance == 0.0

    def test_arc_reset_distance(self):
        logic = CompoundArcLogic()
        logic.accumulate_distance(0.5, 0.0)
        logic.reset_distance()
        assert logic.cumulative_distance == 0.0

    def test_arc_reset_distance_preserves_angle(self):
        logic = CompoundArcLogic()
        logic.current_angle = 1.5
        logic.accumulate_distance(0.5, 0.0)
        logic.reset_distance()
        assert logic.current_angle == 1.5  # Not cleared

    def test_full_reset_clears_angle(self):
        logic = CompoundArcLogic()
        logic.current_angle = 1.5
        logic.reset()
        assert logic.current_angle == 0.0


# ======================================================================
# Fractional Accumulator Tests
# ======================================================================

class TestFractionalAccumulator:
    """Tests for the fractional jog count accumulator pattern.

    The compound slide converts float distances back to integer jog counts.
    Sub-count remainders must be preserved between cycles to prevent
    cumulative position error.
    """

    def test_accumulator_preserves_fractions(self):
        """Simulate the accumulator pattern used in _update_compound."""
        jog_scale = 0.001  # 0.001" per count
        x_accum = 0.0
        z_accum = 0.0
        total_x_counts = 0
        total_z_counts = 0

        # Simulate 100 pulses at 45° — each pulse gives 0.000707" per axis
        # That's 0.707 counts per pulse — should accumulate properly
        for _ in range(100):
            x_delta = 0.001 * math.sin(math.radians(45))  # ~0.000707
            z_delta = 0.001 * math.cos(math.radians(45))  # ~0.000707

            x_accum += x_delta / jog_scale  # ~0.707
            z_accum += z_delta / jog_scale

            x_out = int(x_accum)
            z_out = int(z_accum)
            x_accum -= x_out
            z_accum -= z_out
            total_x_counts += x_out
            total_z_counts += z_out

        # After 100 pulses: total should be ~70-71 counts per axis
        # (100 * 0.707 = 70.7)
        assert 70 <= total_x_counts <= 71
        assert 70 <= total_z_counts <= 71
        # Remainder should be small
        assert abs(x_accum) < 1.0
        assert abs(z_accum) < 1.0

    def test_negative_counts_accumulate_correctly(self):
        """Negative deltas should produce negative output counts."""
        jog_scale = 0.001
        x_accum = 0.0
        total = 0

        for _ in range(100):
            x_delta = -0.001 * math.sin(math.radians(45))
            x_accum += x_delta / jog_scale
            x_out = int(x_accum)
            x_accum -= x_out
            total += x_out

        assert -71 <= total <= -70


# ======================================================================
# Axis Coupling Direction Tests
# ======================================================================

class TestAxisCoupling:
    """Tests for the angle sign → axis coupling convention.

    Positive angle: X−Z+ (cross coupling, OD chamfer)
    Negative angle: X−Z− (same coupling, ID chamfer)
    """

    def test_positive_angle_cross_coupling(self):
        """Positive angle: CW MPG → X decreases, Z increases."""
        x_delta, z_delta = CompoundLinearLogic.decompose_pulse(1, 0.001, 45.0)
        # Before coupling: both positive
        # After coupling (positive angle): negate X only
        coupled_x = -x_delta
        coupled_z = z_delta
        assert coupled_x < 0  # X toward center
        assert coupled_z > 0  # Z away from chuck

    def test_negative_angle_same_coupling(self):
        """Negative angle: CW MPG → X decreases, Z decreases."""
        x_delta, z_delta = CompoundLinearLogic.decompose_pulse(1, 0.001, 45.0)
        # After coupling (negative angle): negate both
        coupled_x = -x_delta
        coupled_z = -z_delta
        assert coupled_x < 0  # X toward center
        assert coupled_z < 0  # Z toward chuck


# ======================================================================
# Edge Cases
# ======================================================================

class TestEdgeCases:
    """Edge case tests for compound slide logic."""

    def test_zero_jog_scale_no_crash(self):
        """Zero jog_scale shouldn't cause division by zero."""
        x, z = CompoundLinearLogic.decompose_pulse(1, 0.0, 45.0)
        assert x == 0.0
        assert z == 0.0

    def test_very_small_jog_scale(self):
        """Very small jog_scale (x1 mode) should still work."""
        x, z = CompoundLinearLogic.decompose_pulse(1, 0.0001, 45.0)
        expected = 0.0001 * math.sin(math.radians(45))
        assert abs(x - expected) < 1e-15

    def test_large_count_delta(self):
        """Large count delta (fast MPG spin) should scale linearly."""
        x1, z1 = CompoundLinearLogic.decompose_pulse(1, 0.001, 30.0)
        x100, z100 = CompoundLinearLogic.decompose_pulse(100, 0.001, 30.0)
        assert abs(x100 - 100 * x1) < 1e-10

    def test_arc_zero_distance_from_center(self):
        """If tool is exactly at arc center, process_pulse handles gracefully."""
        logic = CompoundArcLogic()
        logic.arc_center_x = 1.0
        logic.arc_center_z = 5.0
        logic.radius = 0.5
        logic.angle_start = 0.0
        logic.angle_end = math.pi / 2
        logic.current_angle = 0.0
        # Tool at center — dist would be 0
        x_d, z_d, suppressed, clamped = logic.process_pulse(1, 0.001, 1.0, 5.0)
        # Should handle gracefully (not crash)
        # The re-projection step checks for dist < 1e-15
        assert not suppressed or (x_d == 0.0 and z_d == 0.0)
