"""Collapsible section builders for the Manual Control tab.

Each function builds one CollapsibleSection and returns it along with
references to the widgets that need signal wiring or polling updates.

Separated from the tab orchestrator for:
  - Clean auditing (each section is self-contained)
  - Easy editing (change one section without touching others)
  - Future extraction (sections could become standalone widgets)
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
    QLabel, QPushButton, QComboBox, QLineEdit,
    QFrame, QSpinBox, QDoubleSpinBox,
)

from gui.colors import COLORS, FONTS
from gui.components.collapsible_section import CollapsibleSection
from hal.constants import (
    JOG_INCREMENTS, DEFAULT_JOG_INCREMENT_INDEX,
    DEFAULT_JOG_VELOCITY, MAX_JOG_VELOCITY,
    MAX_TOOLS,
)


# ======================================================================
# Jog Controls Section
# ======================================================================

def build_jog_section() -> tuple:
    """Build the Jog Controls collapsible section.

    Hardware architecture (both always active, no mode selection):
      Pushbuttons (TB3 P6-P9): Velocity jog, speed from analog pot.
      MPG handwheels (7i85S TB2/TB3): Increment jog, step from rotary switch.

    On-screen buttons mirror the pushbuttons (velocity, hold-to-jog).
    The increment and speed displays reflect hardware knob positions
    and allow software override when needed.

    Returns:
        (section, widgets) where widgets is a dict of named widget references.
    """
    section = CollapsibleSection("Jog Controls", expanded=False)

    # --- On-screen jog buttons (velocity mode, mirrors hardware pushbuttons) ---
    btn_header = QLabel("Pushbutton Jog (hold to move)")
    btn_header.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 8pt;")
    section.add_widget(btn_header)

    grid = QGridLayout()
    grid.setSpacing(4)

    btn_style = (
        f"QPushButton {{ "
        f"  background: {COLORS['bg_surface']}; "
        f"  color: {COLORS['text_primary']}; "
        f"  border: 1px solid {COLORS['border_normal']}; "
        f"  border-radius: 4px; "
        f"  font-size: 11pt; font-weight: bold; "
        f"  min-width: 52px; min-height: 40px; "
        f"}} "
        f"QPushButton:pressed {{ background: {COLORS['btn_primary']}; }}"
    )

    btn_x_plus = QPushButton("X+")
    btn_x_plus.setStyleSheet(btn_style)
    btn_x_plus.setAutoRepeat(False)
    btn_x_minus = QPushButton("X−")
    btn_x_minus.setStyleSheet(btn_style)
    btn_x_minus.setAutoRepeat(False)
    btn_z_plus = QPushButton("Z+")
    btn_z_plus.setStyleSheet(btn_style)
    btn_z_plus.setAutoRepeat(False)
    btn_z_minus = QPushButton("Z−")
    btn_z_minus.setStyleSheet(btn_style)
    btn_z_minus.setAutoRepeat(False)

    grid.addWidget(btn_x_minus, 0, 1)
    grid.addWidget(btn_z_minus, 1, 0)
    grid.addWidget(btn_z_plus, 1, 2)
    grid.addWidget(btn_x_plus, 2, 1)
    section.add_layout(grid)

    # --- Pushbutton speed (mirrors analog pot / future 6-pos knob) ---
    speed_row = QHBoxLayout()
    speed_label = QLabel("Speed:")
    speed_label.setFixedWidth(44)
    speed_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 9pt;")
    jog_vel_spin = QDoubleSpinBox()
    jog_vel_spin.setRange(0.01, MAX_JOG_VELOCITY)
    jog_vel_spin.setValue(DEFAULT_JOG_VELOCITY)
    jog_vel_spin.setSingleStep(0.1)
    jog_vel_spin.setSuffix(" in/s")
    jog_vel_spin.setDecimals(2)
    jog_vel_spin.setToolTip(
        "Pushbutton jog velocity.\n"
        "Mirrors analog pot (analogin2). Will track 6-pos knob when wired."
    )
    speed_row.addWidget(speed_label)
    speed_row.addWidget(jog_vel_spin, stretch=1)
    section.add_layout(speed_row)

    # --- MPG increment (mirrors rotary switch / future 6-pos knob) ---
    sep = QFrame()
    sep.setFrameShape(QFrame.HLine)
    sep.setStyleSheet(f"color: {COLORS['border_normal']};")
    section.add_widget(sep)

    mpg_header = QLabel("MPG Increment (per detent)")
    mpg_header.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 8pt;")
    section.add_widget(mpg_header)

    inc_row = QHBoxLayout()
    inc_label = QLabel("Step:")
    inc_label.setFixedWidth(44)
    inc_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 9pt;")
    jog_inc_combo = QComboBox()
    for inc in JOG_INCREMENTS:
        jog_inc_combo.addItem(f"{inc:.4f}\"")
    jog_inc_combo.setCurrentIndex(DEFAULT_JOG_INCREMENT_INDEX)
    jog_inc_combo.setToolTip(
        "MPG jog increment per encoder detent.\n"
        "Mirrors rotary switch (mux4 sel0/sel1). Will track 6-pos knob when wired.\n"
        "x1=0.0001\" | x10=0.001\" | x100=0.01\" | x1000=0.1\""
    )
    inc_row.addWidget(inc_label)
    inc_row.addWidget(jog_inc_combo, stretch=1)
    section.add_layout(inc_row)

    # --- Clear trail ---
    btn_clear_trail = QPushButton("Clear Trail")
    btn_clear_trail.setFixedHeight(26)
    section.add_widget(btn_clear_trail)

    widgets = {
        "btn_x_plus": btn_x_plus,
        "btn_x_minus": btn_x_minus,
        "btn_z_plus": btn_z_plus,
        "btn_z_minus": btn_z_minus,
        "jog_vel_spin": jog_vel_spin,
        "jog_inc_combo": jog_inc_combo,
        "btn_clear_trail": btn_clear_trail,
    }
    return section, widgets


# ======================================================================
# Spindle Section
# ======================================================================

def build_spindle_section() -> tuple:
    """Build the Spindle collapsible section.

    Manual spindle — no VFD, no speed control from software.
    Just displays live RPM from the spindle encoder (encoder.02).

    Returns:
        (section, widgets) where widgets is a dict of named widget references.
    """
    section = CollapsibleSection("Spindle", expanded=False)

    # RPM display (read-only, from encoder)
    rpm_row = QHBoxLayout()
    rpm_label = QLabel("RPM:")
    rpm_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
    spindle_rpm_display = QLabel("0")
    spindle_rpm_display.setAlignment(Qt.AlignRight)
    spindle_rpm_display.setStyleSheet(
        f"font-family: {FONTS['mono_family']}; font-size: 16pt; "
        f"color: {COLORS['text_primary']}; "
        f"background: {COLORS['bg_base']}; "
        f"border: 1px solid {COLORS['border_normal']}; "
        f"padding: 2px 6px; border-radius: 3px;"
    )
    rpm_row.addWidget(rpm_label)
    rpm_row.addWidget(spindle_rpm_display, stretch=1)
    section.add_layout(rpm_row)

    # Direction indicator
    dir_label = QLabel("● STOPPED")
    dir_label.setAlignment(Qt.AlignCenter)
    dir_label.setStyleSheet(f"color: {COLORS['text_disabled']}; font-size: 9pt;")
    section.add_widget(dir_label)

    widgets = {
        "rpm_display": spindle_rpm_display,
        "dir_label": dir_label,
    }
    return section, widgets


# ======================================================================
# Tool Section
# ======================================================================

def build_tool_section() -> tuple:
    """Build the Tool collapsible section.

    Returns:
        (section, widgets) where widgets is a dict of named widget references.
    """
    section = CollapsibleSection("Tool", expanded=False)

    tool_row = QHBoxLayout()
    tool_row.addWidget(QLabel("Active:"))
    tool_display = QLabel("T0")
    tool_display.setStyleSheet(
        f"font-family: {FONTS['mono_family']}; font-size: 14pt; "
        f"color: {COLORS['text_primary']}; font-weight: bold;"
    )
    tool_row.addWidget(tool_display)
    tool_row.addStretch()
    section.add_layout(tool_row)

    change_row = QHBoxLayout()
    tool_number_spin = QSpinBox()
    tool_number_spin.setRange(1, MAX_TOOLS)
    tool_number_spin.setValue(1)
    tool_number_spin.setPrefix("T")
    btn_change = QPushButton("Change (M6)")
    change_row.addWidget(tool_number_spin)
    change_row.addWidget(btn_change)
    section.add_layout(change_row)

    widgets = {
        "tool_display": tool_display,
        "tool_number_spin": tool_number_spin,
        "btn_change": btn_change,
    }
    return section, widgets


# ======================================================================
# Touch-Off Section
# ======================================================================

def build_touchoff_section() -> tuple:
    """Build the Touch-Off collapsible section.

    Returns:
        (section, widgets) where widgets is a dict of named widget references.
    """
    section = CollapsibleSection("Touch-Off (G10 L20)", expanded=False)

    form = QFormLayout()
    form.setSpacing(4)

    touchoff_axis = QComboBox()
    touchoff_axis.addItems(["X (diameter)", "Z"])
    form.addRow("Axis:", touchoff_axis)

    touchoff_value = QDoubleSpinBox()
    touchoff_value.setRange(-10.0, 25.0)
    touchoff_value.setValue(0.0)
    touchoff_value.setDecimals(4)
    touchoff_value.setSingleStep(0.001)
    touchoff_value.setSuffix("\"")
    form.addRow("Value:", touchoff_value)

    touchoff_wcs = QComboBox()
    touchoff_wcs.addItems(["G54", "G55", "G56", "G57", "G58", "G59"])
    form.addRow("WCS:", touchoff_wcs)

    section.add_layout(form)

    btn_touchoff = QPushButton("Set Offset")
    btn_touchoff.setStyleSheet(
        f"background: {COLORS['btn_generate']}; color: {COLORS['text_primary']}; "
        f"font-weight: bold; border-radius: 3px;"
    )
    section.add_widget(btn_touchoff)

    widgets = {
        "axis": touchoff_axis,
        "value": touchoff_value,
        "wcs": touchoff_wcs,
        "btn_touchoff": btn_touchoff,
    }
    return section, widgets


# ======================================================================
# MDI Section
# ======================================================================

def build_mdi_section() -> tuple:
    """Build the MDI Command collapsible section.

    Returns:
        (section, widgets) where widgets is a dict of named widget references.
    """
    section = CollapsibleSection("MDI Command", expanded=False)

    input_row = QHBoxLayout()
    mdi_input = QLineEdit()
    mdi_input.setPlaceholderText("e.g. G0 X1.0 Z0.5")
    mdi_input.setStyleSheet(
        f"font-family: {FONTS['mono_family']}; font-size: 10pt; "
        f"background: {COLORS['bg_base']}; "
        f"color: {COLORS['text_primary']}; "
        f"border: 1px solid {COLORS['border_normal']}; "
        f"padding: 3px; border-radius: 3px;"
    )
    btn_send = QPushButton("Send")
    btn_send.setFixedWidth(50)
    btn_send.setStyleSheet(
        f"background: {COLORS['btn_primary']}; color: {COLORS['text_primary']};"
    )
    input_row.addWidget(mdi_input, stretch=1)
    input_row.addWidget(btn_send)
    section.add_layout(input_row)

    mdi_history = QComboBox()
    mdi_history.setPlaceholderText("History")
    mdi_history.setMaxCount(10)
    section.add_widget(mdi_history)

    widgets = {
        "input": mdi_input,
        "btn_send": btn_send,
        "history": mdi_history,
    }
    return section, widgets


# ======================================================================
# Machine State Section
# ======================================================================

def build_state_section() -> tuple:
    """Build the Machine State collapsible section.

    Returns:
        (section, widgets) where widgets is a dict of named widget references.
    """
    section = CollapsibleSection("Machine State", expanded=False)

    state_label = QLabel("● E-STOP")
    state_label.setAlignment(Qt.AlignCenter)
    state_label.setStyleSheet(
        f"font-size: 13pt; font-weight: bold; color: {COLORS['status_error']};"
    )
    section.add_widget(state_label)

    mode_label = QLabel("Mode: MANUAL")
    mode_label.setAlignment(Qt.AlignCenter)
    mode_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 9pt;")
    section.add_widget(mode_label)

    btn_row = QHBoxLayout()
    btn_estop = QPushButton("Reset")
    btn_estop.setStyleSheet(
        f"QPushButton {{ background: {COLORS['status_warning']}; color: {COLORS['text_primary']}; "
        f"font-weight: bold; font-size: 9pt; border-radius: 3px; }}"
        f"QPushButton:hover {{ background: #e6a817; }}"
        f"QPushButton:pressed {{ background: #c48a10; }}"
    )
    btn_on = QPushButton("ON")
    btn_on.setStyleSheet(
        f"QPushButton {{ background: {COLORS['status_ok']}; color: {COLORS['text_primary']}; "
        f"font-size: 9pt; border-radius: 3px; }}"
        f"QPushButton:hover {{ background: #2ea84a; }}"
        f"QPushButton:pressed {{ background: #1e8a38; }}"
    )
    btn_off = QPushButton("OFF")
    btn_off.setStyleSheet(
        f"QPushButton {{ font-size: 9pt; border-radius: 3px; }}"
        f"QPushButton:hover {{ background: {COLORS['bg_surface']}; }}"
        f"QPushButton:pressed {{ background: {COLORS['border_normal']}; }}"
    )
    btn_row.addWidget(btn_estop)
    btn_row.addWidget(btn_on)
    btn_row.addWidget(btn_off)
    section.add_layout(btn_row)

    error_label = QLabel("")
    error_label.setWordWrap(True)
    error_label.setStyleSheet(f"color: {COLORS['status_error']}; font-size: 8pt;")
    section.add_widget(error_label)

    widgets = {
        "state_label": state_label,
        "mode_label": mode_label,
        "btn_estop": btn_estop,
        "btn_on": btn_on,
        "btn_off": btn_off,
        "error_label": error_label,
    }
    return section, widgets


# ======================================================================
# Homing Section
# ======================================================================

def build_homing_section() -> tuple:
    """Build the Homing collapsible section.

    Returns:
        (section, widgets) where widgets is a dict of named widget references.
    """
    section = CollapsibleSection("Homing", expanded=False)

    status_row = QHBoxLayout()
    home_x_label = QLabel("X: ✗")
    home_x_label.setStyleSheet(f"color: {COLORS['status_warning']}; font-size: 9pt;")
    home_z_label = QLabel("Z: ✗")
    home_z_label.setStyleSheet(f"color: {COLORS['status_warning']}; font-size: 9pt;")
    status_row.addWidget(home_x_label)
    status_row.addWidget(home_z_label)
    section.add_layout(status_row)

    btn_row = QHBoxLayout()
    btn_all = QPushButton("Home All")
    btn_all.setStyleSheet(
        f"background: {COLORS['btn_primary']}; color: {COLORS['text_primary']}; font-size: 9pt;"
    )
    btn_x = QPushButton("Home X")
    btn_x.setStyleSheet("font-size: 9pt;")
    btn_z = QPushButton("Home Z")
    btn_z.setStyleSheet("font-size: 9pt;")
    btn_row.addWidget(btn_all)
    btn_row.addWidget(btn_x)
    btn_row.addWidget(btn_z)
    section.add_layout(btn_row)

    widgets = {
        "home_x_label": home_x_label,
        "home_z_label": home_z_label,
        "btn_all": btn_all,
        "btn_x": btn_x,
        "btn_z": btn_z,
    }
    return section, widgets


# ======================================================================
# Compound Slide Section
# ======================================================================

def build_compound_section() -> tuple:
    """Build the Compound Slide collapsible section.

    Emulates a manual lathe's compound rest in software. A single MPG
    handwheel drives coordinated X+Z motion along a user-defined angle
    (Linear mode) or circular arc (Arc mode).

    Returns:
        (section, widgets) where widgets is a dict of named widget references.
    """
    from gui.components.quadrant_graphic import QuadrantGraphic

    section = CollapsibleSection("Compound Slide", expanded=False)

    # --- Activation toggle ---
    btn_activate = QPushButton("OFF")
    btn_activate.setCheckable(True)
    btn_activate.setFixedHeight(32)
    btn_activate.setStyleSheet(
        f"QPushButton {{ background: {COLORS['bg_surface']}; "
        f"color: {COLORS['text_primary']}; border: 1px solid {COLORS['border_normal']}; "
        f"border-radius: 3px; font-weight: bold; font-size: 10pt; "
        f"margin-top: 4px; margin-bottom: 4px; }}"
        f"QPushButton:checked {{ background: {COLORS['status_ok']}; "
        f"color: {COLORS['text_primary']}; border: 1px solid {COLORS['status_ok']}; "
        f"margin-top: 4px; margin-bottom: 4px; }}"
    )
    section.add_widget(btn_activate)

    # --- Mode selector ---
    mode_row = QHBoxLayout()
    mode_row.setContentsMargins(0, 6, 0, 0)
    mode_label = QLabel("Mode:")
    mode_label.setMinimumWidth(56)
    mode_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 9pt;")
    combo_mode = QComboBox()
    combo_mode.addItems(["Linear", "Arc"])
    combo_mode.setCurrentIndex(0)
    combo_mode.setFixedHeight(26)
    mode_row.addWidget(mode_label)
    mode_row.addWidget(combo_mode, stretch=1)
    section.add_layout(mode_row)

    # --- Linear mode: Angle input (sign determines direction) ---
    angle_row = QHBoxLayout()
    angle_row.setContentsMargins(0, 6, 0, 0)
    angle_label = QLabel("Angle:")
    angle_label.setMinimumWidth(56)
    angle_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 9pt;")
    from PyQt5.QtWidgets import QLineEdit as _QLE
    input_angle = _QLE("45.0")
    input_angle.setAlignment(Qt.AlignRight)
    input_angle.setFixedHeight(26)
    input_angle.setStyleSheet(
        f"font-family: {FONTS['mono_family']}; font-size: 10pt; "
        f"background: {COLORS['bg_base']}; color: {COLORS['text_primary']}; "
        f"border: 1px solid {COLORS['border_normal']}; border-radius: 3px; padding: 2px 4px;"
    )
    input_angle.setToolTip(
        "Compound angle (-90 to +90°).\n"
        "Positive: X−Z+ coupling (OD chamfer direction)\n"
        "Negative: X−Z− coupling (ID chamfer direction)\n"
        "Examples: +45 = OD chamfer, -29.5 = ID threading"
    )
    deg_label = QLabel("°")
    deg_label.setStyleSheet(f"color: {COLORS['text_disabled']};")
    angle_row.addWidget(angle_label)
    angle_row.addWidget(input_angle, stretch=1)
    angle_row.addWidget(deg_label)
    section.add_layout(angle_row)

    # --- Arc mode: Radius + Quadrant + Start Type + Graphic ---
    arc_container = QWidget()
    arc_container.setMinimumHeight(140)
    arc_layout = QHBoxLayout(arc_container)
    arc_layout.setContentsMargins(4, 10, 4, 10)
    arc_layout.setSpacing(12)

    quadrant_graphic = QuadrantGraphic()
    arc_layout.addWidget(quadrant_graphic, alignment=Qt.AlignTop)

    arc_selectors = QVBoxLayout()
    arc_selectors.setSpacing(6)

    # Radius
    radius_row = QHBoxLayout()
    radius_row.setSpacing(4)
    r_label = QLabel("R:")
    r_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 9pt;")
    input_radius = _QLE("0.250")
    input_radius.setAlignment(Qt.AlignRight)
    input_radius.setFixedHeight(26)
    input_radius.setStyleSheet(
        f"font-family: {FONTS['mono_family']}; font-size: 9pt; "
        f"background: {COLORS['bg_base']}; color: {COLORS['text_primary']}; "
        f"border: 1px solid {COLORS['border_normal']}; border-radius: 2px; padding: 2px 4px;"
    )
    r_unit = QLabel("\"")
    r_unit.setStyleSheet(f"color: {COLORS['text_disabled']};")
    radius_row.addWidget(r_label)
    radius_row.addWidget(input_radius, stretch=1)
    radius_row.addWidget(r_unit)
    arc_selectors.addLayout(radius_row)

    # Quadrant
    combo_quadrant = QComboBox()
    combo_quadrant.addItems(["NE", "NW", "SW", "SE"])
    combo_quadrant.setCurrentIndex(3)  # SE default
    combo_quadrant.setFixedHeight(26)
    arc_selectors.addWidget(combo_quadrant)

    # Start type
    combo_start = QComboBox()
    combo_start.addItems(["Arc Top", "Arc Bottom"])
    combo_start.setCurrentIndex(0)
    combo_start.setFixedHeight(26)
    arc_selectors.addWidget(combo_start)

    arc_layout.addLayout(arc_selectors, stretch=1)
    section.add_widget(arc_container)
    arc_container.setVisible(False)  # Hidden by default (Linear mode)

    # --- MPG selector ---
    mpg_row = QHBoxLayout()
    mpg_row.setContentsMargins(0, 6, 0, 0)
    mpg_label = QLabel("MPG:")
    mpg_label.setMinimumWidth(56)
    mpg_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 9pt;")
    combo_mpg = QComboBox()
    combo_mpg.addItems(["X MPG", "Z MPG"])
    combo_mpg.setCurrentIndex(0)
    combo_mpg.setFixedHeight(26)
    mpg_row.addWidget(mpg_label)
    mpg_row.addWidget(combo_mpg, stretch=1)
    section.add_layout(mpg_row)

    # --- Cumulative distance display ---
    dist_row = QHBoxLayout()
    dist_row.setContentsMargins(0, 6, 0, 4)
    dist_label = QLabel("Dist:")
    dist_label.setMinimumWidth(56)
    dist_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 9pt;")
    lbl_distance = QLabel("0.0000\"")
    lbl_distance.setAlignment(Qt.AlignRight)
    lbl_distance.setStyleSheet(
        f"font-family: {FONTS['mono_family']}; font-size: 11pt; font-weight: bold; "
        f"color: {COLORS['text_primary']}; background: {COLORS['bg_base']}; "
        f"border: 1px solid {COLORS['border_normal']}; border-radius: 3px; "
        f"padding: 2px 6px;"
    )
    dist_row.addWidget(dist_label)
    dist_row.addWidget(lbl_distance, stretch=1)
    section.add_layout(dist_row)

    widgets = {
        "btn_activate": btn_activate,
        "combo_mode": combo_mode,
        "input_angle": input_angle,
        "angle_label": angle_label,
        "deg_label": deg_label,
        "arc_container": arc_container,
        "input_radius": input_radius,
        "combo_quadrant": combo_quadrant,
        "combo_start": combo_start,
        "quadrant_graphic": quadrant_graphic,
        "combo_mpg": combo_mpg,
        "lbl_distance": lbl_distance,
    }
    return section, widgets
