"""Profile segment list widget for Industry CAM Engine.

QTableWidget-based editor for building profile geometry segment by segment.
Columns: Type (LINE/ARC dropdown), X (diameter), Z (inches), Radius (inches).
Emits segments_changed signal on any edit with List[dict] of segment data.

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
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QComboBox, QHeaderView,
    QAbstractItemView,
)

from gui.colors import COLORS, FONTS
from models.profile import SegmentType


# Column indices
COL_TYPE = 0
COL_X = 1
COL_Z = 2
COL_RADIUS = 3

COLUMN_HEADERS = ["Type", "X (Dia)", "Z", "Radius"]


class SegmentListWidget(QWidget):
    """Profile segment list editor.

    Allows the user to build a profile segment by segment using a table
    with Type, X, Z, and Radius columns. Provides Add/Remove/Move buttons
    and inline validation for arc geometry.

    Signals:
        segments_changed(list): Emitted on any edit with List[dict] containing
            segment data: [{"type": "line"|"arc", "x": float, "z": float, "radius": float}, ...]
            where radius is signed: +R = minor arc, -R = major arc.
    """

    segments_changed = pyqtSignal(list)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._updating = False  # Guard against recursive signal emission
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        """Build the widget layout: table + button bar."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Table
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

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_segments(self) -> List[dict]:
        """Return current segment data as a list of dicts.

        Each dict: {"type": "line"|"arc", "x": float, "z": float, "radius": float}
        Radius is signed: +R = minor arc (sweep <= 180), -R = major arc (sweep > 180).
        """
        segments = []
        for row in range(self._table.rowCount()):
            seg = self._read_row(row)
            if seg is not None:
                segments.append(seg)
        return segments

    def set_segments(self, segments: List[dict]):
        """Load segments into the table, replacing current content.

        Args:
            segments: List of dicts with keys "type", "x", "z", "radius".
                      Radius is signed: +R = minor arc, -R = major arc.
        """
        self._updating = True
        try:
            self._table.setRowCount(0)
            for seg in segments:
                self._add_row(
                    seg_type=seg.get("type", "line"),
                    x=seg.get("x", 0.0),
                    z=seg.get("z", 0.0),
                    radius=seg.get("radius", 0.0),
                )
        finally:
            self._updating = False
        self._validate_all()
        self._emit_changed()

    def clear(self):
        """Remove all segments."""
        self._table.setRowCount(0)
        self._emit_changed()

    # ------------------------------------------------------------------
    # Row management
    # ------------------------------------------------------------------

    def _add_row(self, seg_type: str = "line", x: float = 0.0,
                 z: float = 0.0, radius: float = 0.0):
        """Insert a new row at the end of the table."""
        self._updating = True
        try:
            row = self._table.rowCount()
            self._table.insertRow(row)

            # Type column — combo box
            combo = QComboBox()
            combo.addItems(["LINE", "ARC"])
            combo.setCurrentText(seg_type.upper())
            combo.currentTextChanged.connect(self._on_type_changed)
            self._table.setCellWidget(row, COL_TYPE, combo)

            # X column
            x_item = QTableWidgetItem(f"{x:.4f}")
            x_item.setFont(self._mono_font)
            x_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._table.setItem(row, COL_X, x_item)

            # Z column
            z_item = QTableWidgetItem(f"{z:.4f}")
            z_item.setFont(self._mono_font)
            z_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._table.setItem(row, COL_Z, z_item)

            # Radius column (signed: +R = minor arc, -R = major arc)
            r_item = QTableWidgetItem(f"{radius:.4f}")
            r_item.setFont(self._mono_font)
            r_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._table.setItem(row, COL_RADIUS, r_item)

            # Enable/disable radius based on type
            self._update_arc_fields_enabled(row)
        finally:
            self._updating = False

    def _read_row(self, row: int) -> Optional[dict]:
        """Read segment data from a table row. Returns None if parsing fails.

        Radius is read directly from the cell (signed value).
        """
        combo = self._table.cellWidget(row, COL_TYPE)
        if combo is None:
            return None

        seg_type = combo.currentText().lower()

        try:
            x = float(self._table.item(row, COL_X).text())
        except (ValueError, AttributeError):
            x = 0.0

        try:
            z = float(self._table.item(row, COL_Z).text())
        except (ValueError, AttributeError):
            z = 0.0

        try:
            radius = float(self._table.item(row, COL_RADIUS).text())
        except (ValueError, AttributeError):
            radius = 0.0

        return {"type": seg_type, "x": x, "z": z, "radius": radius}

    # ------------------------------------------------------------------
    # Button handlers
    # ------------------------------------------------------------------

    def _on_add(self):
        """Add a new LINE segment with default values."""
        self._add_row(seg_type="line", x=0.0, z=0.0, radius=0.0)
        self._validate_all()
        self._emit_changed()

    def _on_remove(self):
        """Remove the currently selected row."""
        row = self._table.currentRow()
        if row >= 0:
            self._table.removeRow(row)
            self._validate_all()
            self._emit_changed()

    def _on_move_up(self):
        """Move the selected row up by one position."""
        row = self._table.currentRow()
        if row > 0:
            self._swap_rows(row, row - 1)
            self._table.selectRow(row - 1)
            self._validate_all()
            self._emit_changed()

    def _on_move_down(self):
        """Move the selected row down by one position."""
        row = self._table.currentRow()
        if row >= 0 and row < self._table.rowCount() - 1:
            self._swap_rows(row, row + 1)
            self._table.selectRow(row + 1)
            self._validate_all()
            self._emit_changed()

    def _swap_rows(self, row_a: int, row_b: int):
        """Swap the data of two rows."""
        self._updating = True
        try:
            data_a = self._read_row(row_a)
            data_b = self._read_row(row_b)
            if data_a is None or data_b is None:
                return

            self._set_row_data(row_a, data_b)
            self._set_row_data(row_b, data_a)
        finally:
            self._updating = False

    def _set_row_data(self, row: int, data: dict):
        """Write segment data into an existing row."""
        combo = self._table.cellWidget(row, COL_TYPE)
        if combo:
            combo.setCurrentText(data["type"].upper())

        x_item = self._table.item(row, COL_X)
        if x_item:
            x_item.setText(f"{data['x']:.4f}")

        z_item = self._table.item(row, COL_Z)
        if z_item:
            z_item.setText(f"{data['z']:.4f}")

        # Radius is signed directly
        r_item = self._table.item(row, COL_RADIUS)
        if r_item:
            r_item.setText(f"{data['radius']:.4f}")

        self._update_arc_fields_enabled(row)

    # ------------------------------------------------------------------
    # Edit handlers
    # ------------------------------------------------------------------

    def _on_cell_changed(self, row: int, col: int):
        """Handle cell edits — validate and emit signal."""
        if self._updating:
            return
        self._validate_all()
        self._emit_changed()

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
            r_item.setText("0.0000")
            self._updating = prev_updating

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_all(self):
        """Run inline validation on all rows.

        For ARC segments: abs(radius) >= chord_length / 2
        where chord = distance between this point and the previous point.
        Invalid cells get a red background and a tooltip explaining the issue.
        """
        # Block signals during validation to prevent recursive cellChanged
        self._table.blockSignals(True)

        error_bg = QColor(COLORS["status_error"])
        error_bg.setAlpha(80)
        normal_bg = QColor(0, 0, 0, 0)  # Transparent (use table default)

        for row in range(self._table.rowCount()):
            r_item = self._table.item(row, COL_RADIUS)
            if r_item is None:
                continue

            combo = self._table.cellWidget(row, COL_TYPE)
            if combo is None:
                continue

            is_arc = combo.currentText() == "ARC"
            if not is_arc:
                # LINE segments — no radius validation needed
                r_item.setBackground(normal_bg)
                r_item.setToolTip("")
                continue

            # ARC validation: abs(radius) >= chord_length / 2
            valid, error_msg = self._validate_arc_radius(row)
            if valid:
                r_item.setBackground(normal_bg)
                r_item.setToolTip("")
            else:
                r_item.setBackground(error_bg)
                r_item.setToolTip(error_msg)

        self._table.blockSignals(False)

    def _validate_arc_radius(self, row: int) -> tuple:
        """Check if arc radius is valid for the given row.

        Returns (True, "") if valid, (False, error_message) if invalid.
        When invalid, the error message includes actionable alternatives:
        - Minimum radius for these endpoints
        - Maximum Z reachable at this X with this radius
        - Maximum X reachable at this Z with this radius

        Radius can be positive (minor arc) or negative (major arc).
        Validation uses abs(radius) for the chord check.
        If this is the first row (no previous point), we use (0, 0) as the start.
        """
        try:
            radius = float(self._table.item(row, COL_RADIUS).text())
        except (ValueError, AttributeError):
            return (False, "Radius must be a number")

        abs_radius = abs(radius)
        if abs_radius < 1e-9:
            return (False, "Arc radius cannot be zero")

        # Get current endpoint
        try:
            x_end = float(self._table.item(row, COL_X).text())
            z_end = float(self._table.item(row, COL_Z).text())
        except (ValueError, AttributeError):
            return (False, "X and Z must be valid numbers")

        # Get previous endpoint (or origin if first segment)
        if row > 0:
            try:
                x_start = float(self._table.item(row - 1, COL_X).text())
                z_start = float(self._table.item(row - 1, COL_Z).text())
            except (ValueError, AttributeError):
                x_start, z_start = 0.0, 0.0
        else:
            x_start, z_start = 0.0, 0.0

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
            # Generate detailed message with alternatives
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
