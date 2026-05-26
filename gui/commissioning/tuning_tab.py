"""Tuning Tab — PID, Following Error Graph, Stepgen & Encoder Parameters.

The core tuning workflow:
    1. Load from INI → populate fields with current machine config
    2. Watch the following error graph — see real-time deviation
    3. Adjust PID gains (P, FF1, deadband are the main ones for steppers)
    4. Apply Live → push to HAL immediately (no restart)
    5. Save to INI → persist for next startup

Architecture:
    - Per-axis parameter panels (stepper, encoder, PID, FERROR)
    - Real-time following error strip chart with freeze/zoom
    - Live status readouts (positions, errors, RPM)
    - Offline mode with SimulatedTuningProvider
    - Timer management via set_active()

Key machine facts:
    - stepgen.00 = Z axis, stepgen.01 = X axis (REVERSED from joint #)
    - PID pin names use capitals: pid.x.Pgain, not pid.x.pgain
    - X is RADIUS internally — do NOT apply diameter conversion here
    - FF1 = 1.0 for velocity-mode stepgens (the critical feedforward)
"""

import os
import logging
from typing import Dict, Optional

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QGroupBox, QLineEdit, QScrollArea,
    QMessageBox, QFrame,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont

from gui.colors import COLORS, FONTS
from gui.commissioning.tuning_graph import FollowingErrorPanel
from gui.commissioning.tuning_provider import SimulatedTuningProvider
from gui.commissioning.ini_io import load_ini_section, save_ini_value
from gui.commissioning.pin_providers import get_pin_provider, PinProvider
from hal.interface import HALBackend
from hal.constants import (
    PID_P, PID_I, PID_D, PID_FF0, PID_FF1, PID_FF2,
    PID_DEADBAND, PID_MAX_OUTPUT, PID_MAX_ERROR,
    FERROR, MIN_FERROR,
)

logger = logging.getLogger(__name__)


# =============================================================================
# HAL Pin Mappings
# =============================================================================

# Pins to read for the following error graph and status panel
TUNING_PINS = {
    'x': {
        'pid_error': 'pid.x.error',
        'pid_command': 'pid.x.command',
        'pid_feedback': 'pid.x.feedback',
        'pid_output': 'pid.x.output',
        'encoder_pos': 'hm2_7i96s.0.encoder.01.position',
        'stepgen_fb': 'hm2_7i96s.0.stepgen.01.position-fb',
    },
    'z': {
        'pid_error': 'pid.z.error',
        'pid_command': 'pid.z.command',
        'pid_feedback': 'pid.z.feedback',
        'pid_output': 'pid.z.output',
        'encoder_pos': 'hm2_7i96s.0.encoder.00.position',
        'stepgen_fb': 'hm2_7i96s.0.stepgen.00.position-fb',
    },
    'spindle': {
        'velocity': 'hm2_7i96s.0.encoder.04.velocity',
    },
}

# PID pins for live adjustment (halcmd setp)
PID_HAL_PINS = {
    'x': {
        'Pgain': 'pid.x.Pgain', 'Igain': 'pid.x.Igain',
        'Dgain': 'pid.x.Dgain', 'FF0': 'pid.x.FF0',
        'FF1': 'pid.x.FF1', 'FF2': 'pid.x.FF2',
        'deadband': 'pid.x.deadband', 'maxoutput': 'pid.x.maxoutput',
        'maxerror': 'pid.x.maxerror',
    },
    'z': {
        'Pgain': 'pid.z.Pgain', 'Igain': 'pid.z.Igain',
        'Dgain': 'pid.z.Dgain', 'FF0': 'pid.z.FF0',
        'FF1': 'pid.z.FF1', 'FF2': 'pid.z.FF2',
        'deadband': 'pid.z.deadband', 'maxoutput': 'pid.z.maxoutput',
        'maxerror': 'pid.z.maxerror',
    },
}

# UI field key → INI key mapping
FIELD_TO_INI = {
    'step_scale': 'STEP_SCALE',
    'max_vel': 'MAX_VELOCITY',
    'max_accel': 'MAX_ACCELERATION',
    'sg_maxvel': 'STEPGEN_MAXVEL',
    'sg_maxaccel': 'STEPGEN_MAXACCEL',
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


# =============================================================================
# Axis Parameter Panel
# =============================================================================

class AxisTuningPanel(QGroupBox):
    """Tuning controls for a single axis (stepper + encoder + PID)."""

    def __init__(self, axis_name: str, joint_num: int, parent=None):
        super().__init__(f"{axis_name} Axis — Joint {joint_num}", parent)
        self.axis_name = axis_name
        self.joint_num = joint_num
        self._fields: Dict[str, QLineEdit] = {}

        self._build_fields()

    def _build_fields(self):
        layout = QGridLayout(self)
        layout.setSpacing(4)

        lbl_style = f"color: {COLORS['text_secondary']};"
        val_style = (
            f"background-color: {COLORS['bg_panel']};"
            f"color: {COLORS['text_primary']};"
            f"border: 1px solid {COLORS['border_normal']};"
            f"border-radius: 2px; padding: 4px;"
            f"font-family: {FONTS['mono_family']};"
        )
        section_style = (
            f"color: {COLORS['status_info']}; font-weight: bold;"
            f"border: none; background: transparent;"
        )

        row = 0

        # --- Stepper ---
        row = self._add_section(layout, row, "Stepper Drive", section_style)
        stepper_fields = [
            ("Step Scale:", "step_scale", "8000", "Steps/inch"),
            ("Max Velocity:", "max_vel", "2.0", "in/sec"),
            ("Max Accel:", "max_accel", "10.0", "in/sec²"),
            ("Stepgen Max Vel:", "sg_maxvel", "2.4", "~120% of max vel"),
            ("Stepgen Max Accel:", "sg_maxaccel", "12.5", "~125% of max accel"),
        ]
        for label, key, default, tip in stepper_fields:
            row = self._add_field(layout, row, label, key, default, tip,
                                  lbl_style, val_style)

        # --- Encoder ---
        row = self._add_section(layout, row, "Linear Encoder", section_style)
        row = self._add_field(layout, row, "Encoder Scale:", "enc_scale",
                              "5080", "Counts/inch (4× line count)",
                              lbl_style, val_style)

        # --- PID ---
        row = self._add_section(layout, row, "PID Tuning", section_style)
        pid_fields = [
            ("P Gain:", "p_gain", str(PID_P),
             "Proportional — start low, increase until responsive"),
            ("I Gain:", "i_gain", str(PID_I),
             "Integral — usually 0 for steppers"),
            ("D Gain:", "d_gain", str(PID_D),
             "Derivative — rarely needed for steppers"),
            ("FF0:", "ff0", str(PID_FF0), "Position feedforward — usually 0"),
            ("FF1:", "ff1", str(PID_FF1),
             "Velocity feedforward — 1.0 for velocity-mode stepgen"),
            ("FF2:", "ff2", str(PID_FF2), "Acceleration feedforward — usually 0"),
            ("Deadband:", "deadband", str(PID_DEADBAND),
             "Ignore errors smaller than this (inches)"),
            ("Max Output:", "max_output", str(PID_MAX_OUTPUT),
             "Clamp PID output velocity (in/sec)"),
            ("Max Error:", "max_error", str(PID_MAX_ERROR),
             "Max error PID will act on (inches)"),
        ]
        for label, key, default, tip in pid_fields:
            row = self._add_field(layout, row, label, key, default, tip,
                                  lbl_style, val_style)

        # --- FERROR ---
        row = self._add_section(layout, row, "Following Error Limits", section_style)
        ferr_fields = [
            ("FERROR:", "ferror", str(FERROR),
             "Max error at full speed — faults if exceeded"),
            ("MIN_FERROR:", "min_ferror", str(MIN_FERROR),
             "Max error at low speed"),
        ]
        for label, key, default, tip in ferr_fields:
            row = self._add_field(layout, row, label, key, default, tip,
                                  lbl_style, val_style)

    def _add_section(self, layout, row, text, style):
        lbl = QLabel(text)
        lbl.setStyleSheet(style)
        layout.addWidget(lbl, row, 0, 1, 4)
        return row + 1

    def _add_field(self, layout, row, label, key, default, tooltip,
                   lbl_style, val_style):
        lbl = QLabel(label)
        lbl.setStyleSheet(lbl_style)
        lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(lbl, row, 0)

        field = QLineEdit(default)
        field.setStyleSheet(val_style)
        field.setToolTip(tooltip)
        field.setFixedWidth(120)
        field.setFixedHeight(28)
        layout.addWidget(field, row, 1)
        self._fields[key] = field
        return row + 1

    def get_values(self) -> Dict[str, str]:
        return {k: v.text() for k, v in self._fields.items()}

    def set_values(self, data: Dict[str, str]):
        for k, v in data.items():
            if k in self._fields:
                self._fields[k].setText(str(v))


# =============================================================================
# Main Tuning Tab
# =============================================================================

class TuningTab(QWidget):
    """Stepper, encoder, and PID tuning with live data and INI I/O."""

    def __init__(self, backend: HALBackend, ini_path: str = "", parent=None):
        super().__init__(parent)
        self._backend = backend
        self._ini_path = ini_path
        self._active = False

        # Pin provider for reading HAL values
        self._pin_provider: PinProvider = get_pin_provider()

        # Determine if we have REAL LinuxCNC (not just mock backend)
        # The pin provider will be OfflinePinProvider on Windows regardless
        # of what the backend reports.
        from gui.commissioning.pin_providers import OfflinePinProvider
        self._is_offline = isinstance(self._pin_provider, OfflinePinProvider)

        # Offline simulation
        self._sim_provider: Optional[SimulatedTuningProvider] = None
        if self._is_offline:
            self._sim_provider = SimulatedTuningProvider()

        self._build_ui()
        self._connect_signals()

        # Timers
        self._graph_timer = QTimer(self)
        self._graph_timer.timeout.connect(self._poll_graph)
        self._graph_timer.setInterval(50)  # 20 FPS for smooth graph

        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._poll_status)
        self._status_timer.setInterval(200)  # 5 Hz for numeric readouts

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # --- Offline banner ---
        if self._is_offline:
            banner = QLabel("OFFLINE — Simulated Data")
            banner.setAlignment(Qt.AlignCenter)
            banner.setStyleSheet(
                f"background-color: {COLORS['status_warning']};"
                f"color: {COLORS['bg_base']};"
                f"padding: 4px; border-radius: 4px; font-weight: bold;"
            )
            banner.setFixedHeight(26)
            layout.addWidget(banner)

        # --- Action buttons ---
        btn_bar = QHBoxLayout()

        self._btn_load = QPushButton("Load from INI")
        self._btn_load.setToolTip("Read current values from industry-cam.ini")

        self._btn_save = QPushButton("Save to INI")
        self._btn_save.setToolTip("Write to INI (requires restart)")
        self._btn_save.setStyleSheet(
            f"QPushButton {{ background-color: {COLORS['status_ok']};"
            f"  color: {COLORS['bg_base']}; }}"
        )

        self._btn_apply = QPushButton("Apply Live")
        self._btn_apply.setToolTip("Push PID gains to HAL now (no restart)")
        self._btn_apply.setEnabled(not self._is_offline)

        self._btn_defaults = QPushButton("Reset Defaults")

        btn_bar.addWidget(self._btn_load)
        btn_bar.addWidget(self._btn_save)
        btn_bar.addWidget(self._btn_apply)
        btn_bar.addWidget(self._btn_defaults)
        btn_bar.addStretch()
        layout.addLayout(btn_bar)

        # --- Following Error Graph ---
        self._error_panel = FollowingErrorPanel()
        self._error_panel.setMinimumHeight(150)
        layout.addWidget(self._error_panel, stretch=2)

        # --- Scrollable axis panels ---
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            f"QScrollArea {{ border: 1px solid {COLORS['border_normal']}; }}"
        )

        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setSpacing(8)

        self._x_panel = AxisTuningPanel("X", 0)
        self._z_panel = AxisTuningPanel("Z", 1)
        container_layout.addWidget(self._x_panel)
        container_layout.addWidget(self._z_panel)
        container_layout.addStretch()

        scroll.setWidget(container)
        layout.addWidget(scroll, stretch=3)

        # --- Live status readouts ---
        status_group = QGroupBox("Live Status")
        status_layout = QGridLayout(status_group)
        status_layout.setSpacing(4)

        ro_style = (
            f"background-color: {COLORS['bg_panel']};"
            f"color: {COLORS['text_primary']};"
            f"border: 1px solid {COLORS['border_normal']};"
            f"border-radius: 2px; padding: 2px 4px;"
            f"font-family: {FONTS['mono_family']};"
        )

        self._status_fields: Dict[str, QLineEdit] = {}
        items = [
            ("X Error:", "x_err"), ("Z Error:", "z_err"),
            ("X Cmd:", "x_cmd"), ("Z Cmd:", "z_cmd"),
            ("X Enc:", "x_enc"), ("Z Enc:", "z_enc"),
            ("X PID Out:", "x_pid"), ("Z PID Out:", "z_pid"),
            ("Spindle RPM:", "rpm"),
        ]
        for i, (label_text, key) in enumerate(items):
            lbl = QLabel(label_text)
            lbl.setStyleSheet(f"color: {COLORS['text_secondary']};")
            lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            status_layout.addWidget(lbl, i // 3, (i % 3) * 2)

            field = QLineEdit("0.000000")
            field.setReadOnly(True)
            field.setStyleSheet(ro_style)
            field.setFixedWidth(100)
            field.setFixedHeight(24)
            status_layout.addWidget(field, i // 3, (i % 3) * 2 + 1)
            self._status_fields[key] = field

        layout.addWidget(status_group)

    def _connect_signals(self):
        self._btn_load.clicked.connect(self._load_from_ini)
        self._btn_save.clicked.connect(self._save_to_ini)
        self._btn_apply.clicked.connect(self._apply_live)
        self._btn_defaults.clicked.connect(self._reset_defaults)

    # =================================================================
    # Public API
    # =================================================================

    def set_active(self, active: bool):
        """Start/stop polling timers."""
        self._active = active
        if active:
            self._graph_timer.start()
            self._status_timer.start()
        else:
            self._graph_timer.stop()
            self._status_timer.stop()

    # =================================================================
    # Polling
    # =================================================================

    def _poll_graph(self):
        """50ms timer — feed following error to graph."""
        if not self._is_offline:
            try:
                x_err = self._pin_provider.get_pin_value(
                    TUNING_PINS['x']['pid_error'])
                z_err = self._pin_provider.get_pin_value(
                    TUNING_PINS['z']['pid_error'])
            except (KeyError, Exception) as e:
                # pid.x.error / pid.z.error not found — fall back to
                # the backend's following_error from linuxcnc.stat
                state = self._backend.state
                x_err = state.x.following_error
                z_err = state.z.following_error
                if not hasattr(self, '_pin_fallback_warned'):
                    self._pin_fallback_warned = True
                    logger.warning(
                        "Tuning graph: pid.error pins not readable (%s), "
                        "falling back to stat.following_error", e)
        elif self._sim_provider:
            self._sim_provider.tick()
            x_err = self._sim_provider.get_following_error('x')
            z_err = self._sim_provider.get_following_error('z')
        else:
            x_err, z_err = 0.0, 0.0

        self._error_panel.add_sample(x_err, z_err)

    def _poll_status(self):
        """200ms timer — update numeric readouts."""
        if not self._is_offline:
            data = self._read_live_status()
            # If pin reads failed, fall back to backend state for error fields
            if not data:
                state = self._backend.state
                data = {
                    'x_err': state.x.following_error,
                    'z_err': state.z.following_error,
                    'x_cmd': state.x.commanded,
                    'z_cmd': state.z.commanded,
                    'x_enc': state.x.position / 2.0,  # diameter → radius
                    'z_enc': state.z.position,
                    'x_pid': 0.0,
                    'z_pid': 0.0,
                    'rpm': state.spindle.speed,
                }
        elif self._sim_provider:
            snap = self._sim_provider.get_snapshot()
            data = {
                'x_err': snap.x_following_error,
                'z_err': snap.z_following_error,
                'x_cmd': snap.x_commanded,
                'z_cmd': snap.z_commanded,
                'x_enc': snap.x_encoder,
                'z_enc': snap.z_encoder,
                'x_pid': snap.x_pid_output,
                'z_pid': snap.z_pid_output,
                'rpm': snap.spindle_rpm,
            }
        else:
            data = {}

        for key, value in data.items():
            if key in self._status_fields:
                if key == 'rpm':
                    self._status_fields[key].setText(f"{value:.0f}")
                else:
                    self._status_fields[key].setText(f"{value:.6f}")

    def _read_live_status(self) -> dict:
        """Read HAL pins for status panel."""
        data = {}
        try:
            pins = TUNING_PINS
            data['x_err'] = self._pin_provider.get_pin_value(pins['x']['pid_error'])
            data['z_err'] = self._pin_provider.get_pin_value(pins['z']['pid_error'])
            data['x_cmd'] = self._pin_provider.get_pin_value(pins['x']['pid_command'])
            data['z_cmd'] = self._pin_provider.get_pin_value(pins['z']['pid_command'])
            data['x_enc'] = self._pin_provider.get_pin_value(pins['x']['encoder_pos'])
            data['z_enc'] = self._pin_provider.get_pin_value(pins['z']['encoder_pos'])
            data['x_pid'] = self._pin_provider.get_pin_value(pins['x']['pid_output'])
            data['z_pid'] = self._pin_provider.get_pin_value(pins['z']['pid_output'])
            vel = self._pin_provider.get_pin_value(pins['spindle']['velocity'])
            data['rpm'] = vel * 60.0
        except (KeyError, Exception) as e:
            logger.debug("Live status read error: %s", e)
        return data

    # =================================================================
    # INI Load / Save
    # =================================================================

    def _load_from_ini(self):
        if not self._ini_path or not os.path.isfile(self._ini_path):
            QMessageBox.warning(self, "Load Error",
                                f"INI file not found:\n{self._ini_path}")
            return

        # X axis = JOINT_0
        j0 = load_ini_section(self._ini_path, 'JOINT_0')
        x_data = {fk: j0[ik] for fk, ik in FIELD_TO_INI.items() if ik in j0}
        self._x_panel.set_values(x_data)

        # Z axis = JOINT_1
        j1 = load_ini_section(self._ini_path, 'JOINT_1')
        z_data = {fk: j1[ik] for fk, ik in FIELD_TO_INI.items() if ik in j1}
        self._z_panel.set_values(z_data)

        # Update FERROR limits on graph
        try:
            ferror = float(j0.get('FERROR', str(FERROR)))
            min_ferror = float(j0.get('MIN_FERROR', str(MIN_FERROR)))
            self._error_panel.set_ferror_limits(ferror, min_ferror)
        except ValueError:
            pass

        logger.info("Loaded tuning params from INI")

    def _save_to_ini(self):
        if not self._ini_path:
            QMessageBox.warning(self, "Save Error", "No INI path configured.")
            return

        reply = QMessageBox.question(
            self, "Save to INI",
            "Save tuning parameters to INI?\n\n"
            "LinuxCNC must be restarted for changes to take effect.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        # Save X (JOINT_0)
        x_vals = self._x_panel.get_values()
        for fk, ik in FIELD_TO_INI.items():
            if fk in x_vals and x_vals[fk]:
                save_ini_value(self._ini_path, 'JOINT_0', ik, x_vals[fk])

        # Save Z (JOINT_1)
        z_vals = self._z_panel.get_values()
        for fk, ik in FIELD_TO_INI.items():
            if fk in z_vals and z_vals[fk]:
                save_ini_value(self._ini_path, 'JOINT_1', ik, z_vals[fk])

        QMessageBox.information(self, "Saved",
                                "Parameters saved. Restart LinuxCNC to apply.")

    # =================================================================
    # Apply Live
    # =================================================================

    def _apply_live(self):
        """Push PID gains to HAL via halcmd setp (no restart needed)."""
        if self._is_offline:
            return

        pid_field_map = {
            'p_gain': 'Pgain', 'i_gain': 'Igain', 'd_gain': 'Dgain',
            'ff0': 'FF0', 'ff1': 'FF1', 'ff2': 'FF2',
            'deadband': 'deadband', 'max_output': 'maxoutput',
            'max_error': 'maxerror',
        }

        errors = []

        # Validate before applying
        x_vals = self._x_panel.get_values()
        z_vals = self._z_panel.get_values()

        # Validate all PID fields are valid numbers and non-negative where required
        non_negative_fields = {'p_gain', 'i_gain', 'd_gain', 'ff0', 'ff1', 'ff2',
                               'deadband', 'max_output', 'max_error'}
        for axis_name, vals in [('X', x_vals), ('Z', z_vals)]:
            for fk in pid_field_map:
                raw = vals.get(fk, '').strip()
                if not raw:
                    continue
                try:
                    v = float(raw)
                    if fk in non_negative_fields and v < 0:
                        errors.append(f"{axis_name} {fk}: cannot be negative")
                except ValueError:
                    errors.append(f"{axis_name} {fk}: not a valid number")

        if errors:
            QMessageBox.warning(self, "Validation Error",
                                "\n".join(errors))
            return

        # Apply X axis PID
        apply_errors = []
        for fk, hal_suffix in pid_field_map.items():
            raw = x_vals.get(fk, '').strip()
            if raw:
                pin = PID_HAL_PINS['x'][hal_suffix]
                if not self._pin_provider.set_pin_value(pin, raw):
                    apply_errors.append(f"Failed: {pin}")

        # Apply Z axis PID
        for fk, hal_suffix in pid_field_map.items():
            raw = z_vals.get(fk, '').strip()
            if raw:
                pin = PID_HAL_PINS['z'][hal_suffix]
                if not self._pin_provider.set_pin_value(pin, raw):
                    apply_errors.append(f"Failed: {pin}")

        if apply_errors:
            QMessageBox.warning(self, "Apply Errors",
                                "Some values failed:\n" + "\n".join(apply_errors))
        else:
            QMessageBox.information(self, "Applied",
                                    "PID gains applied to HAL.\n"
                                    "Active immediately — save to INI to persist.")

    def _reset_defaults(self):
        reply = QMessageBox.question(
            self, "Reset Defaults",
            "Reset all fields to defaults?\n"
            "Does not affect INI or running HAL.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes and self._ini_path:
            self._load_from_ini()
