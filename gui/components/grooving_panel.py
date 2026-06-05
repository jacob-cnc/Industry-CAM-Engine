"""Grooving/parting parameter panel for the Program tab.

Displays input fields for grooving and parting operations.
Swaps into the parameter area when a grooving/parting block is selected.
"""

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QComboBox, QSpinBox,
    QLabel, QCheckBox,
)

from gui.colors import COLORS, FONTS
from gui.components.numeric_field import NumericField, NumericFieldConfig


class GroovingPanel(QWidget):
    """Parameter input panel for grooving and parting operations.

    Signals:
        params_changed(): Emitted when any field value changes.
    """

    params_changed = pyqtSignal()

    def __init__(self, is_parting: bool = False, parent=None):
        super().__init__(parent)
        self._is_parting = is_parting
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Groove geometry
        form1 = QFormLayout()
        form1.setSpacing(2)

        self._z_start = NumericField(NumericFieldConfig(
            min_value=-12.0, max_value=0.5, decimals=4, default_value=-0.500, suffix='"'))
        form1.addRow("Z Start (left):", self._z_start)

        self._z_end = NumericField(NumericFieldConfig(
            min_value=-12.0, max_value=0.5, decimals=4, default_value=-0.625, suffix='"'))
        form1.addRow("Z End (right):", self._z_end)

        self._groove_depth = NumericField(NumericFieldConfig(
            min_value=0.010, max_value=4.0, decimals=4, default_value=0.100, suffix='"'))
        form1.addRow("Depth (dia):", self._groove_depth)

        self._start_diameter = NumericField(NumericFieldConfig(
            min_value=0.1, max_value=8.0, decimals=4, default_value=1.000, suffix='"'))
        form1.addRow("Start Dia:", self._start_diameter)

        self._bottom_dia_label = QLabel("0.9000")
        self._bottom_dia_label.setStyleSheet(
            f"color: {COLORS['text_secondary']}; font-family: 'JetBrains Mono';"
        )
        form1.addRow("Bottom Dia:", self._bottom_dia_label)

        self._width_label = QLabel("0.1250")
        self._width_label.setStyleSheet(
            f"color: {COLORS['text_secondary']}; font-family: 'JetBrains Mono';"
        )
        form1.addRow("Groove Width:", self._width_label)

        layout.addLayout(form1)

        # Peck parameters
        form2 = QFormLayout()
        form2.setSpacing(2)

        self._peck_check = QCheckBox("Peck grooving")
        self._peck_check.setChecked(True if self._is_parting else False)
        self._peck_check.setStyleSheet(
            f"QCheckBox {{ color: {COLORS['text_primary']}; font-size: {FONTS['ui_size']}pt; }}"
        )
        form2.addRow(self._peck_check)

        self._peck_depth = NumericField(NumericFieldConfig(
            min_value=0.005, max_value=0.500, decimals=4, default_value=0.030, suffix='"'))
        form2.addRow("Peck Depth:", self._peck_depth)

        self._peck_retract = NumericField(NumericFieldConfig(
            min_value=0.005, max_value=0.250, decimals=4, default_value=0.010, suffix='"'))
        form2.addRow("Peck Retract:", self._peck_retract)

        layout.addLayout(form2)

        # Cutting parameters
        form3 = QFormLayout()
        form3.setSpacing(2)

        self._feed = NumericField(NumericFieldConfig(
            min_value=0.0005, max_value=0.050, decimals=4, default_value=0.002, suffix=' ipr'))
        form3.addRow("Feed:", self._feed)

        self._rpm = NumericField(NumericFieldConfig(
            min_value=50, max_value=3000, decimals=0, default_value=800, suffix=" RPM"))
        form3.addRow("RPM:", self._rpm)

        self._tool_num = QSpinBox()
        self._tool_num.setRange(1, 99)
        self._tool_num.setValue(5 if self._is_parting else 4)
        self._tool_num.setPrefix("T")
        form3.addRow("Tool:", self._tool_num)

        self._blade_width = NumericField(NumericFieldConfig(
            min_value=0.020, max_value=0.500, decimals=4, default_value=0.125, suffix='"'))
        form3.addRow("Blade Width:", self._blade_width)

        self._plunges_label = QLabel("1")
        self._plunges_label.setStyleSheet(
            f"color: {COLORS['text_secondary']}; font-family: 'JetBrains Mono';"
        )
        form3.addRow("Plunges (calc):", self._plunges_label)

        layout.addLayout(form3)
        layout.addStretch()

        # Initial computed values
        self._update_computed()

    def _connect_signals(self):
        self._peck_check.toggled.connect(self._on_peck_toggled)
        # All fields emit params_changed
        for field in [self._z_start, self._z_end, self._groove_depth,
                      self._start_diameter, self._peck_depth, self._peck_retract,
                      self._feed, self._rpm, self._blade_width]:
            field.value_changed.connect(self._on_field_changed)
        self._peck_check.toggled.connect(lambda _: self.params_changed.emit())
        self._tool_num.valueChanged.connect(lambda _: self.params_changed.emit())

    def _on_peck_toggled(self, checked: bool):
        self._peck_depth.setEnabled(checked)
        self._peck_retract.setEnabled(checked)

    def _on_field_changed(self):
        self._update_computed()
        self.params_changed.emit()

    def _update_computed(self):
        """Update computed display labels."""
        start_dia = self._start_diameter.value()
        depth = self._groove_depth.value()
        bottom = start_dia - depth
        self._bottom_dia_label.setText(f"{bottom:.4f}\"")

        z_start = self._z_start.value()
        z_end = self._z_end.value()
        width = abs(z_start - z_end)
        self._width_label.setText(f"{width:.4f}\"")

        blade = self._blade_width.value()
        if blade > 0:
            import math
            plunges = max(1, math.ceil(width / blade)) if width > 0.0001 else 1
            self._plunges_label.setText(str(plunges))

    # ------------------------------------------------------------------
    # Public data access
    # ------------------------------------------------------------------

    def get_values(self) -> dict:
        """Return all field values as a dict for GroovingParams construction."""
        return {
            "groove_type": "parting" if self._is_parting else "single",
            "z_start": self._z_start.value(),
            "z_end": self._z_end.value(),
            "groove_depth": self._groove_depth.value(),
            "start_diameter": self._start_diameter.value(),
            "peck_enabled": self._peck_check.isChecked(),
            "peck_depth": self._peck_depth.value(),
            "peck_retract": self._peck_retract.value(),
            "feed": self._feed.value(),
            "spindle_rpm": self._rpm.value(),
            "tool_number": self._tool_num.value(),
            "blade_width": self._blade_width.value(),
        }

    def set_values(self, data: dict):
        """Populate fields from a dict (for file load)."""
        if "z_start" in data:
            self._z_start.set_value(data["z_start"])
        if "z_end" in data:
            self._z_end.set_value(data["z_end"])
        if "groove_depth" in data:
            self._groove_depth.set_value(data["groove_depth"])
        if "start_diameter" in data:
            self._start_diameter.set_value(data["start_diameter"])
        if "peck_enabled" in data:
            self._peck_check.setChecked(data["peck_enabled"])
        if "peck_depth" in data:
            self._peck_depth.set_value(data["peck_depth"])
        if "peck_retract" in data:
            self._peck_retract.set_value(data["peck_retract"])
        if "feed" in data:
            self._feed.set_value(data["feed"])
        if "spindle_rpm" in data:
            self._rpm.set_value(data["spindle_rpm"])
        if "tool_number" in data:
            self._tool_num.setValue(data["tool_number"])
        if "blade_width" in data:
            self._blade_width.set_value(data["blade_width"])
        self._update_computed()

    def get_tool_number(self) -> int:
        return self._tool_num.value()
