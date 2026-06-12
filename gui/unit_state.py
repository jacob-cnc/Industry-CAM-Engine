"""Centralized unit-mode state for the metric/inch toggle.

Provides a singleton UnitState that manages the active display unit system
and emits a Qt signal when it changes. All UI components subscribe to this
signal and re-render their displayed values without touching stored data.

The internal pipeline always operates in inches. Conversion to/from
millimeters happens exclusively at the UI display boundary.
"""

from enum import Enum

from PyQt5.QtCore import QObject, pyqtSignal


class UnitMode(Enum):
    """Display unit system."""

    INCH = "inch"
    METRIC = "metric"


class UnitState(QObject):
    """Singleton managing the active display unit system.

    Emits ``unit_changed`` whenever the mode is toggled so that all
    subscribing widgets can refresh their displayed values.
    """

    unit_changed = pyqtSignal(str)  # emits "inch" or "metric"

    CONVERSION_FACTOR = 25.4

    def __init__(self) -> None:
        super().__init__()
        self._mode: UnitMode = UnitMode.INCH

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def mode(self) -> UnitMode:
        """Current unit mode."""
        return self._mode

    def toggle(self) -> None:
        """Switch between inch and metric."""
        if self._mode == UnitMode.INCH:
            self._mode = UnitMode.METRIC
        else:
            self._mode = UnitMode.INCH
        self.unit_changed.emit(self._mode.value)

    def to_display(self, value_inches: float) -> float:
        """Convert an internal value (inches) to the current display unit.

        In metric mode the value is multiplied by 25.4.
        In inch mode the value is returned unchanged.
        """
        if self._mode == UnitMode.METRIC:
            return value_inches * self.CONVERSION_FACTOR
        return value_inches

    def from_display(self, value_display: float) -> float:
        """Convert a display value to internal inches.

        In metric mode the value is divided by 25.4.
        In inch mode the value is returned unchanged.
        """
        if self._mode == UnitMode.METRIC:
            return value_display / self.CONVERSION_FACTOR
        return value_display

    @property
    def decimals(self) -> int:
        """Number of decimal places for the current mode.

        4 for inch, 3 for metric.
        """
        if self._mode == UnitMode.METRIC:
            return 3
        return 4

    @property
    def is_metric(self) -> bool:
        """True when the active mode is metric."""
        return self._mode == UnitMode.METRIC

    @property
    def length_suffix(self) -> str:
        """Unit suffix for length values: 'in' or 'mm'."""
        if self._mode == UnitMode.METRIC:
            return "mm"
        return "in"

    @property
    def feed_suffix(self) -> str:
        """Unit suffix for feed rate values: 'in/min' or 'mm/min'."""
        if self._mode == UnitMode.METRIC:
            return "mm/min"
        return "in/min"


# Module-level singleton — import this in other modules.
unit_state = UnitState()
