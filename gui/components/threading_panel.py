"""Threading parameter panel for the Program tab.

Displays input fields for threading operations (G76 cycle parameters).
Swaps into the parameter area when a threading block is selected.

Features:
    - Standard thread size selection (UNC/UNF interleaved by diameter, Metric, ACME, NPT)
    - Custom mode for non-standard threads
    - Tolerance position (MMC / Mid / LMC) with computed target dimensions
    - Thread class (1A / 2A / 3A) — affects allowance and tolerance band width
    - All fields 44px touch targets
"""

import math
from typing import Optional

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QComboBox, QSpinBox,
    QLabel,
)

from gui.colors import COLORS, FONTS
from gui.components.numeric_field import NumericField, NumericFieldConfig


# ---------------------------------------------------------------------------
# Standard thread sizes — interleaved by diameter (coarse then fine per size)
# Format: (display_name, major_dia_inches, tpi, standard_key)
# For metric: major_dia is in mm, tpi computed from pitch_mm
# ---------------------------------------------------------------------------

_UN_THREADS = [
    ("#4-40 UNC", 0.1120, 40),
    ("#4-48 UNF", 0.1120, 48),
    ("#6-32 UNC", 0.1380, 32),
    ("#6-40 UNF", 0.1380, 40),
    ("#8-32 UNC", 0.1640, 32),
    ("#8-36 UNF", 0.1640, 36),
    ("#10-24 UNC", 0.1900, 24),
    ("#10-32 UNF", 0.1900, 32),
    ("1/4-20 UNC", 0.2500, 20),
    ("1/4-28 UNF", 0.2500, 28),
    ("5/16-18 UNC", 0.3125, 18),
    ("5/16-24 UNF", 0.3125, 24),
    ("3/8-16 UNC", 0.3750, 16),
    ("3/8-24 UNF", 0.3750, 24),
    ("7/16-14 UNC", 0.4375, 14),
    ("7/16-20 UNF", 0.4375, 20),
    ("1/2-13 UNC", 0.5000, 13),
    ("1/2-20 UNF", 0.5000, 20),
    ("9/16-12 UNC", 0.5625, 12),
    ("9/16-18 UNF", 0.5625, 18),
    ("5/8-11 UNC", 0.6250, 11),
    ("5/8-18 UNF", 0.6250, 18),
    ("3/4-10 UNC", 0.7500, 10),
    ("3/4-16 UNF", 0.7500, 16),
    ("7/8-9 UNC", 0.8750, 9),
    ("7/8-14 UNF", 0.8750, 14),
    ("1-8 UNC", 1.0000, 8),
    ("1-12 UNF", 1.0000, 12),
    ("1-1/8-7 UNC", 1.1250, 7),
    ("1-1/4-7 UNC", 1.2500, 7),
    ("1-1/4-12 UNF", 1.2500, 12),
    ("1-3/8-6 UNC", 1.3750, 6),
    ("1-1/2-6 UNC", 1.5000, 6),
    ("1-1/2-12 UNF", 1.5000, 12),
    ("1-3/4-5 UNC", 1.7500, 5),
    ("2-4.5 UNC", 2.0000, 4.5),
]

_METRIC_THREADS = [
    ("M3×0.5", 3.0, 0.5),
    ("M4×0.7", 4.0, 0.7),
    ("M5×0.8", 5.0, 0.8),
    ("M6×1.0", 6.0, 1.0),
    ("M8×1.25", 8.0, 1.25),
    ("M8×1.0 Fine", 8.0, 1.0),
    ("M10×1.5", 10.0, 1.5),
    ("M10×1.25 Fine", 10.0, 1.25),
    ("M12×1.75", 12.0, 1.75),
    ("M12×1.5 Fine", 12.0, 1.5),
    ("M14×2.0", 14.0, 2.0),
    ("M16×2.0", 16.0, 2.0),
    ("M16×1.5 Fine", 16.0, 1.5),
    ("M20×2.5", 20.0, 2.5),
    ("M20×1.5 Fine", 20.0, 1.5),
    ("M24×3.0", 24.0, 3.0),
    ("M30×3.5", 30.0, 3.5),
]

_NPT_THREADS = [
    ("1/8-27 NPT", 0.405, 27),
    ("1/4-18 NPT", 0.540, 18),
    ("3/8-18 NPT", 0.675, 18),
    ("1/2-14 NPT", 0.840, 14),
    ("3/4-14 NPT", 1.050, 14),
    ("1-11.5 NPT", 1.315, 11.5),
    ("1-1/4-11.5 NPT", 1.660, 11.5),
    ("1-1/2-11.5 NPT", 1.900, 11.5),
    ("2-11.5 NPT", 2.375, 11.5),
]

_ACME_THREADS = [
    ("1/4-16 ACME", 0.2500, 16),
    ("3/8-12 ACME", 0.3750, 12),
    ("1/2-10 ACME", 0.5000, 10),
    ("5/8-8 ACME", 0.6250, 8),
    ("3/4-6 ACME", 0.7500, 6),
    ("1-5 ACME", 1.0000, 5),
    ("1-1/4-5 ACME", 1.2500, 5),
    ("1-1/2-4 ACME", 1.5000, 4),
    ("2-4 ACME", 2.0000, 4),
]


def _build_size_list():
    """Build the complete size dropdown list."""
    items = ["Custom"]
    for name, _, _ in _UN_THREADS:
        items.append(name)
    for name, _, _ in _METRIC_THREADS:
        items.append(name)
    for name, _, _ in _NPT_THREADS:
        items.append(name)
    for name, _, _ in _ACME_THREADS:
        items.append(name)
    return items


# ---------------------------------------------------------------------------
# Tolerance computation (ASME B1.1 class 2A/3A/1A)
# ---------------------------------------------------------------------------

def _compute_un_tolerance(d_basic, pitch, thread_class):
    """Compute pitch diameter tolerance and allowance for UN threads."""
    le = d_basic
    td2_2a = (0.0015 * d_basic ** (1.0/3.0) +
              0.0015 * le ** 0.5 +
              0.015 * pitch ** (2.0/3.0))

    if thread_class == "1A":
        td2 = td2_2a * 1.5
    elif thread_class == "3A":
        td2 = td2_2a * 0.75
    else:
        td2 = td2_2a

    # Allowance
    if thread_class == "3A":
        es = 0.0
    else:
        es = 0.300 * td2_2a

    return td2, es


def _resolve_thread(designation, thread_class="2A", tolerance_pos="mid"):
    """Resolve a thread designation into target dimensions.

    Returns dict with target_major, target_pitch, target_minor, depth, pitch, tpi,
    max_pitch, min_pitch, or None if not found.
    """
    # Find in UN threads
    for name, d_basic, tpi in _UN_THREADS:
        if name == designation:
            pitch = 1.0 / tpi
            H = 0.866025404 * pitch
            depth = (5.0/8.0) * H
            basic_pitch = d_basic - 2 * (3.0/8.0) * H

            td2, es = _compute_un_tolerance(d_basic, pitch, thread_class)
            max_pitch = basic_pitch - es
            min_pitch = max_pitch - td2

            if tolerance_pos == "mmc":
                target_pitch = max_pitch
            elif tolerance_pos == "lmc":
                target_pitch = min_pitch
            else:
                target_pitch = (max_pitch + min_pitch) / 2.0

            # Major: apply allowance
            td_major = 0.060 * pitch ** (2.0/3.0)
            if thread_class == "1A":
                td_major = 0.090 * pitch ** (2.0/3.0)
            max_major = d_basic - es
            min_major = max_major - td_major

            if tolerance_pos == "mmc":
                target_major = max_major
            elif tolerance_pos == "lmc":
                target_major = min_major
            else:
                target_major = (max_major + min_major) / 2.0

            target_minor = target_major - 2 * depth

            return {
                "target_major": target_major,
                "target_pitch": target_pitch,
                "target_minor": target_minor,
                "depth": depth,
                "pitch": pitch,
                "tpi": tpi,
                "max_pitch": max_pitch,
                "min_pitch": min_pitch,
                "standard": "UN",
            }

    # Metric threads (6g tolerance, simplified)
    for name, d_mm, p_mm in _METRIC_THREADS:
        if name == designation:
            d_basic = d_mm / 25.4
            pitch = p_mm / 25.4
            tpi = 25.4 / p_mm
            H = 0.866025404 * pitch
            depth = (5.0/8.0) * H
            basic_pitch = d_basic - 0.6495 * pitch

            es_um = 15.0 + 11.0 * p_mm
            es = es_um / 25400.0
            td2_um = 90.0 * (p_mm ** 0.4) * (d_mm ** 0.1)
            td2 = td2_um / 25400.0

            max_pitch = basic_pitch - es
            min_pitch = max_pitch - td2

            if tolerance_pos == "mmc":
                target_pitch = max_pitch
            elif tolerance_pos == "lmc":
                target_pitch = min_pitch
            else:
                target_pitch = (max_pitch + min_pitch) / 2.0

            td_major = 0.060 * pitch ** (2.0/3.0)
            max_major = d_basic - es
            min_major = max_major - td_major

            if tolerance_pos == "mmc":
                target_major = max_major
            elif tolerance_pos == "lmc":
                target_major = min_major
            else:
                target_major = (max_major + min_major) / 2.0

            target_minor = target_major - 2 * depth

            return {
                "target_major": target_major,
                "target_pitch": target_pitch,
                "target_minor": target_minor,
                "depth": depth,
                "pitch": pitch,
                "tpi": tpi,
                "max_pitch": max_pitch,
                "min_pitch": min_pitch,
                "standard": "Metric",
            }

    # NPT
    for name, d_basic, tpi in _NPT_THREADS:
        if name == designation:
            pitch = 1.0 / tpi
            H = 0.866025404 * pitch
            depth = 0.8 * H  # NPT truncated
            return {
                "target_major": d_basic,
                "target_pitch": d_basic - 2 * (3.0/8.0) * H,
                "target_minor": d_basic - 2 * depth,
                "depth": depth,
                "pitch": pitch,
                "tpi": tpi,
                "max_pitch": 0, "min_pitch": 0,
                "standard": "NPT",
            }

    # ACME
    for name, d_basic, tpi in _ACME_THREADS:
        if name == designation:
            pitch = 1.0 / tpi
            depth = pitch / 2.0
            es = 0.010 * math.sqrt(pitch)
            target_major = d_basic - es
            return {
                "target_major": target_major,
                "target_pitch": target_major - depth,
                "target_minor": target_major - 2 * depth,
                "depth": depth,
                "pitch": pitch,
                "tpi": tpi,
                "max_pitch": 0, "min_pitch": 0,
                "standard": "ACME",
            }

    return None


# ---------------------------------------------------------------------------
# Widget
# ---------------------------------------------------------------------------

class ThreadingPanel(QWidget):
    """Parameter input panel for threading operations.

    Signals:
        params_changed(): Emitted when any field value changes.
    """

    params_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._suppress = False
        self._setup_ui()
        self._connect_signals()
        self._update_custom_visibility()
        self._update_info()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        form = QFormLayout()
        form.setSpacing(4)

        # Size selector (standard sizes + Custom)
        self._size_combo = QComboBox()
        self._size_combo.addItems(_build_size_list())
        self._size_combo.setCurrentIndex(
            self._size_combo.findText("1/2-13 UNC"))
        self._size_combo.setMinimumHeight(44)
        form.addRow("Size:", self._size_combo)

        # Fit (tolerance position)
        self._fit_combo = QComboBox()
        self._fit_combo.addItems(["Mid", "MMC", "LMC"])
        self._fit_combo.setMinimumHeight(44)
        self._fit_combo.setToolTip(
            "MMC = Maximum Material, tightest fit\n"
            "Mid = Middle of tolerance band\n"
            "LMC = Least Material, loosest fit"
        )
        form.addRow("Fit:", self._fit_combo)

        # Class (1A / 2A / 3A)
        self._class_combo = QComboBox()
        self._class_combo.addItems(["2A", "3A", "1A"])
        self._class_combo.setMinimumHeight(44)
        form.addRow("Class:", self._class_combo)

        # Direction
        self._direction_combo = QComboBox()
        self._direction_combo.addItems(["External", "Internal"])
        self._direction_combo.setMinimumHeight(44)
        form.addRow("Direction:", self._direction_combo)

        # --- Custom fields (visible only in Custom mode) ---
        self._custom_tpi_label = QLabel("TPI:")
        self._custom_tpi = NumericField(NumericFieldConfig(
            min_value=2.0, max_value=80.0, decimals=1,
            default_value=13.0, suffix=" TPI"))
        self._custom_tpi.setMinimumHeight(44)
        form.addRow(self._custom_tpi_label, self._custom_tpi)

        self._custom_major_label = QLabel("Major Ø:")
        self._custom_major = NumericField(NumericFieldConfig(
            min_value=0.050, max_value=10.0, decimals=4,
            default_value=0.5000, suffix='"'))
        self._custom_major.setMinimumHeight(44)
        form.addRow(self._custom_major_label, self._custom_major)

        self._custom_std_label = QLabel("Form:")
        self._custom_std = QComboBox()
        self._custom_std.addItems(["UN (60°)", "ACME (29°)"])
        self._custom_std.setMinimumHeight(44)
        form.addRow(self._custom_std_label, self._custom_std)

        # --- Operation fields (always visible) ---
        self._start_z = NumericField(NumericFieldConfig(
            min_value=0.0, max_value=5.0, decimals=4,
            default_value=0.050, suffix='"'))
        self._start_z.setMinimumHeight(44)
        form.addRow("Z Start:", self._start_z)

        self._end_z = NumericField(NumericFieldConfig(
            min_value=-12.0, max_value=0.0, decimals=4,
            default_value=-0.750, suffix='"'))
        self._end_z.setMinimumHeight(44)
        form.addRow("Z End:", self._end_z)

        self._infeed_combo = QComboBox()
        self._infeed_combo.addItems([
            "Modified Flank (30°)", "Flank (29.5°)", "Radial (0°)", "Alternating"])
        self._infeed_combo.setMinimumHeight(44)
        form.addRow("Infeed:", self._infeed_combo)

        self._num_passes = QSpinBox()
        self._num_passes.setRange(3, 20)
        self._num_passes.setValue(6)
        self._num_passes.setMinimumHeight(44)
        form.addRow("Passes:", self._num_passes)

        self._spring_passes = QSpinBox()
        self._spring_passes.setRange(0, 5)
        self._spring_passes.setValue(2)
        self._spring_passes.setMinimumHeight(44)
        form.addRow("Spring:", self._spring_passes)

        self._chamfer_combo = QComboBox()
        self._chamfer_combo.addItems(["None", "0.5 thread", "1 thread", "1.5 threads"])
        self._chamfer_combo.setCurrentIndex(2)
        self._chamfer_combo.setMinimumHeight(44)
        form.addRow("Chamfer:", self._chamfer_combo)

        self._num_starts = QSpinBox()
        self._num_starts.setRange(1, 8)
        self._num_starts.setValue(1)
        self._num_starts.setMinimumHeight(44)
        form.addRow("Starts:", self._num_starts)

        self._rpm = NumericField(NumericFieldConfig(
            min_value=50, max_value=2000, decimals=0,
            default_value=400, suffix=" RPM"))
        self._rpm.setMinimumHeight(44)
        form.addRow("RPM:", self._rpm)

        self._tool_num = QSpinBox()
        self._tool_num.setRange(1, 99)
        self._tool_num.setValue(2)
        self._tool_num.setPrefix("T")
        self._tool_num.setMinimumHeight(44)
        form.addRow("Tool:", self._tool_num)

        layout.addLayout(form)

        # Computed info display
        self._info_label = QLabel("")
        self._info_label.setWordWrap(True)
        self._info_label.setStyleSheet(
            f"color: {COLORS['text_secondary']}; font-size: {FONTS['small_size']}pt;"
            f" padding: 6px; background-color: {COLORS['bg_surface']};"
            f" border-radius: 3px;"
            f" font-family: {FONTS['mono_family']}, {FONTS['fallback_mono']};"
        )
        layout.addWidget(self._info_label)
        layout.addStretch()

    def _connect_signals(self):
        self._size_combo.currentIndexChanged.connect(self._on_size_changed)
        self._fit_combo.currentIndexChanged.connect(self._on_spec_changed)
        self._class_combo.currentIndexChanged.connect(self._on_spec_changed)
        self._direction_combo.currentIndexChanged.connect(self._emit)
        self._custom_tpi.value_changed.connect(self._on_spec_changed)
        self._custom_major.value_changed.connect(self._on_spec_changed)
        self._custom_std.currentIndexChanged.connect(self._on_spec_changed)
        self._start_z.value_changed.connect(self._emit)
        self._end_z.value_changed.connect(self._emit)
        self._infeed_combo.currentIndexChanged.connect(self._emit)
        self._num_passes.valueChanged.connect(self._emit)
        self._spring_passes.valueChanged.connect(self._emit)
        self._chamfer_combo.currentIndexChanged.connect(self._emit)
        self._num_starts.valueChanged.connect(self._emit)
        self._rpm.value_changed.connect(self._emit)
        self._tool_num.valueChanged.connect(self._emit)

    def _emit(self, *args):
        if not self._suppress:
            self.params_changed.emit()

    def _on_size_changed(self, index):
        self._update_custom_visibility()
        self._update_info()
        self._emit()

    def _on_spec_changed(self, *args):
        self._update_info()
        self._emit()

    def _update_custom_visibility(self):
        is_custom = (self._size_combo.currentText() == "Custom")
        self._custom_tpi_label.setVisible(is_custom)
        self._custom_tpi.setVisible(is_custom)
        self._custom_major_label.setVisible(is_custom)
        self._custom_major.setVisible(is_custom)
        self._custom_std_label.setVisible(is_custom)
        self._custom_std.setVisible(is_custom)

    def _update_info(self):
        """Update computed dimensions display."""
        spec = self._resolve_spec()
        if spec is None:
            self._info_label.setText("(select a thread size)")
            return

        max_rpm = (1.5 / spec["pitch"]) * 60.0 if spec["pitch"] > 0 else 9999
        lines = [
            f"Target Major Ø: {spec['target_major']:.4f}\"",
            f"Target Pitch Ø: {spec['target_pitch']:.4f}\"",
            f"Target Minor Ø: {spec['target_minor']:.4f}\"",
            f"Depth (dia): {spec['depth']*2:.5f}\"",
            f"Max RPM: {max_rpm:.0f}",
        ]
        if spec["max_pitch"] and spec["min_pitch"]:
            lines.append(
                f"Pitch band: {spec['max_pitch']:.4f} – {spec['min_pitch']:.4f}")
        self._info_label.setText("\n".join(lines))

    def _resolve_spec(self) -> Optional[dict]:
        """Resolve current selections to thread dimensions."""
        designation = self._size_combo.currentText()
        fit_map = {0: "mid", 1: "mmc", 2: "lmc"}
        class_map = {0: "2A", 1: "3A", 2: "1A"}
        tolerance_pos = fit_map.get(self._fit_combo.currentIndex(), "mid")
        thread_class = class_map.get(self._class_combo.currentIndex(), "2A")

        if designation == "Custom":
            tpi = self._custom_tpi.value()
            major = self._custom_major.value()
            pitch = 1.0 / tpi if tpi > 0 else 0.05
            is_acme = self._custom_std.currentIndex() == 1
            if is_acme:
                depth = pitch / 2.0
            else:
                H = 0.866025404 * pitch
                depth = (5.0/8.0) * H
            return {
                "target_major": major,
                "target_pitch": major - depth,
                "target_minor": major - 2 * depth,
                "depth": depth,
                "pitch": pitch,
                "tpi": tpi,
                "max_pitch": 0, "min_pitch": 0,
                "standard": "ACME" if is_acme else "UN",
            }

        return _resolve_thread(designation, thread_class, tolerance_pos)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_values(self) -> dict:
        """Return all field values as a dict for ThreadingParams construction."""
        spec = self._resolve_spec()
        if spec is None:
            spec = {"pitch": 0.05, "depth": 0.02, "target_major": 0.5,
                    "tpi": 13, "standard": "UN"}

        infeed_map = {0: "modified_flank", 1: "flank", 2: "radial", 3: "alternating"}
        chamfer_map = {0: 0.0, 1: 0.5, 2: 1.0, 3: 1.5}

        return {
            "thread_standard": spec.get("standard", "UN"),
            "designation": self._size_combo.currentText(),
            "major_diameter": spec["target_major"],
            "pitch": spec["pitch"],
            "thread_depth": spec["depth"],
            "start_z": self._start_z.value(),
            "end_z": self._end_z.value(),
            "infeed_method": infeed_map.get(self._infeed_combo.currentIndex(), "modified_flank"),
            "num_passes": self._num_passes.value(),
            "spring_passes": self._spring_passes.value(),
            "chamfer_threads": chamfer_map.get(self._chamfer_combo.currentIndex(), 1.0),
            "num_starts": self._num_starts.value(),
            "spindle_rpm": self._rpm.value(),
            "tool_number": self._tool_num.value(),
            "is_internal": self._direction_combo.currentIndex() == 1,
            # Save UI state for reload
            "fit": ["mid", "mmc", "lmc"][self._fit_combo.currentIndex()],
            "thread_class": ["2A", "3A", "1A"][self._class_combo.currentIndex()],
        }

    def set_values(self, data: dict):
        """Populate fields from a dict (for file load)."""
        self._suppress = True
        try:
            if "designation" in data:
                idx = self._size_combo.findText(data["designation"])
                if idx >= 0:
                    self._size_combo.setCurrentIndex(idx)
                elif data["designation"] not in ("Custom", ""):
                    # Legacy format — try matching by standard + size
                    self._size_combo.setCurrentIndex(0)  # Custom
            if "fit" in data:
                fit_map = {"mid": 0, "mmc": 1, "lmc": 2}
                self._fit_combo.setCurrentIndex(fit_map.get(data["fit"], 0))
            if "thread_class" in data:
                class_map = {"2A": 0, "3A": 1, "1A": 2}
                self._class_combo.setCurrentIndex(class_map.get(data["thread_class"], 0))
            if "is_internal" in data:
                self._direction_combo.setCurrentIndex(1 if data["is_internal"] else 0)
            if "pitch" in data and data["pitch"] > 0:
                self._custom_tpi.set_value(1.0 / data["pitch"])
            if "major_diameter" in data:
                self._custom_major.set_value(data["major_diameter"])
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
            self._update_custom_visibility()
            self._update_info()
        finally:
            self._suppress = False

    def get_tool_number(self) -> int:
        return self._tool_num.value()
