"""Unit tests for CompoundSlideWidget.update_compound() method (task 3.4).

Tests cover:
- Returns (0, 0) when inactive
- Selects correct encoder based on MPG selection
- Computes count delta correctly
- Returns (0, 0) when no encoder change
- Calls decompose_pulse and check_soft_limits
- Updates cumulative distance display
- Emits limit_warning when pulse is suppressed
- Returns correct integer jog counts with fractional accumulation
- Accumulators reset on deactivation

Validates: Requirements 4.1, 4.2, 4.5, 5.4, 7.1
"""

import sys
import os
import math

# Add gui directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from PyQt5.QtWidgets import QApplication

# Ensure QApplication exists for widget tests
app = QApplication.instance()
if app is None:
    app = QApplication([])

from compound_slide_widget import CompoundSlideWidget


@pytest.fixture
def widget():
    """Create a fresh CompoundSlideWidget in active state for testing."""
    w = CompoundSlideWidget()
    w.toggle_active()  # activate
    return w


@pytest.fixture
def inactive_widget():
    """Create a fresh CompoundSlideWidget in inactive state."""
    return CompoundSlideWidget()


class TestInactiveReturnsZero:
    """When inactive, update_compound returns (0, 0)."""

    def test_returns_zero_when_inactive(self, inactive_widget):
        """Inactive widget returns (0, 0) regardless of inputs."""
        result = inactive_widget.update_compound(1.0, 5.0, 100, 200, 0.001)
        assert result == (0, 0)

    def test_returns_zero_after_deactivation(self, widget):
        """After deactivation, returns (0, 0)."""
        widget.toggle_active()  # deactivate
        result = widget.update_compound(1.0, 5.0, 100, 200, 0.001)
        assert result == (0, 0)


class TestMPGSelection:
    """Correct encoder is selected based on MPG selection."""

    def test_x_mpg_uses_x_counts(self, widget):
        """When MPG selection is X, uses mpg_x_counts."""
        widget._mpg_selection = "x"
        widget._last_counts = 0
        # X counts = 10, Z counts = 99 — should use X
        widget.update_compound(2.0, 10.0, 10, 99, 0.001)
        # _last_counts should be updated to the X value
        assert widget._last_counts == 10

    def test_z_mpg_uses_z_counts(self, widget):
        """When MPG selection is Z, uses mpg_z_counts."""
        widget._mpg_selection = "z"
        widget._last_counts = 0
        # X counts = 99, Z counts = 5 — should use Z
        widget.update_compound(2.0, 10.0, 99, 5, 0.001)
        assert widget._last_counts == 5


class TestCountDelta:
    """Count delta computation."""

    def test_zero_delta_returns_zero(self, widget):
        """No encoder change returns (0, 0)."""
        widget._last_counts = 50
        result = widget.update_compound(2.0, 10.0, 50, 0, 0.001)
        assert result == (0, 0)

    def test_positive_delta(self, widget):
        """Positive delta produces motion."""
        widget._last_counts = 0
        widget._angle = 45.0
        result = widget.update_compound(2.0, 10.0, 1, 0, 0.001)
        # At 45°, sin and cos are equal, so x and z should be equal
        # 1 count * 0.001 * sin(45) = 0.000707...
        # Converting back: 0.000707 / 0.001 = 0.707 counts
        # int(0.707) = 0, so first pulse accumulates but doesn't output
        assert result == (0, 0)  # fractional, not yet 1 full count

    def test_larger_delta_produces_output(self, widget):
        """Larger delta produces integer output counts."""
        widget._last_counts = 0
        widget._angle = 45.0
        # 2 counts at 45° with scale 0.001:
        # x_delta = 2 * 0.001 * sin(45) = 0.001414
        # x_accum = 0.001414 / 0.001 = 1.414 → int = 1
        result = widget.update_compound(2.0, 10.0, 2, 0, 0.001)
        assert result == (1, 1)


class TestSoftLimitSuppression:
    """Soft limit enforcement."""

    def test_suppressed_returns_zero(self, widget):
        """When soft limit exceeded, returns (0, 0)."""
        widget._last_counts = 0
        widget._angle = 0.0  # pure Z motion
        # Position at Z max (23.5), moving positive should be suppressed
        result = widget.update_compound(2.0, 23.5, 1, 0, 0.1)
        assert result == (0, 0)

    def test_suppressed_emits_limit_warning(self, widget):
        """Suppressed pulse emits limit_warning signal."""
        widget._last_counts = 0
        widget._angle = 0.0  # pure Z motion
        received = []
        widget.limit_warning.connect(lambda msg: received.append(msg))
        # Position at Z max, moving positive
        widget.update_compound(2.0, 23.5, 1, 0, 0.1)
        assert len(received) == 1
        assert "soft limit" in received[0].lower()

    def test_not_suppressed_no_warning(self, widget):
        """Non-suppressed pulse does not emit limit_warning."""
        widget._last_counts = 0
        widget._angle = 45.0
        received = []
        widget.limit_warning.connect(lambda msg: received.append(msg))
        # Position well within limits
        widget.update_compound(2.0, 10.0, 1, 0, 0.001)
        assert received == []


class TestDistanceDisplay:
    """Cumulative distance display updates."""

    def test_distance_updates_on_motion(self, widget):
        """Distance label updates after successful motion."""
        widget._last_counts = 0
        widget._angle = 45.0
        widget.update_compound(2.0, 10.0, 1, 0, 0.001)
        # Should show non-zero distance
        text = widget.lbl_distance.text()
        assert text != "0.0000\""
        assert text.endswith("\"")

    def test_distance_format_four_decimals(self, widget):
        """Distance display shows exactly 4 decimal places."""
        widget._last_counts = 0
        widget._angle = 45.0
        widget.update_compound(2.0, 10.0, 1, 0, 0.001)
        text = widget.lbl_distance.text()
        # Remove the trailing " and check decimal places
        numeric = text.rstrip("\"")
        parts = numeric.split(".")
        assert len(parts) == 2
        assert len(parts[1]) == 4

    def test_distance_accumulates_over_cycles(self, widget):
        """Distance accumulates across multiple update cycles."""
        widget._last_counts = 0
        widget._angle = 45.0
        widget.update_compound(2.0, 10.0, 1, 0, 0.001)
        dist1 = widget._logic.cumulative_distance

        widget.update_compound(2.0, 10.0, 2, 0, 0.001)
        dist2 = widget._logic.cumulative_distance
        assert dist2 > dist1

    def test_distance_not_updated_when_suppressed(self, widget):
        """Distance does not change when pulse is suppressed."""
        widget._last_counts = 0
        widget._angle = 0.0
        # First, do a valid motion
        widget.update_compound(2.0, 10.0, 1, 0, 0.001)
        dist_before = widget._logic.cumulative_distance

        # Now try a motion that will be suppressed (at Z max)
        widget.update_compound(2.0, 23.5, 2, 0, 0.1)
        dist_after = widget._logic.cumulative_distance
        assert dist_after == dist_before


class TestFractionalAccumulation:
    """Fractional count accumulation for HAL output."""

    def test_fractional_counts_accumulate(self, widget):
        """Sub-count fractions accumulate over multiple cycles."""
        widget._last_counts = 0
        widget._angle = 45.0
        # sin(45) ≈ 0.707, so 1 count produces 0.707 output counts
        # First call: accum = 0.707, output = 0
        r1 = widget.update_compound(2.0, 10.0, 1, 0, 0.001)
        assert r1 == (0, 0)

        # Second call: delta = 1, accum = 0.707 + 0.707 = 1.414, output = 1
        r2 = widget.update_compound(2.0, 10.0, 2, 0, 0.001)
        assert r2 == (1, 1)

    def test_accumulators_reset_on_deactivate(self, widget):
        """Accumulators reset to 0 on deactivation."""
        widget._x_accum = 0.5
        widget._z_accum = 0.3
        widget.toggle_active()  # deactivate
        assert widget._x_accum == 0.0
        assert widget._z_accum == 0.0

    def test_accumulators_reset_on_activate(self):
        """Accumulators reset to 0 on activation."""
        w = CompoundSlideWidget()
        w._x_accum = 0.5
        w._z_accum = 0.3
        w.toggle_active()  # activate
        assert w._x_accum == 0.0
        assert w._z_accum == 0.0

    def test_pure_z_motion_at_zero_degrees(self, widget):
        """At 0°, all motion is Z (sin(0)=0, cos(0)=1)."""
        widget._last_counts = 0
        widget._angle = 0.0
        # 1 count at 0°: x=0, z=1*0.001*1=0.001
        # x_accum = 0/0.001 = 0, z_accum = 0.001/0.001 = 1
        result = widget.update_compound(2.0, 10.0, 1, 0, 0.001)
        assert result == (0, 1)

    def test_pure_x_motion_at_ninety_degrees(self, widget):
        """At 90°, all motion is X (sin(90)=1, cos(90)=0)."""
        widget._last_counts = 0
        widget._angle = 90.0
        # 1 count at 90°: x=1*0.001*1=0.001, z≈0
        # x_accum = 0.001/0.001 = 1, z_accum ≈ 0
        result = widget.update_compound(2.0, 10.0, 1, 0, 0.001)
        assert result == (1, 0)

    def test_negative_delta_produces_negative_output(self, widget):
        """Negative encoder delta produces negative jog counts."""
        widget._last_counts = 10
        widget._angle = 0.0  # pure Z
        # delta = 8 - 10 = -2, z = -2 * 0.001 * cos(0) = -0.002
        # z_accum = -0.002 / 0.001 = -2
        result = widget.update_compound(2.0, 10.0, 8, 0, 0.001)
        assert result == (0, -2)

    def test_zero_jog_scale_no_crash(self, widget):
        """Zero jog_scale doesn't crash (guard against division by zero)."""
        widget._last_counts = 0
        # jog_scale = 0 should not crash
        result = widget.update_compound(2.0, 10.0, 1, 0, 0.0)
        # With scale 0, decompose_pulse returns (0, 0), not suppressed
        # but accumulators don't update (guarded by if jog_scale > 0)
        assert result == (0, 0)
