"""Unit tests for CompoundSlideWidget activation toggle and interlocks.

Tests cover task 3.2 requirements:
- Activation toggles state and emits signal
- Deactivation resets distance display to 0.0000
- Interlock prevents activation when E-Stop active
- Interlock prevents activation when not homed
- Interlock prevents activation when not in MANUAL mode
- Interlock prevents activation when program running
- force_deactivate works during active mode
- Button style changes on state change

Validates: Requirements 1.1, 1.3, 1.5, 6.1, 6.2, 6.3, 6.5
"""

import sys
import os

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
    """Create a fresh CompoundSlideWidget for each test."""
    w = CompoundSlideWidget()
    return w


class TestToggleActive:
    """Test toggle_active() behavior."""

    def test_toggle_activates_when_interlocks_clear(self, widget):
        """Activation succeeds when all interlocks are safe."""
        assert not widget.is_active()
        widget.toggle_active()
        assert widget.is_active()

    def test_toggle_deactivates_when_active(self, widget):
        """Deactivation always succeeds."""
        widget.toggle_active()  # activate
        assert widget.is_active()
        widget.toggle_active()  # deactivate
        assert not widget.is_active()

    def test_toggle_emits_signal_on_activate(self, widget):
        """compound_activated signal emitted with True on activation."""
        received = []
        widget.compound_activated.connect(lambda v: received.append(v))
        widget.toggle_active()
        assert received == [True]

    def test_toggle_emits_signal_on_deactivate(self, widget):
        """compound_activated signal emitted with False on deactivation."""
        widget.toggle_active()  # activate first
        received = []
        widget.compound_activated.connect(lambda v: received.append(v))
        widget.toggle_active()
        assert received == [False]

    def test_button_text_active(self, widget):
        """Button shows 'ACTIVE' when activated."""
        widget.toggle_active()
        assert widget.btn_activate.text() == "ACTIVE"

    def test_button_text_off(self, widget):
        """Button shows 'OFF' when deactivated."""
        widget.toggle_active()
        widget.toggle_active()
        assert widget.btn_activate.text() == "OFF"


class TestDeactivationResets:
    """Test that deactivation resets cumulative distance."""

    def test_distance_resets_on_deactivate(self, widget):
        """Distance display resets to 0.0000 on deactivation."""
        widget.toggle_active()
        # Simulate some distance accumulation
        widget.lbl_distance.setText("1.2345\"")
        widget.toggle_active()  # deactivate
        assert widget.lbl_distance.text() == "0.0000\""

    def test_logic_resets_on_deactivate(self, widget):
        """Logic cumulative_distance resets on deactivation."""
        widget.toggle_active()
        widget._logic.cumulative_distance = 5.0
        widget.toggle_active()  # deactivate
        assert widget._logic.cumulative_distance == 0.0


class TestInterlockPreventsActivation:
    """Test that interlocks prevent activation."""

    def test_estop_prevents_activation(self, widget):
        """E-Stop active prevents activation."""
        widget.set_interlock_state(estop=True)
        widget.toggle_active()
        assert not widget.is_active()

    def test_not_homed_prevents_activation(self, widget):
        """Axes not homed prevents activation."""
        widget.set_interlock_state(homed=False)
        widget.toggle_active()
        assert not widget.is_active()

    def test_not_manual_mode_prevents_activation(self, widget):
        """Not in MANUAL mode prevents activation."""
        widget.set_interlock_state(manual_mode=False)
        widget.toggle_active()
        assert not widget.is_active()

    def test_program_running_prevents_activation(self, widget):
        """Program running prevents activation."""
        widget.set_interlock_state(program_idle=False)
        widget.toggle_active()
        assert not widget.is_active()

    def test_machine_disabled_prevents_activation(self, widget):
        """Machine disabled prevents activation."""
        widget.set_interlock_state(machine_enabled=False)
        widget.toggle_active()
        assert not widget.is_active()

    def test_button_unchecked_on_failed_activation(self, widget):
        """Button stays unchecked when activation is blocked."""
        widget.set_interlock_state(estop=True)
        widget.toggle_active()
        assert not widget.btn_activate.isChecked()

    def test_multiple_interlocks_prevent_activation(self, widget):
        """Multiple interlock violations still prevent activation."""
        widget.set_interlock_state(estop=True, homed=False)
        widget.toggle_active()
        assert not widget.is_active()


class TestForceDeactivate:
    """Test force_deactivate() behavior."""

    def test_force_deactivate_when_active(self, widget):
        """force_deactivate deactivates an active widget."""
        widget.toggle_active()
        assert widget.is_active()
        widget.force_deactivate("E-Stop")
        assert not widget.is_active()

    def test_force_deactivate_resets_distance(self, widget):
        """force_deactivate resets distance display."""
        widget.toggle_active()
        widget.lbl_distance.setText("2.5000\"")
        widget.force_deactivate("Mode change")
        assert widget.lbl_distance.text() == "0.0000\""

    def test_force_deactivate_emits_warning(self, widget):
        """force_deactivate emits limit_warning with reason."""
        widget.toggle_active()
        received = []
        widget.limit_warning.connect(lambda msg: received.append(msg))
        widget.force_deactivate("E-Stop")
        assert len(received) == 1
        assert "E-Stop" in received[0]

    def test_force_deactivate_no_op_when_inactive(self, widget):
        """force_deactivate does nothing when already inactive."""
        assert not widget.is_active()
        # Should not raise or emit signals
        widget.force_deactivate("test")
        assert not widget.is_active()

    def test_force_deactivate_emits_compound_activated_false(self, widget):
        """force_deactivate emits compound_activated(False)."""
        widget.toggle_active()
        received = []
        widget.compound_activated.connect(lambda v: received.append(v))
        widget.force_deactivate("Machine disabled")
        assert received == [False]

    def test_force_deactivate_no_warning_without_reason(self, widget):
        """force_deactivate with empty reason doesn't emit limit_warning."""
        widget.toggle_active()
        received = []
        widget.limit_warning.connect(lambda msg: received.append(msg))
        widget.force_deactivate("")
        assert received == []


class TestCheckInterlocks:
    """Test check_interlocks() return values."""

    def test_all_clear_returns_ok(self, widget):
        """All interlocks clear returns (True, '')."""
        ok, reason = widget.check_interlocks()
        assert ok is True
        assert reason == ""

    def test_estop_returns_reason(self, widget):
        """E-Stop returns descriptive reason."""
        widget.set_interlock_state(estop=True)
        ok, reason = widget.check_interlocks()
        assert ok is False
        assert "E-Stop" in reason

    def test_not_homed_returns_reason(self, widget):
        """Not homed returns descriptive reason."""
        widget.set_interlock_state(homed=False)
        ok, reason = widget.check_interlocks()
        assert ok is False
        assert "homed" in reason.lower()

    def test_not_manual_returns_reason(self, widget):
        """Not in MANUAL mode returns descriptive reason."""
        widget.set_interlock_state(manual_mode=False)
        ok, reason = widget.check_interlocks()
        assert ok is False
        assert "MANUAL" in reason


class TestSetInterlockState:
    """Test set_interlock_state() updates correctly."""

    def test_set_estop(self, widget):
        """Setting estop updates internal state."""
        widget.set_interlock_state(estop=True)
        assert widget._interlocks["estop"] is True

    def test_set_homed(self, widget):
        """Setting homed updates internal state."""
        widget.set_interlock_state(homed=False)
        assert widget._interlocks["homed"] is False

    def test_partial_update(self, widget):
        """Setting one interlock doesn't affect others."""
        widget.set_interlock_state(estop=True)
        assert widget._interlocks["homed"] is True
        assert widget._interlocks["manual_mode"] is True

    def test_none_values_ignored(self, widget):
        """None values don't change state."""
        widget.set_interlock_state(estop=True)
        widget.set_interlock_state(estop=None)
        assert widget._interlocks["estop"] is True


class TestAngleInputValidation:
    """Test angle input validation and red border flash (task 3.3).

    Validates: Requirements 2.5, 2.6
    """

    def test_valid_angle_updates_internal_state(self, widget):
        """Valid angle input updates self._angle."""
        widget.input_angle.setText("30.0")
        widget._on_angle_changed()
        assert widget._angle == 30.0

    def test_valid_angle_boundary_zero(self, widget):
        """Angle 0.0 is valid (pure Z motion)."""
        widget.input_angle.setText("0.0")
        widget._on_angle_changed()
        assert widget._angle == 0.0

    def test_valid_angle_boundary_ninety(self, widget):
        """Angle 90.0 is valid (pure X motion)."""
        widget.input_angle.setText("90.0")
        widget._on_angle_changed()
        assert widget._angle == 90.0

    def test_invalid_angle_reverts_to_previous(self, widget):
        """Invalid input reverts QLineEdit to previous valid value."""
        widget._angle = 45.0
        widget.input_angle.setText("abc")
        widget._on_angle_changed()
        assert widget._angle == 45.0
        assert widget.input_angle.text() == "45.0"

    def test_out_of_range_high_reverts(self, widget):
        """Angle > 90 reverts to previous valid value."""
        widget._angle = 30.0
        widget.input_angle.setText("91.0")
        widget._on_angle_changed()
        assert widget._angle == 30.0
        assert widget.input_angle.text() == "30.0"

    def test_out_of_range_negative_reverts(self, widget):
        """Negative angle reverts to previous valid value."""
        widget._angle = 60.0
        widget.input_angle.setText("-5.0")
        widget._on_angle_changed()
        assert widget._angle == 60.0
        assert widget.input_angle.text() == "60.0"

    def test_empty_input_reverts(self, widget):
        """Empty input reverts to previous valid value."""
        widget._angle = 45.0
        widget.input_angle.setText("")
        widget._on_angle_changed()
        assert widget._angle == 45.0
        assert widget.input_angle.text() == "45.0"

    def test_invalid_input_flashes_red_border(self, widget):
        """Invalid input sets red border style on the input."""
        widget.input_angle.setText("invalid")
        widget._on_angle_changed()
        style = widget.input_angle.styleSheet()
        # Should contain the accent (red) color for the border
        assert "#C0392B" in style or "accent" in style.lower()

    def test_restore_style_clears_stylesheet(self, widget):
        """_restore_angle_style clears the error style."""
        widget.input_angle.setStyleSheet("border: 2px solid red;")
        widget._restore_angle_style()
        assert widget.input_angle.styleSheet() == ""

    def test_angle_changeable_while_active(self, widget):
        """Angle can be changed while compound mode is active."""
        widget.toggle_active()
        assert widget.is_active()
        widget.input_angle.setText("60.0")
        widget._on_angle_changed()
        assert widget._angle == 60.0

    def test_get_angle_returns_current_value(self, widget):
        """get_angle() returns the current validated angle."""
        assert widget.get_angle() == 45.0
        widget.input_angle.setText("30.0")
        widget._on_angle_changed()
        assert widget.get_angle() == 30.0

    def test_whitespace_stripped(self, widget):
        """Leading/trailing whitespace is stripped before validation."""
        widget.input_angle.setText("  30.0  ")
        widget._on_angle_changed()
        assert widget._angle == 30.0


class TestMPGSelection:
    """Test MPG selector logic (task 3.3).

    Validates: Requirements 3.1, 3.4
    """

    def test_default_mpg_is_x(self, widget):
        """Default MPG selection is X."""
        assert widget._mpg_selection == "x"

    def test_select_z_mpg(self, widget):
        """Selecting index 1 sets MPG to Z."""
        widget._on_mpg_changed(1)
        assert widget._mpg_selection == "z"

    def test_select_x_mpg(self, widget):
        """Selecting index 0 sets MPG to X."""
        widget._on_mpg_changed(1)  # switch to Z first
        widget._on_mpg_changed(0)  # back to X
        assert widget._mpg_selection == "x"

    def test_combo_default_index(self, widget):
        """Combo box defaults to index 0 (X MPG)."""
        assert widget.combo_mpg.currentIndex() == 0
