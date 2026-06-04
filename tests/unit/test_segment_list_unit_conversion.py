"""Unit tests for SegmentListWidget unit conversion (metric/inch toggle).

Validates Requirements 9.1, 9.2, 9.3:
- X, Z, and Radius columns display values multiplied by 25.4 when metric
- Values display in inches when in inch mode
- Toggling does not modify underlying segment data
"""

import sys
from unittest.mock import patch

import pytest

# Ensure PyQt5 is available for testing
from PyQt5.QtWidgets import QApplication

from gui.unit_state import unit_state, UnitMode


# Need a QApplication instance for widget tests
@pytest.fixture(scope="module", autouse=True)
def qapp():
    """Create a QApplication instance for the test module."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


@pytest.fixture(autouse=True)
def reset_unit_state():
    """Ensure unit_state is in INCH mode before each test."""
    unit_state._mode = UnitMode.INCH
    yield
    unit_state._mode = UnitMode.INCH


@pytest.fixture
def segment_widget():
    """Create a SegmentListWidget instance for testing."""
    from gui.components.segment_list import SegmentListWidget
    widget = SegmentListWidget()
    return widget


class TestSegmentListUnitConversion:
    """Tests for segment list display conversion on unit toggle."""

    def test_displays_inch_values_in_inch_mode(self, segment_widget):
        """In inch mode, X, Z, Radius display as-is (no conversion)."""
        segments = [
            {"type": "line", "x": 1.0, "z": -0.5, "radius": 0.0},
            {"type": "arc", "x": 2.0, "z": -1.0, "radius": 0.25},
        ]
        segment_widget.set_segments(segments)

        # Read back — should be in inches
        result = segment_widget.get_segments()
        assert len(result) == 2
        assert abs(result[0]["x"] - 1.0) < 1e-6
        assert abs(result[0]["z"] - (-0.5)) < 1e-6
        assert abs(result[1]["x"] - 2.0) < 1e-6
        assert abs(result[1]["z"] - (-1.0)) < 1e-6
        assert abs(result[1]["radius"] - 0.25) < 1e-6

    def test_displays_metric_values_after_toggle(self, segment_widget):
        """After toggling to metric, displayed cell text shows ×25.4 values."""
        from gui.components.segment_list import COL_X, COL_Z, COL_RADIUS

        segments = [
            {"type": "line", "x": 1.0, "z": -0.5, "radius": 0.0},
        ]
        segment_widget.set_segments(segments)

        # Toggle to metric
        unit_state.toggle()  # now metric

        # Check displayed text in cells (should be ×25.4)
        table = segment_widget._table
        x_text = table.item(0, COL_X).text()
        z_text = table.item(0, COL_Z).text()

        assert abs(float(x_text) - 25.4) < 0.01
        assert abs(float(z_text) - (-12.7)) < 0.01

    def test_get_segments_returns_inches_in_metric_mode(self, segment_widget):
        """get_segments() always returns inch values regardless of display mode."""
        segments = [
            {"type": "line", "x": 1.0, "z": -0.5, "radius": 0.0},
            {"type": "arc", "x": 2.0, "z": -1.0, "radius": 0.25},
        ]
        segment_widget.set_segments(segments)

        # Toggle to metric
        unit_state.toggle()

        # get_segments should still return inches
        result = segment_widget.get_segments()
        assert len(result) == 2
        assert abs(result[0]["x"] - 1.0) < 1e-4
        assert abs(result[0]["z"] - (-0.5)) < 1e-4
        assert abs(result[1]["x"] - 2.0) < 1e-4
        assert abs(result[1]["z"] - (-1.0)) < 1e-4
        assert abs(result[1]["radius"] - 0.25) < 1e-4

    def test_toggle_does_not_modify_segment_data(self, segment_widget):
        """Toggling unit mode does not alter the underlying segment data."""
        segments = [
            {"type": "line", "x": 1.5, "z": -0.75, "radius": 0.0},
            {"type": "arc", "x": 3.0, "z": -2.0, "radius": 0.5},
        ]
        segment_widget.set_segments(segments)

        # Toggle multiple times
        unit_state.toggle()  # metric
        unit_state.toggle()  # inch
        unit_state.toggle()  # metric
        unit_state.toggle()  # inch

        # Data should be unchanged
        result = segment_widget.get_segments()
        assert abs(result[0]["x"] - 1.5) < 1e-4
        assert abs(result[0]["z"] - (-0.75)) < 1e-4
        assert abs(result[1]["x"] - 3.0) < 1e-4
        assert abs(result[1]["z"] - (-2.0)) < 1e-4
        assert abs(result[1]["radius"] - 0.5) < 1e-4

    def test_metric_display_uses_3_decimal_places(self, segment_widget):
        """In metric mode, values are formatted with 3 decimal places."""
        from gui.components.segment_list import COL_X

        segments = [{"type": "line", "x": 1.0, "z": 0.0, "radius": 0.0}]
        segment_widget.set_segments(segments)

        # Toggle to metric
        unit_state.toggle()

        table = segment_widget._table
        x_text = table.item(0, COL_X).text()
        # Should be "25.400" (3 decimal places)
        parts = x_text.split(".")
        assert len(parts) == 2
        assert len(parts[1]) == 3

    def test_inch_display_uses_4_decimal_places(self, segment_widget):
        """In inch mode, values are formatted with 4 decimal places."""
        from gui.components.segment_list import COL_X

        segments = [{"type": "line", "x": 1.0, "z": 0.0, "radius": 0.0}]
        segment_widget.set_segments(segments)

        table = segment_widget._table
        x_text = table.item(0, COL_X).text()
        # Should be "1.0000" (4 decimal places)
        parts = x_text.split(".")
        assert len(parts) == 2
        assert len(parts[1]) == 4

    def test_set_segments_in_metric_mode_displays_converted(self, segment_widget):
        """Setting segments while in metric mode displays converted values."""
        from gui.components.segment_list import COL_X, COL_Z

        # Switch to metric first
        unit_state.toggle()

        segments = [{"type": "line", "x": 2.0, "z": -1.0, "radius": 0.0}]
        segment_widget.set_segments(segments)

        table = segment_widget._table
        x_text = table.item(0, COL_X).text()
        z_text = table.item(0, COL_Z).text()

        # Should display 2.0 * 25.4 = 50.8 and -1.0 * 25.4 = -25.4
        assert abs(float(x_text) - 50.8) < 0.01
        assert abs(float(z_text) - (-25.4)) < 0.01

        # But get_segments returns inches
        result = segment_widget.get_segments()
        assert abs(result[0]["x"] - 2.0) < 1e-4
        assert abs(result[0]["z"] - (-1.0)) < 1e-4
