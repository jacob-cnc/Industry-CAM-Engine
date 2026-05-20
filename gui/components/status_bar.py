"""Status bar widget for Industry CAM Engine.

Displays machine state, live DRO (X diameter, Z inches), active G-codes,
spindle RPM, and feed rate. Includes a prominent software E-Stop button.
Supports offline mode with demo values.

Placed at the top of the main window.
"""

try:
    import linuxcnc
    HAS_LINUXCNC = True
except ImportError:
    HAS_LINUXCNC = False

from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QFrame, QPushButton,
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont

from gui.colors import COLORS, FONTS


# Machine state color mapping
_STATE_COLORS = {
    "IDLE": COLORS["status_ok"],
    "RUN": COLORS["status_info"],
    "PAUSE": COLORS["status_warning"],
    "ESTOP": COLORS["status_error"],
}


class _Separator(QFrame):
    """Vertical separator line between status bar sections."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.VLine)
        self.setFrameShadow(QFrame.Plain)
        self.setStyleSheet(f"color: {COLORS['border_normal']};")
        self.setFixedWidth(2)


class StatusBar(QWidget):
    """Top status bar showing machine state, DRO, G-codes, and spindle info.

    Includes a prominent software E-Stop button on the right side that is
    always visible regardless of which tab is selected.

    In offline mode (no linuxcnc module), displays an OFFLINE badge and
    demo values. Provides update methods for live data integration.

    Signals:
        estop_clicked: Emitted when the E-Stop button is pressed.
    """

    estop_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = "IDLE"
        self._x_dia = 0.0
        self._z = 0.0
        self._rpm = 0
        self._feed = 0.0
        self._gcodes = "G90 G20 G40"

        self._setup_ui()

        if not HAS_LINUXCNC:
            self._show_offline()

    def _setup_ui(self):
        """Build the status bar layout."""
        self.setFixedHeight(48)
        self.setStyleSheet(
            f"background-color: {COLORS['bg_status_bar']};"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(12)

        # Fonts
        mono_font = QFont(FONTS["mono_family"], FONTS["dro_size"])
        mono_font.setStyleHint(QFont.Monospace)
        mono_font_small = QFont(FONTS["mono_family"], FONTS["code_size"])
        mono_font_small.setStyleHint(QFont.Monospace)
        label_font = QFont(FONTS["ui_family"], FONTS["small_size"])

        # --- Machine State Indicator ---
        self._state_dot = QLabel("\u25CF")  # Filled circle
        self._state_dot.setFixedWidth(20)
        self._state_dot.setAlignment(Qt.AlignCenter)
        self._state_dot.setStyleSheet(
            f"color: {_STATE_COLORS['IDLE']}; font-size: 16px; border: none;"
        )
        layout.addWidget(self._state_dot)

        self._state_label = QLabel("IDLE")
        self._state_label.setFont(label_font)
        self._state_label.setStyleSheet(
            f"color: {COLORS['text_primary']}; font-weight: bold; border: none;"
        )
        self._state_label.setFixedWidth(50)
        layout.addWidget(self._state_label)

        # --- DRO: X (diameter) ---
        x_label = QLabel("X")
        x_label.setFont(label_font)
        x_label.setStyleSheet(f"color: {COLORS['text_secondary']}; border: none;")
        layout.addWidget(x_label)

        self._x_dro = QLabel("0.0000")
        self._x_dro.setFont(mono_font)
        self._x_dro.setStyleSheet(
            f"color: {COLORS['text_primary']}; border: none;"
        )
        self._x_dro.setMinimumWidth(120)
        layout.addWidget(self._x_dro)

        # --- DRO: Z (inches) ---
        z_label = QLabel("Z")
        z_label.setFont(label_font)
        z_label.setStyleSheet(f"color: {COLORS['text_secondary']}; border: none;")
        layout.addWidget(z_label)

        self._z_dro = QLabel("0.0000")
        self._z_dro.setFont(mono_font)
        self._z_dro.setStyleSheet(
            f"color: {COLORS['text_primary']}; border: none;"
        )
        self._z_dro.setMinimumWidth(120)
        layout.addWidget(self._z_dro)

        # --- Active G-codes ---
        gcode_label = QLabel("G")
        gcode_label.setFont(label_font)
        gcode_label.setStyleSheet(f"color: {COLORS['text_secondary']}; border: none;")
        layout.addWidget(gcode_label)

        self._gcode_display = QLabel("G90 G20 G40")
        self._gcode_display.setFont(mono_font_small)
        self._gcode_display.setStyleSheet(
            f"color: {COLORS['text_subtle']}; border: none;"
        )
        layout.addWidget(self._gcode_display)

        # --- Spindle RPM (live from encoder) ---
        rpm_label = QLabel("RPM")
        rpm_label.setFont(label_font)
        rpm_label.setStyleSheet(f"color: {COLORS['text_secondary']}; border: none;")
        layout.addWidget(rpm_label)

        self._rpm_display = QLabel("0")
        self._rpm_display.setFont(mono_font)
        self._rpm_display.setStyleSheet(
            f"color: {COLORS['text_primary']}; border: none;"
        )
        self._rpm_display.setMinimumWidth(60)
        layout.addWidget(self._rpm_display)

        self._spindle_dir_indicator = QLabel("")
        self._spindle_dir_indicator.setFont(label_font)
        self._spindle_dir_indicator.setFixedWidth(30)
        self._spindle_dir_indicator.setAlignment(Qt.AlignCenter)
        self._spindle_dir_indicator.setStyleSheet(
            f"color: {COLORS['text_disabled']}; border: none;"
        )
        layout.addWidget(self._spindle_dir_indicator)

        # --- Feed Rate ---
        feed_label = QLabel("F")
        feed_label.setFont(label_font)
        feed_label.setStyleSheet(f"color: {COLORS['text_secondary']}; border: none;")
        layout.addWidget(feed_label)

        self._feed_display = QLabel("0.000")
        self._feed_display.setFont(mono_font_small)
        self._feed_display.setStyleSheet(
            f"color: {COLORS['text_primary']}; border: none;"
        )
        self._feed_display.setMinimumWidth(60)
        layout.addWidget(self._feed_display)

        # --- Spacer + E-Stop Button + Offline Badge ---
        layout.addStretch()

        self._estop_btn = QPushButton("E-STOP")
        self._estop_btn.setFixedHeight(36)
        self._estop_btn.setMinimumWidth(90)
        self._estop_btn.setFont(QFont(FONTS["ui_family"], 11, QFont.Bold))
        self._estop_btn.setCursor(Qt.PointingHandCursor)
        self._estop_btn.setToolTip("Software E-Stop — immediately halt all motion")
        self._estop_btn.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {COLORS['status_error']};"
            f"  color: #ffffff;"
            f"  border: 2px solid #ff2222;"
            f"  border-radius: 6px;"
            f"  padding: 0 12px;"
            f"  font-weight: bold;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background-color: #ff3333;"
            f"  border: 2px solid #ff5555;"
            f"}}"
            f"QPushButton:pressed {{"
            f"  background-color: #aa0000;"
            f"  border: 2px solid #cc0000;"
            f"}}"
        )
        self._estop_btn.clicked.connect(self.estop_clicked.emit)
        layout.addWidget(self._estop_btn)

        self._offline_badge = QLabel("OFFLINE")
        self._offline_badge.setFont(label_font)
        self._offline_badge.setStyleSheet(
            f"color: {COLORS['status_warning']};"
            f"background-color: {COLORS['bg_surface']};"
            f"border: 1px solid {COLORS['status_warning']};"
            f"border-radius: 3px;"
            f"padding: 2px 8px;"
            f"font-weight: bold;"
        )
        self._offline_badge.setVisible(False)
        layout.addWidget(self._offline_badge)

    def _show_offline(self):
        """Configure offline mode display with demo values."""
        self._offline_badge.setVisible(True)
        self.update_position(0.0, 0.0)
        self.update_state("IDLE")
        self.update_rpm(0)
        self.update_feed(0.0)
        self.update_gcodes("G90 G20 G40")

    # --- Public update methods ---

    def update_position(self, x_dia: float, z: float):
        """Update DRO with new position values.

        Args:
            x_dia: X position in diameter (inches).
            z: Z position in inches.
        """
        self._x_dia = x_dia
        self._z = z
        self._x_dro.setText(f"{x_dia:.4f}")
        self._z_dro.setText(f"{z:.4f}")

    def update_state(self, state_str: str):
        """Update machine state indicator.

        Args:
            state_str: One of "IDLE", "RUN", "PAUSE", "ESTOP".
        """
        state_str = state_str.upper()
        self._state = state_str
        color = _STATE_COLORS.get(state_str, COLORS["text_disabled"])
        self._state_dot.setStyleSheet(
            f"color: {color}; font-size: 16px; border: none;"
        )
        self._state_label.setText(state_str)
        self._state_label.setStyleSheet(
            f"color: {COLORS['text_primary']}; font-weight: bold; border: none;"
        )

    def update_rpm(self, rpm: int, direction: str = ""):
        """Update spindle RPM display and direction indicator.

        Args:
            rpm: Current spindle speed in revolutions per minute (from encoder).
            direction: "FWD", "REV", or "" for stopped.
        """
        self._rpm = rpm
        self._rpm_display.setText(str(rpm))

        if direction == "FWD":
            self._spindle_dir_indicator.setText("→")
            self._spindle_dir_indicator.setStyleSheet(
                f"color: {COLORS['status_ok']}; border: none; font-size: 14px;"
            )
        elif direction == "REV":
            self._spindle_dir_indicator.setText("←")
            self._spindle_dir_indicator.setStyleSheet(
                f"color: {COLORS['status_info']}; border: none; font-size: 14px;"
            )
        else:
            self._spindle_dir_indicator.setText("")
            self._spindle_dir_indicator.setStyleSheet(
                f"color: {COLORS['text_disabled']}; border: none;"
            )

    def update_feed(self, feed: float):
        """Update feed rate display.

        Args:
            feed: Current feed rate in inches/rev.
        """
        self._feed = feed
        self._feed_display.setText(f"{feed:.3f}")

    def update_gcodes(self, gcodes: str):
        """Update active G-codes display.

        Args:
            gcodes: Space-separated active G-codes (e.g., "G90 G20 G40").
        """
        self._gcodes = gcodes
        self._gcode_display.setText(gcodes)

    # --- Property accessors ---

    @property
    def state(self) -> str:
        """Current machine state string."""
        return self._state

    @property
    def x_position(self) -> float:
        """Current X position (diameter)."""
        return self._x_dia

    @property
    def z_position(self) -> float:
        """Current Z position (inches)."""
        return self._z

    @property
    def is_offline(self) -> bool:
        """Whether running in offline mode (no linuxcnc module)."""
        return not HAS_LINUXCNC
