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
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
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
    reset_clicked = pyqtSignal()
    machine_on_clicked = pyqtSignal()
    machine_off_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = "IDLE"
        self._x_dia = 0.0
        self._z = 0.0
        self._rpm = 0
        self._feed = 0.0
        self._gcodes = "G90 G20 G40"

        self._setup_ui()

        self._error_timer = QTimer(self)
        self._error_timer.setSingleShot(True)
        self._error_timer.timeout.connect(self.clear_error)

        if not HAS_LINUXCNC:
            self._show_offline()

    def _setup_ui(self):
        """Build the status bar layout.

        Height is fixed at 54px (25% smaller than previous 72px). DRO font
        fills the available space; all secondary elements are compact.
        """
        self.setFixedHeight(54)
        self.setStyleSheet(
            f"background-color: {COLORS['bg_status_bar']};"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)   # zero vertical \u2014 DRO fills height
        layout.setSpacing(8)

        # Fonts \u2014 DRO as large as fits in 54px; secondary ~25% smaller than before
        dro_font = QFont(FONTS["mono_family"], 34)   # fills the 54px ribbon
        dro_font.setStyleHint(QFont.Monospace)
        mono_font = QFont(FONTS["mono_family"], 16)  # was 24pt
        mono_font.setStyleHint(QFont.Monospace)
        mono_font_small = QFont(FONTS["mono_family"], 8)  # was 11pt
        mono_font_small.setStyleHint(QFont.Monospace)
        label_font = QFont(FONTS["ui_family"], 7)   # was 9pt
        dro_label_font = QFont(FONTS["ui_family"], 8, QFont.Bold)  # was 11pt

        # --- Machine State Indicator ---
        self._state_dot = QLabel("\u25CF")
        self._state_dot.setFixedWidth(14)
        self._state_dot.setAlignment(Qt.AlignCenter)
        self._state_dot.setStyleSheet(
            f"color: {_STATE_COLORS['IDLE']}; font-size: 12px; border: none;"
        )
        layout.addWidget(self._state_dot)

        self._state_label = QLabel("IDLE")
        self._state_label.setFont(label_font)
        self._state_label.setStyleSheet(
            f"color: {COLORS['text_primary']}; font-weight: bold; border: none;"
        )
        self._state_label.setFixedWidth(36)
        layout.addWidget(self._state_label)

        # --- DRO: X and Z in a prominent bordered box ---
        dro_box = QFrame()
        dro_box.setStyleSheet(
            f"QFrame {{"
            f"  background-color: {COLORS['bg_panel']};"
            f"  border: 1px solid {COLORS['border_normal']};"
            f"  border-radius: 5px;"
            f"}}"
        )
        dro_inner = QHBoxLayout(dro_box)
        dro_inner.setContentsMargins(8, 0, 8, 0)   # zero vertical \u2014 font drives height
        dro_inner.setSpacing(4)

        _dro_axis_ss = (
            f"font-family: '{FONTS['ui_family']}'; font-size: 8pt; font-weight: bold;"
            f" color: {COLORS['status_info']}; border: none; background: transparent;"
        )
        _dro_val_ss = (
            f"font-family: '{FONTS['mono_family']}'; font-size: 34pt;"
            f" color: {COLORS['text_primary']}; border: none; background: transparent;"
        )

        x_label = QLabel("X")
        x_label.setStyleSheet(_dro_axis_ss)
        dro_inner.addWidget(x_label)

        self._x_dro = QLabel("0.0000")
        self._x_dro.setStyleSheet(_dro_val_ss)
        self._x_dro.setMinimumWidth(200)
        dro_inner.addWidget(self._x_dro)

        dro_sep = QFrame()
        dro_sep.setFrameShape(QFrame.VLine)
        dro_sep.setStyleSheet(f"color: {COLORS['border_normal']}; background: transparent;")
        dro_sep.setFixedWidth(2)
        dro_inner.addWidget(dro_sep)

        z_label = QLabel("Z")
        z_label.setStyleSheet(_dro_axis_ss)
        dro_inner.addWidget(z_label)

        self._z_dro = QLabel("0.0000")
        self._z_dro.setStyleSheet(_dro_val_ss)
        self._z_dro.setMinimumWidth(200)
        dro_inner.addWidget(self._z_dro)

        layout.addWidget(dro_box)

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

        # --- Spindle RPM ---
        rpm_label = QLabel("RPM")
        rpm_label.setFont(label_font)
        rpm_label.setStyleSheet(f"color: {COLORS['text_secondary']}; border: none;")
        layout.addWidget(rpm_label)

        self._rpm_display = QLabel("0")
        self._rpm_display.setFont(mono_font)
        self._rpm_display.setStyleSheet(
            f"color: {COLORS['text_primary']}; border: none;"
        )
        self._rpm_display.setMinimumWidth(44)
        layout.addWidget(self._rpm_display)

        self._spindle_dir_indicator = QLabel("")
        self._spindle_dir_indicator.setFont(label_font)
        self._spindle_dir_indicator.setFixedWidth(20)
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
        self._feed_display.setMinimumWidth(44)
        layout.addWidget(self._feed_display)

        # --- Tool Number ---
        tool_label = QLabel("T")
        tool_label.setFont(label_font)
        tool_label.setStyleSheet(f"color: {COLORS['text_secondary']}; border: none;")
        layout.addWidget(tool_label)

        self._tool_display = QLabel("0")
        self._tool_display.setFont(mono_font_small)
        self._tool_display.setStyleSheet(
            f"color: {COLORS['text_primary']}; border: none;"
        )
        self._tool_display.setMinimumWidth(22)
        layout.addWidget(self._tool_display)

        # --- Error message ---
        self._error_label = QLabel("")
        self._error_label.setFont(mono_font_small)
        self._error_label.setStyleSheet(
            f"color: {COLORS['text_primary']};"
            f"background-color: {COLORS['status_error']};"
            f"border: 1px solid {COLORS['border_error']};"
            f"border-radius: 3px;"
            f"padding: 1px 6px;"
        )
        self._error_label.setVisible(False)
        layout.addWidget(self._error_label)

        # --- Spacer + Machine Control Buttons + E-Stop ---
        layout.addStretch()

        self._btn_reset = QPushButton("Reset")
        self._btn_reset.setStyleSheet(
            f"QPushButton {{ background: {COLORS['status_warning']}; color: {COLORS['bg_base']}; "
            f"font-size: 7pt; font-weight: bold; border-radius: 3px; padding: 2px 8px;"
            f" min-height: 20px; }}"
            f"QPushButton:hover {{ background: #e6a817; }}"
        )
        self._btn_reset.setToolTip("Reset E-Stop")
        layout.addWidget(self._btn_reset)

        self._btn_on = QPushButton("ON")
        self._btn_on.setStyleSheet(
            f"QPushButton {{ background: {COLORS['status_ok']}; color: {COLORS['bg_base']}; "
            f"font-size: 7pt; font-weight: bold; border-radius: 3px; padding: 2px 8px;"
            f" min-height: 20px; }}"
            f"QPushButton:hover {{ background: #6FB8A8; }}"
        )
        self._btn_on.setToolTip("Machine On")
        layout.addWidget(self._btn_on)

        self._btn_off = QPushButton("OFF")
        self._btn_off.setStyleSheet(
            f"QPushButton {{ background: {COLORS['bg_surface']}; color: {COLORS['text_primary']}; "
            f"font-size: 7pt; font-weight: bold; border-radius: 3px; padding: 2px 8px;"
            f" min-height: 20px; border: 1px solid {COLORS['border_normal']}; }}"
            f"QPushButton:hover {{ background: {COLORS['border_normal']}; }}"
        )
        self._btn_off.setToolTip("Machine Off")
        layout.addWidget(self._btn_off)

        # Connect machine control signals
        self._btn_reset.clicked.connect(self.reset_clicked.emit)
        self._btn_on.clicked.connect(self.machine_on_clicked.emit)
        self._btn_off.clicked.connect(self.machine_off_clicked.emit)

        self._estop_btn = QPushButton("E-STOP")
        self._estop_btn.setFixedHeight(28)
        self._estop_btn.setMinimumWidth(72)
        self._estop_btn.setFont(QFont(FONTS["ui_family"], 9, QFont.Bold))
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

    def update_tool(self, tool_number: int):
        """Update current tool number display.

        Args:
            tool_number: Tool currently in spindle (0 = no tool).
        """
        self._tool_display.setText(str(tool_number))

    def update_gcodes(self, gcodes: str):
        """Update active G-codes display.

        Args:
            gcodes: Space-separated active G-codes (e.g., "G90 G20 G40").
        """
        self._gcodes = gcodes
        self._gcode_display.setText(gcodes)

    def show_error(self, msg: str):
        """Display an error message in the ribbon. Auto-clears after 8 seconds.

        Args:
            msg: Error text from LinuxCNC error channel.
        """
        self._error_label.setText(f"! {msg}")
        self._error_label.setVisible(True)
        self._error_timer.start(8000)

    def clear_error(self):
        """Hide the error message label."""
        self._error_label.setVisible(False)
        self._error_label.setText("")

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
