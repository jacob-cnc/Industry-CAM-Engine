"""ToolGeometryRow — A single tool card widget for the Mazak-style tool editor.

Compact grid layout showing all tool geometry fields inline:
- Tool number, description, type/insert/orientation dropdowns, delete button
- Wear X/Z in large orange font with non-zero highlighting
- X/Z offsets, nose radius, front/back angles, blade width (conditional)
- Embedded OrientationGraphicWidget (160×160)

X-axis values (offset and wear) are displayed as DIAMETER (×2 of stored radius).
Blade width field is only visible when tool_type == "Grooving/Parting".

Signals:
    field_changed(int): Emitted when any field is edited (tool_number).
    delete_requested(int): Emitted when delete button is clicked (tool_number).
    clicked(int): Emitted when the card is clicked (tool_number).
"""

from PyQt5.QtWidgets import (
    QWidget, QGridLayout, QHBoxLayout, QVBoxLayout,
    QLabel, QLineEdit, QComboBox, QPushButton, QFrame,
    QSizePolicy, QSpinBox,
)
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QFont, QMouseEvent

from gui.colors import COLORS, FONTS
from gui.components.numeric_field import NumericField, NumericFieldConfig
from gui.components.orientation_graphic import OrientationGraphicWidget
from pipeline.tool_card_data import ToolCardData, TOOL_TYPES, TYPE_ORIENTATIONS, TYPE_INSERTS
from pipeline.filter_cascade import get_valid_orientations, get_valid_inserts
from pipeline.insert_geometry_lookup import get_angles


# All possible insert codes (union of all TYPE_INSERTS values)
_ALL_INSERTS = [
    "CNMG", "CCMT", "WNMG", "DNMG", "DCMT", "VNMG", "TNMG", "SNMG", "RCMT",
    "60° UN/Metric", "55° Whitworth", "ACME", "Grooving", "Custom",
]

# All orientations Q1–Q9
_ALL_ORIENTATIONS = list(range(1, 10))


class ToolGeometryRow(QWidget):
    """A single tool card widget representing one tool's complete editable state.

    Displays all tool geometry fields in a compact grid layout with an
    embedded orientation graphic. Emits signals on field changes, delete
    requests, and card clicks.
    """

    field_changed = pyqtSignal(int)       # tool_number
    delete_requested = pyqtSignal(int)    # tool_number
    clicked = pyqtSignal(int)             # tool_number

    def __init__(self, tool_data: ToolCardData, parent=None):
        super().__init__(parent)
        self._tool_number = tool_data.tool_number
        self._suppress_signals = False  # Block signals during programmatic updates
        self._manual_angles_edited = False  # Track if user manually edited angle fields
        self._autofilling_angles = False  # Guard to ignore value_changed during auto-fill

        self._setup_ui()
        self._connect_angle_manual_edit_tracking()
        self._apply_card_style()
        self.set_data(tool_data)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_data(self) -> ToolCardData:
        """Read all field values and return a ToolCardData instance.

        X offset and Wear X are displayed as diameter — divide by 2 for radius storage.
        If insert code is "Custom", uses the custom insert name field value.
        """
        insert_code = self._insert_combo.currentText()
        if insert_code == "Custom" and self._custom_insert_edit.text().strip():
            insert_code = self._custom_insert_edit.text().strip()

        return ToolCardData(
            tool_number=self._tool_number_spin.value(),
            tool_type=self._type_combo.currentText(),
            insert_code=insert_code,
            orientation=self._orientation_value(),
            description=self._desc_edit.text(),
            nose_radius=self._nose_radius_field.value(),
            front_angle=self._front_angle_field.value(),
            back_angle=self._back_angle_field.value(),
            x_offset=self._x_offset_field.value() / 2.0,   # diameter → radius
            z_offset=self._z_offset_field.value(),
            x_wear=self._wear_x_field.value() / 2.0,       # diameter → radius
            z_wear=self._wear_z_field.value(),
            blade_width=self._blade_width_field.value(),
        )

    def set_data(self, data: ToolCardData) -> None:
        """Populate all fields from a ToolCardData instance.

        X offset and Wear X are stored as radius — multiply by 2 for diameter display.
        If front/back angles are both 0.0 and the insert code is in the lookup,
        auto-fills the angles from the lookup (handles legacy files without angle data).
        """
        self._suppress_signals = True
        try:
            self._tool_number = data.tool_number
            self._tool_number_spin.blockSignals(True)
            self._tool_number_spin.setValue(data.tool_number)
            self._tool_number_spin.blockSignals(False)
            self._desc_edit.setText(data.description)

            # Type dropdown — set first so cascade filtering can apply
            idx = self._type_combo.findText(data.tool_type)
            if idx >= 0:
                self._type_combo.setCurrentIndex(idx)

            # Filter dropdowns based on type (without emitting signals)
            valid_inserts = get_valid_inserts(data.tool_type)
            if valid_inserts:
                self._insert_combo.blockSignals(True)
                self._insert_combo.clear()
                self._insert_combo.addItems(valid_inserts)
                self._insert_combo.blockSignals(False)

            self._set_orientation_options(data.tool_type, data.insert_code, preserve=False)

            # Insert code dropdown — if not in list, treat as custom
            idx = self._insert_combo.findText(data.insert_code)
            if idx >= 0:
                self._insert_combo.setCurrentIndex(idx)
                self._custom_insert_edit.setVisible(False)
                self._custom_insert_edit.clear()
            else:
                # Custom insert code not in standard list
                custom_idx = self._insert_combo.findText("Custom")
                if custom_idx >= 0:
                    self._insert_combo.setCurrentIndex(custom_idx)
                self._custom_insert_edit.setText(data.insert_code)
                self._custom_insert_edit.setVisible(True)

            # Orientation dropdown
            orient_text = f"Q{data.orientation}"
            idx = self._orient_combo.findText(orient_text)
            if idx >= 0:
                self._orient_combo.setCurrentIndex(idx)

            # Numeric fields — X values displayed as diameter (×2)
            self._x_offset_field.set_value(data.x_offset * 2.0)
            self._z_offset_field.set_value(data.z_offset)
            self._wear_x_field.set_value(data.x_wear * 2.0)
            self._wear_z_field.set_value(data.z_wear)
            self._nose_radius_field.set_value(data.nose_radius)
            self._blade_width_field.set_value(data.blade_width)

            # Angles: if both are 0.0 and insert code is in lookup, auto-fill
            # This handles legacy .tbl files that didn't store I/J angles
            if data.front_angle == 0.0 and data.back_angle == 0.0:
                try:
                    front, back = get_angles(data.insert_code)
                    self._front_angle_field.set_value(front)
                    self._back_angle_field.set_value(back)
                except KeyError:
                    self._front_angle_field.set_value(0.0)
                    self._back_angle_field.set_value(0.0)
            else:
                self._front_angle_field.set_value(data.front_angle)
                self._back_angle_field.set_value(data.back_angle)

            # Reset manual edit flag so next insert change triggers auto-fill
            self._manual_angles_edited = False

            # Blade width visibility
            self._update_blade_width_visibility(data.tool_type)

            # Wear highlighting
            self._update_wear_highlight()

            # Update orientation graphic with current angle values
            self._orientation_graphic.set_params(
                insert_code=data.insert_code,
                orientation=data.orientation,
                nose_radius=data.nose_radius if data.nose_radius > 0 else self._nose_radius_field.value(),
                front_angle=self._front_angle_field.value(),
                back_angle=self._back_angle_field.value(),
            )
        finally:
            self._suppress_signals = False

    def set_tool_number(self, number: int) -> None:
        """Update the displayed tool number."""
        self._tool_number = number
        self._tool_number_spin.blockSignals(True)
        self._tool_number_spin.setValue(number)
        self._tool_number_spin.blockSignals(False)

    def _on_tool_number_changed(self) -> None:
        """Handle manual tool number edit — update internal state and notify."""
        value = self._tool_number_spin.value()
        self._tool_number = value
        if not self._suppress_signals:
            self.field_changed.emit(value)

    # ------------------------------------------------------------------
    # Mouse event — emit clicked signal
    # ------------------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Emit clicked signal when the card is clicked."""
        self.clicked.emit(self._tool_number)
        super().mousePressEvent(event)

    # ------------------------------------------------------------------
    # UI Setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        """Build the compact grid layout with all fields."""
        main_layout = QGridLayout(self)
        main_layout.setContentsMargins(10, 8, 10, 8)
        main_layout.setSpacing(6)

        # === Row 0: Header row — T##, Type, Insert, Orient, Custom/Desc, Delete ===
        self._tool_number_spin = QSpinBox()
        self._tool_number_spin.setRange(1, 99999)
        self._tool_number_spin.setValue(1)
        self._tool_number_spin.setPrefix("T")
        self._tool_number_spin.setFont(QFont(FONTS["mono_family"], FONTS["ui_size"] + 2, QFont.Bold))
        self._tool_number_spin.setFixedWidth(90)
        self._tool_number_spin.setStyleSheet(
            f"QSpinBox {{ background-color: {COLORS['bg_panel']}; "
            f"color: {COLORS['text_primary']}; "
            f"border: 1px solid {COLORS['border_normal']}; "
            f"border-radius: 3px; padding: 2px 4px; min-height: 28px; }}"
            f"QSpinBox:focus {{ border-color: {COLORS['border_focused']}; }}"
        )
        self._tool_number_spin.editingFinished.connect(self._on_tool_number_changed)
        main_layout.addWidget(self._tool_number_spin, 0, 0)

        self._type_combo = QComboBox()
        self._type_combo.addItems(TOOL_TYPES)
        self._type_combo.setMinimumWidth(130)
        self._type_combo.currentTextChanged.connect(self._on_type_changed)
        main_layout.addWidget(self._type_combo, 0, 1)

        self._insert_combo = QComboBox()
        self._insert_combo.addItems(_ALL_INSERTS)
        self._insert_combo.setMinimumWidth(120)
        self._insert_combo.currentTextChanged.connect(self._on_insert_changed)
        main_layout.addWidget(self._insert_combo, 0, 2)

        self._orient_combo = QComboBox()
        self._orient_combo.addItems([f"Q{i}" for i in _ALL_ORIENTATIONS])
        self._orient_combo.setMinimumWidth(65)
        self._orient_combo.currentTextChanged.connect(self._on_orient_changed)
        main_layout.addWidget(self._orient_combo, 0, 3)

        # Custom insert name field — visible only when "Custom" is selected
        self._custom_insert_edit = QLineEdit()
        self._custom_insert_edit.setPlaceholderText("Custom insert name")
        self._custom_insert_edit.setMinimumWidth(120)
        self._custom_insert_edit.setStyleSheet(
            f"QLineEdit {{ background-color: {COLORS['bg_panel']}; "
            f"color: {COLORS['text_primary']}; "
            f"border: 1px solid {COLORS['border_normal']}; "
            f"border-radius: 3px; padding: 4px; min-height: 28px; }}"
            f"QLineEdit:focus {{ border-color: {COLORS['border_focused']}; }}"
        )
        self._custom_insert_edit.editingFinished.connect(self._on_field_changed)
        self._custom_insert_edit.setVisible(False)
        main_layout.addWidget(self._custom_insert_edit, 0, 4)

        self._desc_edit = QLineEdit()
        self._desc_edit.setPlaceholderText("Description")
        self._desc_edit.setStyleSheet(
            f"QLineEdit {{ background-color: {COLORS['bg_panel']}; "
            f"color: {COLORS['text_primary']}; "
            f"border: 1px solid {COLORS['border_normal']}; "
            f"border-radius: 3px; padding: 4px; min-height: 28px; }}"
            f"QLineEdit:focus {{ border-color: {COLORS['border_focused']}; }}"
        )
        self._desc_edit.editingFinished.connect(self._on_field_changed)
        main_layout.addWidget(self._desc_edit, 0, 5)

        self._delete_btn = QPushButton("✕")
        self._delete_btn.setFixedSize(28, 28)
        self._delete_btn.setStyleSheet(
            f"QPushButton {{ background-color: {COLORS['btn_danger']}; "
            f"color: {COLORS['text_primary']}; border: none; border-radius: 4px; "
            f"font-size: 14px; font-weight: bold; min-height: 28px; padding: 0px; }}"
            f"QPushButton:hover {{ background-color: {COLORS['status_warning']}; }}"
        )
        self._delete_btn.clicked.connect(self._on_delete_clicked)
        main_layout.addWidget(self._delete_btn, 0, 6, Qt.AlignRight | Qt.AlignTop)

        # === Row 1: Wear X, Wear Z | X Offset, Z Offset ===
        wear_row = QHBoxLayout()
        wear_row.setSpacing(8)

        wear_x_label = QLabel("Wear X:")
        wear_x_label.setStyleSheet(f"color: {COLORS['text_secondary']}; background: transparent;")
        wear_row.addWidget(wear_x_label)

        self._wear_x_field = NumericField(NumericFieldConfig(
            min_value=-9.9999, max_value=9.9999, decimals=4, default_value=0.0
        ))
        self._wear_x_field.setFixedWidth(120)
        self._wear_x_field.value_changed.connect(self._on_wear_changed)
        wear_row.addWidget(self._wear_x_field)

        wear_z_label = QLabel("Wear Z:")
        wear_z_label.setStyleSheet(f"color: {COLORS['text_secondary']}; background: transparent;")
        wear_row.addWidget(wear_z_label)

        self._wear_z_field = NumericField(NumericFieldConfig(
            min_value=-9.9999, max_value=9.9999, decimals=4, default_value=0.0
        ))
        self._wear_z_field.setFixedWidth(120)
        self._wear_z_field.value_changed.connect(self._on_wear_changed)
        wear_row.addWidget(self._wear_z_field)

        wear_row.addSpacing(20)

        x_off_label = QLabel("X Offset:")
        x_off_label.setStyleSheet(f"color: {COLORS['text_secondary']}; background: transparent;")
        wear_row.addWidget(x_off_label)

        self._x_offset_field = NumericField(NumericFieldConfig(
            min_value=-99.999999, max_value=99.999999, decimals=6, default_value=0.0
        ))
        self._x_offset_field.setFixedWidth(140)
        self._x_offset_field.value_changed.connect(self._on_field_changed)
        wear_row.addWidget(self._x_offset_field)

        z_off_label = QLabel("Z Offset:")
        z_off_label.setStyleSheet(f"color: {COLORS['text_secondary']}; background: transparent;")
        wear_row.addWidget(z_off_label)

        self._z_offset_field = NumericField(NumericFieldConfig(
            min_value=-99.999999, max_value=99.999999, decimals=6, default_value=0.0
        ))
        self._z_offset_field.setFixedWidth(140)
        self._z_offset_field.value_changed.connect(self._on_field_changed)
        wear_row.addWidget(self._z_offset_field)

        wear_row.addStretch()
        main_layout.addLayout(wear_row, 1, 0, 1, 7)

        # === Row 2: Nose R | Front∠, Back∠ | Orientation Graphic ===
        params_row = QHBoxLayout()
        params_row.setSpacing(8)

        nose_label = QLabel("Nose R:")
        nose_label.setStyleSheet(f"color: {COLORS['text_secondary']}; background: transparent;")
        params_row.addWidget(nose_label)

        self._nose_radius_field = NumericField(NumericFieldConfig(
            min_value=0.0, max_value=1.0, decimals=4, default_value=0.0160
        ))
        self._nose_radius_field.setFixedWidth(100)
        self._nose_radius_field.value_changed.connect(self._on_geometry_changed)
        params_row.addWidget(self._nose_radius_field)

        params_row.addSpacing(20)

        front_label = QLabel("Front∠:")
        front_label.setStyleSheet(f"color: {COLORS['text_secondary']}; background: transparent;")
        params_row.addWidget(front_label)

        self._front_angle_field = NumericField(NumericFieldConfig(
            min_value=0.0, max_value=360.0, decimals=1, default_value=95.0
        ))
        self._front_angle_field.setFixedWidth(90)
        self._front_angle_field.value_changed.connect(self._on_geometry_changed)
        params_row.addWidget(self._front_angle_field)

        back_label = QLabel("Back∠:")
        back_label.setStyleSheet(f"color: {COLORS['text_secondary']}; background: transparent;")
        params_row.addWidget(back_label)

        self._back_angle_field = NumericField(NumericFieldConfig(
            min_value=0.0, max_value=360.0, decimals=1, default_value=175.0
        ))
        self._back_angle_field.setFixedWidth(90)
        self._back_angle_field.value_changed.connect(self._on_geometry_changed)
        params_row.addWidget(self._back_angle_field)

        params_row.addStretch()
        main_layout.addLayout(params_row, 2, 0, 1, 6)

        # === Row 3: Blade Width (conditional) ===
        self._blade_width_container = QWidget()
        blade_layout = QHBoxLayout(self._blade_width_container)
        blade_layout.setContentsMargins(0, 0, 0, 0)
        blade_layout.setSpacing(8)

        blade_label = QLabel("Blade W:")
        blade_label.setStyleSheet(f"color: {COLORS['text_secondary']}; background: transparent;")
        blade_layout.addWidget(blade_label)

        self._blade_width_field = NumericField(NumericFieldConfig(
            min_value=0.0, max_value=2.0, decimals=4, default_value=0.0
        ))
        self._blade_width_field.setFixedWidth(90)
        self._blade_width_field.value_changed.connect(self._on_field_changed)
        blade_layout.addWidget(self._blade_width_field)
        blade_layout.addStretch()

        self._blade_width_container.setVisible(False)
        main_layout.addWidget(self._blade_width_container, 3, 0, 1, 6)

        # === Orientation Graphic (right side, spanning rows 1-3) ===
        self._orientation_graphic = OrientationGraphicWidget()
        main_layout.addWidget(self._orientation_graphic, 1, 6, 3, 1, Qt.AlignRight | Qt.AlignTop)

        # Apply large orange font to wear fields
        self._apply_wear_style()

    def _apply_card_style(self) -> None:
        """Apply card border and background styling."""
        self.setStyleSheet(
            f"ToolGeometryRow {{"
            f"  background-color: {COLORS['bg_surface']};"
            f"  border: 1px solid {COLORS['border_normal']};"
            f"  border-radius: 6px;"
            f"}}"
        )
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def _apply_wear_style(self) -> None:
        """Apply large orange font styling to wear X and wear Z fields."""
        wear_style = (
            f"QLineEdit {{ background-color: {COLORS['bg_panel']}; "
            f"color: {COLORS['status_warning']}; "
            f"border: 1px solid {COLORS['border_normal']}; "
            f"border-radius: 3px; padding: 4px; min-height: 28px; "
            f"font-family: {FONTS['mono_family']}, {FONTS['fallback_mono']}; "
            f"font-size: {FONTS['code_size'] + 2}pt; "
            f"font-weight: bold; }}"
            f"QLineEdit:focus {{ border-color: {COLORS['border_focused']}; }}"
        )
        self._wear_x_field.setStyleSheet(wear_style)
        self._wear_z_field.setStyleSheet(wear_style)

    def _update_wear_highlight(self) -> None:
        """Highlight wear fields with a distinct background when non-zero."""
        wear_x_val = self._wear_x_field.value()
        wear_z_val = self._wear_z_field.value()

        # Non-zero wear gets a highlighted background
        highlight_bg = "#4A2020"  # Dark red-orange tint for non-zero wear
        normal_bg = COLORS['bg_panel']

        x_bg = highlight_bg if abs(wear_x_val) > 0.00001 else normal_bg
        z_bg = highlight_bg if abs(wear_z_val) > 0.00001 else normal_bg

        self._wear_x_field.setStyleSheet(
            f"QLineEdit {{ background-color: {x_bg}; "
            f"color: {COLORS['status_warning']}; "
            f"border: 1px solid {COLORS['border_normal']}; "
            f"border-radius: 3px; padding: 4px; min-height: 28px; "
            f"font-family: {FONTS['mono_family']}, {FONTS['fallback_mono']}; "
            f"font-size: {FONTS['code_size'] + 2}pt; "
            f"font-weight: bold; }}"
            f"QLineEdit:focus {{ border-color: {COLORS['border_focused']}; }}"
        )
        self._wear_z_field.setStyleSheet(
            f"QLineEdit {{ background-color: {z_bg}; "
            f"color: {COLORS['status_warning']}; "
            f"border: 1px solid {COLORS['border_normal']}; "
            f"border-radius: 3px; padding: 4px; min-height: 28px; "
            f"font-family: {FONTS['mono_family']}, {FONTS['fallback_mono']}; "
            f"font-size: {FONTS['code_size'] + 2}pt; "
            f"font-weight: bold; }}"
            f"QLineEdit:focus {{ border-color: {COLORS['border_focused']}; }}"
        )

    def _update_blade_width_visibility(self, tool_type: str) -> None:
        """Show blade width field only for Grooving/Parting tools."""
        self._blade_width_container.setVisible(tool_type == "Grooving/Parting")

    def _set_orientation_options(self, tool_type: str, insert_code: str, preserve: bool = True) -> None:
        """Populate orientation combo based on tool type and insert code.

        When insert_code is "Custom", all Q1–Q9 are available regardless of tool type.
        Otherwise, shows the valid orientations for the tool type.
        If preserve=True, keeps the current selection when it remains valid.
        """
        current_text = self._orient_combo.currentText() if preserve else ""

        if insert_code == "Custom":
            options = [f"Q{i}" for i in range(1, 10)]
        else:
            valid = get_valid_orientations(tool_type)
            options = [f"Q{o}" for o in valid] if valid else [f"Q{i}" for i in range(1, 10)]

        self._orient_combo.blockSignals(True)
        self._orient_combo.clear()
        self._orient_combo.addItems(options)
        idx = self._orient_combo.findText(current_text)
        self._orient_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._orient_combo.blockSignals(False)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _orientation_value(self) -> int:
        """Parse the current orientation combo text (e.g. 'Q3') to int."""
        text = self._orient_combo.currentText()
        try:
            return int(text.replace("Q", ""))
        except (ValueError, AttributeError):
            return 1

    def _emit_field_changed(self) -> None:
        """Emit field_changed signal if not suppressed."""
        if not self._suppress_signals:
            self.field_changed.emit(self._tool_number)

    def _autofill_angles(self, insert_code: str) -> None:
        """Auto-populate front/back angles from InsertGeometryLookup.

        Only fills if the user has not manually edited the angle fields
        since the last insert code change.
        """
        if self._manual_angles_edited:
            return

        try:
            front_angle, back_angle = get_angles(insert_code)
        except KeyError:
            return

        # Set angles programmatically — set_value does NOT emit value_changed
        # so the manual edit flag won't be triggered
        self._autofilling_angles = True
        self._front_angle_field.set_value(front_angle)
        self._back_angle_field.set_value(back_angle)
        self._autofilling_angles = False

    def _connect_angle_manual_edit_tracking(self) -> None:
        """Connect angle field signals to track manual user edits.

        NumericField.value_changed only fires on user interaction (editingFinished),
        not on programmatic set_value() calls (which use blockSignals). So we can
        use it to detect manual edits. However, we also guard with _autofilling_angles
        for extra safety.
        """
        self._front_angle_field.value_changed.connect(self._on_angle_manually_edited)
        self._back_angle_field.value_changed.connect(self._on_angle_manually_edited)

    def _on_angle_manually_edited(self, value: float) -> None:
        """Mark angles as manually edited when user changes them directly."""
        if not self._suppress_signals and not self._autofilling_angles:
            self._manual_angles_edited = True

    # ------------------------------------------------------------------
    # Signal Handlers
    # ------------------------------------------------------------------

    def _on_field_changed(self, *args) -> None:
        """Generic handler for any field edit."""
        self._update_orientation_graphic()
        self._emit_field_changed()

    def _on_type_changed(self, tool_type: str) -> None:
        """Handle tool type dropdown change — filter cascades and update blade width.

        Filters orientation and insert code dropdowns to show only valid options
        for the selected tool type. Auto-populates orientation to the first valid
        option for the new type. Triggers auto-fill on insert code reset.
        """
        self._update_blade_width_visibility(tool_type)

        if self._suppress_signals:
            return

        # --- Filter insert code dropdown ---
        valid_inserts = get_valid_inserts(tool_type)
        current_insert = self._insert_combo.currentText()

        self._insert_combo.blockSignals(True)
        self._insert_combo.clear()
        if valid_inserts:
            self._insert_combo.addItems(valid_inserts)
            if current_insert in valid_inserts:
                idx = self._insert_combo.findText(current_insert)
                if idx >= 0:
                    self._insert_combo.setCurrentIndex(idx)
            # else stays at index 0 (first valid) — triggers auto-fill below
        self._insert_combo.blockSignals(False)

        # If insert code was reset (current not in valid list), trigger auto-fill
        new_insert = self._insert_combo.currentText()
        if new_insert and new_insert != current_insert:
            # Insert code changed due to cascade reset — clear manual flag and auto-fill
            self._manual_angles_edited = False
            self._autofill_angles(new_insert)

        # --- Filter orientation dropdown — reset to first since type changed ---
        # Custom insert always expands to all Q options regardless of tool type
        self._set_orientation_options(tool_type, new_insert, preserve=False)

        self._update_orientation_graphic()
        self._emit_field_changed()

    def _on_insert_changed(self, insert_code: str) -> None:
        """Handle insert code dropdown change — auto-fill angles.

        Always auto-fills front/back angles from InsertGeometryLookup when
        the user changes the insert code, unless they have manually edited
        the angle fields since the last insert code change.

        Shows the custom insert name field when "Custom" is selected.
        """
        if self._suppress_signals:
            return

        # Show/hide custom insert name field
        self._custom_insert_edit.setVisible(insert_code == "Custom")

        # Custom insert expands orientation options to all Q1–Q9; others re-filter by type
        self._set_orientation_options(self._type_combo.currentText(), insert_code, preserve=True)

        # Insert code changed by user — reset manual edit tracking and auto-fill
        self._manual_angles_edited = False

        try:
            front_angle, back_angle = get_angles(insert_code)
            self._autofilling_angles = True
            self._front_angle_field.set_value(front_angle)
            self._back_angle_field.set_value(back_angle)
            self._autofilling_angles = False
        except KeyError:
            pass  # Unknown insert code — leave angles unchanged

        self._update_orientation_graphic()
        self._emit_field_changed()

    def _on_orient_changed(self, orient_text: str) -> None:
        """Handle orientation dropdown change — update graphic."""
        self._update_orientation_graphic()
        self._emit_field_changed()

    def _on_geometry_changed(self, value: float) -> None:
        """Handle geometry parameter change — update graphic."""
        self._update_orientation_graphic()
        self._emit_field_changed()

    def _on_wear_changed(self, value: float) -> None:
        """Handle wear field change — update highlighting."""
        self._update_wear_highlight()
        self._update_orientation_graphic()
        self._emit_field_changed()

    def _on_delete_clicked(self) -> None:
        """Handle delete button click."""
        self.delete_requested.emit(self._tool_number)

    def _update_orientation_graphic(self) -> None:
        """Update the orientation graphic with current field values."""
        self._orientation_graphic.set_params(
            insert_code=self._insert_combo.currentText(),
            orientation=self._orientation_value(),
            nose_radius=self._nose_radius_field.value(),
            front_angle=self._front_angle_field.value(),
            back_angle=self._back_angle_field.value(),
        )
