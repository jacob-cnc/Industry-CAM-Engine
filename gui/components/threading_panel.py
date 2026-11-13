"""Threading parameter panel (owner plan 2026-11-12,
docs/handoffs/2026-11-12-threading-workflow-plan.md, phase T2).

Field-driven threads: OD / ID, tool, thread type + size + class (or Custom with
a form), X start / X end (nominal major), Z start / Z end (Z end = where the
tool pulls out), pitch, pilot (ID), RPM, passes, spring passes, starts, entry
angle. The depth is derived from the standard and class (models/thread_data.py)
and shown read-only with its source. Hints: the pitch-diameter window (OD;
NPT: L1 / ring gauge) or the tap drill (ID). Editing X or the pitch by hand
after choosing a size turns the thread into Custom (the hint never describes
a thread other than the one being cut). All fields 44 px touch targets.
"""

from typing import Optional

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QComboBox, QFormLayout, QLabel, QSpinBox, QVBoxLayout, QWidget

from gui.colors import COLORS, FONTS
from gui.components.numeric_field import NumericField, NumericFieldConfig
from models import thread_data as td

CUSTOM = "Custom"
SIDES = ["External (OD)", "Internal (ID)"]
FORM_KEYS = ["60", "acme", "tr", "npt"]
PITCH_UNITS = ["TPI", "mm"]


def _field(lo, hi, dec, default, suffix, unit_aware=True):
    f = NumericField(NumericFieldConfig(min_value=lo, max_value=hi, decimals=dec,
                                        default_value=default, suffix=suffix,
                                        unit_aware=unit_aware))
    f.setMinimumHeight(44)
    return f


def _combo(items):
    c = QComboBox()
    c.addItems(items)
    c.setMinimumHeight(44)
    return c


def _spin(lo, hi, value, prefix=""):
    s = QSpinBox()
    s.setRange(lo, hi)
    s.setValue(value)
    s.setMinimumHeight(44)
    if prefix:
        s.setPrefix(prefix)
    return s


class ThreadingPanel(QWidget):
    """Parameter input panel for threading blocks.

    Signals:
        params_changed(): any field changed.
        side_changed(bool): OD / ID changed by the user (True = internal).
    """

    params_changed = pyqtSignal()
    side_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._suppress = False
        self._setup_ui()
        self._connect_signals()
        self._fill_sizes()
        self._size.blockSignals(True)
        self._size.setCurrentText("1/2-13 UNC")
        self._size.blockSignals(False)
        self._apply_size()
        self._refresh()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        form = QFormLayout()
        form.setSpacing(4)
        self._form = form

        self._side = _combo(SIDES)
        form.addRow("OD / ID:", self._side)
        self._tool_num = _spin(1, 99, 2, "T")
        form.addRow("Tool:", self._tool_num)
        self._type = _combo([CUSTOM] + td.THREAD_TYPES)
        self._type.setCurrentText("UNC")
        form.addRow("Thread:", self._type)
        self._size_label = QLabel("Size:")
        self._size = _combo([])
        form.addRow(self._size_label, self._size)
        self._class_label = QLabel("Class:")
        self._class = _combo([])
        form.addRow(self._class_label, self._class)
        self._form_label = QLabel("Form:")
        self._form_combo = _combo([td.FORM_LABELS[k] for k in FORM_KEYS])
        form.addRow(self._form_label, self._form_combo)

        self._x_start = _field(0.010, 12.0, 4, 0.5, '"')
        form.addRow("X start:", self._x_start)
        self._x_end = _field(0.010, 12.0, 4, 0.5, '"')
        form.addRow("X end:", self._x_end)
        self._z_start = _field(-12.0, 5.0, 4, 0.10, '"')
        form.addRow("Z start:", self._z_start)
        self._z_end = _field(-12.0, 5.0, 4, -0.75, '"')
        self._z_end.setToolTip("Where the tool pulls out of the thread")
        form.addRow("Z end:", self._z_end)

        self._pitch = _field(0.05, 80.0, 3, 13.0, "", unit_aware=False)
        self._pitch_unit = _combo(PITCH_UNITS)
        self._pitch_label = QLabel("Pitch (TPI):")
        form.addRow(self._pitch_label, self._pitch)
        self._pitch_unit_label = QLabel("Pitch unit:")
        form.addRow(self._pitch_unit_label, self._pitch_unit)

        self._depth_label = QLabel("")
        form.addRow("Depth:", self._depth_label)
        self._pilot_label = QLabel("Pilot Ø:")
        self._pilot = _field(0.010, 12.0, 4, 0.4219, '"')
        self._pilot.setToolTip("Bore the thread is cut in (tap drill); retract at pilot - .005")
        form.addRow(self._pilot_label, self._pilot)

        self._rpm = _field(20, 3000, 0, 300, " RPM", unit_aware=False)
        form.addRow("RPM:", self._rpm)
        self._num_passes = _spin(1, 40, 6)
        form.addRow("Passes:", self._num_passes)
        self._spring_passes = _spin(0, 5, 1)
        form.addRow("Spring passes:", self._spring_passes)
        self._num_starts = _spin(1, 8, 1)
        form.addRow("Starts:", self._num_starts)
        self._entry = _field(0.0, 45.0, 1, 29.5, "°", unit_aware=False)
        self._entry.setToolTip("Compound infeed angle (G76 Q); 0 = straight plunge")
        form.addRow("Entry angle:", self._entry)
        layout.addLayout(form)

        self._hint = QLabel("")
        self._hint.setWordWrap(True)
        self._hint.setStyleSheet(
            f"color: {COLORS['text_secondary']}; font-size: {FONTS['small_size']}pt;"
            f" padding: 6px; background-color: {COLORS['bg_surface']}; border-radius: 3px;"
            f" font-family: {FONTS['mono_family']}, {FONTS['fallback_mono']};")
        layout.addWidget(self._hint)
        layout.addStretch()

    def _connect_signals(self):
        self._side.currentIndexChanged.connect(self._on_side)
        self._type.currentIndexChanged.connect(self._on_type)
        self._size.currentIndexChanged.connect(self._on_size)
        self._class.currentIndexChanged.connect(self._on_spec)
        self._form_combo.currentIndexChanged.connect(self._on_form)
        self._pitch_unit.currentIndexChanged.connect(self._on_pitch_unit)
        for f in (self._x_start, self._x_end, self._pitch):
            f.value_changed.connect(self._on_geometry_edit)
        for f in (self._z_start, self._z_end):
            f.value_changed.connect(self._on_z)
        for f in (self._pilot, self._rpm, self._entry):
            f.value_changed.connect(self._on_spec)
        for s in (self._num_passes, self._spring_passes, self._num_starts, self._tool_num):
            s.valueChanged.connect(self._on_spec)

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    def is_internal(self) -> bool:
        return self._side.currentIndex() == 1

    def _thread_type(self) -> str:
        return self._type.currentText()

    def _is_custom(self) -> bool:
        return self._thread_type() == CUSTOM

    def _form_key(self) -> str:
        if not self._is_custom() and self._size.currentText():
            return td.size(self._size.currentText()).form
        return FORM_KEYS[self._form_combo.currentIndex()]

    def _metric_pitch(self) -> bool:
        t = self._thread_type()
        if t == CUSTOM:
            return self._pitch_unit.currentIndex() == 1
        return t.startswith("Metric")

    def _pitch_inches(self) -> float:
        v = self._pitch.value()
        if v <= 0:
            return 0.0
        return v / 25.4 if self._metric_pitch() else 1.0 / v

    def _set_pitch_inches(self, p: float):
        self._pitch.set_value(p * 25.4 if self._metric_pitch() else 1.0 / p)

    def _fill_sizes(self):
        t = self._thread_type()
        self._size.blockSignals(True)
        self._size.clear()
        if t != CUSTOM:
            self._size.addItems([s.label for s in td.sizes(t)])
        self._size.blockSignals(False)
        self._fill_classes()

    def _fill_classes(self):
        t = self._thread_type()
        cur = self._class.currentText()
        self._class.blockSignals(True)
        self._class.clear()
        if t != CUSTOM:
            self._class.addItems(td.classes(t, self.is_internal()))
            # keep the grade (2A <-> 2B, 6g <-> 6H by position)
        self._class.blockSignals(False)
        if cur and self._class.findText(cur) >= 0:
            self._class.setCurrentText(cur)

    def _apply_size(self):
        """Populate X, pitch, pilot and the entry angle from the chosen size."""
        if self._is_custom() or not self._size.currentText():
            return
        s = td.size(self._size.currentText())
        self._set_pitch_inches(s.pitch)
        if s.type == "NPT":
            npt = td.npt_data(s.label)
            x0 = npt.major_at_gauge_plane if self.is_internal() else npt.major_small_end
            self._x_start.set_value(x0)
        else:
            self._x_start.set_value(s.major)
        self._sync_x_end()
        if self.is_internal():
            self._pilot.set_value(s.tap_drill[1])
        self._entry.set_value(td.FORMS[s.form][1])

    def _sync_x_end(self):
        """Straight standard threads: X end = X start. NPT: from the 1:16 taper."""
        if self._is_custom():
            return
        s = td.size(self._size.currentText())
        if s.type == "NPT":
            self._x_end.set_value(td.npt_x_end(self._x_start.value(), self._z_start.value(),
                                               self._z_end.value(), self.is_internal()))
        else:
            self._x_end.set_value(self._x_start.value())

    def _to_custom(self):
        """X / pitch edited by hand: the thread is no longer the listed one."""
        form = self._form_key()
        metric = self._metric_pitch()
        self._suppress = True
        try:
            self._pitch_unit.blockSignals(True)
            self._pitch_unit.setCurrentIndex(1 if metric else 0)
            self._pitch_unit.blockSignals(False)
            self._type.blockSignals(True)
            self._type.setCurrentText(CUSTOM)
            self._type.blockSignals(False)
            self._fill_sizes()
            self._form_combo.setCurrentIndex(FORM_KEYS.index(form))
        finally:
            self._suppress = False

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _emit(self):
        if not self._suppress:
            self.params_changed.emit()

    def _on_side(self, *_):
        self._fill_classes()
        self._apply_size()
        self._refresh()
        if not self._suppress:
            self.side_changed.emit(self.is_internal())
        self._emit()

    def _on_type(self, *_):
        metric_before = self._pitch_label.text().endswith("(mm):")
        p = self._pitch_inches_from(metric_before)
        self._fill_sizes()
        if self._is_custom() and p > 0:
            self._set_pitch_inches(p)
        self._apply_size()
        self._refresh()
        self._emit()

    def _pitch_inches_from(self, metric: bool) -> float:
        v = self._pitch.value()
        return 0.0 if v <= 0 else (v / 25.4 if metric else 1.0 / v)

    def _on_size(self, *_):
        self._apply_size()
        self._refresh()
        self._emit()

    def _on_form(self, *_):
        if self._is_custom():
            self._entry.set_value(td.FORMS[self._form_key()][1])
        self._refresh()
        self._emit()

    def _on_pitch_unit(self, *_):
        p = self._pitch_inches_from(self._pitch_label.text().endswith("(mm):"))
        if p > 0:
            self._set_pitch_inches(p)
        self._refresh()
        self._emit()

    def _on_geometry_edit(self, *_):
        if not self._is_custom() and self._size.currentText():
            s = td.size(self._size.currentText())
            expect_x = (td.npt_data(s.label).major_at_gauge_plane if self.is_internal()
                        else td.npt_data(s.label).major_small_end) if s.type == "NPT" else s.major
            changed = (abs(self._x_start.value() - expect_x) > 5e-5
                       or abs(self._pitch_inches() - s.pitch) > 1e-6
                       or (s.type != "NPT" and abs(self._x_end.value() - self._x_start.value()) > 5e-5))
            if changed:
                self._to_custom()
        self._refresh()
        self._emit()

    def _on_z(self, *_):
        self._sync_x_end()
        self._refresh()
        self._emit()

    def _on_spec(self, *_):
        self._refresh()
        self._emit()

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def _refresh(self):
        custom = self._is_custom()
        internal = self.is_internal()
        has_class = not custom and self._class.count() > 0
        for w in (self._size_label, self._size):
            w.setVisible(not custom)
        for w in (self._class_label, self._class):
            w.setVisible(has_class)
        for w in (self._form_label, self._form_combo, self._pitch_unit_label, self._pitch_unit):
            w.setVisible(custom)
        for w in (self._pilot_label, self._pilot):
            w.setVisible(internal)
        npt = (not custom and self._thread_type() == "NPT")
        self._x_end.setEnabled(custom or False)
        self._x_end.setToolTip("Derived from the 1:16 NPT taper" if npt else
                               ("Equal to X start for a straight thread" if not custom else
                                "Different from X start = tapered thread"))
        self._pitch_label.setText("Pitch (mm):" if self._metric_pitch() else "Pitch (TPI):")
        try:
            fields = self.get_values()
            d = td.derive(fields["thread_type"], fields["designation"], fields["thread_class"],
                          fields["form"], internal, fields["pitch"])
        except (KeyError, ValueError, ZeroDivisionError) as exc:
            self._depth_label.setText("-")
            self._hint.setText(f"({exc})")
            return
        x = fields["x_start"]
        if internal:
            root = x + d.root_offset
            crest = fields["pilot_dia"] if abs(fields["x_end"] - x) < 1e-9 else root - 2 * d.form_depth
        else:
            crest, root = x, x + d.root_offset
        depth = abs(root - crest) / 2.0
        self._depth_label.setText(f'{depth:.4f}" per side  ({d.source})')
        self._hint.setText(self._hint_text(d, fields, internal))

    def _hint_text(self, d: td.Derived, f: dict, internal: bool) -> str:
        lines = []
        if f["thread_type"] == CUSTOM:
            lines.append("Custom (no tolerance data)")
        elif f["thread_type"] == "NPT":
            npt = td.npt_data(f["designation"])
            if internal:
                s = td.size(f["designation"])
                lines.append(f'Tap drill: {s.tap_drill[0]} ({s.tap_drill[1]:.4f}")')
            else:
                lines.append(f'L1 hand-tight: {npt.l1:.3f}" - check with an L1 ring gauge')
        elif internal:
            s = td.size(f["designation"])
            lines.append(f'Tap drill: {s.tap_drill[0]} ({s.tap_drill[1]:.4f}")')
        elif d.limits is not None:
            lim = d.limits
            lines.append(f"Pitch Ø ({f['thread_class']}): {lim.pd_max:.4f} - {lim.pd_min:.4f}")
            if lim.major_max is not None and lim.major_min is not None:
                lines.append(f"Major \u00d8: {lim.major_max:.4f} - {lim.major_min:.4f}")
        lead = f["pitch"] * max(1, f["num_starts"])
        if lead > 0:
            lines.append(f"Z speed {lead * f['spindle_rpm'] / 60.0:.3f} in/s at {f['spindle_rpm']:.0f} RPM")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_values(self) -> dict:
        """Fields in the saved format (models/thread_data.from_saved / params_from_fields)."""
        custom = self._is_custom()
        return {
            "thread_v": 2,
            "thread_type": self._thread_type(),
            "designation": CUSTOM if custom else self._size.currentText(),
            "thread_class": "" if custom else self._class.currentText(),
            "form": self._form_key(),
            "is_internal": self.is_internal(),
            "x_start": self._x_start.value(),
            "x_end": self._x_end.value(),
            "start_z": self._z_start.value(),
            "end_z": self._z_end.value(),
            "pitch": self._pitch_inches(),
            "pilot_dia": self._pilot.value() if self.is_internal() else 0.0,
            "spindle_rpm": self._rpm.value(),
            "num_passes": self._num_passes.value(),
            "spring_passes": self._spring_passes.value(),
            "num_starts": self._num_starts.value(),
            "entry_angle": self._entry.value(),
            "tool_number": self._tool_num.value(),
            "pitch_unit": "mm" if self._metric_pitch() else "TPI",
        }

    def set_side(self, internal: bool):
        """OD / ID from the block type (no side_changed signal)."""
        self._suppress = True
        try:
            self._side.setCurrentIndex(1 if internal else 0)
        finally:
            self._suppress = False

    def set_values(self, data: dict, internal: Optional[bool] = None):
        """Populate from saved data (new or legacy; legacy is converted)."""
        if internal is None:
            internal = bool(data.get("is_internal", False))
        fields, _notes = td.from_saved(data, internal)
        self._suppress = True
        try:
            self._side.setCurrentIndex(1 if internal else 0)
            self._type.blockSignals(True)
            self._type.setCurrentText(fields["thread_type"])
            self._type.blockSignals(False)
            self._fill_sizes()
            if fields["thread_type"] != CUSTOM:
                self._size.blockSignals(True)
                self._size.setCurrentText(fields["designation"])
                self._size.blockSignals(False)
                self._fill_classes()
                if fields.get("thread_class"):
                    self._class.setCurrentText(fields["thread_class"])
            else:
                self._form_combo.setCurrentIndex(FORM_KEYS.index(fields.get("form", "60")))
                self._pitch_unit.setCurrentIndex(1 if data.get("pitch_unit") == "mm" else 0)
            self._set_pitch_inches(fields["pitch"])
            self._x_start.set_value(fields["x_start"])
            self._x_end.set_value(fields["x_end"])
            self._z_start.set_value(fields["start_z"])
            self._z_end.set_value(fields["end_z"])
            if internal:
                self._pilot.set_value(fields.get("pilot_dia", 0.0))
            self._rpm.set_value(fields["spindle_rpm"])
            self._num_passes.setValue(fields["num_passes"])
            self._spring_passes.setValue(fields["spring_passes"])
            self._num_starts.setValue(fields.get("num_starts", 1))
            self._entry.set_value(fields["entry_angle"])
            self._tool_num.setValue(fields["tool_number"])
            self._refresh()
        finally:
            self._suppress = False

    def get_tool_number(self) -> int:
        return self._tool_num.value()
