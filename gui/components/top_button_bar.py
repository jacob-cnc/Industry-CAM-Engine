"""Top button bar widget for the Tools tab.

Provides file operations (Load Table, Save Table As), tool addition,
table name display, current tool display, and touch-off controls.

Layout:
    Left:   Load Table | Save Table As | Add Tool
    Center: Table name label | Current tool display
    Right:  Touch-off section (X input, Z input, Set X, Set Z)
"""

from PyQt5.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QDoubleSpinBox,
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont

from gui.colors import COLORS, FONTS, TOUCH


class TopButtonBar(QWidget):
    """Top button bar for the Tools tab.

    Signals:
        load_clicked: Emitted when Load Table button is pressed.
        save_as_clicked: Emitted when Save Table As button is pressed.
        add_tool_clicked: Emitted when Add Tool button is pressed.
        set_x_clicked(float): Emitted with the X spinbox value (diameter).
        set_z_clicked(float): Emitted with the Z spinbox value.
    """

    load_clicked = pyqtSignal()
    save_as_clicked = pyqtSignal()
    add_tool_clicked = pyqtSignal()
    set_x_clicked = pyqtSignal(float)
    set_z_clicked = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        """Build the button bar layout."""
        self.setFixedHeight(56)
        self.setStyleSheet(
            f"TopButtonBar {{ background-color: {COLORS['bg_status_bar']}; }}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(8)

        # --- Left section: File operations and Add Tool ---
        self._load_btn = self._make_button("Load Table")
        self._load_btn.clicked.connect(self.load_clicked.emit)
        layout.addWidget(self._load_btn)

        self._save_as_btn = self._make_button("Save Table As")
        self._save_as_btn.clicked.connect(self.save_as_clicked.emit)
        layout.addWidget(self._save_as_btn)

        self._add_tool_btn = self._make_button("Add Tool")
        self._add_tool_btn.setStyleSheet(self._button_style(COLORS["btn_generate"]))
        self._add_tool_btn.clicked.connect(self.add_tool_clicked.emit)
        layout.addWidget(self._add_tool_btn)

        # --- Center section: Table name and current tool ---
        layout.addStretch()

        label_font = QFont(FONTS["ui_family"], FONTS["ui_size"])

        self._table_name_label = QLabel("")
        self._table_name_label.setFont(label_font)
        self._table_name_label.setStyleSheet(
            f"color: {COLORS['text_secondary']}; border: none;"
        )
        self._table_name_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._table_name_label)

        self._current_tool_label = QLabel("Offline")
        self._current_tool_label.setFont(
            QFont(FONTS["mono_family"], FONTS["code_size"])
        )
        self._current_tool_label.setStyleSheet(
            f"color: {COLORS['status_info']}; border: none; padding: 0 8px;"
        )
        self._current_tool_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._current_tool_label)

        layout.addStretch()

        # --- Right section: Touch-off controls ---
        touchoff_label = QLabel("Touch-Off:")
        touchoff_label.setFont(label_font)
        touchoff_label.setStyleSheet(
            f"color: {COLORS['text_secondary']}; border: none;"
        )
        layout.addWidget(touchoff_label)

        # X input
        x_label = QLabel("X")
        x_label.setFont(label_font)
        x_label.setStyleSheet(
            f"color: {COLORS['text_secondary']}; border: none;"
        )
        layout.addWidget(x_label)

        self._x_spinbox = self._make_spinbox()
        layout.addWidget(self._x_spinbox)

        self._set_x_btn = self._make_button("Set X")
        self._set_x_btn.setMinimumWidth(60)
        self._set_x_btn.clicked.connect(self._on_set_x)
        layout.addWidget(self._set_x_btn)

        # Z input
        z_label = QLabel("Z")
        z_label.setFont(label_font)
        z_label.setStyleSheet(
            f"color: {COLORS['text_secondary']}; border: none;"
        )
        layout.addWidget(z_label)

        self._z_spinbox = self._make_spinbox()
        layout.addWidget(self._z_spinbox)

        self._set_z_btn = self._make_button("Set Z")
        self._set_z_btn.setMinimumWidth(60)
        self._set_z_btn.clicked.connect(self._on_set_z)
        layout.addWidget(self._set_z_btn)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_table_name(self, name: str) -> None:
        """Update the table name label with the current filename.

        Args:
            name: The filename to display (e.g., "tool.tbl").
        """
        self._table_name_label.setText(name)

    def set_current_tool(self, number: int, description: str) -> None:
        """Update the current tool display.

        Args:
            number: Active tool number (e.g., 1).
            description: Tool description (e.g., "CNMG roughing").
        """
        self._current_tool_label.setText(f"T{number} - {description}")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_set_x(self):
        """Emit set_x_clicked with the current X spinbox value."""
        self.set_x_clicked.emit(self._x_spinbox.value())

    def _on_set_z(self):
        """Emit set_z_clicked with the current Z spinbox value."""
        self.set_z_clicked.emit(self._z_spinbox.value())

    def _make_button(self, text: str) -> QPushButton:
        """Create a styled button with consistent sizing."""
        btn = QPushButton(text)
        btn.setFixedHeight(TOUCH["button_height"])
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFont(QFont(FONTS["ui_family"], FONTS["ui_size"], QFont.Bold))
        btn.setStyleSheet(self._button_style(COLORS["btn_primary"]))
        return btn

    def _make_spinbox(self) -> QDoubleSpinBox:
        """Create a touch-off numeric spinbox with 6 decimal places."""
        spinbox = QDoubleSpinBox()
        spinbox.setDecimals(6)
        spinbox.setRange(-99.999999, 99.999999)
        spinbox.setValue(0.0)
        spinbox.setSingleStep(0.001)
        spinbox.setFixedWidth(130)
        spinbox.setFixedHeight(TOUCH["button_height"])
        spinbox.setFont(QFont(FONTS["mono_family"], FONTS["code_size"]))
        spinbox.setAlignment(Qt.AlignRight)
        spinbox.setStyleSheet(
            f"QDoubleSpinBox {{"
            f"  background-color: {COLORS['bg_panel']};"
            f"  color: {COLORS['text_primary']};"
            f"  border: 1px solid {COLORS['border_normal']};"
            f"  border-radius: 3px;"
            f"  padding: 4px;"
            f"  font-family: {FONTS['mono_family']}, {FONTS['fallback_mono']};"
            f"}}"
            f"QDoubleSpinBox:focus {{"
            f"  border-color: {COLORS['border_focused']};"
            f"}}"
        )
        return spinbox

    @staticmethod
    def _button_style(bg_color: str) -> str:
        """Generate button stylesheet with the given background color."""
        return (
            f"QPushButton {{"
            f"  background-color: {bg_color};"
            f"  color: {COLORS['text_primary']};"
            f"  border: none;"
            f"  border-radius: 4px;"
            f"  padding: 8px 16px;"
            f"  font-weight: bold;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background-color: {COLORS['btn_primary_hover']};"
            f"}}"
            f"QPushButton:pressed {{"
            f"  background-color: {COLORS['btn_primary']};"
            f"}}"
        )
