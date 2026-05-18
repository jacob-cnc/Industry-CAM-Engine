"""Validated numeric input widget for Industry CAM Engine.

QLineEdit subclass with float validation, range checking, and optional unit suffix.
Emits value_changed signal on valid input; shows red border on invalid input.

Font: JetBrains Mono for numeric fields (per project style guide).
"""

from dataclasses import dataclass
from typing import Optional

from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtWidgets import QLineEdit

from gui.colors import COLORS, FONTS


@dataclass(frozen=True)
class NumericFieldConfig:
    """Configuration for a NumericField widget."""

    min_value: float = -999999.0
    max_value: float = 999999.0
    decimals: int = 4
    default_value: float = 0.0
    suffix: str = ""  # e.g. "in", "dia", "ipr", "rpm"
    placeholder: str = ""


class NumericField(QLineEdit):
    """Validated numeric input field with range checking and unit suffix.

    Emits value_changed(float) when the user enters a valid value.
    Shows a red border when the current text is not a valid float
    or falls outside the configured min/max range.
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
        self._set_display(self._config.default_value)

        # Connect editing signals
        self.editingFinished.connect(self._on_editing_finished)
        self.textChanged.connect(self._on_text_changed)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def value(self) -> float:
        """Return the last valid numeric value."""
        return self._last_good_value

    def set_value(self, val: float) -> None:
        """Programmatically set the field value (clamped to range)."""
        clamped = max(self._config.min_value, min(self._config.max_value, val))
        self._last_good_value = clamped
        self._set_display(clamped)
        self._apply_style(valid=True)
        self._valid = True

    def set_range(self, min_value: float, max_value: float) -> None:
        """Update the allowed range at runtime."""
        self._config = NumericFieldConfig(
            min_value=min_value,
            max_value=max_value,
            decimals=self._config.decimals,
            default_value=self._config.default_value,
            suffix=self._config.suffix,
            placeholder=self._config.placeholder,
        )
        # Re-validate current value
        self._on_text_changed(self.text())

    def is_valid(self) -> bool:
        """Whether the current displayed value is valid."""
        return self._valid

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

    def _set_display(self, val: float) -> None:
        """Format and display a numeric value with optional suffix."""
        formatted = f"{val:.{self._config.decimals}f}"
        if self._config.suffix:
            formatted = f"{formatted} {self._config.suffix}"
        # Block signals to avoid recursive validation
        self.blockSignals(True)
        self.setText(formatted)
        self.blockSignals(False)

    def _parse_text(self, text: str) -> Optional[float]:
        """Parse the displayed text into a float, stripping suffix if present."""
        stripped = text.strip()
        # Remove suffix if present
        if self._config.suffix and stripped.endswith(self._config.suffix):
            stripped = stripped[: -len(self._config.suffix)].strip()
        try:
            return float(stripped)
        except (ValueError, TypeError):
            return None

    def _is_in_range(self, val: float) -> bool:
        """Check if value is within configured min/max range."""
        return self._config.min_value <= val <= self._config.max_value

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
        """Commit value when user finishes editing (Enter or focus lost)."""
        parsed = self._parse_text(self.text())
        if parsed is not None and self._is_in_range(parsed):
            self._last_good_value = parsed
            self._set_display(parsed)
            self._apply_style(valid=True)
            self._valid = True
            self.value_changed.emit(parsed)
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
