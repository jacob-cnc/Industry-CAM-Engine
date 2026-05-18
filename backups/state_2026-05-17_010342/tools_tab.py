# -*- coding: utf-8 -*-
"""Tools Tab for Industry CAM Engine.

Tool table management: list (left) + edit panel with graphic preview (right).
Auto-saves on every change, session backup on launch (max 5).
LinuxCNC tool.tbl format compatibility via pipeline/file_io.

This tab is usable in offline mode (no LinuxCNC dependency).
"""

import math
import os
from typing import Optional, List

from PyQt5.QtCore import Qt, pyqtSignal, QRectF, QPointF
from PyQt5.QtGui import QPainter, QPainterPath, QPen, QBrush, QColor, QFont
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QLabel, QComboBox, QPushButton, QGroupBox,
    QFormLayout, QFrame, QListWidget, QListWidgetItem,
    QLineEdit, QFileDialog, QMessageBox,
)

from gui.colors import COLORS, FONTS
from gui.components.numeric_field import NumericField, NumericFieldConfig
from models.tool import ToolDef, ToolOrientation, ToolDirection, ToolType
from pipeline.file_io import save_tool_table, load_tool_table, create_backup


# Insert shape presets: name -> (tip_angle, edge_length)
INSERT_PRESETS = {
    "CNMG": (80.0, 0.500),
    "VNMG": (35.0, 0.375),
    "CCMT": (80.0, 0.375),
    "DNMG": (55.0, 0.500),
    "WNMG": (80.0, 0.500),
    "TNMG": (60.0, 0.375),
}

# Default tool table path
DEFAULT_TOOL_TABLE = "tool.tbl"
BACKUP_DIR = "backups"


class ToolGraphicWidget(QWidget):
    """Visual-only tool insert preview using QPainterPath.

    Draws a diamond/triangle shape based on tip_angle, nose radius arc,
    and orientation indicator. Does NOT use the engine's ToolShape class.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._tip_angle = 80.0
        self._edge_length = 0.500
        self._nose_radius = 0.016
        self._orientation = ToolOrientation.OD_FRONT_RIGHT
        self._direction = ToolDirection.RIGHT
        self.setMinimumSize(180, 180)
        self.setMaximumSize(300, 300)

    def set_tool_params(
        self,
        tip_angle: float,
        edge_length: float,
        nose_radius: float,
        orientation: ToolOrientation,
        direction: ToolDirection,
    ) -> None:
        """Update tool parameters and repaint."""
        self._tip_angle = tip_angle
        self._edge_length = edge_length
        self._nose_radius = nose_radius
        self._orientation = orientation
        self._direction = direction
        self.update()

    def paintEvent(self, event):
        """Draw the tool insert shape with nose radius and orientation arrow."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Background
        painter.fillRect(self.rect(), QColor(COLORS["bg_panel"]))

        # Drawing area with margin
        margin = 20
        w = self.width() - 2 * margin
        h = self.height() - 2 * margin
        cx = self.width() / 2
        cy = self.height() / 2

        # Scale factor: map edge_length to pixels
        scale = min(w, h) * 0.7 / max(self._edge_length, 0.1)

        # Build insert shape path
        path = self._build_insert_path(scale)

        # Center the path
        bounds = path.boundingRect()
        dx = cx - bounds.center().x()
        dy = cy - bounds.center().y()
        painter.translate(dx, dy)

        # Draw insert body
        pen = QPen(QColor(COLORS["text_primary"]), 2)
        painter.setPen(pen)
        painter.setBrush(QBrush(QColor(COLORS["bg_surface"])))
        painter.drawPath(path)

        # Draw nose radius arc highlight
        self._draw_nose_radius(painter, scale)

        # Draw orientation arrow
        self._draw_orientation_arrow(painter, scale)

        painter.end()

    def _build_insert_path(self, scale: float) -> QPainterPath:
        """Build QPainterPath for the insert diamond/triangle shape."""
        path = QPainterPath()
        half_angle = math.radians(self._tip_angle / 2.0)
        edge_px = self._edge_length * scale

        # Tip at origin, edges extend upward at +/- half_angle from vertical
        tip = QPointF(0, 0)

        # Left edge
        lx = -edge_px * math.sin(half_angle)
        ly = -edge_px * math.cos(half_angle)
        left = QPointF(lx, ly)

        # Right edge
        rx = edge_px * math.sin(half_angle)
        ry = -edge_px * math.cos(half_angle)
        right = QPointF(rx, ry)

        # Diamond: mirror bottom
        blx = lx * 0.6
        bly = -ly * 0.4
        brx = rx * 0.6
        bry = -ry * 0.4

        path.moveTo(tip)
        path.lineTo(left)
        path.lineTo(QPointF(blx + (brx - blx) * 0.5, ly - edge_px * 0.3))
        path.lineTo(right)
        path.closeSubpath()

        return path

    def _draw_nose_radius(self, painter: QPainter, scale: float) -> None:
        """Draw a small arc at the tool tip representing nose radius."""
        r_px = self._nose_radius * scale
        if r_px < 2:
            r_px = 2  # Minimum visible size

        pen = QPen(QColor(COLORS["status_info"]), 2)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        # Arc at tip (0, 0)
        rect = QRectF(-r_px, -r_px, 2 * r_px, 2 * r_px)
        start_angle = 180 * 16  # Start from left
        span_angle = 180 * 16   # Half circle
        painter.drawArc(rect, start_angle, span_angle)

    def _draw_orientation_arrow(self, painter: QPainter, scale: float) -> None:
        """Draw an arrow indicating cutting direction based on orientation."""
        pen = QPen(QColor(COLORS["btn_generate"]), 2)
        painter.setPen(pen)

        arrow_len = 25.0
        # Direction determines arrow side
        if self._direction == ToolDirection.RIGHT:
            start = QPointF(10, 5)
            end = QPointF(10 + arrow_len, 5)
        elif self._direction == ToolDirection.LEFT:
            start = QPointF(-10, 5)
            end = QPointF(-10 - arrow_len, 5)
        else:
            start = QPointF(0, 10)
            end = QPointF(0, 10 + arrow_len)

        painter.drawLine(start, end)

        # Arrowhead
        angle = math.atan2(end.y() - start.y(), end.x() - start.x())
        head_len = 8
        p1 = QPointF(
            end.x() - head_len * math.cos(angle - 0.4),
            end.y() - head_len * math.sin(angle - 0.4),
        )
        p2 = QPointF(
            end.x() - head_len * math.cos(angle + 0.4),
            end.y() - head_len * math.sin(angle + 0.4),
        )
        painter.drawLine(end, p1)
        painter.drawLine(end, p2)


class ToolsTab(QWidget):
    """Tool table management tab.

    Layout:
        Left: Tool list (QListWidget showing tool# + description)
        Right: Edit panel with fields for selected tool + graphic preview
        Bottom: Save/Load buttons, file path display

    Signals:
        tool_changed(int): Emitted with tool_number when any tool field is edited
        tool_selected(object): Emitted with ToolDef when user selects a tool
    """

    tool_changed = pyqtSignal(int)
    tool_selected = pyqtSignal(object)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._tools: List[ToolDef] = []
        self._current_index: int = -1
        self._file_path: str = DEFAULT_TOOL_TABLE
        self._suppress_signals = False

        self._setup_ui()
        self._connect_signals()
        self._load_or_create_default()
        self._create_session_backup()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_tools(self) -> List[ToolDef]:
        """Return the current tool list."""
        return list(self._tools)

    def get_tool(self, tool_number: int) -> Optional[ToolDef]:
        """Return a specific tool by number, or None."""
        for t in self._tools:
            if t.tool_number == tool_number:
                return t
        return None

    def get_selected_tool(self) -> Optional[ToolDef]:
        """Return the currently selected tool, or None."""
        if 0 <= self._current_index < len(self._tools):
            return self._tools[self._current_index]
        return None

    # ------------------------------------------------------------------
    # UI Setup
    # ------------------------------------------------------------------

    def _setup_ui(self):
        """Build the complete tab layout."""
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # Main splitter: tool list (left) + edit panel (right)
        self._splitter = QSplitter(Qt.Horizontal)
        outer_layout.addWidget(self._splitter, stretch=1)

        # Left panel: tool list + add/remove buttons
        self._left_panel = self._build_left_panel()
        self._splitter.addWidget(self._left_panel)

        # Right panel: edit fields + graphic preview
        self._right_panel = self._build_right_panel()
        self._splitter.addWidget(self._right_panel)

        # Splitter proportions: 30% left, 70% right
        self._splitter.setSizes([280, 650])
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)

        # Bottom bar: file path + save/load buttons
        bottom_bar = self._build_bottom_bar()
        outer_layout.addWidget(bottom_bar)

    def _build_left_panel(self) -> QWidget:
        """Build the left panel with tool list and add/remove buttons."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 4, 8)
        layout.setSpacing(8)

        # Header
        header = QLabel("Tool Table")
        header.setStyleSheet(
            f"color: {COLORS['text_primary']}; font-weight: bold; font-size: 11pt;"
        )
        layout.addWidget(header)

        # Tool list
        self._tool_list = QListWidget()
        self._tool_list.setStyleSheet(
            f"QListWidget {{"
            f"  background-color: {COLORS['bg_panel']};"
            f"  color: {COLORS['text_primary']};"
            f"  border: 1px solid {COLORS['border_normal']};"
            f"  border-radius: 3px;"
            f"  font-family: {FONTS['mono_family']}, {FONTS['fallback_mono']};"
            f"  font-size: {FONTS['code_size']}pt;"
            f"}}"
            f"QListWidget::item {{"
            f"  padding: 6px 8px;"
            f"  min-height: 28px;"
            f"}}"
            f"QListWidget::item:selected {{"
            f"  background-color: {COLORS['bg_surface']};"
            f"}}"
        )
        layout.addWidget(self._tool_list, stretch=1)

        # Add/Remove buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._btn_add = QPushButton("+ Add Tool")
        self._btn_add.setMinimumHeight(36)
        btn_row.addWidget(self._btn_add)

        self._btn_remove = QPushButton("- Remove")
        self._btn_remove.setMinimumHeight(36)
        self._btn_remove.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {COLORS['btn_danger']};"
            f"  color: {COLORS['text_primary']};"
            f"  border: none; border-radius: 4px;"
            f"  padding: 8px 12px; min-height: 36px; font-weight: bold;"
            f"}}"
            f"QPushButton:hover {{ background-color: {COLORS['status_warning']}; }}"
        )
        btn_row.addWidget(self._btn_remove)

        layout.addLayout(btn_row)
        return panel

    def _build_right_panel(self) -> QWidget:
        """Build the right panel with edit fields and tool graphic preview."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 8, 8, 8)
        layout.setSpacing(12)

        # Insert shape preset dropdown
        preset_row = QHBoxLayout()
        preset_row.setSpacing(8)
        preset_label = QLabel("Insert Shape:")
        preset_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        preset_row.addWidget(preset_label)

        self._insert_combo = QComboBox()
        self._insert_combo.addItem("(Custom)")
        for name in INSERT_PRESETS:
            self._insert_combo.addItem(name)
        self._insert_combo.setMinimumWidth(120)
        preset_row.addWidget(self._insert_combo)
        preset_row.addStretch()
        layout.addLayout(preset_row)

        # Edit fields in a form layout
        fields_group = self._build_fields_group()
        layout.addWidget(fields_group)

        # Tool graphic preview
        preview_label = QLabel("Preview")
        preview_label.setStyleSheet(
            f"color: {COLORS['text_secondary']}; font-weight: bold;"
        )
        layout.addWidget(preview_label)

        self._tool_graphic = ToolGraphicWidget()
        self._tool_graphic.setStyleSheet(
            f"border: 1px solid {COLORS['border_normal']}; border-radius: 4px;"
        )
        layout.addWidget(self._tool_graphic)

        layout.addStretch()
        return panel

    def _build_fields_group(self) -> QGroupBox:
        """Build the editable fields group for the selected tool."""
        group = QGroupBox("Tool Parameters")
        group.setStyleSheet(
            f"QGroupBox {{"
            f"  color: {COLORS['text_primary']};"
            f"  font-weight: bold;"
            f"  font-size: {FONTS['ui_size']}pt;"
            f"  border: 1px solid {COLORS['border_normal']};"
            f"  border-radius: 4px;"
            f"  margin-top: 12px;"
            f"  padding-top: 8px;"
            f"}}"
            f"QGroupBox::title {{"
            f"  subcontrol-origin: margin;"
            f"  left: 8px;"
            f"  padding: 0 4px;"
            f"}}"
        )
        form = QFormLayout()
        form.setContentsMargins(8, 16, 8, 8)
        form.setSpacing(6)

        # Tool number
        self._field_tool_number = NumericField(NumericFieldConfig(
            min_value=1, max_value=99, decimals=0,
            default_value=1, suffix="",
        ))
        form.addRow("Tool #:", self._field_tool_number)

        # Nose radius
        self._field_nose_radius = NumericField(NumericFieldConfig(
            min_value=0.001, max_value=0.250, decimals=4,
            default_value=0.016, suffix="in",
        ))
        form.addRow("Nose Radius:", self._field_nose_radius)

        # Tip angle
        self._field_tip_angle = NumericField(NumericFieldConfig(
            min_value=10.0, max_value=120.0, decimals=1,
            default_value=80.0, suffix="°",
        ))
        form.addRow("Tip Angle:", self._field_tip_angle)

        # Edge length
        self._field_edge_length = NumericField(NumericFieldConfig(
            min_value=0.050, max_value=2.0, decimals=3,
            default_value=0.375, suffix="in",
        ))
        form.addRow("Edge Length:", self._field_edge_length)

        # Orientation
        self._field_orientation = QComboBox()
        for orient in ToolOrientation:
            self._field_orientation.addItem(
                f"{orient.value} - {orient.name.replace('_', ' ').title()}",
                orient.value,
            )
        form.addRow("Orientation:", self._field_orientation)

        # Direction
        self._field_direction = QComboBox()
        for d in ToolDirection:
            self._field_direction.addItem(d.name, d.value)
        form.addRow("Direction:", self._field_direction)

        # Description
        self._field_description = QLineEdit()
        self._field_description.setPlaceholderText("e.g. CNMG 432 Roughing")
        self._field_description.setStyleSheet(
            f"QLineEdit {{"
            f"  background-color: {COLORS['bg_panel']};"
            f"  color: {COLORS['text_primary']};"
            f"  border: 1px solid {COLORS['border_normal']};"
            f"  border-radius: 3px; padding: 6px; min-height: 36px;"
            f"}}"
            f"QLineEdit:focus {{ border-color: {COLORS['border_focused']}; }}"
        )
        form.addRow("Description:", self._field_description)

        group.setLayout(form)
        return group

    def _build_bottom_bar(self) -> QWidget:
        """Build the bottom bar with file path display and save/load buttons."""
        bar = QWidget()
        bar.setStyleSheet(f"background-color: {COLORS['bg_panel']};")
        bar.setFixedHeight(48)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        # File path label
        path_icon = QLabel("File:")
        path_icon.setStyleSheet(f"color: {COLORS['text_secondary']}; font-weight: bold;")
        layout.addWidget(path_icon)

        self._path_label = QLabel(self._file_path)
        self._path_label.setStyleSheet(
            f"color: {COLORS['text_secondary']};"
            f" font-family: {FONTS['mono_family']}, {FONTS['fallback_mono']};"
            f" font-size: {FONTS['small_size']}pt;"
        )
        layout.addWidget(self._path_label, stretch=1)

        # Load button
        self._btn_load = QPushButton("Load")
        self._btn_load.setMinimumHeight(36)
        layout.addWidget(self._btn_load)

        # Save button
        self._btn_save = QPushButton("Save")
        self._btn_save.setMinimumHeight(36)
        layout.addWidget(self._btn_save)

        # Save As button
        self._btn_save_as = QPushButton("Save As...")
        self._btn_save_as.setMinimumHeight(36)
        layout.addWidget(self._btn_save_as)

        return bar

    # ------------------------------------------------------------------
    # Signal Connections
    # ------------------------------------------------------------------

    def _connect_signals(self):
        """Wire up all internal signals."""
        # Tool list selection
        self._tool_list.currentRowChanged.connect(self._on_tool_selected)

        # Add/Remove buttons
        self._btn_add.clicked.connect(self._on_add_tool)
        self._btn_remove.clicked.connect(self._on_remove_tool)

        # Insert shape preset
        self._insert_combo.currentIndexChanged.connect(self._on_insert_preset_changed)

        # Edit fields — auto-save on change
        self._field_tool_number.value_changed.connect(self._on_field_edited)
        self._field_nose_radius.value_changed.connect(self._on_field_edited)
        self._field_tip_angle.value_changed.connect(self._on_field_edited)
        self._field_edge_length.value_changed.connect(self._on_field_edited)
        self._field_orientation.currentIndexChanged.connect(self._on_field_edited)
        self._field_direction.currentIndexChanged.connect(self._on_field_edited)
        self._field_description.editingFinished.connect(self._on_field_edited)

        # File buttons
        self._btn_load.clicked.connect(self._on_load)
        self._btn_save.clicked.connect(self._on_save)
        self._btn_save_as.clicked.connect(self._on_save_as)

    # ------------------------------------------------------------------
    # Event Handlers
    # ------------------------------------------------------------------

    def _on_tool_selected(self, row: int):
        """User selected a tool in the list — populate edit fields."""
        if row < 0 or row >= len(self._tools):
            self._current_index = -1
            return

        self._current_index = row
        tool = self._tools[row]

        # Suppress signals while populating fields
        self._suppress_signals = True
        self._field_tool_number.set_value(float(tool.tool_number))
        self._field_nose_radius.set_value(tool.nose_radius)
        self._field_tip_angle.set_value(tool.tip_angle)
        self._field_edge_length.set_value(tool.edge_length)

        # Set orientation combo
        orient_idx = 0
        for i in range(self._field_orientation.count()):
            if self._field_orientation.itemData(i) == tool.orientation.value:
                orient_idx = i
                break
        self._field_orientation.setCurrentIndex(orient_idx)

        # Set direction combo
        dir_idx = 0
        for i in range(self._field_direction.count()):
            if self._field_direction.itemData(i) == tool.direction.value:
                dir_idx = i
                break
        self._field_direction.setCurrentIndex(dir_idx)

        self._field_description.setText(tool.description)

        # Reset insert combo to (Custom) since we're loading existing
        self._insert_combo.setCurrentIndex(0)
        self._suppress_signals = False

        # Update graphic preview
        self._update_graphic_preview()

        # Emit selection signal
        self.tool_selected.emit(tool)

    def _on_field_edited(self, *args):
        """Any edit field changed — update tool, auto-save, emit signal."""
        if self._suppress_signals:
            return
        if self._current_index < 0 or self._current_index >= len(self._tools):
            return

        # Build updated ToolDef from fields
        updated = self._build_tool_from_fields()
        if updated is None:
            return

        self._tools[self._current_index] = updated
        self._refresh_list_item(self._current_index)
        self._update_graphic_preview()
        self._auto_save()
        self.tool_changed.emit(updated.tool_number)

    def _on_insert_preset_changed(self, index: int):
        """Insert shape dropdown changed — auto-populate tip_angle and edge_length."""
        if self._suppress_signals:
            return
        if index <= 0:
            return  # "(Custom)" selected

        preset_name = self._insert_combo.currentText()
        if preset_name in INSERT_PRESETS:
            tip_angle, edge_length = INSERT_PRESETS[preset_name]
            self._suppress_signals = True
            self._field_tip_angle.set_value(tip_angle)
            self._field_edge_length.set_value(edge_length)
            self._suppress_signals = False
            # Trigger field edit to save
            self._on_field_edited()

    def _on_add_tool(self):
        """Add a new tool to the table."""
        # Find next available tool number
        used_numbers = {t.tool_number for t in self._tools}
        new_number = 1
        while new_number in used_numbers and new_number <= 99:
            new_number += 1
        if new_number > 99:
            return  # Table full

        new_tool = ToolDef(
            tool_number=new_number,
            nose_radius=0.016,
            tip_angle=80.0,
            edge_length=0.500,
            orientation=ToolOrientation.OD_FRONT_RIGHT,
            direction=ToolDirection.RIGHT,
            description=f"T{new_number} New Tool",
        )
        self._tools.append(new_tool)
        self._refresh_tool_list()
        self._tool_list.setCurrentRow(len(self._tools) - 1)
        self._auto_save()

    def _on_remove_tool(self):
        """Remove the currently selected tool."""
        if self._current_index < 0 or self._current_index >= len(self._tools):
            return
        if len(self._tools) <= 1:
            return  # Keep at least one tool

        self._tools.pop(self._current_index)
        self._refresh_tool_list()

        # Select nearest tool
        new_idx = min(self._current_index, len(self._tools) - 1)
        self._tool_list.setCurrentRow(new_idx)
        self._auto_save()

    def _on_load(self):
        """Load tool table from file."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Tool Table", "",
            "Tool Table (*.tbl);;All Files (*)",
        )
        if not path:
            return

        try:
            tools = load_tool_table(path)
            if tools:
                self._tools = tools
                self._file_path = path
                self._path_label.setText(path)
                self._refresh_tool_list()
                if self._tools:
                    self._tool_list.setCurrentRow(0)
        except Exception as e:
            QMessageBox.warning(self, "Load Error", f"Failed to load tool table:\n{e}")

    def _on_save(self):
        """Save tool table to current file path."""
        try:
            save_tool_table(self._tools, self._file_path)
        except Exception as e:
            QMessageBox.warning(self, "Save Error", f"Failed to save tool table:\n{e}")

    def _on_save_as(self):
        """Save tool table to a new file path."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Tool Table As", self._file_path,
            "Tool Table (*.tbl);;All Files (*)",
        )
        if not path:
            return

        self._file_path = path
        self._path_label.setText(path)
        self._on_save()

    # ------------------------------------------------------------------
    # Internal Helpers
    # ------------------------------------------------------------------

    def _build_tool_from_fields(self) -> Optional[ToolDef]:
        """Build a ToolDef from the current edit field values."""
        try:
            tool_number = int(self._field_tool_number.value())
            nose_radius = self._field_nose_radius.value()
            tip_angle = self._field_tip_angle.value()
            edge_length = self._field_edge_length.value()

            orient_val = self._field_orientation.currentData()
            orientation = ToolOrientation(orient_val)

            dir_val = self._field_direction.currentData()
            direction = ToolDirection(dir_val)

            description = self._field_description.text().strip()

            # Preserve offsets from existing tool
            existing = self._tools[self._current_index]

            return ToolDef(
                tool_number=tool_number,
                nose_radius=nose_radius,
                tip_angle=tip_angle,
                edge_length=edge_length,
                orientation=orientation,
                direction=direction,
                tool_type=existing.tool_type,
                rotation=existing.rotation,
                description=description,
                x_offset=existing.x_offset,
                z_offset=existing.z_offset,
                x_wear=existing.x_wear,
                z_wear=existing.z_wear,
            )
        except (ValueError, TypeError, IndexError):
            return None

    def _update_graphic_preview(self):
        """Update the tool graphic widget with current field values."""
        if self._current_index < 0 or self._current_index >= len(self._tools):
            return

        tool = self._tools[self._current_index]
        self._tool_graphic.set_tool_params(
            tip_angle=tool.tip_angle,
            edge_length=tool.edge_length,
            nose_radius=tool.nose_radius,
            orientation=tool.orientation,
            direction=tool.direction,
        )

    def _refresh_tool_list(self):
        """Rebuild the tool list widget from self._tools."""
        self._tool_list.blockSignals(True)
        self._tool_list.clear()
        for tool in self._tools:
            text = f"T{tool.tool_number:02d}  {tool.description}"
            self._tool_list.addItem(text)
        self._tool_list.blockSignals(False)

    def _refresh_list_item(self, index: int):
        """Update a single list item text after edit."""
        if 0 <= index < len(self._tools):
            tool = self._tools[index]
            text = f"T{tool.tool_number:02d}  {tool.description}"
            item = self._tool_list.item(index)
            if item:
                item.setText(text)

    def _auto_save(self):
        """Auto-save tool table on every change."""
        try:
            save_tool_table(self._tools, self._file_path)
        except Exception:
            pass  # Silent fail on auto-save — user can manually save

    def _load_or_create_default(self):
        """Load existing tool table or create default with one CNMG tool."""
        if os.path.exists(self._file_path):
            try:
                self._tools = load_tool_table(self._file_path)
            except Exception:
                self._tools = []

        if not self._tools:
            # Create default tool: T1 CNMG roughing
            self._tools = [
                ToolDef(
                    tool_number=1,
                    nose_radius=0.016,
                    tip_angle=80.0,
                    edge_length=0.500,
                    orientation=ToolOrientation.OD_FRONT_RIGHT,
                    direction=ToolDirection.RIGHT,
                    description="CNMG 432 Roughing",
                ),
            ]
            # Save the default
            self._auto_save()

        self._refresh_tool_list()
        if self._tools:
            self._tool_list.setCurrentRow(0)

    def _create_session_backup(self):
        """Create a session backup on launch (max 5 backups)."""
        if not os.path.exists(self._file_path):
            return
        try:
            create_backup(self._file_path, BACKUP_DIR, max_backups=5)
        except Exception:
            pass  # Non-critical — don't block startup
