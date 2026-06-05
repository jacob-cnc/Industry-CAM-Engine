"""Threading parameter panel for the Program tab.

Displays input fields for threading operations (G76 cycle parameters).
Swaps into the parameter area when a threading block is selected.
"""

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QComboBox, QSpinBox,
    QLabel, QHBoxLayout, QGroupBox,
)

from gui.colors import COLORS, FONTS
from gui.components.numeric_field import NumericField, NumericFieldConfig


# Thread standard data (subset — full tables in steering/thread-data.md)
THREAD_STANDARDS = {
    "UNC": [
        "1/4-20", "5/16-18", "3/8-16", "7/16-14", "1/2-13",
        "9/16-12", "5/8-11", "3/4-10", "7/8-9", "1-8",
        "1-1/8-7", "1-1/4-7", "1-3/8-6", "1-1/2-6",
    ],
    "UNF": [
        "1/4-28", "5/16-24", "3/8-24", "7/16-20", "1/2-20",
        "9/16-18", "5/8-18", "3/4-16", "7/8-14", "1-12",
        "1-1/4-12", "1-1/2-12",
    ],
    "NPT": [
        "1/8-27", "1/4-18", "3/8-18", "1/2-14", "3/4-14",
        "1-11.5", "1-1/4-11.5", "1-1/2-11.5", "2-11.5",
    ],
    "Metric": [
        "M6x1.0", "M8x1.25", "M10x1.5", "M12x1.75",
        "M14x2.0", "M16x2.0", "M18x2.5", "M20x2.5",
        "M24x3.0", "M30x3.5",
    ],
    "ACME": [
        "1/2-10", "5/8-8", "3/4-6", "1-5", "1-1/4-5",
        "1-1/2-4", "2-4",
    ],
}

INFEED_METHODS = ["modified_flank", "flank", "radial", "alternating"]
CHAMFER_OPTIONS = ["0", "0.5", "1.0", "1.5"]


class ThreadingPanel(QWidget):
    """Parameter input panel for threading operations.

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

        # Thread selection
        form1 = QFormLayout()
        form1.setSpacing(2)

        self._standard_combo = QComboBox()
        self._standard_combo.addItems(list(THREAD_STANDARDS.keys()))
        form1.addRow("Standard:", self._standard_combo)

        self._designation_combo = QComboBox()
        self._designation_combo.setEditable(True)  # Allow custom entry
        form1.addRow("Size:", self._designation_combo)

        layout.addLayout(form1)

        # Geometry fields
        form2 = QFormLayout()
        form2.setSpacing(2)

        self._major_dia = NumericField(NumericFieldConfig(
            min_value=0.05, max_value=4.0, decimals=4, default_value=0.5, suffix='"'))
        form2.addRow("Major Dia:", self._major_dia)

        self._tpi = NumericField(NumericFieldConfig(
            min_value=2, max_value=80, decimals=1, default_value=13, suffix=" TPI"))
        form2.addRow("TPI:", self._tpi)

        self._thread_length = NumericField(NumericFieldConfig(
            min_value=0.050, max_value=12.0, decimals=4, default_value=0.750, suffix='"'))
        form2.addRow("Length:", self._thread_length)

        self._depth_label = QLabel("0.0417")
        self._depth_label.setStyleSheet(
            f"color: {COLORS['text_secondary']}; font-family: 'JetBrains Mono';"
        )
        form2.addRow("Depth (calc):", self._depth_label)

        layout.addLayout(form2)

        # Cycle parameters
        form3 = QFormLayout()
        form3.setSpacing(2)

        self._infeed_combo = QComboBox()
        self._infeed_combo.addItems(["Modified Flank (30°)", "Flank (29.5°)", "Radial (0°)", "Alternating"])
        form3.addRow("Infeed:", self._infeed_combo)

        self._num_passes = QSpinBox()
        self._num_passes.setRange(3, 20)
        self._num_passes.setValue(6)
        form3.addRow("Passes:", self._num_passes)

        self._spring_passes = QSpinBox()
        self._spring_passes.setRange(0, 5)
        self._spring_passes.setValue(2)
        form3.addRow("Spring:", self._spring_passes)

        self._chamfer_combo = QComboBox()
        self._chamfer_combo.addItems(["None", "0.5 thread", "1 thread", "1.5 threads"])
        self._chamfer_combo.setCurrentIndex(2)  # Default "1 thread"
        form3.addRow("Chamfer:", self._chamfer_combo)

        self._num_starts = QSpinBox()
        self._num_starts.setRange(1, 6)
        self._num_starts.setValue(1)
        form3.addRow("Starts:", self._num_starts)

        layout.addLayout(form3)

        # Z positions + RPM + Tool
        form4 = QFormLayout()
        form4.setSpacing(2)

        self._start_z = NumericField(NumericFieldConfig(
            min_value=-12.0, max_value=1.0, decimals=4, default_value=0.050, suffix='"'))
        form4.addRow("Start Z:", self._start_z)

        self._end_z = NumericField(NumericFieldConfig(
            min_value=-12.0, max_value=0.0, decimals=4, default_value=-0.750, suffix='"'))
        form4.addRow("End Z:", self._end_z)

        self._rpm = NumericField(NumericFieldConfig(
            min_value=50, max_value=3000, decimals=0, default_value=400, suffix=" RPM"))
        form4.addRow("RPM:", self._rpm)

        self._tool_num = QSpinBox()
        self._tool_num.setRange(1, 99)
        self._tool_num.setValue(3)
        self._tool_num.setPrefix("T")
        form4.addRow("Tool:", self._tool_num)

        layout.addLayout(form4)
        layout.addStretch()

        # Populate initial designations
        self._on_standard_changed(0)

    def _connect_signals(self):
        self._standard_combo.currentIndexChanged.connect(self._on_standard_changed)
        self._designation_combo.currentTextChanged.connect(self._on_designation_changed)
        self._major_dia.value_changed.connect(self._update_depth)
        self._tpi.value_changed.connect(self._update_depth)
        # Connect all fields to params_changed
        for field in [self._major_dia, self._tpi, self._thread_length,
                      self._start_z, self._end_z, self._rpm]:
            field.value_changed.connect(self.params_changed.emit)
        self._standard_combo.currentIndexChanged.connect(lambda _: self.params_changed.emit())
        self._infeed_combo.currentIndexChanged.connect(lambda _: self.params_changed.emit())
        self._num_passes.valueChanged.connect(lambda _: self.params_changed.emit())
        self._spring_passes.valueChanged.connect(lambda _: self.params_changed.emit())
        self._chamfer_combo.currentIndexChanged.connect(lambda _: self.params_changed.emit())
        self._num_starts.valueChanged.connect(lambda _: self.params_changed.emit())
        self._tool_num.valueChanged.connect(lambda _: self.params_changed.emit())

    def _on_standard_changed(self, index: int):
        """Update designation dropdown when standard changes."""
        standard = self._standard_combo.currentText()
        designations = THREAD_STANDARDS.get(standard, [])
        self._designation_combo.clear()
        self._designation_combo.addItems(designations)
        self._update_depth()

    def _on_designation_changed(self, text: str):
        """Auto-fill major diameter and TPI from designation."""
        # Try to parse TPI from designation (e.g., "1/2-13" → TPI=13)
        if not text:
            return
        parts = text.split("-")
        if len(parts) == 2:
            try:
                tpi = float(parts[1])
                self._tpi.set_value(tpi)
            except ValueError:
                pass
        self._update_depth()
        self.params_changed.emit()

    def _update_depth(self):
        """Recompute thread depth from current standard and TPI."""
        tpi = self._tpi.value()
        if tpi <= 0:
            return
        pitch = 1.0 / tpi
        standard = self._standard_combo.currentText()

        if standard == "ACME":
            depth = 0.5 * pitch
        elif standard == "NPT":
            depth = 0.692820 * pitch
        else:
            # UN, Metric (60° thread)
            depth = 0.541266 * pitch

        self._depth_label.setText(f"{depth:.5f}\"")

    # ------------------------------------------------------------------
    # Public data access
    # ------------------------------------------------------------------

    def get_values(self) -> dict:
        """Return all field values as a dict for ThreadingParams construction."""
        tpi = self._tpi.value()
        pitch = 1.0 / tpi if tpi > 0 else 0.07692
        standard = self._standard_combo.currentText()

        if standard == "ACME":
            depth = 0.5 * pitch
        elif standard == "NPT":
            depth = 0.692820 * pitch
        else:
            depth = 0.541266 * pitch

        infeed_map = {0: "modified_flank", 1: "flank", 2: "radial", 3: "alternating"}
        chamfer_map = {0: 0.0, 1: 0.5, 2: 1.0, 3: 1.5}

        return {
            "thread_standard": standard,
            "designation": self._designation_combo.currentText(),
            "major_diameter": self._major_dia.value(),
            "pitch": pitch,
            "thread_depth": depth,
            "start_z": self._start_z.value(),
            "end_z": self._end_z.value(),
            "infeed_method": infeed_map.get(self._infeed_combo.currentIndex(), "modified_flank"),
            "num_passes": self._num_passes.value(),
            "spring_passes": self._spring_passes.value(),
            "chamfer_threads": chamfer_map.get(self._chamfer_combo.currentIndex(), 1.0),
            "num_starts": self._num_starts.value(),
            "spindle_rpm": self._rpm.value(),
            "tool_number": self._tool_num.value(),
        }

    def set_values(self, data: dict):
        """Populate fields from a dict (for file load)."""
        if "thread_standard" in data:
            idx = self._standard_combo.findText(data["thread_standard"])
            if idx >= 0:
                self._standard_combo.setCurrentIndex(idx)
        if "designation" in data:
            self._designation_combo.setCurrentText(data["designation"])
        if "major_diameter" in data:
            self._major_dia.set_value(data["major_diameter"])
        if "pitch" in data and data["pitch"] > 0:
            self._tpi.set_value(1.0 / data["pitch"])
        if "start_z" in data:
            self._start_z.set_value(data["start_z"])
        if "end_z" in data:
            self._end_z.set_value(data["end_z"])
        if "infeed_method" in data:
            methods = {"modified_flank": 0, "flank": 1, "radial": 2, "alternating": 3}
            self._infeed_combo.setCurrentIndex(methods.get(data["infeed_method"], 0))
        if "num_passes" in data:
            self._num_passes.setValue(data["num_passes"])
        if "spring_passes" in data:
            self._spring_passes.setValue(data["spring_passes"])
        if "chamfer_threads" in data:
            chamfers = {0.0: 0, 0.5: 1, 1.0: 2, 1.5: 3}
            self._chamfer_combo.setCurrentIndex(chamfers.get(data["chamfer_threads"], 2))
        if "num_starts" in data:
            self._num_starts.setValue(data["num_starts"])
        if "spindle_rpm" in data:
            self._rpm.set_value(data["spindle_rpm"])
        if "tool_number" in data:
            self._tool_num.setValue(data["tool_number"])

    def get_tool_number(self) -> int:
        return self._tool_num.value()
