"""Validated numeric input widget for Industry CAM Engine.

QLineEdit subclass with float validation, range checking, and optional unit suffix.
Emits value_changed signal on valid input; shows red border on invalid input.

Font: JetBrains Mono for numeric fields (per project style guide).

Unit awareness: When ``unit_aware`` is True in the config, the field subscribes
to the global UnitState and converts between internal inches and display
millimeters automatically. The ``.value()`` method always returns inches.
"""

from dataclasses import dataclass
from typing import Optional

from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtWidgets import QLineEdit

from gui.colors import COLORS, FONTS
from gui.unit_state import unit_state


# Suffix mapping: inch suffix → metric suffix
_SUFFIX_MAP = {
    "in": "mm",
    "in/min": "mm/min",
    "in/rev": "mm/rev",
}

# Reverse mapping for parsing: metric suffix → inch suffix
_SUFFIX_MAP_REVERSE = {v: k for k, v in _SUFFIX_MAP.items()}


@dataclass(frozen=True)
class NumericFieldConfig:
    """Configuration for a NumericField widget."""

    min_value: float = -999999.0
    max_value: float = 999999.0
    decimals: int = 4
    default_value: float = 0.0
    suffix: str = ""  # e.g. "in", "dia", "ipr", "rpm"
    placeholder: str = ""
    unit_aware: bool = True  # False for RPM, tool number, pass count, angles


class NumericField(QLineEdit):
    """Validated numeric input field with range checking and unit suffix.

    Emits value_changed(float) when the user enters a valid value.
    Shows a red border when the current text is not a valid float
    or falls outside the configured min/max range.

    When ``unit_aware`` is True, the field:
    - Displays stored inch values multiplied by 25.4 in metric mode
    - Divides user-entered metric values by 25.4 before storing
    - Updates suffix labels on mode change ("in" ↔ "mm", etc.)
    - Adjusts validation min/max by conversion factor in metric mode
    - Uses 4 decimal places in inch mode, 3 in metric mode

    The ``.value()`` method ALWAYS returns the internal value in inches.
    The ``.set_value()`` method accepts inches and stores inches.
    """

    value_changed = pyqtSignal(float)

    def __init__(
        self,
        config: Optional[NumericFieldConfig] = None,
        parent=None,
    ):
        super().__init__(parent)
        self._config = config or NumericFieldConfig()
        self._valid = True
        self._last_good_value: float = self._config.default_value

        self._setup_ui()
        self._apply_style(valid=True)

        # Set initial display value
        self._set_display(self._last_good_value)

        # Connect editing signals
        self.editingFinished.connect(self._on_editing_finished)
        self.textChanged.connect(self._on_text_changed)

        # Subscribe to unit mode changes
        if self._config.unit_aware:
            unit_state.unit_changed.connect(self._on_unit_changed)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def value(self) -> float:
        """Return the last valid numeric value (always in inches)."""
        return self._last_good_value

    def set_value(self, val: float) -> None:
        """Programmatically set the field value in inches (clamped to range)."""
        clamped = max(self._config.min_value, min(self._config.max_value, val))
        self._last_good_value = clamped
        self._set_display(clamped)
        self._apply_style(valid=True)
        self._valid = True

    def set_range(self, min_value: float, max_value: float) -> None:
        """Update the allowed range at runtime (in inches)."""
        self._config = NumericFieldConfig(
            min_value=min_value,
            max_value=max_value,
            decimals=self._config.decimals,
            default_value=self._config.default_value,
            suffix=self._config.suffix,
            placeholder=self._config.placeholder,
            unit_aware=self._config.unit_aware,
        )
        # Re-validate current value
        self._on_text_changed(self.text())

    def is_valid(self) -> bool:
        """Whether the current displayed value is valid."""
        return self._valid

    # ------------------------------------------------------------------
    # Unit conversion helpers
    # ------------------------------------------------------------------

    @property
    def _is_unit_aware_metric(self) -> bool:
        """True when this field is unit-aware AND currently in metric mode."""
        return self._config.unit_aware and unit_state.is_metric

    @property
    def _active_suffix(self) -> str:
        """Return the suffix appropriate for the current unit mode."""
        if not self._config.suffix:
            return ""
        if self._config.unit_aware and unit_state.is_metric:
            return _SUFFIX_MAP.get(self._config.suffix, self._config.suffix)
        return self._config.suffix

    @property
    def _active_decimals(self) -> int:
        """Return decimal places for the current unit mode."""
        if self._config.unit_aware and unit_state.is_metric:
            return 3
        return self._config.decimals

    @property
    def _active_min(self) -> float:
        """Return the min validation value scaled for the current display mode."""
        if self._is_unit_aware_metric:
            return self._config.min_value * unit_state.CONVERSION_FACTOR
        return self._config.min_value

    @property
    def _active_max(self) -> float:
        """Return the max validation value scaled for the current display mode."""
        if self._is_unit_aware_metric:
            return self._config.max_value * unit_state.CONVERSION_FACTOR
        return self._config.max_value

    # ------------------------------------------------------------------
    # Unit change handler
    # ------------------------------------------------------------------

    def _on_unit_changed(self, mode: str) -> None:
        """Re-display the stored value in the new unit system.

        Called when the global unit mode changes. Does NOT alter the
        stored internal value — only updates the display text, suffix,
        and decimal places.
        """
        self._set_display(self._last_good_value)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        """Configure font, alignment, placeholder."""
        font_family = f"{FONTS['mono_family']}, {FONTS['fallback_mono']}"
        self.setStyleSheet(self._build_stylesheet(valid=True))
        self.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        if self._config.placeholder:
            self.setPlaceholderText(self._config.placeholder)

    def _set_display(self, val_inches: float) -> None:
        """Format and display a numeric value with unit conversion and suffix.

        Args:
            val_inches: The internal value in inches to display.
        """
        # Convert to display units if unit-aware and metric
        if self._is_unit_aware_metric:
            display_val = val_inches * unit_state.CONVERSION_FACTOR
        else:
            display_val = val_inches

        decimals = self._active_decimals
        suffix = self._active_suffix

        formatted = f"{display_val:.{decimals}f}"
        if suffix:
            formatted = f"{formatted} {suffix}"
        # Block signals to avoid recursive validation
        self.blockSignals(True)
        self.setText(formatted)
        self.blockSignals(False)

    def _parse_text(self, text: str) -> Optional[float]:
        """Parse the displayed text into a float, stripping suffix if present.

        Returns the value in display units (metric mm or inches depending on mode).
        """
        stripped = text.strip()
        # Remove the active suffix (which may be the metric version)
        suffix = self._active_suffix
        if suffix and stripped.endswith(suffix):
            stripped = stripped[: -len(suffix)].strip()
        # Also try the base suffix in case user typed it
        if self._config.suffix and stripped.endswith(self._config.suffix):
            stripped = stripped[: -len(self._config.suffix)].strip()
        try:
            return float(stripped)
        except (ValueError, TypeError):
            return None

    def _is_in_range(self, display_val: float) -> bool:
        """Check if a display value is within the active (possibly scaled) range."""
        return self._active_min <= display_val <= self._active_max

    def _on_text_changed(self, text: str) -> None:
        """Live validation — update border color as user types."""
        parsed = self._parse_text(text)
        if parsed is None or not self._is_in_range(parsed):
            self._apply_style(valid=False)
            self._valid = False
        else:
            self._apply_style(valid=True)
            self._valid = True

    def _on_editing_finished(self) -> None:
        """Commit value when user finishes editing (Enter or focus lost).

        If unit-aware and metric, the entered value is in mm — divide by
        25.4 to convert back to inches before storing.
        """
        parsed = self._parse_text(self.text())
        if parsed is not None and self._is_in_range(parsed):
            # Convert display value back to internal inches
            if self._is_unit_aware_metric:
                internal_val = parsed / unit_state.CONVERSION_FACTOR
            else:
                internal_val = parsed
            self._last_good_value = internal_val
            self._set_display(internal_val)
            self._apply_style(valid=True)
            self._valid = True
            self.value_changed.emit(internal_val)
        else:
            # Revert to last good value on invalid commit
            self._set_display(self._last_good_value)
            self._apply_style(valid=True)
            self._valid = True

    def _apply_style(self, valid: bool) -> None:
        """Apply stylesheet with appropriate border color."""
        self.setStyleSheet(self._build_stylesheet(valid))

    def _build_stylesheet(self, valid: bool) -> str:
        """Build the QSS stylesheet string for this widget."""
        border_color = COLORS["border_normal"] if valid else COLORS["border_error"]
        focus_color = COLORS["border_focused"] if valid else COLORS["border_error"]

        return (
            f"QLineEdit {{"
            f"  background-color: {COLORS['bg_panel']};"
            f"  color: {COLORS['text_primary']};"
            f"  border: 1px solid {border_color};"
            f"  border-radius: 3px;"
            f"  padding: 6px;"
            f"  min-height: 36px;"
            f"  font-family: {FONTS['mono_family']}, {FONTS['fallback_mono']};"
            f"  font-size: {FONTS['code_size']}pt;"
            f"}}"
            f"QLineEdit:focus {{"
            f"  border-color: {focus_color};"
            f"}}"
        )
