"""Profile segment list widget for Industry CAM Engine.

QTableWidget-based editor for building profile geometry segment by segment.
Columns: Type (LINE/ARC dropdown), X (diameter), Z (inches), Radius (inches).
Corner break sub-rows appear between segments (Mazak-style): Type (None/Chamfer/Arc),
Size (inches), Angle (degrees, chamfer only).

Emits segments_changed signal on any edit with List[dict] of segment data.
Emits corner_breaks_changed signal with List[Optional[dict]] of corner break data.

Signed radius convention:
- +R = CW arc (clockwise direction of travel as seen on screen)
- -R = CCW arc (counterclockwise direction of travel as seen on screen)
- The sign determines which of the two possible arc paths to take between
  the start and end points at the given radius.

Inline validation:
- ARC segments: abs(radius) >= chord_length / 2
- Invalid cells show red background with tooltip showing valid alternatives

Coordinates:
- X values are in DIAMETER (inches) in user-facing fields
- Z values are in inches (negative = into workpiece)
- Radius is signed in the UI: positive = CW, negative = CCW
"""

import math
from typing import List, Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPalette
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QComboBox, QHeaderView,
    QAbstractItemView, QLabel, QFrame,
)

from gui.colors import COLORS, FONTS
from gui.unit_state import unit_state
from models.profile import SegmentType


# Column indices for segment table
COL_TYPE = 0
COL_X = 1
COL_Z = 2
COL_RADIUS = 3

COLUMN_HEADERS = ["Type", "X (Dia)", "Z", "Radius"]


# Corner break type options
CB_TYPES = ["None", "Chamfer", "Arc"]

# Row heights
SEGMENT_ROW_HEIGHT = 69   # 55 * 1.25
CB_ROW_HEIGHT = 50        # 40 * 1.25


class CornerBreakRow(QFrame):
    """Sub-row widget for corner break between two adjacent segments.

    Displays a dashed separator with:
    - Type combo: None / Chamfer / Arc
    - Size field: leg length (chamfer) or radius (arc) in inches
    - Angle field: chamfer angle in degrees (only visible for chamfer)

    Signals:
        changed(): Emitted when any field is edited.
    """

    changed = pyqtSignal()

    def __init__(self, index: int, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._index = index
        self._updating = False
        self._setup_ui()
        self._connect_signals()

    @property
    def index(self) -> int:
        """Junction index (between segment[index] and segment[index+1])."""
        return self._index

    @index.setter
    def index(self, value: int):
        self._index = value
        self._update_label()

    def _setup_ui(self):
        """Build the corner break row layout."""
        self.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet(
            f"CornerBreakRow {{"
            f"  background-color: {COLORS['bg_surface']};"
            f"  border-top: 1px dashed {COLORS['border_normal']};"
            f"  border-bottom: 1px dashed {COLORS['border_normal']};"
            f"  padding: 2px 4px;"
            f"}}"
        )
        self.setFixedHeight(CB_ROW_HEIGHT)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)

        # Shared bubble style for labels
        label_bubble_style = (
            f"color: {COLORS['text_secondary']};"
            f"background-color: {COLORS['bg_panel']};"
            f"border: 1px solid {COLORS['border_normal']};"
            f"border-radius: 2px;"
            f"padding: 1px 4px;"
            f"font-size: {FONTS['small_size']}pt;"
        )

        # Shared compact style for numeric fields
        field_height = "max-height: 20px; min-height: 20px;"

        # Junction label (e.g., "1→2")
        self._label = QLabel()
        self._label.setStyleSheet(label_bubble_style)
        self._label.setFixedWidth(44)
        self._label.setAlignment(Qt.AlignCenter)
        self._update_label()
        layout.addWidget(self._label)

        # Type combo
        self._type_combo = QComboBox()
        self._type_combo.addItems(CB_TYPES)
        self._type_combo.setCurrentText("None")
        self._type_combo.setFixedWidth(100)
        self._type_combo.setStyleSheet(
            f"QComboBox {{"
            f"  background-color: {COLORS['bg_panel']};"
            f"  color: {COLORS['text_primary']};"
            f"  border: 1px solid {COLORS['border_normal']};"
            f"  border-radius: 2px;"
            f"  padding: 1px 4px;"
            f"  max-height: 22px; min-height: 22px;"
            f"}}"
        )
        layout.addWidget(self._type_combo)

        # Size label + field
        self._size_label = QLabel("C:")
        self._size_label.setStyleSheet(label_bubble_style)
        self._size_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._size_label)

        from gui.components.numeric_field import NumericField, NumericFieldConfig
        self._size_field = NumericField(NumericFieldConfig(
            min_value=0.001, max_value=1.0, decimals=4, default_value=0.015,
            suffix='"',
        ))
        self._size_field.setFixedWidth(117)
        self._size_field.setStyleSheet(
            self._size_field.styleSheet() + field_height
        )
        layout.addWidget(self._size_field)

        # Angle label + field (chamfer only)
        self._angle_label = QLabel("A:")
        self._angle_label.setStyleSheet(label_bubble_style)
        self._angle_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._angle_label)

        self._angle_field = NumericField(NumericFieldConfig(
            min_value=1.0, max_value=89.0, decimals=1, default_value=45.0,
            suffix="°", unit_aware=False,
        ))
        self._angle_field.setFixedWidth(91)
        self._angle_field.setStyleSheet(
            self._angle_field.styleSheet() + field_height
        )
        layout.addWidget(self._angle_field)

        layout.addStretch()

        # Start with fields hidden (type = None)
        self._set_fields_visible(False)

    def _connect_signals(self):
        """Wire combo and field changes."""
        self._type_combo.currentTextChanged.connect(self._on_type_changed)
        self._size_field.value_changed.connect(self._on_value_changed)
        self._angle_field.value_changed.connect(self._on_value_changed)

    def _update_label(self):
        """Update the junction label text."""
        self._label.setText(f"{self._index + 1}→{self._index + 2}")

    def _set_fields_visible(self, visible: bool):
        """Show/hide size and angle fields based on type."""
        cb_type = self._type_combo.currentText()
        has_break = cb_type != "None"
        is_chamfer = cb_type == "Chamfer"

        self._size_label.setVisible(has_break)
        self._size_field.setVisible(has_break)
        self._angle_label.setVisible(is_chamfer)
        self._angle_field.setVisible(is_chamfer)

        # Update size label based on type
        if is_chamfer:
            self._size_label.setText("C:")
        elif cb_type == "Arc":
            self._size_label.setText("R:")

    def _on_type_changed(self, text: str):
        """Handle type combo change."""
        self._set_fields_visible(text != "None")
        if not self._updating:
            self.changed.emit()

    def _on_value_changed(self):
        """Handle size/angle field change."""
        if not self._updating:
            self.changed.emit()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_data(self) -> Optional[dict]:
        """Return corner break data as a dict, or None if type is None.

        Returns:
            None if type is "None", otherwise:
            {"type": "chamfer"|"fillet", "size": float, "angle": float, "radius": float}
        """
        cb_type = self._type_combo.currentText()
        if cb_type == "None":
            return None

        size = self._size_field.value()
        if cb_type == "Chamfer":
            return {
                "type": "chamfer",
                "size": size,
                "angle": self._angle_field.value(),
                "radius": 0.0,
            }
        else:  # Arc
            return {
                "type": "fillet",
                "radius": size,
                "size": 0.0,
                "angle": 45.0,
            }

    def set_data(self, data: Optional[dict]):
        """Load corner break data from a dict.

        Args:
            data: None for no break, or dict with "type", "size"/"radius", "angle".
        """
        self._updating = True
        try:
            if data is None or data.get("type", "none") == "none":
                self._type_combo.setCurrentText("None")
            elif data["type"] == "chamfer":
                self._type_combo.setCurrentText("Chamfer")
                self._size_field.set_value(data.get("size", 0.015))
                self._angle_field.set_value(data.get("angle", 45.0))
            elif data["type"] == "fillet":
                self._type_combo.setCurrentText("Arc")
                self._size_field.set_value(data.get("radius", 0.015))
            self._set_fields_visible(True)
        finally:
            self._updating = False


class SegmentListWidget(QWidget):
    """Profile segment list editor with corner break sub-rows.

    Allows the user to build a profile segment by segment using a table
    with Type, X, Z, and Radius columns. Between each pair of segments,
    a CornerBreakRow sub-row allows specifying chamfers or arcs
    (Mazak-style conversational programming).

    Provides Add/Remove/Move buttons and inline validation for arc geometry.

    Signals:
        segments_changed(list): Emitted on any edit with List[dict] containing
            segment data: [{"type": "line"|"arc", "x": float, "z": float, "radius": float}, ...]
            where radius is signed: +R = minor arc, -R = major arc.
        corner_breaks_changed(list): Emitted on any corner break edit with
            List[Optional[dict]] of corner break data (length = segments - 1).
    """

    segments_changed = pyqtSignal(list)
    corner_breaks_changed = pyqtSignal(list)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._updating = False  # Guard against recursive signal emission
        self._corner_break_rows: List[CornerBreakRow] = []
        self._setup_ui()
        self._connect_signals()
        # Subscribe to unit mode changes for display conversion
        unit_state.unit_changed.connect(self._on_unit_changed)

    def _setup_ui(self):
        """Build the widget layout: table with interleaved corner breaks + button bar.

        Corner break rows are inserted as table rows between segment rows.
        They span all columns and contain a CornerBreakRow widget.
        """
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Table — corner breaks are embedded as spanned rows between segments
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(COLUMN_HEADERS)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.verticalHeader().setVisible(False)

        # Column sizing
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(COL_TYPE, QHeaderView.Fixed)
        header.resizeSection(COL_TYPE, 80)
        header.setSectionResizeMode(COL_X, QHeaderView.Stretch)
        header.setSectionResizeMode(COL_Z, QHeaderView.Stretch)
        header.setSectionResizeMode(COL_RADIUS, QHeaderView.Stretch)

        # Mono font for numeric cells
        self._mono_font = QFont(FONTS["mono_family"], FONTS["code_size"])
        self._mono_font.setStyleHint(QFont.Monospace)

        layout.addWidget(self._table)

        # Button bar
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(4)

        self._btn_add = QPushButton("Add")
        self._btn_remove = QPushButton("Remove")
        self._btn_move_up = QPushButton("Move Up")
        self._btn_move_down = QPushButton("Move Down")

        for btn in (self._btn_add, self._btn_remove, self._btn_move_up, self._btn_move_down):
            btn.setMinimumHeight(32)
            btn_layout.addWidget(btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

    def _connect_signals(self):
        """Wire up button clicks and table edit signals."""
        self._btn_add.clicked.connect(self._on_add)
        self._btn_remove.clicked.connect(self._on_remove)
        self._btn_move_up.clicked.connect(self._on_move_up)
        self._btn_move_down.clicked.connect(self._on_move_down)
        self._table.cellChanged.connect(self._on_cell_changed)
        self._table.cellDoubleClicked.connect(self._on_cell_double_clicked)

    # ------------------------------------------------------------------
    # Unit conversion
    # ------------------------------------------------------------------

    def _format_value(self, value_inches: float) -> str:
        """Format an internal inch value for display in the current unit mode.

        Applies conversion factor (×25.4) when in metric mode.
        Uses appropriate decimal places (4 for inch, 3 for metric).
        """
        display_val = unit_state.to_display(value_inches)
        decimals = unit_state.decimals
        return f"{display_val:.{decimals}f}"

    def _parse_display_value(self, text: str) -> float:
        """Parse a displayed cell value back to internal inches.

        Reverses the conversion factor (÷25.4) when in metric mode.
        """
        try:
            display_val = float(text)
        except (ValueError, TypeError):
            return 0.0
        return unit_state.from_display(display_val)

    def _on_unit_changed(self, mode: str):
        """Handle unit mode change — refresh all displayed values.

        Re-reads segment data from internal storage (always inches) and
        re-formats the X, Z, and Radius columns in the new unit system.
        Does not modify underlying segment data.
        """
        self._updating = True
        self._table.blockSignals(True)
        try:
            decimals = unit_state.decimals
            for row in range(self._table.rowCount()):
                if self._is_corner_break_row(row):
                    continue
                # Read the internal inch values from the segment data
                # We need to reverse-convert from the OLD display to get inches,
                # then format in the NEW display. But since we just changed mode,
                # the values in cells are in the OLD mode. We need to get the
                # raw inch values first.
                #
                # Strategy: The cells currently show values in the PREVIOUS mode.
                # Since mode just changed, we need to figure out what the inch
                # values were. The previous mode is the opposite of current.
                x_item = self._table.item(row, COL_X)
                z_item = self._table.item(row, COL_Z)
                r_item = self._table.item(row, COL_RADIUS)

                if x_item is None or z_item is None or r_item is None:
                    continue

                # Parse the old display values back to inches
                # Since mode JUST changed, the old mode is the opposite
                old_is_metric = not unit_state.is_metric
                factor = unit_state.CONVERSION_FACTOR

                try:
                    x_display_old = float(x_item.text())
                    x_inches = x_display_old / factor if old_is_metric else x_display_old
                except (ValueError, TypeError):
                    x_inches = 0.0

                try:
                    z_display_old = float(z_item.text())
                    z_inches = z_display_old / factor if old_is_metric else z_display_old
                except (ValueError, TypeError):
                    z_inches = 0.0

                try:
                    r_display_old = float(r_item.text())
                    r_inches = r_display_old / factor if old_is_metric else r_display_old
                except (ValueError, TypeError):
                    r_inches = 0.0

                # Now format in the new mode
                x_item.setText(self._format_value(x_inches))
                z_item.setText(self._format_value(z_inches))
                r_item.setText(self._format_value(r_inches))
        finally:
            self._table.blockSignals(False)
            self._updating = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_segments(self) -> List[dict]:
        """Return current segment data as a list of dicts.

        Each dict: {"type": "line"|"arc", "x": float, "z": float, "radius": float}
        Radius is signed: +R = minor arc (sweep <= 180), -R = major arc (sweep > 180).
        Skips corner break rows in the table.
        """
        segments = []
        for row in range(self._table.rowCount()):
            if self._is_corner_break_row(row):
                continue
            seg = self._read_row(row)
            if seg is not None:
                segments.append(seg)
        return segments

    def get_corner_breaks(self) -> List[Optional[dict]]:
        """Return current corner break data.

        Returns:
            List of length (num_segments - 1). Each element is None (no break)
            or a dict: {"type": "chamfer"|"fillet", "size": float, "angle": float, "radius": float}
        """
        return [cb_row.get_data() for cb_row in self._corner_break_rows]

    def set_segments(self, segments: List[dict],
                     corner_breaks: Optional[List[Optional[dict]]] = None):
        """Load segments into the table, replacing current content.

        Builds the interleaved table: segment rows with corner break rows between them.

        Args:
            segments: List of dicts with keys "type", "x", "z", "radius".
                      Radius is signed: +R = minor arc, -R = major arc.
            corner_breaks: Optional list of corner break dicts (length = len(segments) - 1).
                          If None, all corner breaks default to None.
        """
        self._updating = True
        self._corner_break_rows.clear()
        self._table.setRowCount(0)

        try:
            for i, seg in enumerate(segments):
                self._add_row(
                    seg_type=seg.get("type", "line"),
                    x=seg.get("x", 0.0),
                    z=seg.get("z", 0.0),
                    radius=seg.get("radius", 0.0),
                )
                # Insert corner break row after each segment except the last
                if i < len(segments) - 1:
                    cb_data = None
                    if corner_breaks and i < len(corner_breaks):
                        cb_data = corner_breaks[i]
                    self._insert_corner_break_row(i, cb_data)
        finally:
            self._updating = False

        self._validate_all()
        self._emit_changed()

    def clear(self):
        """Remove all segments and corner breaks."""
        self._clear_corner_breaks()
        self._table.setRowCount(0)
        self._emit_changed()

    # ------------------------------------------------------------------
    # Corner break management
    # ------------------------------------------------------------------

    def _rebuild_corner_breaks(self, data: Optional[List[Optional[dict]]] = None):
        """Rebuild the table with interleaved corner break rows.

        The table layout is:
            Row 0: Segment 0
            Row 1: Corner break 0→1 (if >= 2 segments)
            Row 2: Segment 1
            Row 3: Corner break 1→2 (if >= 3 segments)
            ...

        This method rebuilds the entire table from scratch using current
        segment data and the provided (or preserved) corner break data.
        """
        # Collect current segment data
        segments = []
        for row in range(self._table.rowCount()):
            if self._is_corner_break_row(row):
                continue
            seg = self._read_row(row)
            if seg is not None:
                segments.append(seg)

        # Preserve existing corner break data if none provided
        if data is None:
            data = [cb.get_data() for cb in self._corner_break_rows]

        # Clear everything
        self._corner_break_rows.clear()
        self._updating = True
        self._table.setRowCount(0)

        # Rebuild interleaved
        for i, seg in enumerate(segments):
            self._add_row(
                seg_type=seg["type"],
                x=seg["x"],
                z=seg["z"],
                radius=seg["radius"],
            )
            # Insert corner break row after each segment except the last
            if i < len(segments) - 1:
                cb_data = data[i] if i < len(data) else None
                self._insert_corner_break_row(i, cb_data)

        self._updating = False

    def _insert_corner_break_row(self, junction_index: int, data: Optional[dict] = None):
        """Insert a corner break row at the current end of the table.

        Args:
            junction_index: Which junction this represents (between segment[i] and segment[i+1])
            data: Optional corner break data to populate
        """
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._table.setSpan(row, 0, 1, 4)  # Span all 4 columns
        self._table.setRowHeight(row, CB_ROW_HEIGHT)

        cb_row = CornerBreakRow(index=junction_index, parent=self._table)
        if data is not None:
            cb_row.set_data(data)
        cb_row.changed.connect(self._on_corner_break_changed)
        self._table.setCellWidget(row, 0, cb_row)

        # Mark this row as non-selectable/non-editable
        for col in range(4):
            item = QTableWidgetItem()
            item.setFlags(Qt.NoItemFlags)
            if col > 0:  # col 0 has the widget
                self._table.setItem(row, col, item)

        self._corner_break_rows.append(cb_row)

    def _is_corner_break_row(self, row: int) -> bool:
        """Check if a table row is a corner break row (vs a segment row)."""
        widget = self._table.cellWidget(row, 0)
        return isinstance(widget, CornerBreakRow)

    def _clear_corner_breaks(self):
        """Disconnect all corner break row signals."""
        for cb_row in self._corner_break_rows:
            try:
                cb_row.changed.disconnect(self._on_corner_break_changed)
            except (TypeError, RuntimeError):
                pass
        self._corner_break_rows.clear()

    def _on_corner_break_changed(self):
        """Handle corner break field edit."""
        if self._updating:
            return
        self._emit_corner_breaks_changed()

    def _emit_corner_breaks_changed(self):
        """Emit corner_breaks_changed with current data."""
        if self._updating:
            return
        self.corner_breaks_changed.emit(self.get_corner_breaks())

    # ------------------------------------------------------------------
    # Row management
    # ------------------------------------------------------------------

    def _add_row(self, seg_type: str = "line", x: float = 0.0,
                 z: float = 0.0, radius: float = 0.0):
        """Insert a new row at the end of the table.

        Args:
            seg_type: Segment type ("line" or "arc").
            x: X value in inches (diameter).
            z: Z value in inches.
            radius: Radius value in inches (signed).
        """
        self._updating = True
        try:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setRowHeight(row, SEGMENT_ROW_HEIGHT)

            # Type column — combo box
            combo = QComboBox()
            combo.addItems(["LINE", "ARC"])
            combo.setCurrentText(seg_type.upper())
            combo.currentTextChanged.connect(self._on_type_changed)
            self._table.setCellWidget(row, COL_TYPE, combo)

            # X column (display in current unit mode)
            x_item = QTableWidgetItem(self._format_value(x))
            x_item.setFont(self._mono_font)
            x_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._table.setItem(row, COL_X, x_item)

            # Z column (display in current unit mode)
            z_item = QTableWidgetItem(self._format_value(z))
            z_item.setFont(self._mono_font)
            z_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._table.setItem(row, COL_Z, z_item)

            # Radius column (signed: +R = minor arc, -R = major arc)
            r_item = QTableWidgetItem(self._format_value(radius))
            r_item.setFont(self._mono_font)
            r_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._table.setItem(row, COL_RADIUS, r_item)

            # Enable/disable radius based on type
            self._update_arc_fields_enabled(row)
        finally:
            self._updating = False

    def _read_row(self, row: int) -> Optional[dict]:
        """Read segment data from a table row. Returns None if parsing fails
        or if the row is a corner break row.

        Radius is read directly from the cell (signed value).
        Values are always returned in inches regardless of display mode.
        """
        if self._is_corner_break_row(row):
            return None

        combo = self._table.cellWidget(row, COL_TYPE)
        if combo is None:
            return None
        # Skip if it's a CornerBreakRow widget in col 0
        if isinstance(combo, CornerBreakRow):
            return None

        seg_type = combo.currentText().lower()

        try:
            x = self._parse_display_value(self._table.item(row, COL_X).text())
        except (ValueError, AttributeError):
            x = 0.0

        try:
            z = self._parse_display_value(self._table.item(row, COL_Z).text())
        except (ValueError, AttributeError):
            z = 0.0

        try:
            r = self._parse_display_value(self._table.item(row, COL_RADIUS).text())
        except (ValueError, AttributeError):
            r = 0.0

        return {"type": seg_type, "x": x, "z": z, "radius": r}

    # ------------------------------------------------------------------
    # Button handlers
    # ------------------------------------------------------------------

    def _on_add(self):
        """Add a new LINE segment with default values."""
        # Collect current state, add new segment, rebuild
        segments = self.get_segments()
        corner_breaks = self.get_corner_breaks()
        segments.append({"type": "line", "x": 0.0, "z": 0.0, "radius": 0.0})
        # New junction gets None corner break
        corner_breaks.append(None)
        self.set_segments(segments, corner_breaks)

    def _on_remove(self):
        """Remove the currently selected segment row."""
        row = self._table.currentRow()
        if row < 0:
            return
        # Don't allow removing corner break rows directly
        if self._is_corner_break_row(row):
            return

        # Find which segment index this row corresponds to
        seg_index = self._table_row_to_segment_index(row)
        if seg_index is None:
            return

        segments = self.get_segments()
        corner_breaks = self.get_corner_breaks()

        if seg_index < len(segments):
            segments.pop(seg_index)
            # Remove the corner break at this junction
            # If removing segment i, remove corner break at index min(i, len-1)
            if corner_breaks:
                cb_idx = min(seg_index, len(corner_breaks) - 1)
                if cb_idx >= 0:
                    corner_breaks.pop(cb_idx)

        self.set_segments(segments, corner_breaks)

    def _on_move_up(self):
        """Move the selected segment up by one position."""
        row = self._table.currentRow()
        if row < 0 or self._is_corner_break_row(row):
            return

        seg_index = self._table_row_to_segment_index(row)
        if seg_index is None or seg_index <= 0:
            return

        segments = self.get_segments()
        corner_breaks = self.get_corner_breaks()

        # Swap segments
        segments[seg_index], segments[seg_index - 1] = segments[seg_index - 1], segments[seg_index]

        self.set_segments(segments, corner_breaks)

    def _on_move_down(self):
        """Move the selected segment down by one position."""
        row = self._table.currentRow()
        if row < 0 or self._is_corner_break_row(row):
            return

        seg_index = self._table_row_to_segment_index(row)
        segments = self.get_segments()
        if seg_index is None or seg_index >= len(segments) - 1:
            return

        corner_breaks = self.get_corner_breaks()

        # Swap segments
        segments[seg_index], segments[seg_index + 1] = segments[seg_index + 1], segments[seg_index]

        self.set_segments(segments, corner_breaks)

    def _table_row_to_segment_index(self, row: int) -> Optional[int]:
        """Convert a table row number to a logical segment index.

        Skips corner break rows in the count.
        Returns None if the row is a corner break row.
        """
        if self._is_corner_break_row(row):
            return None
        seg_index = 0
        for r in range(row):
            if not self._is_corner_break_row(r):
                seg_index += 1
        return seg_index

    def _set_row_data(self, row: int, data: dict):
        """Write segment data into an existing row (used during swap).

        Args:
            data: Dict with keys "type", "x", "z", "radius" in inches.
        """
        combo = self._table.cellWidget(row, COL_TYPE)
        if combo and isinstance(combo, QComboBox):
            combo.setCurrentText(data["type"].upper())

        x_item = self._table.item(row, COL_X)
        if x_item:
            x_item.setText(self._format_value(data['x']))

        z_item = self._table.item(row, COL_Z)
        if z_item:
            z_item.setText(self._format_value(data['z']))

        r_item = self._table.item(row, COL_RADIUS)
        if r_item:
            r_item.setText(self._format_value(data['radius']))

        self._update_arc_fields_enabled(row)

    # ------------------------------------------------------------------
    # Edit handlers
    # ------------------------------------------------------------------

    def _on_cell_changed(self, row: int, col: int):
        """Handle cell edits — validate and emit signal."""
        if self._updating:
            return
        if self._is_corner_break_row(row):
            return
        self._validate_all()
        self._emit_changed()

    def _on_cell_double_clicked(self, row: int, col: int):
        """Double-click on a cell: populate with suggested value if available.

        For ARC segments, if the cell has a computed suggestion (from the
        auto-compute hint system), double-clicking fills it in automatically.
        This saves the user from reading the tooltip and typing the value.
        """
        if self._is_corner_break_row(row):
            return

        combo = self._table.cellWidget(row, COL_TYPE)
        if combo is None or combo.currentText() != "ARC":
            return  # Only works on ARC rows

        if col not in (COL_X, COL_Z, COL_RADIUS):
            return

        # Compute the suggested value for this cell
        suggested = self._compute_suggestion(row, col)
        if suggested is None:
            return  # No suggestion available, let normal edit proceed

        # Populate the cell with the suggested value
        item = self._table.item(row, col)
        if item is not None:
            self._updating = True
            item.setText(self._format_value(suggested))
            self._updating = False
            self._validate_all()
            self._emit_changed()

    def _compute_suggestion(self, row: int, col: int) -> Optional[float]:
        """Compute a suggested value for a cell on an ARC row.

        Returns the suggested value in inches, or None if no suggestion is possible.
        """
        from geometry.arc_helpers import (
            compute_min_radius, compute_max_z_for_radius, compute_max_x_for_radius
        )

        # Get previous segment endpoint in inches (skip corner break rows)
        x_start, z_start = self._get_prev_segment_endpoint(row)

        # Parse current values (convert from display to inches)
        try:
            x_val = self._parse_display_value(self._table.item(row, COL_X).text())
        except (ValueError, AttributeError):
            x_val = None
        try:
            z_val = self._parse_display_value(self._table.item(row, COL_Z).text())
        except (ValueError, AttributeError):
            z_val = None
        try:
            r_val = self._parse_display_value(self._table.item(row, COL_RADIUS).text())
        except (ValueError, AttributeError):
            r_val = None

        x_start_r = x_start / 2.0

        if col == COL_RADIUS:
            # Suggest minimum radius (with small margin for a comfortable arc)
            if x_val is not None and z_val is not None:
                x_end_r = x_val / 2.0
                min_r = compute_min_radius(x_start_r, z_start, x_end_r, z_val)
                if min_r > 1e-6:
                    return min_r * 1.15
            return None

        elif col == COL_Z:
            # Suggest max Z reach
            if x_val is not None and r_val is not None and abs(r_val) > 1e-9:
                x_end_r = x_val / 2.0
                max_z = compute_max_z_for_radius(x_start_r, z_start, x_end_r, abs(r_val))
                return max_z
            return None

        elif col == COL_X:
            # Suggest max X reach
            if z_val is not None and r_val is not None and abs(r_val) > 1e-9:
                max_x_r = compute_max_x_for_radius(x_start_r, z_start, z_val, abs(r_val))
                if max_x_r is not None:
                    return max_x_r * 2.0  # Convert back to diameter
            return None

        return None

    def _on_type_changed(self, text: str):
        """Handle type combo change — enable/disable radius, validate, emit."""
        if self._updating:
            return
        # Find which row this combo belongs to
        sender = self.sender()
        for row in range(self._table.rowCount()):
            if self._table.cellWidget(row, COL_TYPE) is sender:
                self._update_arc_fields_enabled(row)
                break
        self._validate_all()
        self._emit_changed()

    def _update_arc_fields_enabled(self, row: int):
        """Enable/disable radius cell based on segment type."""
        if self._is_corner_break_row(row):
            return
        combo = self._table.cellWidget(row, COL_TYPE)
        r_item = self._table.item(row, COL_RADIUS)
        if combo is None or r_item is None:
            return

        is_arc = combo.currentText() == "ARC"
        if is_arc:
            r_item.setFlags(r_item.flags() | Qt.ItemIsEditable | Qt.ItemIsEnabled)
            r_item.setForeground(QColor(COLORS["text_primary"]))
        else:
            r_item.setFlags(r_item.flags() & ~Qt.ItemIsEditable)
            r_item.setForeground(QColor(COLORS["text_disabled"]))
            # Reset radius to 0 for LINE segments
            prev_updating = self._updating
            self._updating = True
            r_item.setText(self._format_value(0.0))
            self._updating = prev_updating

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_prev_segment_endpoint(self, row: int) -> tuple:
        """Get the X, Z endpoint of the previous segment row in inches.

        Walks backwards from `row` skipping corner break rows.
        Returns (0.0, 0.0) if this is the first segment.
        Values are converted from display units back to inches.
        """
        for r in range(row - 1, -1, -1):
            if not self._is_corner_break_row(r):
                try:
                    x = self._parse_display_value(self._table.item(r, COL_X).text())
                    z = self._parse_display_value(self._table.item(r, COL_Z).text())
                    return (x, z)
                except (ValueError, AttributeError):
                    return (0.0, 0.0)
        return (0.0, 0.0)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_all(self):
        """Run inline validation and auto-compute hints on all segment rows.

        Skips corner break rows. For ARC segments:
        - Validates abs(radius) >= chord_length / 2
        - Shows auto-compute tooltips on blank/zero fields when the other
          two fields are filled (tells user what value would complete the arc)

        Invalid radius cells get a red background with fix suggestions.
        Blank/zero cells on ARC rows get a hint tooltip with computed values.
        """
        # Block signals during validation to prevent recursive cellChanged
        self._table.blockSignals(True)

        error_bg = QColor(COLORS["status_error"])
        error_bg.setAlpha(80)
        hint_bg = QColor(COLORS.get("accent_blue", "#5b9bd5"))
        hint_bg.setAlpha(40)
        normal_bg = QColor(0, 0, 0, 0)

        for row in range(self._table.rowCount()):
            if self._is_corner_break_row(row):
                continue

            r_item = self._table.item(row, COL_RADIUS)
            x_item = self._table.item(row, COL_X)
            z_item = self._table.item(row, COL_Z)
            if r_item is None or x_item is None or z_item is None:
                continue

            combo = self._table.cellWidget(row, COL_TYPE)
            if combo is None or isinstance(combo, CornerBreakRow):
                continue

            is_arc = combo.currentText() == "ARC"
            if not is_arc:
                r_item.setBackground(normal_bg)
                r_item.setToolTip("")
                x_item.setBackground(normal_bg)
                x_item.setToolTip("")
                z_item.setBackground(normal_bg)
                z_item.setToolTip("")
                continue

            # ARC validation: abs(radius) >= chord_length / 2
            valid, error_msg = self._validate_arc_radius(row)
            if valid:
                r_item.setBackground(normal_bg)
                r_item.setToolTip("")
            else:
                r_item.setBackground(error_bg)
                r_item.setToolTip(error_msg)

            # Auto-compute hints for blank/zero fields
            self._show_arc_hints(row, x_item, z_item, r_item, hint_bg, normal_bg)

        self._table.blockSignals(False)

    def _show_arc_hints(self, row, x_item, z_item, r_item, hint_bg, normal_bg):
        """Show auto-compute tooltips on ARC fields that are blank or zero.

        When one field is empty/zero and the other two are filled, computes
        what value would make a valid arc and shows it as a tooltip hint.
        All geometry calculations are done in inches; tooltip values are
        displayed in the current unit mode.
        """
        from geometry.arc_helpers import (
            compute_min_radius, compute_max_z_for_radius, compute_max_x_for_radius
        )

        # Get previous segment endpoint in inches (skip corner break rows)
        x_start, z_start = self._get_prev_segment_endpoint(row)

        # Parse current values (convert from display to inches)
        try:
            x_val = self._parse_display_value(x_item.text())
        except (ValueError, AttributeError):
            x_val = None
        try:
            z_val = self._parse_display_value(z_item.text())
        except (ValueError, AttributeError):
            z_val = None
        try:
            r_val = self._parse_display_value(r_item.text())
        except (ValueError, AttributeError):
            r_val = None

        x_is_blank = x_val is None
        z_is_blank = z_val is None
        r_is_blank = r_val is None or abs(r_val) < 1e-9

        x_start_r = x_start / 2.0
        decimals = unit_state.decimals

        # Case 1: Radius blank, X and Z filled → suggest minimum radius
        if r_is_blank and not x_is_blank and not z_is_blank:
            x_end_r = x_val / 2.0
            min_r = compute_min_radius(x_start_r, z_start, x_end_r, z_val)
            if min_r > 1e-6:
                # Display suggested values in current unit mode
                min_r_disp = unit_state.to_display(min_r)
                comfortable_disp = unit_state.to_display(min_r * 1.15)
                r_item.setToolTip(
                    f"Suggested radius for these endpoints:\n"
                    f"  Minimum (semicircle): {min_r_disp:.{decimals}f}\n"
                    f"  Comfortable (120° arc): {comfortable_disp:.{decimals}f}"
                )
                if abs(r_val or 0) < 1e-9:
                    r_item.setBackground(hint_bg)

        # Case 2: Z needs hint
        z_needs_hint = z_is_blank or (z_val is not None and abs(z_val - z_start) < 1e-9)
        if z_needs_hint and not x_is_blank and not r_is_blank:
            x_end_r = x_val / 2.0
            max_z = compute_max_z_for_radius(x_start_r, z_start, x_end_r, abs(r_val))
            if max_z is not None:
                # Display in current unit mode
                r_disp = unit_state.to_display(abs(r_val))
                x_disp = unit_state.to_display(x_val)
                max_z_disp = unit_state.to_display(max_z)
                z_item.setToolTip(
                    f"For R={r_disp:.{decimals}f} at X={x_disp:.{decimals}f}:\n"
                    f"  Max Z reach: {max_z_disp:.{decimals}f}"
                )
                z_item.setBackground(hint_bg)
            else:
                r_disp = unit_state.to_display(abs(r_val))
                x_disp = unit_state.to_display(x_val)
                z_item.setToolTip(
                    f"X distance exceeds arc diameter.\n"
                    f"No valid Z exists for R={r_disp:.{decimals}f} at X={x_disp:.{decimals}f}."
                )
                z_item.setBackground(normal_bg)
        elif not z_needs_hint:
            z_item.setBackground(normal_bg)
            z_item.setToolTip("")

        # Case 3: X needs hint
        x_needs_hint = x_is_blank or (x_val is not None and abs(x_val - x_start) < 1e-9)
        if x_needs_hint and not z_is_blank and not r_is_blank and z_val is not None:
            max_x_r = compute_max_x_for_radius(x_start_r, z_start, z_val, abs(r_val))
            if max_x_r is not None:
                max_x_dia = max_x_r * 2.0
                # Display in current unit mode
                r_disp = unit_state.to_display(abs(r_val))
                z_disp = unit_state.to_display(z_val)
                max_x_dia_disp = unit_state.to_display(max_x_dia)
                x_item.setToolTip(
                    f"For R={r_disp:.{decimals}f} at Z={z_disp:.{decimals}f}:\n"
                    f"  Max X reach: {max_x_dia_disp:.{decimals}f} dia"
                )
                x_item.setBackground(hint_bg)
            else:
                r_disp = unit_state.to_display(abs(r_val))
                z_disp = unit_state.to_display(z_val)
                x_item.setToolTip(
                    f"Z distance exceeds arc diameter.\n"
                    f"No valid X exists for R={r_disp:.{decimals}f} at Z={z_disp:.{decimals}f}."
                )
                x_item.setBackground(normal_bg)
        elif not x_needs_hint:
            x_item.setBackground(normal_bg)
            x_item.setToolTip("")

    def _validate_arc_radius(self, row: int) -> tuple:
        """Check if arc radius is valid for the given row.

        Returns (True, "") if valid, (False, error_message) if invalid.
        When invalid, the error message includes actionable alternatives.

        Radius can be positive (minor arc) or negative (major arc).
        Validation uses abs(radius) for the chord check.
        All geometry calculations are done in inches.
        """
        try:
            radius = self._parse_display_value(self._table.item(row, COL_RADIUS).text())
        except (ValueError, AttributeError):
            return (False, "Radius must be a number")

        abs_radius = abs(radius)
        if abs_radius < 1e-9:
            return (False, "Arc radius cannot be zero")

        # Get current endpoint (in inches)
        try:
            x_end = self._parse_display_value(self._table.item(row, COL_X).text())
            z_end = self._parse_display_value(self._table.item(row, COL_Z).text())
        except (ValueError, AttributeError):
            return (False, "X and Z must be valid numbers")

        # Get previous segment endpoint (already in inches)
        x_start, z_start = self._get_prev_segment_endpoint(row)

        # Compute chord length (X is in diameter, convert to radius for distance)
        dx = (x_end - x_start) / 2.0
        dz = z_end - z_start
        chord_length = math.sqrt(dx * dx + dz * dz)

        if chord_length < 1e-9:
            return (True, "")

        # Validation: abs(radius) >= chord_length / 2
        min_radius = chord_length / 2.0
        if abs_radius >= min_radius:
            return (True, "")
        else:
            from geometry.arc_helpers import format_validation_message
            msg = format_validation_message(x_start, z_start, x_end, z_end, abs_radius)
            return (False, msg)

    # ------------------------------------------------------------------
    # Signal emission
    # ------------------------------------------------------------------

    def _emit_changed(self):
        """Emit segments_changed with current segment data."""
        if self._updating:
            return
        segments = self.get_segments()
        self.segments_changed.emit(segments)
        # Also emit corner breaks (they may have been rebuilt)
        self._emit_corner_breaks_changed()
