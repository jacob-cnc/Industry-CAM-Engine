"""
Tuning Tab — Stepper, Encoder, and PID Tuning
===============================================
Provides per-axis tuning panels (stepper drive, linear encoder, PID gains,
following error limits) and a spindle encoder section. Includes live status
readouts and load/save to INI functionality.
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QGroupBox, QLineEdit, QScrollArea,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from theme import COLORS, mono_font, ui_font


# ---------------------------------------------------------------------------
# TuningAxisPanel — single axis tuning controls
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
            ("Step Scale:", "step_scale", "8000", "Steps per inch (microsteps × leadscrew TPI)"),
            ("Max Velocity:", "max_vel", "3.0", "Max axis velocity (in/sec)"),
            ("Max Accel:", "max_accel", "15.0", "Max axis acceleration (in/sec²)"),
            ("Stepgen Max Vel:", "sg_maxvel", "3.6", "Stepgen headroom — ~120% of max velocity"),
            ("Stepgen Max Accel:", "sg_maxaccel", "18.75", "Stepgen headroom — ~125% of max accel"),
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
            field.setToolTip("Nanoseconds — check your stepper driver datasheet")
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
            ("Encoder Scale:", "enc_scale", "50800", "Counts per inch (4× line count for quadrature)"),
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
            ("P Gain:", "p_gain", "1000.0", "Proportional — corrects position error. Start low, increase until responsive without oscillation."),
            ("I Gain:", "i_gain", "0.0", "Integral — eliminates steady-state error. Usually 0 for steppers. Add small value only if persistent offset."),
            ("D Gain:", "d_gain", "0.0", "Derivative — dampens oscillation. Rarely needed for steppers."),
            ("FF0:", "ff0", "0.0", "Feedforward 0 — position. Usually 0."),
            ("FF1:", "ff1", "1.0", "Feedforward 1 — velocity. Set to 1.0 for steppers. Does most of the work."),
            ("FF2:", "ff2", "0.0", "Feedforward 2 — acceleration. Usually 0."),
            ("Deadband:", "deadband", "0.0001", "Ignore errors smaller than this (inches). Prevents chasing encoder noise."),
            ("Max Output:", "max_output", "3.6", "Clamp PID output to this velocity (in/sec). Match stepgen max vel."),
            ("Max Error:", "max_error", "0.0005", "Max error the PID will act on (inches)."),
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
            ("FERROR:", "ferror", "0.010", "Max following error at full speed (inches). Machine faults if exceeded."),
            ("MIN_FERROR:", "min_ferror", "0.002", "Max following error at low speed (inches). Tighter limit when moving slowly."),
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
# TuningTab — main tuning interface with both axis panels + spindle
# ---------------------------------------------------------------------------
class TuningTab(QWidget):
    """Stepper, encoder, and PID tuning interface for both axes + spindle encoder."""

    def __init__(self, ini_path=None, parent=None):
        super().__init__(parent)
        self.ini_path = ini_path

        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # --- Info banner ---
        info = QLabel(
            "Adjust stepper drive, linear encoder, and PID parameters for each axis. "
            "Hover over any field for a description. Save writes values to the INI file. "
            "LinuxCNC must be restarted for changes to take effect."
        )
        info.setWordWrap(True)
        info.setStyleSheet(
            f"color: {COLORS['text_dim']}; font-size: 16px; "
            f"padding: 6px; background-color: {COLORS['bg_mid']}; "
            f"border: 1px solid {COLORS['border']}; border-radius: 4px;"
        )
        layout.addWidget(info)

        # --- Action buttons ---
        btn_bar = QHBoxLayout()
        self.btn_load = QPushButton("Load from INI")
        self.btn_save = QPushButton("Save to INI")
        self.btn_save.setStyleSheet(
            f"QPushButton {{ background-color: {COLORS['accent_green']}; color: {COLORS['bg_dark']}; "
            f"font-weight: 700; border: none; border-radius: 8px; }}"
            f"QPushButton:hover {{ background-color: {COLORS['accent_green_lt']}; }}"
        )
        self.btn_defaults = QPushButton("Reset Defaults")
        btn_bar.addWidget(self.btn_load)
        btn_bar.addWidget(self.btn_save)
        btn_bar.addWidget(self.btn_defaults)
        btn_bar.addStretch()
        layout.addLayout(btn_bar)

        # --- Scrollable axis panels ---
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            f"QScrollArea {{ border: 1px solid {COLORS['border']}; background: {COLORS['bg_dark']}; }}"
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
        self.spindle_ppr = QLineEdit("2048")
        self.spindle_ppr.setStyleSheet(val_style)
        self.spindle_ppr.setFixedWidth(120)
        self.spindle_ppr.setToolTip(
            "Pulses per revolution of the spindle encoder.\n"
            "This is the ENCODER_SCALE in [SPINDLE_0].\n"
            "For a 1024-line encoder with quadrature, enter 4096."
        )
        spindle_layout.addWidget(self.spindle_ppr, 0, 1)

        container_layout.addWidget(spindle_group)
        container_layout.addStretch()

        scroll.setWidget(container)
        layout.addWidget(scroll, stretch=3)

        # --- Live status (read-only, populated when connected) ---
        status_group = QGroupBox("Live Status (read-only)")
        status_layout = QGridLayout(status_group)
        status_layout.setSpacing(4)
        status_layout.setContentsMargins(6, 4, 6, 4)

        ro_style = (
            f"background-color: {COLORS['bg_mid']}; color: {COLORS['dro_text']}; "
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
            ("Spindle RPM:", "spindle_rpm"),
        ]
        for i, (label_text, key) in enumerate(status_items):
            lbl = QLabel(label_text)
            lbl.setStyleSheet(lbl_style)
            lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            status_layout.addWidget(lbl, i // 2, (i % 2) * 2)
            field = QLineEdit("0.0000")
            field.setReadOnly(True)
            field.setStyleSheet(ro_style)
            field.setFixedWidth(120)
            field.setFixedHeight(28)
            status_layout.addWidget(field, i // 2, (i % 2) * 2 + 1)
            self._status_fields[key] = field

        layout.addWidget(status_group)

    def update_live_status(self, data):
        """Update read-only live status fields from a dict."""
        metric = getattr(self, '_metric_display', False)
        conv = 25.4 if metric else 1.0
        # Keys that represent position/distance values (not RPM)
        position_keys = {"x_ferror", "z_ferror", "x_cmd_pos", "z_cmd_pos", "x_enc_pos", "z_enc_pos"}
        for k, v in data.items():
            if k in self._status_fields:
                if isinstance(v, float):
                    if k in position_keys:
                        self._status_fields[k].setText(f"{v * conv:.6f}")
                    else:
                        self._status_fields[k].setText(f"{v:.6f}")
                else:
                    self._status_fields[k].setText(str(v))

    def set_metric_display(self, metric: bool):
        """Store metric display preference for live status updates."""
        self._metric_display = metric
