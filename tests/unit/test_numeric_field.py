"""Unit tests for gui/components/numeric_field.py."""

import pytest
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

from gui.components.numeric_field import NumericField, NumericFieldConfig

# QApplication must exist before creating any QWidget
_app = QApplication.instance() or QApplication([])


class TestNumericFieldConfig:
    """Tests for the frozen dataclass configuration."""

    def test_default_config(self):
        cfg = NumericFieldConfig()
        assert cfg.min_value == -999999.0
        assert cfg.max_value == 999999.0
        assert cfg.decimals == 4
        assert cfg.default_value == 0.0
        assert cfg.suffix == ""
        assert cfg.placeholder == ""

    def test_custom_config(self):
        cfg = NumericFieldConfig(
            min_value=0.0, max_value=5.0, decimals=3, suffix="in"
        )
        assert cfg.min_value == 0.0
        assert cfg.max_value == 5.0
        assert cfg.decimals == 3
        assert cfg.suffix == "in"


class TestNumericFieldValue:
    """Tests for value get/set and validation."""

    def test_initial_value(self):
        cfg = NumericFieldConfig(default_value=1.5, decimals=3)
        field = NumericField(config=cfg)
        assert field.value() == 1.5

    def test_set_value(self):
        field = NumericField(config=NumericFieldConfig(decimals=2))
        field.set_value(3.14)
        assert field.value() == 3.14

    def test_set_value_clamps_to_max(self):
        cfg = NumericFieldConfig(min_value=0.0, max_value=10.0)
        field = NumericField(config=cfg)
        field.set_value(15.0)
        assert field.value() == 10.0

    def test_set_value_clamps_to_min(self):
        cfg = NumericFieldConfig(min_value=0.0, max_value=10.0)
        field = NumericField(config=cfg)
        field.set_value(-5.0)
        assert field.value() == 0.0

    def test_is_valid_initially(self):
        field = NumericField(config=NumericFieldConfig())
        assert field.is_valid() is True


class TestNumericFieldValidation:
    """Tests for input validation and error state."""

    def test_valid_input_accepted(self):
        cfg = NumericFieldConfig(min_value=0.0, max_value=10.0, decimals=3)
        field = NumericField(config=cfg)
        # Simulate typing a valid value
        field.blockSignals(False)
        field.setText("5.000")
        assert field.is_valid() is True

    def test_out_of_range_high_shows_error(self):
        cfg = NumericFieldConfig(min_value=0.0, max_value=10.0, decimals=3)
        field = NumericField(config=cfg)
        field.setText("15.000")
        assert field.is_valid() is False

    def test_out_of_range_low_shows_error(self):
        cfg = NumericFieldConfig(min_value=0.0, max_value=10.0, decimals=3)
        field = NumericField(config=cfg)
        field.setText("-1.000")
        assert field.is_valid() is False

    def test_non_numeric_shows_error(self):
        cfg = NumericFieldConfig(min_value=0.0, max_value=10.0)
        field = NumericField(config=cfg)
        field.setText("abc")
        assert field.is_valid() is False

    def test_empty_string_shows_error(self):
        cfg = NumericFieldConfig(min_value=0.0, max_value=10.0)
        field = NumericField(config=cfg)
        field.setText("")
        assert field.is_valid() is False

    def test_value_with_suffix_valid(self):
        cfg = NumericFieldConfig(min_value=0.0, max_value=10.0, decimals=3, suffix="in")
        field = NumericField(config=cfg)
        field.setText("5.000 in")
        assert field.is_valid() is True

    def test_value_with_suffix_out_of_range(self):
        cfg = NumericFieldConfig(min_value=0.0, max_value=10.0, decimals=3, suffix="in")
        field = NumericField(config=cfg)
        field.setText("15.000 in")
        assert field.is_valid() is False


class TestNumericFieldSignal:
    """Tests for value_changed signal emission."""

    def test_signal_emitted_on_valid_edit(self):
        cfg = NumericFieldConfig(min_value=0.0, max_value=10.0, decimals=3)
        field = NumericField(config=cfg)
        received = []
        field.value_changed.connect(lambda v: received.append(v))

        # Simulate user typing and pressing Enter
        field.setText("7.500")
        field.editingFinished.emit()

        assert len(received) == 1
        assert received[0] == 7.5

    def test_signal_not_emitted_on_invalid_edit(self):
        cfg = NumericFieldConfig(min_value=0.0, max_value=10.0, decimals=3)
        field = NumericField(config=cfg)
        received = []
        field.value_changed.connect(lambda v: received.append(v))

        # Simulate user typing invalid value and pressing Enter
        field.setText("abc")
        field.editingFinished.emit()

        assert len(received) == 0

    def test_reverts_to_last_good_on_invalid_commit(self):
        cfg = NumericFieldConfig(min_value=0.0, max_value=10.0, decimals=3, default_value=2.0)
        field = NumericField(config=cfg)

        # Type invalid and commit
        field.setText("xyz")
        field.editingFinished.emit()

        # Should revert to default
        assert field.value() == 2.0
        assert field.is_valid() is True


class TestNumericFieldSetRange:
    """Tests for dynamic range updates."""

    def test_set_range_updates_validation(self):
        cfg = NumericFieldConfig(min_value=0.0, max_value=100.0, decimals=2)
        field = NumericField(config=cfg)
        field.set_value(50.0)

        # Narrow the range
        field.set_range(0.0, 10.0)

        # Current display "50.00" is now out of range
        assert field.is_valid() is False
