"""Manual Control Tab — orchestrator.

Assembles the position graph, DRO, and collapsible control sections.
Handles polling, signal wiring, and event dispatch to the HAL backend.

This file is intentionally thin — UI construction is in sections.py,
the graph widget is in components/position_graph.py.
"""

import logging
from typing import Optional

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QSplitter, QScrollArea,
)

from gui.colors import COLORS, FONTS
from gui.components.position_graph import PositionGraphWidget
from gui.manual.sections import (
    build_jog_section,
    build_tool_section,
    build_touchoff_section,
    build_mdi_section,
    build_homing_section,
    build_compound_section,
)
from gui.unit_state import unit_state
from hal import get_backend, HALBackend
from hal.interface import TaskState, HomingState
from hal.constants import JOG_MODES, DEFAULT_JOG_MODE_INDEX, JOG_INCREMENTS, DEFAULT_JOG_VELOCITY
from hal.compound_logic import (
    CompoundLinearLogic, CompoundArcLogic,
    Quadrant, ArcStartType,
)

logger = logging.getLogger(__name__)


class ManualTab(QWidget):
    """Manual machine control tab with real-time position visualization.

    Layout:
        QSplitter (horizontal):
            Left: PositionGraphWidget (dominant, ~60% width)
            Right: DRO (always visible) + scrollable collapsible sections

    Signals:
        mdi_executed(str): Emitted after an MDI command is sent
    """

    mdi_executed = pyqtSignal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._backend: HALBackend = get_backend()
        self._jog_increment_idx = DEFAULT_JOG_MODE_INDEX
        self._jog_velocity = DEFAULT_JOG_VELOCITY

        # Compound slide state
        self._compound_active = False
        self._compound_mode = "linear"  # "linear" or "arc"
        self._compound_angle = 45.0
        self._compound_mpg = "x"  # "x" or "z"
        self._compound_last_counts = 0
        self._compound_first_cycle = True  # Snapshot encoder on first poll
        self._compound_x_accum = 0.0
        self._compound_z_accum = 0.0
        self._compound_x_out_total = 0  # Cumulative HAL output counts
        self._compound_z_out_total = 0
        self._linear_logic = CompoundLinearLogic()
        self._arc_logic = CompoundArcLogic()

        self._setup_ui()
        self._connect_signals()
        self._setup_polling()

        # Track which arrow keys are currently held (for velocity jog)
        self._keys_held: set = set()
        self.setFocusPolicy(Qt.StrongFocus)

        logger.info("ManualTab initialized")

    # ==================================================================
    # UI Assembly
    # ==================================================================

    def _setup_ui(self):
        """Assemble graph + controls splitter layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(0)

        splitter = QSplitter(Qt.Horizontal, self)
        layout.addWidget(splitter)

        # Left: Position Graph
        self._graph = PositionGraphWidget(self)
        self._graph.setMinimumWidth(400)
        splitter.addWidget(self._graph)

        # Right: DRO + sections
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(4, 4, 4, 4)
        right_layout.setSpacing(4)

        right_layout.addWidget(self._build_dro_widget())

        # Scrollable collapsible sections
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(2)

        # Build sections and store widget references
        jog_section, self._jog = build_jog_section()
        compound_section, self._compound = build_compound_section()
        tool_section, self._tool = build_tool_section()
        touchoff_section, self._touchoff = build_touchoff_section()
        mdi_section, self._mdi = build_mdi_section()
        homing_section, self._homing = build_homing_section()

        scroll_layout.addWidget(jog_section)
        scroll_layout.addWidget(compound_section)
        scroll_layout.addWidget(tool_section)
        scroll_layout.addWidget(touchoff_section)
        scroll_layout.addWidget(mdi_section)
        scroll_layout.addWidget(homing_section)
        scroll_layout.addStretch()

        scroll.setWidget(scroll_content)
        right_layout.addWidget(scroll, stretch=1)

        splitter.addWidget(right_panel)
        splitter.setSizes([600, 350])
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

    def _build_dro_widget(self) -> QWidget:
        """Large DRO — always visible at top of controls panel."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 8)
        layout.setSpacing(4)

        # Coordinate mode toggle
        self._coord_toggle = QPushButton("Work Coords (G54)")
        self._coord_toggle.setCheckable(True)
        self._coord_toggle.setChecked(False)
        self._coord_toggle.setFixedHeight(28)
        self._coord_toggle.setStyleSheet(
            f"QPushButton {{ background: {COLORS['bg_surface']}; "
            f"color: {COLORS['text_secondary']}; border: 1px solid {COLORS['border_normal']}; "
            f"border-radius: 3px; font-size: 9pt; }}"
            f"QPushButton:checked {{ background: {COLORS['btn_primary']}; "
            f"color: {COLORS['text_primary']}; }}"
        )
        layout.addWidget(self._coord_toggle)

        # X DRO
        x_row = QHBoxLayout()
        x_label = QLabel("X")
        x_label.setFixedWidth(28)
        x_label.setAlignment(Qt.AlignCenter)
        x_label.setStyleSheet(
            f"color: {COLORS['status_info']}; font-weight: bold; "
            f"font-size: 16pt; font-family: {FONTS['mono_family']};"
        )
        self._dro_x = QLabel("+0.0000")
        self._dro_x.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._dro_x.setMinimumHeight(44)
        self._dro_x.setStyleSheet(
            f"font-family: {FONTS['mono_family']}; font-size: 28pt; "
            f"color: {COLORS['text_primary']}; "
            f"background: {COLORS['bg_base']}; "
            f"border: 1px solid {COLORS['border_normal']}; "
            f"border-radius: 4px; padding: 4px 10px;"
        )
        x_row.addWidget(x_label)
        x_row.addWidget(self._dro_x, stretch=1)
        layout.addLayout(x_row)

        # Z DRO
        z_row = QHBoxLayout()
        z_label = QLabel("Z")
        z_label.setFixedWidth(28)
        z_label.setAlignment(Qt.AlignCenter)
        z_label.setStyleSheet(
            f"color: {COLORS['status_ok']}; font-weight: bold; "
            f"font-size: 16pt; font-family: {FONTS['mono_family']};"
        )
        self._dro_z = QLabel("+0.0000")
        self._dro_z.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._dro_z.setMinimumHeight(44)
        self._dro_z.setStyleSheet(
            f"font-family: {FONTS['mono_family']}; font-size: 28pt; "
            f"color: {COLORS['text_primary']}; "
            f"background: {COLORS['bg_base']}; "
            f"border: 1px solid {COLORS['border_normal']}; "
            f"border-radius: 4px; padding: 4px 10px;"
        )
        z_row.addWidget(z_label)
        z_row.addWidget(self._dro_z, stretch=1)
        layout.addLayout(z_row)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color: {COLORS['border_normal']};")
        layout.addWidget(sep)

        return widget

    # ==================================================================
    # Signal Wiring
    # ==================================================================

    def _connect_signals(self):
        """Wire section widgets to handlers."""
        # Jog buttons — always velocity mode (hold to move)
        self._jog["btn_x_plus"].pressed.connect(lambda: self._jog_start(0, +1.0))
        self._jog["btn_x_plus"].released.connect(lambda: self._jog_end(0))
        self._jog["btn_x_minus"].pressed.connect(lambda: self._jog_start(0, -1.0))
        self._jog["btn_x_minus"].released.connect(lambda: self._jog_end(0))
        self._jog["btn_z_plus"].pressed.connect(lambda: self._jog_start(1, +1.0))
        self._jog["btn_z_plus"].released.connect(lambda: self._jog_end(1))
        self._jog["btn_z_minus"].pressed.connect(lambda: self._jog_start(1, -1.0))
        self._jog["btn_z_minus"].released.connect(lambda: self._jog_end(1))
        self._jog["jog_vel_spin"].valueChanged.connect(self._on_jog_vel_changed)
        self._jog["jog_inc_combo"].currentIndexChanged.connect(self._on_jog_inc_changed)
        self._jog["btn_clear_trail"].clicked.connect(self._graph.clear_trail)

        # Tool
        self._tool["btn_change"].clicked.connect(self._on_tool_change)
        self._tool["tool_number_input"].returnPressed.connect(self._on_tool_change)

        # Touch-off
        self._touchoff["btn_touchoff"].clicked.connect(self._on_touchoff)

        # MDI
        self._mdi["btn_send"].clicked.connect(self._on_mdi_send)
        self._mdi["input"].returnPressed.connect(self._on_mdi_send)
        self._mdi["history"].activated.connect(
            lambda idx: self._mdi["input"].setText(self._mdi["history"].itemText(idx)))

        # Homing
        self._homing["btn_all"].clicked.connect(self._backend.home_all)
        self._homing["btn_x"].clicked.connect(lambda: self._backend.home_axis(0))
        self._homing["btn_z"].clicked.connect(lambda: self._backend.home_axis(1))

        # Coordinate toggle
        self._coord_toggle.toggled.connect(self._on_coord_toggle)

        # Compound slide
        self._compound["btn_activate"].toggled.connect(self._on_compound_toggle)
        self._compound["combo_mode"].currentIndexChanged.connect(self._on_compound_mode_changed)
        self._compound["input_angle"].editingFinished.connect(self._on_compound_angle_changed)
        self._compound["combo_quadrant"].currentIndexChanged.connect(self._on_compound_quadrant_changed)
        self._compound["combo_mpg"].currentIndexChanged.connect(
            lambda idx: setattr(self, '_compound_mpg', 'x' if idx == 0 else 'z')
        )
        self._compound["input_radius"].editingFinished.connect(self._on_compound_radius_changed)
        self._compound["btn_reset_dist"].clicked.connect(self._on_compound_reset_distance)

        # Preset angle buttons
        for label, btn in self._compound["preset_buttons"].items():
            angle_val = CompoundLinearLogic.PRESETS[label]
            btn.clicked.connect(self._make_preset_handler(angle_val))

        # Unit mode toggle — update DRO, touch-off, and jog velocity displays
        unit_state.unit_changed.connect(self._on_unit_changed)

    # ==================================================================
    # Polling
    # ==================================================================

    def _setup_polling(self):
        """Start 100ms timer to poll backend and update all displays."""
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._on_poll)
        self._poll_timer.start(100)

    def _on_poll(self):
        """Poll backend, update DRO + graph + section indicators + compound."""
        self._backend.poll()
        s = self._backend.state

        # DRO — apply unit conversion for display
        dp = unit_state.decimals
        x_display = unit_state.to_display(s.x.position)
        z_display = unit_state.to_display(s.z.position)
        self._dro_x.setText(f"{x_display:+.{dp}f}")
        self._dro_z.setText(f"{z_display:+.{dp}f}")

        # Graph
        self._graph.update_position(s.x.position, s.z.position)

        # Compound slide — process MPG pulses and check interlocks
        if self._compound_active:
            self._update_compound(s)

        # Homing
        for axis, label_key in [(s.x, "home_x_label"), (s.z, "home_z_label")]:
            lbl = self._homing[label_key]
            if axis.homed == HomingState.HOMED:
                lbl.setText(f"{label_key[5].upper()}: ✓")
                lbl.setStyleSheet(f"color: {COLORS['status_ok']}; font-size: 9pt;")
            else:
                lbl.setText(f"{label_key[5].upper()}: ✗")
                lbl.setStyleSheet(f"color: {COLORS['status_warning']}; font-size: 9pt;")

        # Tool
        t = s.tool_in_spindle
        self._tool["tool_display"].setText(f"T{t}" if t > 0 else "T0")

    # ==================================================================
    # Handlers
    # ==================================================================

    def _jog_start(self, axis: int, direction: float):
        """Start velocity jog — mirrors hardware pushbuttons."""
        self._backend.jog_continuous(axis, direction, self._jog_velocity)

    def _jog_end(self, axis: int):
        """Stop velocity jog on button release."""
        self._backend.jog_stop(axis)

    def _on_jog_vel_changed(self, value: float):
        """Update pushbutton jog velocity (mirrors analog pot / 6-pos knob).

        The spinbox displays in the current unit system (in/s or mm/s).
        Convert to inches/sec for the backend.
        """
        self._jog_velocity = unit_state.from_display(value)

    def _on_jog_inc_changed(self, index: int):
        """Update MPG mode selection — updates both GUI state and HAL mux8."""
        self._jog_increment_idx = index
        if hasattr(self._backend, 'set_mpg_scale_index'):
            self._backend.set_mpg_scale_index(index)

    def _on_tool_change(self):
        """Validate tool number input and execute tool change if valid."""
        text = self._tool["tool_number_input"].text().strip().upper()
        # Strip leading 'T' if user typed it
        if text.startswith("T"):
            text = text[1:]
        try:
            tool_num = int(text)
        except ValueError:
            self._tool["tool_number_input"].setStyleSheet(
                f"font-family: '{FONTS['mono_family']}'; font-size: 12pt;"
                f" color: {COLORS['status_error']};"
                f" background: {COLORS['bg_surface']};"
                f" border: 1px solid {COLORS['status_error']};"
                f" border-radius: 4px; padding: 2px 6px;"
            )
            return

        # Get valid tool numbers from the tools tab
        valid_tools = self._get_valid_tool_numbers()
        if tool_num not in valid_tools:
            self._tool["tool_number_input"].setStyleSheet(
                f"font-family: '{FONTS['mono_family']}'; font-size: 12pt;"
                f" color: {COLORS['status_error']};"
                f" background: {COLORS['bg_surface']};"
                f" border: 1px solid {COLORS['status_error']};"
                f" border-radius: 4px; padding: 2px 6px;"
            )
            return

        # Valid — reset style and execute
        self._tool["tool_number_input"].setStyleSheet(
            f"font-family: '{FONTS['mono_family']}'; font-size: 12pt;"
            f" color: {COLORS['text_primary']};"
            f" background: {COLORS['bg_surface']};"
            f" border: 1px solid {COLORS['border_normal']};"
            f" border-radius: 4px; padding: 2px 6px;"
        )
        self._tool["tool_number_input"].clear()
        self._backend.tool_change(tool_num)

    def _get_valid_tool_numbers(self) -> set:
        """Return set of valid tool numbers from the Tools tab."""
        main_window = self.window()
        if hasattr(main_window, 'tools_tab'):
            tools = main_window.tools_tab.get_tools()
            return {t.tool_number for t in tools}
        # Fallback: allow 1 through MAX_TOOLS
        from hal.constants import MAX_TOOLS
        return set(range(1, MAX_TOOLS + 1))

    def _on_touchoff(self):
        """Execute touch-off (G10 L20).

        The touch-off value spinbox displays in the current unit system.
        Convert to inches before sending to LinuxCNC.
        """
        axis = self._touchoff["axis"].currentIndex()
        display_value = self._touchoff["value"].value()
        value = unit_state.from_display(display_value)
        wcs = self._touchoff["wcs"].currentIndex() + 1
        self._backend.touch_off(axis, value, wcs)
        logger.info("Touch-off: axis=%d, value=%.4f (inches), WCS=%d", axis, value, wcs)

    def _on_mdi_send(self):
        """Send MDI command."""
        cmd = self._mdi["input"].text().strip()
        if not cmd:
            return
        if self._backend.mdi_command(cmd):
            self._mdi["history"].insertItem(0, cmd)
            self._mdi["input"].clear()
            self.mdi_executed.emit(cmd)

    def _on_coord_toggle(self, checked: bool):
        """Toggle work/machine coordinate display."""
        self._coord_toggle.setText(
            "Machine Coords (G53)" if checked else "Work Coords (G54)"
        )

    def _on_unit_changed(self, mode: str):
        """Handle unit mode change — update suffixes, ranges, and displays.

        Called when the global unit toggle switches between inch and metric.
        Updates:
          - Touch-off value spinbox suffix and range
          - Jog velocity spinbox suffix and range
          - DRO is updated automatically on next poll cycle
        """
        from hal.constants import MAX_JOG_VELOCITY

        # Touch-off value spinbox — update suffix and range
        touchoff_spin = self._touchoff["value"]
        if unit_state.is_metric:
            touchoff_spin.setSuffix(" mm")
            touchoff_spin.setDecimals(3)
            touchoff_spin.setRange(-10.0 * 25.4, 25.0 * 25.4)
            touchoff_spin.setSingleStep(0.025)
        else:
            touchoff_spin.setSuffix("\"")
            touchoff_spin.setDecimals(4)
            touchoff_spin.setRange(-10.0, 25.0)
            touchoff_spin.setSingleStep(0.001)

        # Jog velocity spinbox — update suffix and range
        jog_spin = self._jog["jog_vel_spin"]
        # Block signals to avoid triggering _on_jog_vel_changed during update
        jog_spin.blockSignals(True)
        current_vel_inches = self._jog_velocity  # always stored in inches/sec
        if unit_state.is_metric:
            jog_spin.setSuffix(" mm/s")
            jog_spin.setDecimals(1)
            jog_spin.setRange(0.01 * 25.4, MAX_JOG_VELOCITY * 25.4)
            jog_spin.setSingleStep(2.5)
            jog_spin.setValue(current_vel_inches * 25.4)
        else:
            jog_spin.setSuffix(" in/s")
            jog_spin.setDecimals(2)
            jog_spin.setRange(0.01, MAX_JOG_VELOCITY)
            jog_spin.setSingleStep(0.1)
            jog_spin.setValue(current_vel_inches)
        jog_spin.blockSignals(False)

    # ==================================================================
    # Compound Slide
    # ==================================================================

    def _on_compound_toggle(self, checked: bool):
        """Handle compound slide toggle button state change."""
        if checked:
            self._compound_activate()
        else:
            self._compound_deactivate()

    def _compound_activate(self):
        """Activate compound slide mode."""
        # Check interlocks
        s = self._backend.state
        if s.task_state == TaskState.ESTOP or not s.all_homed or not s.machine_on:
            # Revert button without triggering toggled signal again
            self._compound["btn_activate"].blockSignals(True)
            self._compound["btn_activate"].setChecked(False)
            self._compound["btn_activate"].blockSignals(False)
            # Flash reason on button text for 2 seconds
            reason = "E-STOP" if s.task_state == TaskState.ESTOP else \
                     "NOT HOMED" if not s.all_homed else "MACHINE OFF"
            self._compound["btn_activate"].setText(reason)
            QTimer.singleShot(2000, lambda: self._compound["btn_activate"].setText("OFF"))
            return

        self._compound_active = True
        self._compound_last_counts = 0
        self._compound_first_cycle = True  # Will snapshot on next poll
        self._compound_x_accum = 0.0
        self._compound_z_accum = 0.0
        self._compound_x_out_total = 0  # Cumulative output counts for HAL
        self._compound_z_out_total = 0
        self._linear_logic.reset()
        self._arc_logic.reset()

        # Snapshot current position for arc center computation
        current_x_r = s.x.position / 2.0  # Convert diameter to radius
        current_z = s.z.position

        if self._compound_mode == "arc":
            radius_text = self._compound["input_radius"].text()
            valid, radius = CompoundArcLogic.validate_radius(radius_text)
            if not valid:
                radius = 0.25
            quadrant = self._get_selected_quadrant()
            start_idx = self._compound["combo_start"].currentIndex()
            # Combo: index 0 = "Arc Top", index 1 = "Arc Bottom"
            start_type = ArcStartType.ARC_TOP if start_idx == 0 else ArcStartType.ARC_BOTTOM

            # The N↔S quadrant swap (user NE/NW → logic SE/SW) inverts the
            # meaning of "top" and "bottom" for north quadrants. Compensate:
            user_idx = self._compound["combo_quadrant"].currentIndex()
            user_is_north = user_idx in (0, 1)  # "NE"=0, "NW"=1
            if user_is_north:
                # Flip: user "Arc Top" (small X, top of graph) needs logic ARC_BOTTOM
                #        user "Arc Bottom" (large X, bottom of graph) needs logic ARC_TOP
                if start_type == ArcStartType.ARC_TOP:
                    start_type = ArcStartType.ARC_BOTTOM
                else:
                    start_type = ArcStartType.ARC_TOP
            self._arc_logic.activate(current_x_r, current_z, radius, quadrant, start_type)
            # Draw arc overlay on graph
            self._draw_compound_overlay()

        elif self._compound_mode == "linear":
            # Draw angle line overlay on graph
            self._draw_compound_overlay()

        # Lock mode selector while active
        self._compound["combo_mode"].setEnabled(False)
        self._compound["combo_quadrant"].setEnabled(False)
        self._compound["combo_start"].setEnabled(False)

        # Update button text
        self._compound["btn_activate"].setText("ACTIVE")
        self._compound["btn_activate"].setChecked(True)

        # Set HAL compound-enable pin (live backend only)
        if hasattr(self._backend, 'set_compound_enable'):
            self._backend.set_compound_enable(True)
            self._backend.set_compound_angle(self._compound_angle)

    def _compound_deactivate(self):
        """Deactivate compound slide mode."""
        self._compound_active = False
        self._linear_logic.reset()
        self._arc_logic.reset()
        self._compound_x_accum = 0.0
        self._compound_z_accum = 0.0
        self._compound_x_out_total = 0
        self._compound_z_out_total = 0
        self._compound["lbl_distance"].setText("0.0000\"")

        # Unlock selectors
        self._compound["combo_mode"].setEnabled(True)
        self._compound["combo_quadrant"].setEnabled(True)
        self._compound["combo_start"].setEnabled(True)

        # Update button
        self._compound["btn_activate"].blockSignals(True)
        self._compound["btn_activate"].setText("OFF")
        self._compound["btn_activate"].setChecked(False)
        self._compound["btn_activate"].blockSignals(False)

        # Clear HAL compound-enable pin (live backend only)
        if hasattr(self._backend, 'set_compound_enable'):
            self._backend.set_compound_enable(False)
            self._backend.set_compound_jog_counts(0, 0)

        # Clear graph overlay
        self._clear_compound_overlay()

    def _update_compound(self, s):
        """Process compound slide motion each poll cycle.

        Called from _on_poll() when compound mode is active.
        Reads MPG encoder counts, decomposes into X+Z motion,
        and writes cumulative jog counts to HAL output pins.

        The mux2 components in postgui.hal route these output counts
        to the joints when compound-enable is true.

        Also checks interlocks and force-deactivates if violated.

        Args:
            s: Current MachineState snapshot.
        """
        # Interlock check — force deactivate if unsafe
        if s.task_state == TaskState.ESTOP or not s.machine_on or not s.all_homed:
            self._compound_deactivate()
            logger.warning("Compound slide force-deactivated: interlock violated")
            return

        # Read MPG encoder counts from backend
        # In live mode these come from HAL pins; in mock mode they're simulated
        mpg_x_counts, mpg_z_counts = self._read_mpg_counts()

        # Select which MPG is the input source
        selected_counts = mpg_x_counts if self._compound_mpg == "x" else mpg_z_counts

        # First cycle after activation: snapshot counts, no motion
        if self._compound_first_cycle:
            self._compound_last_counts = selected_counts
            self._compound_first_cycle = False
            return

        # Compute delta
        count_delta = selected_counts - self._compound_last_counts
        self._compound_last_counts = selected_counts

        if count_delta == 0:
            return

        # Current position in radius
        current_x_r = s.x.position / 2.0
        current_z = s.z.position

        # Get jog scale (MPG increment)
        jog_scale = JOG_INCREMENTS[self._jog_increment_idx]

        # Dispatch to logic layer
        if self._compound_mode == "arc":
            x_delta, z_delta, suppressed, clamped = self._arc_logic.process_pulse(
                count_delta, jog_scale, current_x_r, current_z
            )
            if suppressed or (clamped and x_delta == 0.0 and z_delta == 0.0):
                return
            self._arc_logic.accumulate_distance(x_delta, z_delta)
            dist = self._arc_logic.cumulative_distance
        else:
            x_delta, z_delta = self._linear_logic.decompose_pulse(
                count_delta, jog_scale, abs(self._compound_angle)
            )
            # Apply axis coupling based on angle sign:
            # Positive angle: cross (X−Z+) — negate X only
            # Negative angle: same (X−Z−) — negate both
            if self._compound_angle > 0:
                x_delta = -x_delta  # X toward center, Z away from chuck
            else:
                x_delta = -x_delta  # X toward center
                z_delta = -z_delta  # Z toward chuck
            x_delta, z_delta, suppressed = self._linear_logic.check_soft_limits(
                current_x_r, current_z, x_delta, z_delta
            )
            if suppressed:
                return
            self._linear_logic.accumulate_distance(x_delta, z_delta)
            dist = self._linear_logic.cumulative_distance

        # Update distance display
        self._compound["lbl_distance"].setText(f"{dist:.4f}\"")

        # Convert distance deltas to integer jog counts via fractional accumulators
        if jog_scale > 0:
            self._compound_x_accum += x_delta / jog_scale
            self._compound_z_accum += z_delta / jog_scale

        x_counts_out = int(self._compound_x_accum)
        z_counts_out = int(self._compound_z_accum)
        self._compound_x_accum -= x_counts_out
        self._compound_z_accum -= z_counts_out

        # Accumulate total output counts and write to HAL pins
        self._compound_x_out_total += x_counts_out
        self._compound_z_out_total += z_counts_out

        if hasattr(self._backend, 'set_compound_jog_counts'):
            # HAL pin-based output (live mode with mux2 routing)
            self._backend.set_compound_jog_counts(
                self._compound_x_out_total,
                self._compound_z_out_total
            )
        else:
            # Fallback: jog_increment commands (mock mode / no HAL component)
            if x_counts_out != 0:
                direction = 1.0 if x_counts_out > 0 else -1.0
                for _ in range(abs(x_counts_out)):
                    self._backend.jog_increment(0, direction, self._jog_velocity, jog_scale)

            if z_counts_out != 0:
                direction = 1.0 if z_counts_out > 0 else -1.0
                for _ in range(abs(z_counts_out)):
                    self._backend.jog_increment(1, direction, self._jog_velocity, jog_scale)

    def _read_mpg_counts(self) -> tuple:
        """Read MPG encoder counts from the backend.

        In live mode: reads HAL pins encoder.03.count and encoder.04.count.
        In mock mode: returns simulated counts (0 unless externally driven).

        Returns:
            (mpg_x_counts, mpg_z_counts) — raw integer encoder counts.
        """
        # The mock backend doesn't simulate MPG counts directly.
        # In live mode, these would come from HAL pin reads.
        # For now, return the backend's internal MPG state if available,
        # otherwise 0 (no MPG motion in offline mode unless simulated).
        if hasattr(self._backend, '_mpg_x_counts'):
            return (self._backend._mpg_x_counts, self._backend._mpg_z_counts)
        return (0, 0)

    def _on_compound_mode_changed(self, index: int):
        """Handle mode switch between Linear and Arc."""
        if index == 0:
            self._compound_mode = "linear"
            self._compound["input_angle"].setVisible(True)
            self._compound["angle_label"].setVisible(True)
            self._compound["deg_label"].setVisible(True)
            self._compound["arc_container"].setVisible(False)
            # Show preset buttons (linear mode only)
            for btn in self._compound["preset_buttons"].values():
                btn.setVisible(True)
        else:
            self._compound_mode = "arc"
            self._compound["input_angle"].setVisible(False)
            self._compound["angle_label"].setVisible(False)
            self._compound["deg_label"].setVisible(False)
            self._compound["arc_container"].setVisible(True)
            # Hide preset buttons (not applicable to arc mode)
            for btn in self._compound["preset_buttons"].values():
                btn.setVisible(False)

    def _on_compound_angle_changed(self):
        """Validate and update compound angle.

        Accepts -90.0 to +90.0. Sign determines axis coupling:
            Positive: X−Z+ (cross coupling)
            Negative: X−Z− (same coupling)
        """
        text = self._compound["input_angle"].text().strip()
        try:
            angle = float(text)
            if -90.0 <= angle <= 90.0 and angle != 0.0:
                self._compound_angle = angle
                # Sync HAL pin if live backend
                if hasattr(self._backend, 'set_compound_angle'):
                    self._backend.set_compound_angle(angle)
                if self._compound_active:
                    self._draw_compound_overlay()
            else:
                self._compound["input_angle"].setText(f"{self._compound_angle:.1f}")
        except ValueError:
            self._compound["input_angle"].setText(f"{self._compound_angle:.1f}")

    def _on_compound_quadrant_changed(self, index: int):
        """Update quadrant graphic when selection changes.

        The graphic uses the user-facing convention (NE=top-right, SE=bottom-right)
        which matches the combo box labels directly.
        """
        # Pass the user-facing quadrant to the graphic (not the logic quadrant)
        user_quadrant = [Quadrant.NE, Quadrant.NW, Quadrant.SW, Quadrant.SE][index]
        self._compound["quadrant_graphic"].set_quadrant(user_quadrant)

    def _get_selected_quadrant(self) -> Quadrant:
        """Get the currently selected quadrant enum.

        The combo box labels use the operator's visual convention:
            NE = smaller X (toward centerline), +Z (away from headstock)
            SE = larger X (away from centerline), +Z
            NW = smaller X, -Z (toward headstock)
            SW = larger X, -Z

        The arc logic angle ranges use atan2(dx, dz) convention where
        +X is at π/2. On the inverted-Y graph, +X is at the bottom.
        So the logic's "NE" (0 to π/2) actually draws bottom-right = visual SE.

        This mapping corrects the inversion:
            User "NE" (top-right on graph) → Logic SE (3π/2 to 2π)
            User "SE" (bottom-right on graph) → Logic NE (0 to π/2)
            User "NW" (top-left on graph) → Logic SW (π to 3π/2)
            User "SW" (bottom-left on graph) → Logic NW (π/2 to π)
        """
        idx = self._compound["combo_quadrant"].currentIndex()
        # Combo items: ["NE", "NW", "SW", "SE"] at indices 0, 1, 2, 3
        # Map user-facing labels to logic quadrants (N/S swapped):
        return [Quadrant.SE, Quadrant.SW, Quadrant.NW, Quadrant.NE][idx]

    def _on_compound_radius_changed(self):
        """Validate and update arc radius input.

        Accepts any positive float. Invalid input reverts to previous value.
        """
        text = self._compound["input_radius"].text().strip()
        valid, radius = CompoundArcLogic.validate_radius(text)
        if not valid:
            self._compound["input_radius"].setText("0.250")

    def _on_compound_reset_distance(self):
        """Reset the distance counter without deactivating compound mode."""
        self._linear_logic.reset_distance()
        self._arc_logic.reset_distance()
        self._compound["lbl_distance"].setText("0.0000\"")

    def _make_preset_handler(self, angle_val: float):
        """Create a closure for preset angle button click.

        Args:
            angle_val: The preset angle value to apply.

        Returns:
            A callable that sets the angle input and updates state.
        """
        def handler():
            self._compound_angle = angle_val
            self._compound["input_angle"].setText(f"{angle_val:.1f}")
            if hasattr(self._backend, 'set_compound_angle'):
                self._backend.set_compound_angle(angle_val)
            if self._compound_active:
                self._draw_compound_overlay()
        return handler

    # ==================================================================
    # Compound Slide — Graph Overlay
    # ==================================================================

    def _draw_compound_overlay(self):
        """Draw the compound path on the position graph."""
        import pyqtgraph as pg
        from pyqtgraph.Qt import QtCore as _QtCore

        self._clear_compound_overlay()

        s = self._backend.state
        x_r = s.x.position / 2.0
        z = s.z.position

        pen = pg.mkPen(COLORS['status_info'], width=2, style=_QtCore.Qt.DashLine)

        if self._compound_mode == "linear":
            # Draw a line showing the compound angle path.
            # Angle sign determines axis coupling:
            #   Positive angle: X−Z+ (cross) — e.g. +45 = OD chamfer
            #   Negative angle: X−Z− (same)  — e.g. -45 = ID chamfer
            import math
            abs_angle_rad = math.radians(abs(self._compound_angle))
            length = 2.0

            x_component = length * math.sin(abs_angle_rad)
            z_component = length * math.cos(abs_angle_rad)

            if self._compound_angle > 0:
                # Positive: cross coupling (X−Z+)
                end_x_r = x_r - x_component
                end_z = z + z_component
                start_x_r = x_r + x_component
                start_z = z - z_component
            else:
                # Negative: same coupling (X−Z−)
                end_x_r = x_r - x_component
                end_z = z - z_component
                start_x_r = x_r + x_component
                start_z = z + z_component

            item = self._graph.plot(
                [start_z, end_z], [start_x_r, end_x_r], pen=pen
            )
            self._compound_overlay_items = [item]

        elif self._compound_mode == "arc":
            points = self._arc_logic.get_arc_points(40)
            if points:
                z_coords = [p[1] for p in points]
                x_coords = [p[0] for p in points]
                item = self._graph.plot(z_coords, x_coords, pen=pen)
                self._compound_overlay_items = [item]

    def _clear_compound_overlay(self):
        """Remove compound path overlay from graph."""
        if hasattr(self, '_compound_overlay_items'):
            for item in self._compound_overlay_items:
                self._graph.removeItem(item)
            self._compound_overlay_items = []

    # ==================================================================
    # Keyboard Jog (Arrow Keys)
    # ==================================================================

    def keyPressEvent(self, event):
        """Handle arrow key press — start velocity jog.

        Arrow key mapping (operator POV, graph has invertY):
            Up    = X- (decrease diameter, tool moves away from operator)
            Down  = X+ (increase diameter, tool moves toward operator)
            Left  = Z- (toward headstock)
            Right = Z+ (away from headstock)

        Only fires on initial press (not auto-repeat).
        """
        key = event.key()
        if event.isAutoRepeat():
            return

        if key == Qt.Key_Up and Qt.Key_Up not in self._keys_held:
            self._keys_held.add(Qt.Key_Up)
            self._jog_start(0, -1.0)  # X-
        elif key == Qt.Key_Down and Qt.Key_Down not in self._keys_held:
            self._keys_held.add(Qt.Key_Down)
            self._jog_start(0, +1.0)  # X+
        elif key == Qt.Key_Left and Qt.Key_Left not in self._keys_held:
            self._keys_held.add(Qt.Key_Left)
            self._jog_start(1, -1.0)  # Z-
        elif key == Qt.Key_Right and Qt.Key_Right not in self._keys_held:
            self._keys_held.add(Qt.Key_Right)
            self._jog_start(1, +1.0)  # Z+
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        """Handle arrow key release — stop velocity jog."""
        key = event.key()
        if event.isAutoRepeat():
            return

        if key == Qt.Key_Up:
            self._keys_held.discard(Qt.Key_Up)
            self._jog_end(0)
        elif key == Qt.Key_Down:
            self._keys_held.discard(Qt.Key_Down)
            self._jog_end(0)
        elif key == Qt.Key_Left:
            self._keys_held.discard(Qt.Key_Left)
            self._jog_end(1)
        elif key == Qt.Key_Right:
            self._keys_held.discard(Qt.Key_Right)
            self._jog_end(1)
        else:
            super().keyReleaseEvent(event)
