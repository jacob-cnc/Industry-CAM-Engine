"""
Enhanced Tuning Tab — Stepper, Encoder, PID Tuning with Live Data & INI I/O
=============================================================================
Extends the base TuningTab with:
- Real-time following error graph
- Live HAL pin polling (online) / simulated data (offline)
- Load/Save to INI file
- Live PID adjustment via halcmd setp
- Proper set_active() timer management

This file is intended to REPLACE gui/tabs/tuning.py
"""

import os
import re
import subprocess
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QGroupBox, QLineEdit, QScrollArea,
    QMessageBox, QFrame, QCheckBox,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont

from theme import COLORS, mono_font, ui_font

# Conditional imports for online/offline
try:
    import linuxcnc
    import hal
    HAS_LINUXCNC = True
except ImportError:
    HAS_LINUXCNC = False


# ---------------------------------------------------------------------------
# Constants — HAL pin names for this machine
# ---------------------------------------------------------------------------
# CRITICAL: stepgen.00 = Z axis, stepgen.01 = X axis (reversed from joint #)
TUNING_PINS = {
    'x': {
        'pid_command':  'pid.x.command',
        'pid_feedback': 'pid.x.feedback',
        'pid_output':   'pid.x.output',
        'pid_error':    'pid.x.error',
        'encoder_pos':  'hm2_10.10.10.10.encoder.00.position',
        'stepgen_fb':   'hm2_10.10.10.10.stepgen.01.position-fb',
        'stepgen_vel':  'hm2_10.10.10.10.stepgen.01.velocity-cmd',
    },
    'z': {
        'pid_command':  'pid.z.command',
        'pid_feedback': 'pid.z.feedback',
        'pid_output':   'pid.z.output',
        'pid_error':    'pid.z.error',
        'encoder_pos':  'hm2_10.10.10.10.encoder.01.position',
        'stepgen_fb':   'hm2_10.10.10.10.stepgen.00.position-fb',
        'stepgen_vel':  'hm2_10.10.10.10.stepgen.00.velocity-cmd',
    },
    'spindle': {
        'position':     'hm2_10.10.10.10.encoder.02.position',
        'velocity':     'hm2_10.10.10.10.encoder.02.velocity',
        'index_enable': 'hm2_10.10.10.10.encoder.02.index-enable',
    },
}

# PID HAL pin names (for live adjustment via halcmd setp)
PID_HAL_PINS = {
    'x': {
        'Pgain': 'pid.x.Pgain',
        'Igain': 'pid.x.Igain',
        'Dgain': 'pid.x.Dgain',
        'FF0': 'pid.x.FF0',
        'FF1': 'pid.x.FF1',
        'FF2': 'pid.x.FF2',
        'deadband': 'pid.x.deadband',
        'maxoutput': 'pid.x.maxoutput',
        'maxerror': 'pid.x.maxerror',
    },
    'z': {
        'Pgain': 'pid.z.Pgain',
        'Igain': 'pid.z.Igain',
        'Dgain': 'pid.z.Dgain',
        'FF0': 'pid.z.FF0',
        'FF1': 'pid.z.FF1',
        'FF2': 'pid.z.FF2',
        'deadband': 'pid.z.deadband',
        'maxoutput': 'pid.z.maxoutput',
        'maxerror': 'pid.z.maxerror',
    },
}

# Mapping from UI field keys to INI keys (for load/save)
FIELD_TO_INI = {
    'step_scale': 'STEP_SCALE',
    'max_vel': 'MAX_VELOCITY',
    'max_accel': 'MAX_ACCELERATION',
    'sg_maxvel': 'STEPGEN_MAXVEL',
    'sg_maxaccel': 'STEPGEN_MAXACCEL',
    'dirsetup': 'DIRSETUP',
    'dirhold': 'DIRHOLD',
    'steplen': 'STEPLEN',
    'stepspace': 'STEPSPACE',
    'enc_scale': 'ENCODER_SCALE',
    'p_gain': 'P',
    'i_gain': 'I',
    'd_gain': 'D',
    'ff0': 'FF0',
    'ff1': 'FF1',
    'ff2': 'FF2',
    'deadband': 'DEADBAND',
    'max_output': 'MAX_OUTPUT',
    'max_error': 'MAX_ERROR',
    'ferror': 'FERROR',
    'min_ferror': 'MIN_FERROR',
}


# ---------------------------------------------------------------------------
# INI File I/O — regex-based to preserve comments and formatting
# ---------------------------------------------------------------------------

def load_ini_section(ini_path, section_name):
    """Load all key=value pairs from an INI section.

    Uses regex parsing to handle LinuxCNC INI quirks (comments, spacing).

    Args:
        ini_path: Path to the INI file
        section_name: Section name without brackets (e.g. 'JOINT_0')

    Returns:
        Dict of {key: value_string} for all keys in the section.
    """
    result = {}
    if not os.path.isfile(ini_path):
        return result

    in_section = False
    section_re = re.compile(r'^\[(.+)\]')
    kv_re = re.compile(r'^(\w+)\s*=\s*(.+?)(?:\s*#.*)?$')

    with open(ini_path, 'r') as f:
        for line in f:
            line = line.rstrip('\n')
            # Check for section header
            m = section_re.match(line)
            if m:
                if m.group(1) == section_name:
                    in_section = True
                else:
                    if in_section:
                        break  # Left our section
                    in_section = False
                continue

            if in_section:
                m = kv_re.match(line)
                if m:
                    result[m.group(1)] = m.group(2).strip()

    return result


def save_ini_value(ini_path, section_name, key, value):
    """Update a single key=value in an INI file, preserving formatting.

    Replaces the value in-place using regex. If the key doesn't exist
    in the section, appends it at the end of the section.

    Args:
        ini_path: Path to the INI file
        section_name: Section name without brackets
        key: The INI key to update
        value: New value as string
    """
    if not os.path.isfile(ini_path):
        return False

    with open(ini_path, 'r') as f:
        lines = f.readlines()

    section_re = re.compile(r'^\[(.+)\]')
    kv_re = re.compile(rf'^({re.escape(key)})\s*=\s*(.+?)(\s*#.*)?$')

    in_section = False
    found = False
    new_lines = []

    for line in lines:
        stripped = line.rstrip('\n')
        m = section_re.match(stripped)
        if m:
            if in_section and not found:
                # Key not found in section — append before leaving
                new_lines.append(f"{key} = {value}\n")
                found = True
            in_section = (m.group(1) == section_name)
            new_lines.append(line)
            continue

        if in_section and not found:
            m = kv_re.match(stripped)
            if m:
                # Preserve any inline comment
                comment = m.group(3) or ''
                new_lines.append(f"{key} = {value}{comment}\n")
                found = True
                continue

        new_lines.append(line)

    # If section was the last one and key wasn't found
    if in_section and not found:
        new_lines.append(f"{key} = {value}\n")

    with open(ini_path, 'w') as f:
        f.writelines(new_lines)

    return True


def hal_setp(pin_name, value):
    """Set a HAL pin value at runtime via halcmd subprocess.

    Only call this when HAS_LINUXCNC is True.

    Args:
        pin_name: Full HAL pin name (e.g. 'pid.x.Pgain')
        value: Value to set (will be converted to string)

    Returns:
        True on success, False on failure
    """
    try:
        result = subprocess.run(
            ['halcmd', 'setp', pin_name, str(value)],
            capture_output=True, text=True, timeout=2
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


# ---------------------------------------------------------------------------
# TuningAxisPanel — single axis tuning controls (unchanged from original)
# ---------------------------------------------------------------------------
class TuningAxisPanel(QGroupBox):
    """Tuning controls for a single axis (stepper + encoder + PID)."""

    def __init__(self, axis_name, joint_num, parent=None):
        super().__init__(f"{axis_name} Axis — Joint {joint_num}", parent)
        self.axis_name = axis_name
        self.joint_num = joint_num

        layout = QGridLayout(self)
        layout.setSpacing(6)

        lbl_style = f"color: {COLORS['text_dim']}; font-size: 16px;"
        val_style = (
            f"background-color: {COLORS['dro_bg']}; color: {COLORS['text']}; "
            f"border: 1px solid {COLORS['border']}; border-radius: 2px; "
            f"padding: 4px; font-family: Consolas; font-size: 18px;"
        )
        section_style = (
            f"color: {COLORS['accent_blue']}; font-size: 18px; "
            f"font-weight: bold; border: none; background: transparent;"
        )

        row = 0

        # === Stepper Section ===
        hdr = QLabel("Stepper Drive")
        hdr.setStyleSheet(section_style)
        layout.addWidget(hdr, row, 0, 1, 4)
        row += 1

        fields_stepper = [
            ("Step Scale:", "step_scale", "8000",
             "Steps per inch (microsteps x leadscrew TPI)"),
            ("Max Velocity:", "max_vel", "3.0",
             "Max axis velocity (in/sec)"),
            ("Max Accel:", "max_accel", "15.0",
             "Max axis acceleration (in/sec^2)"),
            ("Stepgen Max Vel:", "sg_maxvel", "3.6",
             "Stepgen headroom — ~120% of max velocity"),
            ("Stepgen Max Accel:", "sg_maxaccel", "18.75",
             "Stepgen headroom — ~125% of max accel"),
        ]

        self._fields = {}
        for label_text, key, default, tooltip in fields_stepper:
            lbl = QLabel(label_text)
            lbl.setStyleSheet(lbl_style)
            lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            layout.addWidget(lbl, row, 0)
            field = QLineEdit(default)
            field.setStyleSheet(val_style)
            field.setToolTip(tooltip)
            field.setFixedWidth(120)
            layout.addWidget(field, row, 1)
            self._fields[key] = field
            row += 1

        # Step timing row (compact)
        hdr2 = QLabel("Step Timing (ns)")
        hdr2.setStyleSheet(section_style)
        layout.addWidget(hdr2, row, 0, 1, 4)
        row += 1

        timing_fields = [
            ("Dir Setup:", "dirsetup", "5000"),
            ("Dir Hold:", "dirhold", "5000"),
            ("Step Len:", "steplen", "5000"),
            ("Step Space:", "stepspace", "5000"),
        ]
        col = 0
        for label_text, key, default in timing_fields:
            lbl = QLabel(label_text)
            lbl.setStyleSheet(lbl_style)
            lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            layout.addWidget(lbl, row, col)
            field = QLineEdit(default)
            field.setStyleSheet(val_style)
            field.setFixedWidth(80)
            field.setToolTip("Nanoseconds — check stepper driver datasheet")
            layout.addWidget(field, row, col + 1)
            self._fields[key] = field
            col += 2
            if col >= 4:
                col = 0
                row += 1
        if col != 0:
            row += 1

        # === Encoder Section ===
        hdr3 = QLabel("Linear Encoder")
        hdr3.setStyleSheet(section_style)
        layout.addWidget(hdr3, row, 0, 1, 4)
        row += 1

        enc_fields = [
            ("Encoder Scale:", "enc_scale", "50800",
             "Counts per inch (4x line count for quadrature)"),
        ]
        for label_text, key, default, tooltip in enc_fields:
            lbl = QLabel(label_text)
            lbl.setStyleSheet(lbl_style)
            lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            layout.addWidget(lbl, row, 0)
            field = QLineEdit(default)
            field.setStyleSheet(val_style)
            field.setToolTip(tooltip)
            field.setFixedWidth(120)
            layout.addWidget(field, row, 1)
            self._fields[key] = field
            row += 1

        # === PID Section ===
        hdr4 = QLabel("PID Tuning")
        hdr4.setStyleSheet(section_style)
        layout.addWidget(hdr4, row, 0, 1, 4)
        row += 1

        pid_fields = [
            ("P Gain:", "p_gain", "1000.0",
             "Proportional — corrects position error. Start low, increase "
             "until responsive without oscillation."),
            ("I Gain:", "i_gain", "0.0",
             "Integral — eliminates steady-state error. Usually 0 for "
             "steppers."),
            ("D Gain:", "d_gain", "0.0",
             "Derivative — dampens oscillation. Rarely needed for steppers."),
            ("FF0:", "ff0", "0.0",
             "Feedforward 0 — position. Usually 0."),
            ("FF1:", "ff1", "1.0",
             "Feedforward 1 — velocity. Set to 1.0 for steppers."),
            ("FF2:", "ff2", "0.0",
             "Feedforward 2 — acceleration. Usually 0."),
            ("Deadband:", "deadband", "0.0001",
             "Ignore errors smaller than this (inches)."),
            ("Max Output:", "max_output", "3.6",
             "Clamp PID output to this velocity (in/sec)."),
            ("Max Error:", "max_error", "0.0005",
             "Max error the PID will act on (inches)."),
        ]

        for label_text, key, default, tooltip in pid_fields:
            lbl = QLabel(label_text)
            lbl.setStyleSheet(lbl_style)
            lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            layout.addWidget(lbl, row, 0)
            field = QLineEdit(default)
            field.setStyleSheet(val_style)
            field.setToolTip(tooltip)
            field.setFixedWidth(120)
            layout.addWidget(field, row, 1)
            self._fields[key] = field
            row += 1

        # === Following Error ===
        hdr5 = QLabel("Following Error Limits")
        hdr5.setStyleSheet(section_style)
        layout.addWidget(hdr5, row, 0, 1, 4)
        row += 1

        ferr_fields = [
            ("FERROR:", "ferror", "0.010",
             "Max following error at full speed (inches). Faults if exceeded."),
            ("MIN_FERROR:", "min_ferror", "0.002",
             "Max following error at low speed (inches)."),
        ]
        for label_text, key, default, tooltip in ferr_fields:
            lbl = QLabel(label_text)
            lbl.setStyleSheet(lbl_style)
            lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            layout.addWidget(lbl, row, 0)
            field = QLineEdit(default)
            field.setStyleSheet(val_style)
            field.setToolTip(tooltip)
            field.setFixedWidth(120)
            layout.addWidget(field, row, 1)
            self._fields[key] = field
            row += 1

    def get_values(self):
        """Return all field values as a dict."""
        return {k: v.text() for k, v in self._fields.items()}

    def set_values(self, data):
        """Set field values from a dict."""
        for k, v in data.items():
            if k in self._fields:
                self._fields[k].setText(str(v))


# ---------------------------------------------------------------------------
# TuningTab — Enhanced main tuning interface
# ---------------------------------------------------------------------------
class TuningTab(QWidget):
    """Stepper, encoder, and PID tuning with live data and INI I/O.

    Features:
    - Per-axis parameter panels (stepper, encoder, PID, FERROR)
    - Real-time following error strip chart
    - Live status readouts (positions, errors, RPM)
    - Load from / Save to INI file
    - Apply Live button (halcmd setp for PID gains without restart)
    - Offline demo mode with simulated data
    """

    def __init__(self, ini_path=None, has_linuxcnc=False, parent=None):
        super().__init__(parent)
        self.ini_path = ini_path
        self._has_linuxcnc = has_linuxcnc
        self._active = False
        self._metric_display = False

        # Provider selection
        if has_linuxcnc:
            try:
                from hal_providers import LiveHALProvider
                self._provider = LiveHALProvider()
            except Exception:
                self._provider = None
                self._has_linuxcnc = False
        else:
            self._provider = None

        # Offline simulation provider
        if not self._has_linuxcnc:
            from tuning_provider import SimulatedTuningProvider
            self._sim_provider = SimulatedTuningProvider()
        else:
            self._sim_provider = None

        self._build_ui()
        self._connect_signals()

        # Polling timers
        self._graph_timer = QTimer(self)
        self._graph_timer.timeout.connect(self._poll_graph_data)
        self._graph_timer.setInterval(50)  # 50ms for smooth graph

        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._poll_status_data)
        self._status_timer.setInterval(200)  # 200ms for numeric readouts

    def _build_ui(self):
        """Build the complete tab layout."""
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # --- Offline banner ---
        if not self._has_linuxcnc:
            banner = QLabel("OFFLINE — Simulated Data")
            banner.setAlignment(Qt.AlignCenter)
            banner.setFont(ui_font(12, QFont.Bold))
            banner.setStyleSheet(
                f"background-color: {COLORS['accent_orange']};"
                f"color: {COLORS['bg_dark']};"
                f"padding: 4px; border-radius: 4px;"
            )
            banner.setFixedHeight(26)
            layout.addWidget(banner)

        # --- Info banner ---
        info = QLabel(
            "Adjust stepper drive, linear encoder, and PID parameters. "
            "Hover fields for descriptions. 'Apply Live' pushes PID gains "
            "to HAL immediately. 'Save to INI' persists (requires restart)."
        )
        info.setWordWrap(True)
        info.setStyleSheet(
            f"color: {COLORS['text_dim']}; font-size: 14px; "
            f"padding: 6px; background-color: {COLORS['bg_mid']}; "
            f"border: 1px solid {COLORS['border']}; border-radius: 4px;"
        )
        layout.addWidget(info)

        # --- Action buttons ---
        btn_bar = QHBoxLayout()
        self.btn_load = QPushButton("Load from INI")
        self.btn_load.setToolTip("Read current values from my-lathe.ini")

        self.btn_save = QPushButton("Save to INI")
        self.btn_save.setToolTip(
            "Write values to INI file. Requires LinuxCNC restart."
        )
        self.btn_save.setStyleSheet(
            f"QPushButton {{ background-color: {COLORS['accent_green']}; "
            f"color: {COLORS['bg_dark']}; font-weight: 700; border: none; "
            f"border-radius: 8px; }}"
            f"QPushButton:hover {{ "
            f"background-color: {COLORS['accent_green_lt']}; }}"
        )

        self.btn_apply_live = QPushButton("Apply Live")
        self.btn_apply_live.setToolTip(
            "Push PID gains to HAL now (no restart needed). "
            "Only affects PID parameters."
        )
        self.btn_apply_live.setStyleSheet(
            f"QPushButton {{ background-color: {COLORS['accent_blue']}; "
            f"color: white; font-weight: 700; border: none; "
            f"border-radius: 8px; }}"
            f"QPushButton:hover {{ "
            f"background-color: {COLORS['accent_blue_lt']}; }}"
        )
        if not self._has_linuxcnc:
            self.btn_apply_live.setEnabled(False)
            self.btn_apply_live.setToolTip("Requires LinuxCNC connection")

        self.btn_defaults = QPushButton("Reset Defaults")

        btn_bar.addWidget(self.btn_load)
        btn_bar.addWidget(self.btn_save)
        btn_bar.addWidget(self.btn_apply_live)
        btn_bar.addWidget(self.btn_defaults)
        btn_bar.addStretch()
        layout.addLayout(btn_bar)

        # --- Following Error Graph ---
        from tuning_graph import FollowingErrorPanel
        self.error_panel = FollowingErrorPanel()
        self.error_panel.setMinimumHeight(160)
        layout.addWidget(self.error_panel, stretch=2)

        # --- Scrollable axis panels ---
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            f"QScrollArea {{ border: 1px solid {COLORS['border']}; "
            f"background: {COLORS['bg_dark']}; }}"
        )

        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setSpacing(8)

        self.x_panel = TuningAxisPanel("X", 0)
        self.z_panel = TuningAxisPanel("Z", 1)

        container_layout.addWidget(self.x_panel)
        container_layout.addWidget(self.z_panel)

        # --- Spindle Encoder ---
        spindle_group = QGroupBox("Spindle Encoder")
        spindle_layout = QGridLayout(spindle_group)

        lbl_style = f"color: {COLORS['text_dim']}; font-size: 16px;"
        val_style = (
            f"background-color: {COLORS['dro_bg']}; color: {COLORS['text']}; "
            f"border: 1px solid {COLORS['border']}; border-radius: 2px; "
            f"padding: 4px; font-family: Consolas; font-size: 18px;"
        )

        lbl = QLabel("Encoder PPR:")
        lbl.setStyleSheet(lbl_style)
        lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        spindle_layout.addWidget(lbl, 0, 0)
        self.spindle_ppr = QLineEdit("4000")
        self.spindle_ppr.setStyleSheet(val_style)
        self.spindle_ppr.setFixedWidth(120)
        self.spindle_ppr.setToolTip(
            "Encoder scale (counts/rev). For 1000-line encoder with "
            "quadrature: 4000."
        )
        spindle_layout.addWidget(self.spindle_ppr, 0, 1)

        container_layout.addWidget(spindle_group)
        container_layout.addStretch()

        scroll.setWidget(container)
        layout.addWidget(scroll, stretch=3)

        # --- Live status (read-only) ---
        status_group = QGroupBox("Live Status (read-only)")
        status_layout = QGridLayout(status_group)
        status_layout.setSpacing(4)
        status_layout.setContentsMargins(6, 4, 6, 4)

        ro_style = (
            f"background-color: {COLORS['bg_mid']}; "
            f"color: {COLORS['dro_text']}; "
            f"border: 1px solid {COLORS['border']}; border-radius: 2px; "
            f"padding: 2px 4px; font-family: Consolas; font-size: 16px;"
        )

        self._status_fields = {}
        status_items = [
            ("X Following Error:", "x_ferror"),
            ("Z Following Error:", "z_ferror"),
            ("X Cmd Position:", "x_cmd_pos"),
            ("Z Cmd Position:", "z_cmd_pos"),
            ("X Encoder Pos:", "x_enc_pos"),
            ("Z Encoder Pos:", "z_enc_pos"),
            ("X PID Output:", "x_pid_out"),
            ("Z PID Output:", "z_pid_out"),
            ("Spindle RPM:", "spindle_rpm"),
        ]
        for i, (label_text, key) in enumerate(status_items):
            lbl = QLabel(label_text)
            lbl.setStyleSheet(lbl_style)
            lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            status_layout.addWidget(lbl, i // 2, (i % 2) * 2)
            field = QLineEdit("0.000000")
            field.setReadOnly(True)
            field.setStyleSheet(ro_style)
            field.setFixedWidth(120)
            field.setFixedHeight(28)
            status_layout.addWidget(field, i // 2, (i % 2) * 2 + 1)
            self._status_fields[key] = field

        layout.addWidget(status_group)

    def _connect_signals(self):
        """Wire button signals."""
        self.btn_load.clicked.connect(self._load_from_ini)
        self.btn_save.clicked.connect(self._save_to_ini)
        self.btn_apply_live.clicked.connect(self._apply_live)
        self.btn_defaults.clicked.connect(self._reset_defaults)

    # =================================================================
    # Public API — called by LatheGUI
    # =================================================================

    def set_active(self, active):
        """Start/stop polling timers based on tab visibility.

        Args:
            active: True when this tab is visible, False otherwise
        """
        self._active = active
        if active:
            self._graph_timer.start()
            self._status_timer.start()
        else:
            self._graph_timer.stop()
            self._status_timer.stop()

    def set_metric_display(self, metric):
        """Store metric display preference for live status updates."""
        self._metric_display = metric

    def update_live_status(self, data):
        """Update read-only live status fields from a dict.

        Args:
            data: Dict with keys matching self._status_fields
        """
        conv = 25.4 if self._metric_display else 1.0
        position_keys = {
            "x_ferror", "z_ferror", "x_cmd_pos", "z_cmd_pos",
            "x_enc_pos", "z_enc_pos", "x_pid_out", "z_pid_out",
        }
        for k, v in data.items():
            if k in self._status_fields:
                if isinstance(v, float):
                    if k in position_keys:
                        self._status_fields[k].setText(f"{v * conv:.6f}")
                    else:
                        self._status_fields[k].setText(f"{v:.1f}")
                else:
                    self._status_fields[k].setText(str(v))

    # =================================================================
    # Polling — graph and status data
    # =================================================================

    def _poll_graph_data(self):
        """Timer callback (50ms) — feed following error to the graph."""
        if self._has_linuxcnc and self._provider:
            # Online: read real PID error pins
            try:
                x_err = self._provider.get_pin_value(
                    TUNING_PINS['x']['pid_error']
                )
                z_err = self._provider.get_pin_value(
                    TUNING_PINS['z']['pid_error']
                )
            except (KeyError, Exception):
                x_err = 0.0
                z_err = 0.0
        elif self._sim_provider:
            # Offline: use simulated data
            self._sim_provider.tick()
            x_err = self._sim_provider.get_following_error('x')
            z_err = self._sim_provider.get_following_error('z')
        else:
            x_err = 0.0
            z_err = 0.0

        self.error_panel.add_sample(x_err, z_err)

    def _poll_status_data(self):
        """Timer callback (200ms) — update numeric status readouts."""
        if self._has_linuxcnc and self._provider:
            data = self._read_live_status()
        elif self._sim_provider:
            data = self._sim_provider.get_all_tuning_data()
        else:
            data = {}

        self.update_live_status(data)

    def _read_live_status(self):
        """Read all tuning-relevant HAL pins for the status panel."""
        data = {}
        try:
            pins = TUNING_PINS
            data['x_ferror'] = self._provider.get_pin_value(
                pins['x']['pid_error'])
            data['z_ferror'] = self._provider.get_pin_value(
                pins['z']['pid_error'])
            data['x_cmd_pos'] = self._provider.get_pin_value(
                pins['x']['pid_command'])
            data['z_cmd_pos'] = self._provider.get_pin_value(
                pins['z']['pid_command'])
            data['x_enc_pos'] = self._provider.get_pin_value(
                pins['x']['encoder_pos'])
            data['z_enc_pos'] = self._provider.get_pin_value(
                pins['z']['encoder_pos'])
            data['x_pid_out'] = self._provider.get_pin_value(
                pins['x']['pid_output'])
            data['z_pid_out'] = self._provider.get_pin_value(
                pins['z']['pid_output'])
            # Spindle RPM = velocity (rev/sec) * 60
            vel = self._provider.get_pin_value(
                pins['spindle']['velocity'])
            data['spindle_rpm'] = vel * 60.0
        except (KeyError, Exception):
            pass
        return data

    # =================================================================
    # INI Load / Save
    # =================================================================

    def _load_from_ini(self):
        """Load tuning parameters from the INI file into UI fields."""
        if not self.ini_path or not os.path.isfile(self.ini_path):
            QMessageBox.warning(
                self, "Load Error",
                f"INI file not found:\n{self.ini_path}"
            )
            return

        # Load JOINT_0 (X axis)
        j0 = load_ini_section(self.ini_path, 'JOINT_0')
        x_data = {}
        for field_key, ini_key in FIELD_TO_INI.items():
            if ini_key in j0:
                x_data[field_key] = j0[ini_key]
        self.x_panel.set_values(x_data)

        # Load JOINT_1 (Z axis)
        j1 = load_ini_section(self.ini_path, 'JOINT_1')
        z_data = {}
        for field_key, ini_key in FIELD_TO_INI.items():
            if ini_key in j1:
                z_data[field_key] = j1[ini_key]
        self.z_panel.set_values(z_data)

        # Load spindle encoder scale
        sp = load_ini_section(self.ini_path, 'SPINDLE_0')
        if 'ENCODER_SCALE' in sp:
            self.spindle_ppr.setText(sp['ENCODER_SCALE'])

        # Update FERROR limits on the graph
        try:
            ferror = float(j0.get('FERROR', '0.005'))
            min_ferror = float(j0.get('MIN_FERROR', '0.001'))
            self.error_panel.set_ferror_limits(ferror, min_ferror)
        except ValueError:
            pass

    def _save_to_ini(self):
        """Save tuning parameters from UI fields to the INI file."""
        if not self.ini_path:
            QMessageBox.warning(
                self, "Save Error", "No INI path configured."
            )
            return

        # Confirm with user
        reply = QMessageBox.question(
            self, "Save to INI",
            "Save tuning parameters to INI file?\n\n"
            "LinuxCNC must be restarted for changes to take effect.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        # Save X axis (JOINT_0)
        x_vals = self.x_panel.get_values()
        for field_key, ini_key in FIELD_TO_INI.items():
            if field_key in x_vals and x_vals[field_key]:
                save_ini_value(
                    self.ini_path, 'JOINT_0', ini_key, x_vals[field_key]
                )

        # Save Z axis (JOINT_1)
        z_vals = self.z_panel.get_values()
        for field_key, ini_key in FIELD_TO_INI.items():
            if field_key in z_vals and z_vals[field_key]:
                save_ini_value(
                    self.ini_path, 'JOINT_1', ini_key, z_vals[field_key]
                )

        # Save spindle encoder scale
        ppr = self.spindle_ppr.text().strip()
        if ppr:
            save_ini_value(
                self.ini_path, 'SPINDLE_0', 'ENCODER_SCALE', ppr
            )

        QMessageBox.information(
            self, "Saved",
            "Parameters saved to INI file.\n"
            "Restart LinuxCNC for changes to take effect."
        )

    # =================================================================
    # Apply Live — push PID gains to HAL without restart
    # =================================================================

    def _apply_live(self):
        """Push current PID values to HAL via halcmd setp.

        Only PID gains can be changed live. Stepgen parameters and
        encoder scales require a restart.
        """
        if not self._has_linuxcnc:
            return

        # Mapping from UI field keys to HAL pin suffixes
        pid_field_map = {
            'p_gain': 'Pgain',
            'i_gain': 'Igain',
            'd_gain': 'Dgain',
            'ff0': 'FF0',
            'ff1': 'FF1',
            'ff2': 'FF2',
            'deadband': 'deadband',
            'max_output': 'maxoutput',
            'max_error': 'maxerror',
        }

        errors = []

        # Apply X axis PID
        x_vals = self.x_panel.get_values()
        for field_key, hal_suffix in pid_field_map.items():
            if field_key in x_vals and x_vals[field_key]:
                pin = PID_HAL_PINS['x'][hal_suffix]
                if not hal_setp(pin, x_vals[field_key]):
                    errors.append(f"Failed: {pin} = {x_vals[field_key]}")

        # Apply Z axis PID
        z_vals = self.z_panel.get_values()
        for field_key, hal_suffix in pid_field_map.items():
            if field_key in z_vals and z_vals[field_key]:
                pin = PID_HAL_PINS['z'][hal_suffix]
                if not hal_setp(pin, z_vals[field_key]):
                    errors.append(f"Failed: {pin} = {z_vals[field_key]}")

        if errors:
            QMessageBox.warning(
                self, "Apply Live — Errors",
                "Some values could not be applied:\n\n" +
                "\n".join(errors)
            )
        else:
            QMessageBox.information(
                self, "Applied",
                "PID gains applied to HAL.\n"
                "Changes are active immediately but will be lost on restart\n"
                "unless also saved to INI."
            )

    # =================================================================
    # Reset Defaults
    # =================================================================

    def _reset_defaults(self):
        """Reset all fields to factory defaults."""
        reply = QMessageBox.question(
            self, "Reset Defaults",
            "Reset all tuning fields to default values?\n"
            "This does not affect the INI file or running HAL.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        # The TuningAxisPanel constructor sets defaults — recreating is
        # overkill, so just load from INI if available, else leave as-is
        if self.ini_path and os.path.isfile(self.ini_path):
            self._load_from_ini()
