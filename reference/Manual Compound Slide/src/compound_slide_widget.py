"""Compound Slide Widget — Compound Jog controls for the sidebar.

Provides the operator interface for compound slide mode:
- Activation toggle button
- Mode selector (Linear / Arc)
- Angle input (0-90°) for Linear mode
- Arc parameters (radius, quadrant, start type) for Arc mode
- MPG handwheel selector (X/Z)
- Cumulative distance display

This is a thin UI wrapper around CompoundSlideLogic and ArcJogLogic.
"""

from PyQt5.QtWidgets import (
    QGroupBox, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QFont

from theme import COLORS, mono_font, ui_font
from compound_slide_logic import CompoundSlideLogic
from arc_jog_logic import ArcJogLogic, Quadrant, StartType
from quadrant_graphic import QuadrantGraphic


class CompoundSlideWidget(QGroupBox):
    """Compound slide controls for the sidebar panel.

    Provides angle-based jog control using a single MPG handwheel
    to drive coordinated X and Z axis motion along a user-defined angle,
    or arc-based jog control for circular arc traversal.
    """

    # Emitted when compound mode is toggled (True = activated)
    compound_activated = pyqtSignal(bool)
    # Emitted when a pulse is suppressed due to soft limit proximity
    limit_warning = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__("Compound Jog", parent)

        self._active = False
        self._angle = 45.0
        self._mpg_selection = "x"  # "x" or "z"
        self._last_counts = 0
        self._x_accum = 0.0  # Fractional jog count accumulator for X
        self._z_accum = 0.0  # Fractional jog count accumulator for Z

        # Arc mode state (Task 5.1)
        self._mode = "linear"  # "linear" or "arc"
        self._arc_radius = 0.25
        self._quadrant = Quadrant.BOTTOM_RIGHT
        self._start_type = StartType.POLE
        self._arc_logic = ArcJogLogic(
            x_min=-0.01, x_max=4.25,
            z_min=-0.01, z_max=23.5
        )

        # Current position tracking for arc activation (Task 6.1)
        self._current_x = 0.0
        self._current_z = 0.0

        # Interlock state — updated by the GUI each periodic cycle.
        # All conditions must be "safe" for activation to be allowed.
        self._interlocks = {
            "estop": False,           # True = E-Stop is active (unsafe)
            "homed": True,            # True = axes are homed (safe)
            "manual_mode": True,      # True = in MANUAL mode (safe)
            "program_idle": True,     # True = interpreter idle (safe)
            "machine_enabled": True,  # True = machine power on (safe)
        }

        # Pure logic instance with default soft limits from INI
        self._logic = CompoundSlideLogic(
            x_min=-0.01, x_max=4.25,
            z_min=-0.01, z_max=23.5
        )

        self._build_ui()

    def _build_ui(self):
        """Build compact vertical layout for sidebar placement.

        Layout:
          - Row 1: Activation toggle button
          - Row 2: Mode selector (Linear / Arc)
          - Row 3: Angle label + QLineEdit (with ° suffix) [Linear mode]
          - Row 3 alt: Arc parameters [Arc mode, hidden by default]
          - Row 4: MPG label + QComboBox (X MPG / Z MPG)
          - Row 5: Distance display label
          - Stretch at bottom to keep fields compact at top
        """
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 8, 6, 6)
        layout.setSpacing(16)  # Linear mode default; Arc mode uses 12

        row_h = 22

        # --- Activation toggle button ---
        self.btn_activate = QPushButton("OFF")
        self.btn_activate.setFont(ui_font(10, QFont.Bold))
        self.btn_activate.setFixedHeight(row_h)
        self.btn_activate.setCheckable(True)
        self.btn_activate.setToolTip("Toggle compound slide mode")
        self.btn_activate.clicked.connect(self.toggle_active)
        self._update_button_style()
        layout.addWidget(self.btn_activate)

        # --- Mode selector (Task 5.2) ---
        mode_row = QHBoxLayout()
        mode_row.setSpacing(4)

        lbl_mode = QLabel("Mode:")
        lbl_mode.setFont(ui_font(11))
        lbl_mode.setStyleSheet(f"color: {COLORS['text_secondary']}; background: transparent;")
        mode_row.addWidget(lbl_mode)

        self.combo_mode = QComboBox()
        self.combo_mode.addItems(["Linear", "Arc"])
        self.combo_mode.setCurrentIndex(0)
        self.combo_mode.setFixedHeight(row_h)
        self.combo_mode.setFont(ui_font(11))
        self.combo_mode.setToolTip("Select jog mode: Linear (angle) or Arc (radius)")
        self.combo_mode.currentIndexChanged.connect(self._on_mode_changed)
        mode_row.addWidget(self.combo_mode, stretch=1)

        layout.addLayout(mode_row)

        # --- Angle input row (Linear mode) ---
        self.angle_row_layout = QHBoxLayout()
        self.angle_row_layout.setSpacing(4)

        self.lbl_angle = QLabel("Angle:")
        self.lbl_angle.setFont(ui_font(11))
        self.lbl_angle.setStyleSheet(f"color: {COLORS['text_secondary']}; background: transparent;")
        self.angle_row_layout.addWidget(self.lbl_angle)

        self.input_angle = QLineEdit("45.0")
        self.input_angle.setFont(mono_font(12))
        self.input_angle.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.input_angle.setFixedHeight(row_h)
        self.input_angle.setToolTip("Compound angle (0-90°)")
        self.input_angle.editingFinished.connect(self._on_angle_changed)
        self.angle_row_layout.addWidget(self.input_angle, stretch=1)

        self.lbl_deg = QLabel("°")
        self.lbl_deg.setFont(mono_font(12))
        self.lbl_deg.setStyleSheet(f"color: {COLORS['text_dim']}; background: transparent;")
        self.angle_row_layout.addWidget(self.lbl_deg)

        layout.addLayout(self.angle_row_layout)

        # --- Arc parameter UI elements (hidden by default) ---
        # Use a horizontal layout: graphic on left, selectors on right
        self.arc_params_layout = QHBoxLayout()
        self.arc_params_layout.setSpacing(6)

        # Left side: quadrant graphic (60x60 to save space)
        self.quadrant_graphic = QuadrantGraphic(self)
        self.quadrant_graphic.setFixedSize(60, 60)
        self.arc_params_layout.addWidget(self.quadrant_graphic, alignment=Qt.AlignTop)

        # Right side: stacked selectors
        arc_selectors = QVBoxLayout()
        arc_selectors.setSpacing(3)

        # Radius input row
        radius_row = QHBoxLayout()
        radius_row.setSpacing(3)
        self.lbl_radius = QLabel("R:")
        self.lbl_radius.setFont(ui_font(10))
        self.lbl_radius.setStyleSheet(f"color: {COLORS['text_secondary']}; background: transparent;")
        radius_row.addWidget(self.lbl_radius)
        self.input_radius = QLineEdit("0.250")
        self.input_radius.setFont(mono_font(11))
        self.input_radius.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.input_radius.setFixedHeight(26)
        self.input_radius.setToolTip("Arc radius (inches, must be > 0)")
        self.input_radius.editingFinished.connect(self._on_radius_changed)
        radius_row.addWidget(self.input_radius, stretch=1)
        self.lbl_radius_unit = QLabel("\"")
        self.lbl_radius_unit.setFont(mono_font(11))
        self.lbl_radius_unit.setStyleSheet(f"color: {COLORS['text_dim']}; background: transparent;")
        radius_row.addWidget(self.lbl_radius_unit)
        arc_selectors.addLayout(radius_row)

        # Quadrant selector
        self.combo_quadrant = QComboBox()
        self.combo_quadrant.addItems(["NE", "NW", "SW", "SE"])
        self.combo_quadrant.setCurrentIndex(3)
        self.combo_quadrant.setFixedHeight(26)
        self.combo_quadrant.setFont(ui_font(10))
        self.combo_quadrant.setToolTip("Select which 90° quadrant arc to traverse")
        self.combo_quadrant.currentIndexChanged.connect(self._on_quadrant_changed)
        arc_selectors.addWidget(self.combo_quadrant)

        # Start type selector
        self.combo_start_type = QComboBox()
        self.combo_start_type.addItems(["Arc Top", "Arc Bottom"])
        self.combo_start_type.setCurrentIndex(0)
        self.combo_start_type.setFixedHeight(26)
        self.combo_start_type.setFont(ui_font(10))
        self.combo_start_type.setToolTip("Tool start position: Arc Top (tangent horizontal) or Arc Bottom (tangent vertical)")
        self.combo_start_type.currentIndexChanged.connect(self._on_start_type_changed)
        arc_selectors.addWidget(self.combo_start_type)

        self.arc_params_layout.addLayout(arc_selectors, stretch=1)
        layout.addLayout(self.arc_params_layout)

        # Store references for visibility toggling (no separate label widgets needed)
        self.lbl_quadrant = None  # not used as separate label anymore
        self.lbl_start_type = None  # not used as separate label anymore

        # Hide arc widgets by default (Linear mode is default)
        self._set_arc_widgets_visible(False)

        # --- MPG selector row ---
        mpg_row = QHBoxLayout()
        mpg_row.setSpacing(4)

        lbl_mpg = QLabel("MPG:")
        lbl_mpg.setFont(ui_font(11))
        lbl_mpg.setStyleSheet(f"color: {COLORS['text_secondary']}; background: transparent;")
        mpg_row.addWidget(lbl_mpg)

        self.combo_mpg = QComboBox()
        self.combo_mpg.addItems(["X MPG", "Z MPG"])
        self.combo_mpg.setCurrentIndex(0)  # Default: X MPG
        self.combo_mpg.setFixedHeight(row_h)
        self.combo_mpg.setFont(ui_font(11))
        self.combo_mpg.setToolTip("Select which MPG handwheel controls compound motion")
        self.combo_mpg.currentIndexChanged.connect(self._on_mpg_changed)
        mpg_row.addWidget(self.combo_mpg, stretch=1)

        layout.addLayout(mpg_row)

        # --- Cumulative distance display ---
        layout.addSpacing(15)
        dist_row = QHBoxLayout()
        dist_row.setSpacing(4)

        lbl_dist_label = QLabel("Dist:")
        lbl_dist_label.setFont(ui_font(11))
        lbl_dist_label.setStyleSheet(f"color: {COLORS['text_secondary']}; background: transparent;")
        dist_row.addWidget(lbl_dist_label)

        self.lbl_distance = QLabel("0.0000\"")
        self.lbl_distance.setFont(mono_font(12, QFont.Bold))
        self.lbl_distance.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.lbl_distance.setStyleSheet(
            f"color: {COLORS['dro_text']}; background: {COLORS['dro_bg']}; "
            f"border: 1px solid {COLORS['border']}; border-radius: 4px; "
            f"padding: 2px 6px;"
        )
        self.lbl_distance.setFixedHeight(row_h)
        self.lbl_distance.setToolTip("Cumulative distance along compound angle")
        dist_row.addWidget(self.lbl_distance, stretch=1)

        layout.addLayout(dist_row)

        # Push all fields to the top — dead space at bottom
        layout.addStretch(1)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def is_active(self):
        """Return whether compound slide mode is currently active."""
        return self._active

    def set_interlock_state(self, estop=None, homed=None, manual_mode=None,
                            program_idle=None, machine_enabled=None):
        """Update interlock state from the GUI's periodic cycle.

        Call this each cycle with current machine state. The widget uses
        these values to gate activation and trigger force-deactivation.

        Args:
            estop: True if E-Stop is active (unsafe)
            homed: True if all required axes are homed (safe)
            manual_mode: True if machine is in MANUAL mode (safe)
            program_idle: True if interpreter is idle (safe)
            machine_enabled: True if machine power is on (safe)
        """
        if estop is not None:
            self._interlocks["estop"] = estop
        if homed is not None:
            self._interlocks["homed"] = homed
        if manual_mode is not None:
            self._interlocks["manual_mode"] = manual_mode
        if program_idle is not None:
            self._interlocks["program_idle"] = program_idle
        if machine_enabled is not None:
            self._interlocks["machine_enabled"] = machine_enabled

    def check_interlocks(self):
        """Check if all interlocks allow activation.

        Returns:
            (ok, reason) — ok is True if activation is allowed,
            reason is a human-readable string if not.
        """
        if self._interlocks["estop"]:
            return (False, "E-Stop active")
        if not self._interlocks["homed"]:
            return (False, "Axes not homed")
        if not self._interlocks["manual_mode"]:
            return (False, "Not in MANUAL mode")
        if not self._interlocks["program_idle"]:
            return (False, "Program running")
        if not self._interlocks["machine_enabled"]:
            return (False, "Machine disabled")
        return (True, "")

    def toggle_active(self):
        """Toggle compound slide mode on/off.

        Checks interlocks before activation. On deactivation, resets
        cumulative distance and restores button to OFF state.
        """
        if self._active:
            # Deactivating — always allowed
            self._deactivate()
        else:
            # Activating — check interlocks first
            ok, reason = self.check_interlocks()
            if not ok:
                # Cannot activate — ensure button stays unchecked
                self.btn_activate.setChecked(False)
                return
            self._activate()

    def _activate(self):
        """Internal activation — set state, update UI, emit signal."""
        self._active = True
        self._logic.reset()
        self._last_counts = 0
        self._x_accum = 0.0
        self._z_accum = 0.0

        # Arc mode activation (Task 6.1)
        if self._mode == "arc":
            self._arc_logic.activate(
                self._current_x, self._current_z,
                self._arc_radius, self._quadrant, self._start_type
            )

        # Lock mode and parameter selectors (Task 5.6)
        self.combo_mode.setEnabled(False)
        self.combo_quadrant.setEnabled(False)
        self.combo_start_type.setEnabled(False)
        # Note: input_radius remains editable while active

        self.btn_activate.setChecked(True)
        self._update_button_style()
        self.compound_activated.emit(True)

    def _deactivate(self):
        """Internal deactivation — reset state, update UI, emit signal."""
        self._active = False
        self._logic.reset()
        self._arc_logic.reset()  # Task 6.3: reset arc logic on deactivation
        self._last_counts = 0
        self._x_accum = 0.0
        self._z_accum = 0.0
        self.lbl_distance.setText("0.0000\"")

        # Unlock mode and parameter selectors (Task 5.6)
        self.combo_mode.setEnabled(True)
        self.combo_quadrant.setEnabled(True)
        self.combo_start_type.setEnabled(True)

        self.btn_activate.setChecked(False)
        self._update_button_style()
        self.compound_activated.emit(False)

    def force_deactivate(self, reason=""):
        """Force deactivation due to interlock trigger.

        Called by the GUI when an interlock condition is detected during
        the periodic update cycle (E-Stop, mode change, machine disable).

        Args:
            reason: Human-readable reason for deactivation (for status bar).
        """
        if not self._active:
            return
        self._deactivate()
        # Emit a warning so the GUI can display the reason in the status bar
        if reason:
            self.limit_warning.emit(f"Compound slide deactivated: {reason}")

    def update_compound(self, current_x, current_z, mpg_x_counts,
                        mpg_z_counts, jog_scale):
        """Process MPG counts during periodic update cycle.

        Called from LatheGUI.periodic_update() every 100ms when active.

        Args:
            current_x: Current X position (radius)
            current_z: Current Z position
            mpg_x_counts: Raw X MPG encoder count
            mpg_z_counts: Raw Z MPG encoder count
            jog_scale: Current jog increment (inches per pulse)

        Returns:
            (x_jog_counts, z_jog_counts) integer jog counts for HAL output,
            or (0, 0) if inactive or no motion needed.
        """
        # Store current position for arc activation (Task 6.1/6.2)
        self._current_x = current_x
        self._current_z = current_z

        if not self._active:
            return (0, 0)

        # Select encoder counts based on MPG selection
        if self._mpg_selection == "x":
            selected_counts = mpg_x_counts
        else:
            selected_counts = mpg_z_counts

        # Compute delta since last cycle
        count_delta = selected_counts - self._last_counts
        self._last_counts = selected_counts

        # No motion needed if no encoder change
        if count_delta == 0:
            return (0, 0)

        if self._mode == "arc":
            # Arc mode logic (Task 6.2)
            x_delta, z_delta, suppressed, clamped = self._arc_logic.process_pulse(
                count_delta, jog_scale, current_x, current_z
            )

            # Handle clamped case: if both deltas are 0, no motion
            if clamped and x_delta == 0.0 and z_delta == 0.0:
                return (0, 0)

            if suppressed:
                self.limit_warning.emit(
                    "Compound: soft limit reached — pulse suppressed"
                )
                return (0, 0)

            # Accumulate distance via arc_logic
            self._arc_logic.accumulate_distance(x_delta, z_delta)
            self.lbl_distance.setText(
                f"{self._arc_logic.cumulative_distance:.4f}\""
            )
        else:
            # Linear mode — existing logic unchanged
            # Decompose pulse into X and Z distance components
            x_delta, z_delta = self._logic.decompose_pulse(
                count_delta, jog_scale, self._angle
            )

            # Check soft limits — suppress entire pulse if either axis exceeds
            x_delta, z_delta, suppressed = self._logic.check_soft_limits(
                current_x, current_z, x_delta, z_delta
            )

            if suppressed:
                self.limit_warning.emit(
                    "Compound: soft limit reached — pulse suppressed"
                )
                return (0, 0)

            # Accumulate distance for display
            self._logic.accumulate_distance(x_delta, z_delta)
            self.lbl_distance.setText(
                f"{self._logic.cumulative_distance:.4f}\""
            )

        # Convert distance back to integer jog counts with fractional
        # accumulation to avoid losing sub-count motion over time.
        if jog_scale > 0:
            self._x_accum += x_delta / jog_scale
            self._z_accum += z_delta / jog_scale
        x_out = int(self._x_accum)
        z_out = int(self._z_accum)
        self._x_accum -= x_out
        self._z_accum -= z_out

        return (x_out, z_out)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _set_arc_widgets_visible(self, visible):
        """Show or hide all arc-specific UI widgets.

        Args:
            visible: True to show arc widgets, False to hide them.
        """
        self.lbl_radius.setVisible(visible)
        self.input_radius.setVisible(visible)
        self.lbl_radius_unit.setVisible(visible)
        self.combo_quadrant.setVisible(visible)
        self.quadrant_graphic.setVisible(visible)
        self.combo_start_type.setVisible(visible)

    def _set_angle_widgets_visible(self, visible):
        """Show or hide the angle input row widgets.

        Args:
            visible: True to show angle widgets, False to hide them.
        """
        self.lbl_angle.setVisible(visible)
        self.input_angle.setVisible(visible)
        self.lbl_deg.setVisible(visible)

    def _on_mode_changed(self, index):
        """Handle mode selector change (Task 5.4).

        Args:
            index: 0 = Linear, 1 = Arc
        """
        if index == 0:
            self._mode = "linear"
            self._set_angle_widgets_visible(True)
            self._set_arc_widgets_visible(False)
            self.layout().setSpacing(16)
        else:
            self._mode = "arc"
            self._set_angle_widgets_visible(False)
            self._set_arc_widgets_visible(True)
            self.layout().setSpacing(12)

    def _on_radius_changed(self):
        """Handle radius input editing finished (Task 5.5).

        Validates input using ArcJogLogic.validate_radius().
        If valid, updates self._arc_radius with the parsed value.
        If invalid, reverts the QLineEdit text to the previous valid value
        and briefly flashes the border red (~500ms).
        """
        text = self.input_radius.text().strip()
        is_valid, parsed_value = ArcJogLogic.validate_radius(text)

        if is_valid:
            self._arc_radius = parsed_value
        else:
            # Revert to previous valid value
            self.input_radius.setText(f"{self._arc_radius:.3f}")
            # Flash border red to indicate invalid input
            self.input_radius.setStyleSheet(
                f"border: 2px solid {COLORS['accent']};"
            )
            QTimer.singleShot(500, self._restore_radius_style)

    def _restore_radius_style(self):
        """Restore the radius input to its default style after error flash."""
        self.input_radius.setStyleSheet("")

    def _on_quadrant_changed(self, index):
        """Handle quadrant selector change (Task 5.5).

        Args:
            index: 0=NE, 1=NW, 2=SW, 3=SE
        """
        quadrant_map = [
            Quadrant.TOP_RIGHT,
            Quadrant.TOP_LEFT,
            Quadrant.BOTTOM_LEFT,
            Quadrant.BOTTOM_RIGHT,
        ]
        self._quadrant = quadrant_map[index]
        self.quadrant_graphic.set_quadrant(self._quadrant)

    def _on_start_type_changed(self, index):
        """Handle start type selector change (Task 5.5).

        Args:
            index: 0 = Arc Top, 1 = Arc Bottom
        """
        self._start_type = StartType.POLE if index == 0 else StartType.MIDPOINT

    def _update_button_style(self):
        """Update activation button appearance based on active state."""
        if self._active:
            self.btn_activate.setText("ACTIVE")
            self.btn_activate.setStyleSheet(
                f"QPushButton {{"
                f"  background-color: {COLORS['accent_green']};"
                f"  color: #ffffff;"
                f"  border: 1px solid {COLORS['accent_green_dk']};"
                f"  border-radius: 6px;"
                f"  font-weight: bold;"
                f"}}"
            )
        else:
            self.btn_activate.setText("OFF")
            self.btn_activate.setStyleSheet("")  # Use default theme style

    def get_angle(self):
        """Return the current validated compound angle in degrees.

        Returns:
            float: The current angle value (0.0 to 90.0).
        """
        return self._angle

    def _on_angle_changed(self):
        """Handle angle input editing finished.

        Validates input using CompoundSlideLogic.validate_angle().
        If valid, updates self._angle with the parsed value.
        If invalid, reverts the QLineEdit text to the previous valid value
        and briefly flashes the border red (~500ms).
        """
        text = self.input_angle.text().strip()
        is_valid, parsed_value = CompoundSlideLogic.validate_angle(text)

        if is_valid:
            self._angle = parsed_value
        else:
            # Revert to previous valid value
            self.input_angle.setText(f"{self._angle:.1f}")
            # Flash border red to indicate invalid input
            self.input_angle.setStyleSheet(
                f"border: 2px solid {COLORS['accent']};"
            )
            QTimer.singleShot(500, self._restore_angle_style)

    def _restore_angle_style(self):
        """Restore the angle input to its default style after error flash."""
        self.input_angle.setStyleSheet("")

    def _on_mpg_changed(self, index):
        """Handle MPG selector change.

        Args:
            index: 0 = X MPG, 1 = Z MPG
        """
        self._mpg_selection = "x" if index == 0 else "z"
