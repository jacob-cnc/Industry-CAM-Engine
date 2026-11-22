"""On-center drilling parameter panel for the Program tab (spec: drilling-cycles).

Displays input fields for an axial drilling operation (a hole on the spindle
centreline, X0, fed along Z). Swaps into the parameter area when a drilling
block is selected. Mirrors the GroovingPanel contract:
``params_changed`` / ``get_values()`` / ``set_values()`` / ``get_tool_number()``.
"""

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QComboBox, QSpinBox,
    QLabel, QCheckBox,
)

from gui.colors import COLORS, FONTS
from gui.components.numeric_field import NumericField, NumericFieldConfig

# (display label, DrillingParams.operation value)
_OPERATIONS = [
    ("Center drill", "center"),
    ("Spot drill", "spot"),
    ("Twist drill", "drill"),
    ("Reamer", "ream"),
]


class DrillingPanel(QWidget):
    """Parameter input panel for an on-center axial drilling operation.

    Signals:
        params_changed(): Emitted when any field value changes.
    """

    params_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Operation + hole geometry
        form1 = QFormLayout()
        form1.setSpacing(2)

        self._operation = QComboBox()
        for label, _ in _OPERATIONS:
            self._operation.addItem(label)
        self._operation.setCurrentIndex(2)          # Twist drill
        form1.addRow("Operation:", self._operation)

        self._z_start = NumericField(NumericFieldConfig(
            min_value=-12.0, max_value=2.0, decimals=4, default_value=0.000, suffix='"'))
        form1.addRow("Z Start (face):", self._z_start)

        self._depth = NumericField(NumericFieldConfig(
            min_value=0.001, max_value=12.0, decimals=4, default_value=0.500, suffix='"'))
        form1.addRow("Depth:", self._depth)

        self._depth_ref = QComboBox()
        self._depth_ref.addItem("To tip")
        self._depth_ref.addItem("To full dia")
        form1.addRow("Depth measured:", self._depth_ref)

        self._through = QCheckBox("Through hole (break through)")
        self._through.setStyleSheet(
            f"QCheckBox {{ color: {COLORS['text_primary']}; font-size: {FONTS['ui_size']}pt; }}"
        )
        form1.addRow(self._through)

        self._clearance = NumericField(NumericFieldConfig(
            min_value=0.010, max_value=1.0, decimals=4, default_value=0.100, suffix='"'))
        form1.addRow("Clearance (R):", self._clearance)

        self._rplane_label = QLabel("0.1000")
        self._rplane_label.setStyleSheet(
            f"color: {COLORS['text_secondary']}; font-family: 'JetBrains Mono';"
        )
        form1.addRow("R-plane Z:", self._rplane_label)

        layout.addLayout(form1)

        # Peck
        form2 = QFormLayout()
        form2.setSpacing(2)

        self._peck_check = QCheckBox("Peck drilling")
        self._peck_check.setChecked(True)
        self._peck_check.setStyleSheet(
            f"QCheckBox {{ color: {COLORS['text_primary']}; font-size: {FONTS['ui_size']}pt; }}"
        )
        form2.addRow(self._peck_check)

        self._peck_increment = NumericField(NumericFieldConfig(
            min_value=0.005, max_value=2.0, decimals=4, default_value=0.100, suffix='"'))
        form2.addRow("Peck Increment:", self._peck_increment)

        self._peck_style = QComboBox()
        self._peck_style.addItem("Full retract")      # G83 style
        self._peck_style.addItem("Chip break")        # G73 style
        form2.addRow("Peck Style:", self._peck_style)

        self._dwell = NumericField(NumericFieldConfig(
            min_value=0.0, max_value=5.0, decimals=2, default_value=0.00, suffix=" s"))
        form2.addRow("Bottom Dwell:", self._dwell)

        layout.addLayout(form2)

        # Cutting parameters + stock context
        form3 = QFormLayout()
        form3.setSpacing(2)

        self._feed = NumericField(NumericFieldConfig(
            min_value=0.0005, max_value=0.050, decimals=4, default_value=0.004, suffix=' ipr'))
        form3.addRow("Feed:", self._feed)

        self._rpm = NumericField(NumericFieldConfig(
            min_value=50, max_value=3000, decimals=0, default_value=1200, suffix=" RPM"))
        form3.addRow("RPM:", self._rpm)

        self._tool_num = QSpinBox()
        self._tool_num.setRange(1, 99)
        self._tool_num.setValue(6)
        self._tool_num.setPrefix("T")
        form3.addRow("Tool:", self._tool_num)

        self._stock_dia = NumericField(NumericFieldConfig(
            min_value=0.1, max_value=8.0, decimals=4, default_value=1.000, suffix='"'))
        form3.addRow("Stock Dia:", self._stock_dia)

        self._stock_length = NumericField(NumericFieldConfig(
            min_value=0.05, max_value=24.0, decimals=4, default_value=2.000, suffix='"'))
        form3.addRow("Stock Length:", self._stock_length)

        layout.addLayout(form3)
        layout.addStretch()

        self._update_computed()

    def _connect_signals(self):
        for field in [self._z_start, self._depth, self._clearance,
                      self._peck_increment, self._dwell, self._feed, self._rpm,
                      self._stock_dia, self._stock_length]:
            field.value_changed.connect(self._on_field_changed)
        self._operation.currentIndexChanged.connect(lambda _: self.params_changed.emit())
        self._depth_ref.currentIndexChanged.connect(lambda _: self.params_changed.emit())
        self._peck_style.currentIndexChanged.connect(lambda _: self.params_changed.emit())
        self._through.toggled.connect(lambda _: self.params_changed.emit())
        self._peck_check.toggled.connect(self._on_peck_toggled)
        self._peck_check.toggled.connect(lambda _: self.params_changed.emit())
        self._tool_num.valueChanged.connect(lambda _: self.params_changed.emit())

    def _on_peck_toggled(self, checked: bool):
        self._peck_increment.setEnabled(checked)
        self._peck_style.setEnabled(checked)

    def _on_field_changed(self):
        self._update_computed()
        self.params_changed.emit()

    def _update_computed(self):
        r_plane = self._z_start.value() + self._clearance.value()
        self._rplane_label.setText(f"{r_plane:.4f}\"")

    # ------------------------------------------------------------------
    # Public data access
    # ------------------------------------------------------------------

    def get_values(self) -> dict:
        """Return field values as a dict for DrillingParams + stock construction.

        The r_plane the planner uses is z_start + clearance; ``clearance`` is also
        stored so the field restores exactly. ``stock_dia`` / ``stock_length`` are
        extra keys the generator uses to build the validation StockDef.
        """
        z_start = self._z_start.value()
        clearance = self._clearance.value()
        return {
            "operation": _OPERATIONS[self._operation.currentIndex()][1],
            "z_start": z_start,
            "depth": self._depth.value(),
            "depth_to_tip": self._depth_ref.currentIndex() == 0,
            "through_hole": self._through.isChecked(),
            "clearance": clearance,
            "r_plane": z_start + clearance,
            "peck_enabled": self._peck_check.isChecked(),
            "peck_increment": self._peck_increment.value(),
            "full_retract": self._peck_style.currentIndex() == 0,
            "dwell": self._dwell.value(),
            "feed": self._feed.value(),
            "spindle_rpm": self._rpm.value(),
            "tool_number": self._tool_num.value(),
            "stock_dia": self._stock_dia.value(),
            "stock_length": self._stock_length.value(),
        }

    def set_values(self, data: dict):
        """Populate fields from a dict (for file load)."""
        if "operation" in data:
            for i, (_, value) in enumerate(_OPERATIONS):
                if value == data["operation"]:
                    self._operation.setCurrentIndex(i)
                    break
        if "z_start" in data:
            self._z_start.set_value(data["z_start"])
        if "depth" in data:
            self._depth.set_value(data["depth"])
        if "depth_to_tip" in data:
            self._depth_ref.setCurrentIndex(0 if data["depth_to_tip"] else 1)
        if "through_hole" in data:
            self._through.setChecked(bool(data["through_hole"]))
        if "clearance" in data:
            self._clearance.set_value(data["clearance"])
        if "peck_enabled" in data:
            self._peck_check.setChecked(bool(data["peck_enabled"]))
        if "peck_increment" in data:
            self._peck_increment.set_value(data["peck_increment"])
        if "full_retract" in data:
            self._peck_style.setCurrentIndex(0 if data["full_retract"] else 1)
        if "dwell" in data:
            self._dwell.set_value(data["dwell"])
        if "feed" in data:
            self._feed.set_value(data["feed"])
        if "spindle_rpm" in data:
            self._rpm.set_value(data["spindle_rpm"])
        if "tool_number" in data:
            self._tool_num.setValue(int(data["tool_number"]))
        if "stock_dia" in data:
            self._stock_dia.set_value(data["stock_dia"])
        if "stock_length" in data:
            self._stock_length.set_value(data["stock_length"])
        self._update_computed()

    def get_tool_number(self) -> int:
        return self._tool_num.value()
