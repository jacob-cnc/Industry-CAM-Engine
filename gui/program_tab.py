"""Program Tab for Industry CAM Engine.

Main machining program interface: input fields (left) + graph/playback (right).
Implements state machine: IDLE → BUILDING → READY → GENERATING → DISPLAYING ↔ PLAYING.

This tab is usable in offline mode (no LinuxCNC dependency).
"""

from enum import Enum, auto
from typing import Optional, List
import logging
import os

from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QScrollArea, QLabel, QComboBox, QCheckBox, QSpinBox,
    QPushButton, QGroupBox, QFormLayout, QFrame,
    QFileDialog, QMessageBox,
)

from gui.colors import COLORS, FONTS
from gui.components.numeric_field import NumericField, NumericFieldConfig
from gui.components.segment_list import SegmentListWidget
from gui.components.graph_widget import MachiningGraphWidget
from gui.unit_state import unit_state

# Pipeline imports
from pipeline.pipeline import execute as pipeline_execute
from pipeline.model_builder import build_from_fields
from outputs.gcode_writer import GCodeWriter
from outputs.graph_adapter import convert as graph_convert
from outputs.gcode_parser import parse as parse_gcode
from outputs import material_sim
from models.tool import ToolDef, ToolOrientation, ToolDirection, ToolType
from models.validation import PipelineStatus
from geometry.arc_helpers import is_arc_within_x_bounds

logger = logging.getLogger(__name__)


def _quadrant_arc_kernel_points(
    x_start_r: float, z_start: float,
    x_end_r: float, z_end: float,
    quadrant_sign: int = 1,
    num_points: int = 48,
) -> list:
    """Construct a quadrant arc as display points using parametric ellipse math.

    The quadrant arc is a quarter ellipse inscribed in the bounding box defined
    by the start and end points. ALL points on the curve must lie within this
    bounding box — this is the defining constraint of a tangent-bounded arc.

    For +Q (convex):
        Center at (x_start_r, z_end) — the bounding box corner where
        the start's X column meets the end's Z row.
        x(t) = center_x + sign_x * b * sin(t)   [b = |dx|]
        z(t) = center_z + sign_z * a * cos(t)   [a = |dz|]
        At t=0: point = start (tangent purely in X direction)
        At t=π/2: point = end (tangent purely in Z direction)

    For -Q (concave):
        Center at (x_end_r, z_start) — the opposite bounding box corner.
        Same parametric form with swapped center and adjusted signs.

    Args:
        x_start_r: Start X in radius units
        z_start: Start Z in inches
        x_end_r: End X in radius units
        z_end: End Z in inches
        quadrant_sign: +1 for convex (Q), -1 for concave (-Q)
        num_points: Number of display points to sample

    Returns:
        List of (x_r, z) tuples from start to end along the quarter ellipse.
    """
    import math
    from models.constants import TOLERANCE

    dx = x_end_r - x_start_r
    dz = z_end - z_start

    # Degenerate case: both deltas near zero → straight line
    if abs(dx) < TOLERANCE and abs(dz) < TOLERANCE:
        return [(x_start_r, z_start), (x_end_r, z_end)]

    # Axis-aligned degenerate: one delta is zero → straight line
    if abs(dx) < TOLERANCE or abs(dz) < TOLERANCE:
        # For truly axis-aligned, the "ellipse" collapses to a line along one axis.
        # Use a circular arc via RadiusArc for proper curvature.
        axis_aligned_x = abs(dx) < TOLERANCE
        try:
            from build123d import RadiusArc
            from OCP.BRepAdaptor import BRepAdaptor_Curve

            arc_radius = abs(dz) if axis_aligned_x else abs(dx)
            # For +Q convex axis-aligned: arc curves INTO the bounding box
            # For -Q concave: arc curves AWAY (but stays in bounds for quarter-arc)
            # The RadiusArc sign must produce an arc that stays within bounds.
            # Negative radius = arc center on one side, positive = other side.
            # We need the arc to bulge toward the bounding box interior.
            #
            # For same-X (vertical chord): bounding box extends in X on one side.
            #   +Q wants the arc to NOT extend beyond [x_start, x_end] in X.
            #   Since x_start == x_end, the arc can only go left or right.
            #   +Q (convex on a lathe profile): arc should NOT extend outward.
            #   Actually for axis-aligned same-X, this is just a straight line
            #   since the bounding box has zero width in X.
            # Wait — if same X, the bounding box has zero X extent, so ANY
            # curvature would violate bounds. Return a straight line.
            if axis_aligned_x:
                return [(x_start_r, z_start + dz * i / num_points)
                        for i in range(num_points + 1)]
            else:
                return [(x_start_r + dx * i / num_points, z_start)
                        for i in range(num_points + 1)]
        except Exception:
            if axis_aligned_x:
                return [(x_start_r, z_start + dz * i / num_points)
                        for i in range(num_points + 1)]
            else:
                return [(x_start_r + dx * i / num_points, z_start)
                        for i in range(num_points + 1)]

    # Off-axis: true quarter ellipse using parametric math
    # This is the proven approach from interpolate_quadrant_arc — always in bounds.
    b = abs(dx)  # semi-axis along X
    a = abs(dz)  # semi-axis along Z

    if quadrant_sign == 1:
        # Convex (+Q): center at (x_start_r, z_end)
        # At t=0: x = cx, z = cz + sign_z*a = z_start → sign_z = (z_start - z_end) / a
        # At t=π/2: x = cx + sign_x*b = x_end_r → sign_x = (x_end_r - x_start_r) / b
        cx = x_start_r
        cz = z_end
        sign_x = 1.0 if dx > 0 else -1.0
        sign_z = -1.0 if dz > 0 else 1.0
    else:
        # Concave (-Q): center at (x_end_r, z_start)
        # At t=0: x = cx + sign_x*b*sin(0) = cx, z = cz + sign_z*a*cos(0) = z_start
        # → cz + sign_z*a = z_start → sign_z*a = z_start - z_start = 0???
        # No — for concave, the parametrization is different.
        # At t=0: point = start → x_start = cx + sign_x*b*sin(0) = cx → cx = x_start??? 
        # That doesn't work either. Let me think about this differently.
        #
        # For -Q: same endpoints, but the arc curves the other way.
        # The center is at the OPPOSITE bounding box corner: (x_end_r, z_start)
        # At t=0: (x_start_r, z_start) — tangent is along Z
        # At t=π/2: (x_end_r, z_end) — tangent is along X
        #
        # x(t) = cx + sign_x * b * cos(t)  [note: cos not sin — tangent at start is Z]
        # z(t) = cz + sign_z * a * sin(t)
        # At t=0: x = cx + sign_x*b = x_start → sign_x = (x_start - x_end) / b
        # At t=π/2: z = cz + sign_z*a = z_end → sign_z = (z_end - z_start) / a
        cx = x_end_r
        cz = z_start
        sign_x = -1.0 if dx > 0 else 1.0  # opposite of dx direction
        sign_z = 1.0 if dz < 0 else -1.0  # opposite of what +Q does... 

        # Actually let me just use a clean formulation:
        # For -Q, swap start/end tangent behavior:
        # x(t) = cx + sign_x * b * cos(t)
        # z(t) = cz + sign_z * a * sin(t)
        # At t=0: x(0) = cx + sign_x*b should = x_start
        #   sign_x*b = x_start - cx = x_start - x_end = -dx
        #   sign_x = -dx / b = -dx / |dx|
        sign_x = -1.0 if dx > 0 else 1.0
        # At t=π/2: z(π/2) = cz + sign_z*a should = z_end
        #   sign_z*a = z_end - cz = z_end - z_start = dz
        #   sign_z = dz / a = dz / |dz|
        sign_z = 1.0 if dz > 0 else -1.0

    points = []
    for i in range(num_points + 1):
        t = (math.pi / 2.0) * i / num_points
        if quadrant_sign == 1:
            x = cx + sign_x * b * math.sin(t)
            z = cz + sign_z * a * math.cos(t)
        else:
            x = cx + sign_x * b * math.cos(t)
            z = cz + sign_z * a * math.sin(t)
        points.append((x, z))

    return points


class ProgramState(Enum):
    """State machine states for the Program Tab."""
    IDLE = auto()
    BUILDING = auto()
    READY = auto()
    GENERATING = auto()
    DISPLAYING = auto()
    PLAYING = auto()


class ProgramTab(QWidget):
    """Main machining program tab with input fields and graph visualization.

    State Machine:
        IDLE → BUILDING: Any field edit
        BUILDING → READY: All required fields valid
        READY → GENERATING: Generate button clicked
        GENERATING → DISPLAYING: Pipeline completes (external signal)
        DISPLAYING → PLAYING: Play button clicked
        PLAYING → DISPLAYING: Pause/stop or playback finishes
        Any → BUILDING: Field edited while in READY/DISPLAYING/PLAYING

    Signals:
        gcode_generated(str): Emitted when G-code text is ready
        plan_result_ready(object): Emitted when PlanResult is available
        tool_requested(int): Emitted when user wants to select a tool
        generate_requested(): Emitted when Generate button is clicked (for pipeline)
        state_changed(str): Emitted on state transitions (state name)
    """

    gcode_generated = pyqtSignal(str)
    plan_result_ready = pyqtSignal(object)
    tool_requested = pyqtSignal(int)
    generate_requested = pyqtSignal()
    state_changed = pyqtSignal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._state = ProgramState.IDLE
        self._active_tool: Optional[ToolDef] = None
        self._program_file_path: Optional[str] = None
        self._last_gcode_text: str = ""  # Last generated G-code for saving
        self._profile_contour_segments: list = []  # Profile overlay for toolpath display
        self._selected_segment_index: int = -1  # Currently selected segment in builder
        self._setup_ui()
        self._connect_signals()
        self._update_ui_for_state()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def state(self) -> ProgramState:
        """Current state machine state."""
        return self._state

    def set_state(self, new_state: ProgramState) -> None:
        """Transition to a new state (with UI update)."""
        if new_state == self._state:
            return
        self._state = new_state
        self._update_ui_for_state()
        self.state_changed.emit(new_state.name)

    def get_stock_values(self) -> dict:
        """Return current stock field values as a dict."""
        return {
            "diameter": self._stock_diameter.value(),
            "x_start": self._stock_x_start.value(),
            "z_start": self._stock_z_start.value(),
            "z_end": self._stock_z_end.value(),
            "x_park": self._stock_x_park.value(),
            "z_park": self._stock_z_park.value(),
            "pilot_hole_dia": self._stock_pilot_hole.value(),
            "mode": self._get_machining_mode(),
        }

    def get_roughing_values(self) -> dict:
        """Return current roughing field values as a dict."""
        return {
            "tool_number": self._rough_tool_num.value(),
            "doc_dia": self._rough_doc.value(),
            "feed": self._rough_feed.value(),
            "strategy": self._rough_strategy.currentText().lower().replace(" ", "_"),
            "fin_allowance": self._rough_fin_allowance.value(),
            "peck_enabled": self._rough_peck_check.isChecked(),
            "peck_length": self._rough_peck_length.value() if self._rough_peck_check.isChecked() else None,
            "spindle_rpm": self._rough_rpm.value(),
        }

    def get_finishing_values(self) -> dict:
        """Return current finishing field values as a dict."""
        return {
            "tool_number": self._finish_tool_num.value(),
            "passes": int(self._finish_passes.value()),
            "doc_dia": self._finish_doc.value(),
            "feed": self._finish_feed.value(),
            "spindle_rpm": self._finish_rpm.value(),
            "spring_pass": self._finish_spring_pass.isChecked(),
        }

    def get_segments(self) -> list:
        """Return current profile segments from the segment list widget."""
        return self._segment_list.get_segments()

    def get_corner_breaks(self) -> list:
        """Return current corner break data from the segment list widget."""
        return self._segment_list.get_corner_breaks()

    def get_block_type(self) -> str:
        """Return current block type selection."""
        return self._block_type_combo.currentText()

    def set_active_tool(self, tool_def) -> None:
        """Set the active tool for pipeline generation.

        Called from MainWindow when user selects a tool in the Tools tab.

        Args:
            tool_def: ToolDef instance to use for next generation.
        """
        self._active_tool = tool_def
        self._on_field_changed()  # Mark as stale so user re-generates

    @property
    def graph_widget(self) -> MachiningGraphWidget:
        """Access the graph widget for external data loading."""
        return self._graph_widget

    # ------------------------------------------------------------------
    # UI Setup
    # ------------------------------------------------------------------

    def _setup_ui(self):
        """Build the complete tab layout."""
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # QSplitter: left panel + right panel
        self._splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(self._splitter)

        # Left panel (scrollable input fields)
        self._left_panel = self._build_left_panel()
        self._splitter.addWidget(self._left_panel)

        # Right panel (graph + playback)
        self._right_panel = self._build_right_panel()
        self._splitter.addWidget(self._right_panel)

        # Splitter proportions: left panel ~600px default, right gets the rest
        self._splitter.setSizes([600, 400])
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._left_panel.setMinimumWidth(400)

    def _build_left_panel(self) -> QWidget:
        """Build the left panel with collapsible accordion sections.

        Layout:
            - File ops row (always visible)
            - Toolpath Type (collapsible, starts expanded)
            - Stock (collapsible, starts expanded)
            - Roughing (collapsible, starts collapsed)
            - Finishing (collapsible, starts collapsed)
            - Profile Segments (collapsible, starts expanded)
            - Generate button (always visible, fixed at bottom)
            - Status label
        """
        from gui.components.collapsible_section import CollapsibleSection

        panel = QWidget()
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(4, 4, 4, 4)
        panel_layout.setSpacing(2)

        # File operations row (always visible)
        panel_layout.addWidget(self._build_file_ops_section())

        # Scrollable area for the accordion sections
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(f"QScrollArea {{ background-color: {COLORS['bg_base']}; border: none; }}")

        container = QWidget()
        sections_layout = QVBoxLayout(container)
        sections_layout.setContentsMargins(0, 0, 0, 0)
        sections_layout.setSpacing(2)

        # --- Toolpath Type section ---
        self._section_type = CollapsibleSection("Toolpath Type", expanded=True)
        self._build_block_type_content(self._section_type)
        sections_layout.addWidget(self._section_type)

        # --- Stock section ---
        self._section_stock = CollapsibleSection("Stock", expanded=True)
        self._build_stock_content(self._section_stock)
        sections_layout.addWidget(self._section_stock)

        # --- Roughing section ---
        self._section_roughing = CollapsibleSection("Roughing", expanded=False)
        self._build_roughing_content(self._section_roughing)
        sections_layout.addWidget(self._section_roughing)

        # --- Finishing section ---
        self._section_finishing = CollapsibleSection("Finishing", expanded=False)
        self._build_finishing_content(self._section_finishing)
        sections_layout.addWidget(self._section_finishing)

        # --- Profile Segments section ---
        self._section_profile = CollapsibleSection("Profile Segments", expanded=True)
        self._build_profile_content(self._section_profile)
        sections_layout.addWidget(self._section_profile, stretch=1)

        scroll.setWidget(container)
        panel_layout.addWidget(scroll, stretch=1)

        # --- Generate button (always visible at bottom) ---
        self._generate_btn = QPushButton("Generate Toolpath")
        self._generate_btn.setObjectName("generateBtn")
        self._generate_btn.setMinimumHeight(44)
        self._generate_btn.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {COLORS['btn_generate']};"
            f"  color: {COLORS['text_primary']};"
            f"  border: none;"
            f"  border-radius: 4px;"
            f"  padding: 8px 16px;"
            f"  min-height: 44px;"
            f"  font-size: 11pt;"
            f"  font-weight: bold;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background-color: {COLORS['status_ok']};"
            f"}}"
            f"QPushButton:disabled {{"
            f"  background-color: {COLORS['bg_surface']};"
            f"  color: {COLORS['text_disabled']};"
            f"}}"
        )
        panel_layout.addWidget(self._generate_btn)

        # Status label
        self._status_label = QLabel("")
        self._status_label.setStyleSheet(
            f"color: {COLORS['text_secondary']}; font-size: {FONTS['small_size']}pt;"
        )
        self._status_label.setAlignment(Qt.AlignCenter)
        panel_layout.addWidget(self._status_label)

        return panel

    # --- Accordion content builders ---

    def _build_block_type_content(self, section):
        """Populate the Toolpath Type section."""
        from PyQt5.QtWidgets import QFormLayout
        form = QFormLayout()
        form.setContentsMargins(4, 2, 4, 2)
        form.setSpacing(2)

        self._block_type_combo = QComboBox()
        self._block_type_combo.addItem("OD Profile")
        self._block_type_combo.addItem("ID Profile")
        self._block_type_combo.addItem("Threading")
        self._block_type_combo.addItem("Grooving")
        model = self._block_type_combo.model()
        for i in (2, 3):
            item = model.item(i)
            item.setEnabled(False)

        form.addRow("Type:", self._block_type_combo)
        section.add_layout(form)

    def _build_stock_content(self, section):
        """Populate the Stock section."""
        from PyQt5.QtWidgets import QFormLayout
        form = QFormLayout()
        form.setContentsMargins(4, 2, 4, 2)
        form.setSpacing(2)

        self._stock_diameter = NumericField(NumericFieldConfig(
            min_value=0.01, max_value=20.0, decimals=4,
            default_value=1.0, suffix="dia",
        ))
        form.addRow("Diameter:", self._stock_diameter)

        self._stock_x_start = NumericField(NumericFieldConfig(
            min_value=0.0, max_value=20.0, decimals=4,
            default_value=0.0, suffix="dia",
        ))
        form.addRow("X Start:", self._stock_x_start)

        self._stock_z_start = NumericField(NumericFieldConfig(
            min_value=0.0, max_value=5.0, decimals=4,
            default_value=0.1, suffix="in",
        ))
        form.addRow("Z Start:", self._stock_z_start)

        self._stock_z_end = NumericField(NumericFieldConfig(
            min_value=-10.0, max_value=0.0, decimals=4,
            default_value=-1.0, suffix="in",
        ))
        form.addRow("Z End:", self._stock_z_end)

        self._stock_x_park = NumericField(NumericFieldConfig(
            min_value=0.0, max_value=20.0, decimals=4,
            default_value=2.0, suffix="dia",
        ))
        form.addRow("X Park:", self._stock_x_park)

        self._stock_z_park = NumericField(NumericFieldConfig(
            min_value=0.0, max_value=20.0, decimals=4,
            default_value=2.0, suffix="in",
        ))
        form.addRow("Z Park:", self._stock_z_park)

        self._stock_pilot_hole = NumericField(NumericFieldConfig(
            min_value=0.0, max_value=10.0, decimals=4,
            default_value=0.0, suffix="dia",
        ))
        self._pilot_hole_label = QLabel("Pilot Hole:")
        form.addRow(self._pilot_hole_label, self._stock_pilot_hole)
        self._pilot_hole_label.setVisible(False)
        self._stock_pilot_hole.setVisible(False)

        section.add_layout(form)

    def _build_roughing_content(self, section):
        """Populate the Roughing section."""
        from PyQt5.QtWidgets import QFormLayout
        form = QFormLayout()
        form.setContentsMargins(4, 2, 4, 2)
        form.setSpacing(2)

        self._rough_tool_num = QSpinBox()
        self._rough_tool_num.setMinimum(1)
        self._rough_tool_num.setMaximum(99)
        self._rough_tool_num.setValue(1)
        self._rough_tool_num.setPrefix("T")
        self._rough_tool_num.setFixedHeight(32)
        form.addRow("Tool:", self._rough_tool_num)

        self._rough_doc = NumericField(NumericFieldConfig(
            min_value=0.001, max_value=1.0, decimals=4,
            default_value=0.050, suffix="dia",
        ))
        form.addRow("DOC:", self._rough_doc)

        self._rough_feed = NumericField(NumericFieldConfig(
            min_value=0.0001, max_value=0.1, decimals=4,
            default_value=0.006, suffix="ipr",
        ))
        form.addRow("Feed:", self._rough_feed)

        self._rough_strategy = QComboBox()
        self._rough_strategy.addItem("Staircase")
        self._rough_strategy.addItem("Offset Contour")
        form.addRow("Strategy:", self._rough_strategy)

        self._rough_fin_allowance = NumericField(NumericFieldConfig(
            min_value=0.0, max_value=0.1, decimals=4,
            default_value=0.005, suffix="dia",
        ))
        form.addRow("Fin Allow:", self._rough_fin_allowance)

        # Peck row
        peck_widget = QWidget()
        peck_layout = QHBoxLayout(peck_widget)
        peck_layout.setContentsMargins(0, 0, 0, 0)
        peck_layout.setSpacing(4)
        self._rough_peck_check = QCheckBox("Peck")
        self._rough_peck_check.setStyleSheet(f"color: {COLORS['text_primary']};")
        peck_layout.addWidget(self._rough_peck_check)
        self._rough_peck_length = NumericField(NumericFieldConfig(
            min_value=0.01, max_value=5.0, decimals=3,
            default_value=0.250, suffix="in",
        ))
        self._rough_peck_length.setEnabled(False)
        peck_layout.addWidget(self._rough_peck_length)
        form.addRow("Peck:", peck_widget)

        self._rough_rpm = NumericField(NumericFieldConfig(
            min_value=50.0, max_value=5000.0, decimals=0,
            default_value=1200.0, suffix="rpm", unit_aware=False,
        ))
        form.addRow("RPM:", self._rough_rpm)

        section.add_layout(form)

    def _build_finishing_content(self, section):
        """Populate the Finishing section."""
        from PyQt5.QtWidgets import QFormLayout
        form = QFormLayout()
        form.setContentsMargins(4, 2, 4, 2)
        form.setSpacing(2)

        self._finish_tool_num = QSpinBox()
        self._finish_tool_num.setMinimum(1)
        self._finish_tool_num.setMaximum(99)
        self._finish_tool_num.setValue(1)
        self._finish_tool_num.setPrefix("T")
        self._finish_tool_num.setFixedHeight(32)
        form.addRow("Tool:", self._finish_tool_num)

        self._finish_passes = NumericField(NumericFieldConfig(
            min_value=1.0, max_value=10.0, decimals=0,
            default_value=1.0, suffix="", unit_aware=False,
        ))
        form.addRow("Passes:", self._finish_passes)

        self._finish_doc = NumericField(NumericFieldConfig(
            min_value=0.0005, max_value=0.05, decimals=4,
            default_value=0.002, suffix="dia",
        ))
        form.addRow("DOC:", self._finish_doc)

        self._finish_feed = NumericField(NumericFieldConfig(
            min_value=0.0001, max_value=0.05, decimals=4,
            default_value=0.003, suffix="ipr",
        ))
        form.addRow("Feed:", self._finish_feed)

        self._finish_rpm = NumericField(NumericFieldConfig(
            min_value=50.0, max_value=5000.0, decimals=0,
            default_value=1200.0, suffix="rpm", unit_aware=False,
        ))
        form.addRow("RPM:", self._finish_rpm)

        self._finish_spring_pass = QCheckBox("Spring pass")
        self._finish_spring_pass.setToolTip(
            "Repeat the final finish pass at zero DOC to remove deflection.\n"
            "The last pass runs twice — second time with no additional cut."
        )
        self._finish_spring_pass.setStyleSheet(f"color: {COLORS['text_primary']};")
        form.addRow("", self._finish_spring_pass)

        section.add_layout(form)

    def _build_profile_content(self, section):
        """Populate the Profile Segments section."""
        self._segment_list = SegmentListWidget()
        # Make the segment list expand to fill available space
        from PyQt5.QtWidgets import QSizePolicy
        self._segment_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        section.add_widget(self._segment_list)
        # Make the content stretch to fill the section
        section.content_layout().setStretch(0, 1)

    def _build_right_panel(self) -> QWidget:
        """Build the right panel — the proven SimViewerWidget.

        G-code panel starts hidden until Generate or Open loads data.
        """
        from gui.components.sim_viewer import SimViewerWidget
        self._sim_viewer = SimViewerWidget()
        # Keep _graph_widget reference for backward compat (preview uses it)
        self._graph_widget = self._sim_viewer._graph
        # Start with G-code panel hidden (full graph view)
        self._sim_viewer._splitter.setSizes([1000, 0])
        self._sim_viewer._gcode_collapsed = True
        self._sim_viewer._btn_toggle_code.setText("Show Code")
        return self._sim_viewer

    def _build_file_ops_section(self) -> QWidget:
        """Build the file operations row: Open, Save, Save As."""
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        btn_style = (
            f"QPushButton {{"
            f"  background-color: {COLORS['bg_panel']};"
            f"  color: {COLORS['text_primary']};"
            f"  border: 1px solid {COLORS['border_normal']};"
            f"  border-radius: 3px;"
            f"  padding: 4px 10px;"
            f"  min-height: 30px;"
            f"  font-size: {FONTS['small_size']}pt;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background-color: {COLORS['btn_primary_hover']};"
            f"  border-color: {COLORS['border_focused']};"
            f"}}"
        )

        self._btn_file_open = QPushButton("Open")
        self._btn_file_open.setToolTip("Open program file")
        self._btn_file_open.setStyleSheet(btn_style)
        layout.addWidget(self._btn_file_open)

        self._btn_file_save = QPushButton("Save")
        self._btn_file_save.setToolTip("Save program file")
        self._btn_file_save.setStyleSheet(btn_style)
        layout.addWidget(self._btn_file_save)

        self._btn_file_save_as = QPushButton("Save As")
        self._btn_file_save_as.setToolTip("Save program file as...")
        self._btn_file_save_as.setStyleSheet(btn_style)
        layout.addWidget(self._btn_file_save_as)

        layout.addStretch()

        # File path label
        self._program_file_label = QLabel("")
        self._program_file_label.setStyleSheet(
            f"color: {COLORS['text_subtle']};"
            f" font-size: {FONTS['small_size']}pt;"
        )
        layout.addWidget(self._program_file_label)

        return row

    # ------------------------------------------------------------------
    # Signal Connections
    # ------------------------------------------------------------------

    def _connect_signals(self):
        """Wire up all internal signals."""
        # Block type change
        self._block_type_combo.currentIndexChanged.connect(self._on_block_type_changed)

        # Stock fields
        self._stock_diameter.value_changed.connect(self._on_field_changed)
        self._stock_x_start.value_changed.connect(self._on_field_changed)
        self._stock_z_start.value_changed.connect(self._on_field_changed)
        self._stock_z_end.value_changed.connect(self._on_field_changed)
        self._stock_x_park.value_changed.connect(self._on_field_changed)
        self._stock_z_park.value_changed.connect(self._on_field_changed)
        self._stock_pilot_hole.value_changed.connect(self._on_field_changed)

        # Roughing fields
        self._rough_doc.value_changed.connect(self._on_field_changed)
        self._rough_feed.value_changed.connect(self._on_field_changed)
        self._rough_strategy.currentIndexChanged.connect(self._on_field_changed)
        self._rough_fin_allowance.value_changed.connect(self._on_field_changed)
        self._rough_peck_check.toggled.connect(self._on_peck_toggled)
        self._rough_peck_length.value_changed.connect(self._on_field_changed)
        self._rough_rpm.value_changed.connect(self._on_field_changed)

        # Finishing fields
        self._finish_passes.value_changed.connect(self._on_field_changed)
        self._finish_doc.value_changed.connect(self._on_field_changed)
        self._finish_feed.value_changed.connect(self._on_field_changed)
        self._finish_rpm.value_changed.connect(self._on_field_changed)

        # Segment list
        self._segment_list.segments_changed.connect(self._on_segments_changed)
        self._segment_list.corner_breaks_changed.connect(self._on_field_changed)
        self._segment_list.selection_changed.connect(self._on_segment_selection_changed)

        # Generate button
        self._generate_btn.clicked.connect(self._on_generate_clicked)

        # File operations
        self._btn_file_open.clicked.connect(self._on_file_open)
        self._btn_file_save.clicked.connect(self._on_file_save)
        self._btn_file_save_as.clicked.connect(self._on_file_save_as)

    # ------------------------------------------------------------------
    # Event Handlers
    # ------------------------------------------------------------------

    def _on_block_type_changed(self, index: int):
        """Handle block type combo change — show/hide pilot hole for ID mode."""
        is_id = index == 1  # "ID Profile"
        self._pilot_hole_label.setVisible(is_id)
        self._stock_pilot_hole.setVisible(is_id)
        self._on_field_changed()

    def _on_field_changed(self, *args):
        """Any input field changed — transition to BUILDING, then check READY."""
        if self._state in (ProgramState.IDLE, ProgramState.BUILDING,
                           ProgramState.READY, ProgramState.DISPLAYING,
                           ProgramState.PLAYING):
            # Clear toolpath when leaving DISPLAYING/PLAYING
            if self._state in (ProgramState.DISPLAYING, ProgramState.PLAYING):
                self._sim_viewer._sim_stop()
            self.set_state(ProgramState.BUILDING)
            # Debounce validation and preview
            QTimer.singleShot(100, self._check_ready)
            QTimer.singleShot(50, self._validate_inline)
            QTimer.singleShot(150, self._update_preview)

    def _on_segments_changed(self, segments: list):
        """Profile segments changed — auto-populate Z End from most negative Z."""
        if segments:
            z_values = [seg.get("z", 0.0) for seg in segments]
            min_z = min(z_values)
            if min_z < 0:
                self._stock_z_end.set_value(min_z)
        self._on_field_changed()

    def _on_segment_selection_changed(self, seg_index: int):
        """Segment selection changed in the builder — highlight on graph."""
        self._selected_segment_index = seg_index
        self._update_preview()

    def _on_peck_toggled(self, checked: bool):
        """Enable/disable peck length field based on checkbox."""
        self._rough_peck_length.setEnabled(checked)
        self._on_field_changed()

    def _on_generate_clicked(self):
        """Generate button clicked — execute pipeline and display results.

        Uses staged error handling: each pipeline phase is wrapped individually
        so the error dialog can report exactly which stage failed and why.
        """
        # Allow generate from BUILDING or READY (user may not have triggered validation)
        if self._state not in (ProgramState.READY, ProgramState.BUILDING):
            return

        self.set_state(ProgramState.GENERATING)
        self.generate_requested.emit()

        stage = "model_build"
        try:
            # 1. Gather field values
            stock = self.get_stock_values()
            roughing = self.get_roughing_values()
            finishing = self.get_finishing_values()
            segments = self.get_segments()

            # 2. Resolve tool from active selection or roughing tool number
            #    Priority: _active_tool (set by Tools tab selection or startup)
            #    Fallback: look up roughing tool_number from tool table via signal
            tool_def = self._active_tool
            if tool_def is None:
                # No tool selected — use hardcoded default as last resort
                tool_def = ToolDef(
                    tool_number=roughing["tool_number"],
                    nose_radius=0.016,
                    tip_angle=80.0,
                    edge_length=0.375,
                    orientation=ToolOrientation.OD_FRONT_RIGHT,
                    direction=ToolDirection.RIGHT,
                    tool_type=ToolType.TURNING,
                    description=f"Default T{roughing['tool_number']}",
                )

            # 3. Build typed dataclasses from field values
            # x_start: Use the user's X Start value directly.
            # X Start = 0 means face passes cut all the way to the centerline.
            # X Start > 0 means face passes stop at that diameter.
            x_start_val = stock["x_start"]

            profile, stock_def, roughing_params, finishing_params = build_from_fields(
                segments=segments,
                stock_dia=stock["diameter"],
                x_start=x_start_val,
                z_start=stock["z_start"],
                z_end=stock["z_end"],
                mode=stock["mode"],
                pilot_hole_dia=stock["pilot_hole_dia"],
                doc_dia=roughing["doc_dia"],
                feed=roughing["feed"],
                strategy=roughing["strategy"],
                fin_allowance=roughing["fin_allowance"],
                peck_enabled=roughing["peck_enabled"],
                peck_length=roughing["peck_length"],
                spindle_rpm=roughing["spindle_rpm"],
                finish_passes=int(finishing["passes"]),
                finish_doc_dia=finishing["doc_dia"],
                finish_feed=finishing["feed"],
                tool_def=tool_def,
                x_park=stock["x_park"],
                z_park=stock["z_park"],
                corner_breaks=self.get_corner_breaks(),
            )

            # 4. Execute pipeline
            stage = "pipeline"
            pipeline_result = pipeline_execute(
                profile=profile,
                stock=stock_def,
                tool=tool_def,
                roughing_params=roughing_params,
                finishing_params=finishing_params,
            )

            # 5. Check result status
            if pipeline_result.status not in (PipelineStatus.SUCCESS, PipelineStatus.SUCCESS_WITH_WARNINGS):
                # Show validation errors in status label (brief)
                errors = [v for v in pipeline_result.validations
                          if v.severity.value == "error"]
                first_msg = errors[0].message if errors else "Pipeline blocked"
                self._status_label.setText(f"Error: {first_msg}")
                self._status_label.setStyleSheet(
                    f"color: {COLORS['status_error']}; font-size: {FONTS['small_size']}pt;"
                )
                # Log all validation results
                for v in pipeline_result.validations:
                    logger.warning("Validation [%s/%s]: %s", v.severity.value, v.category, v.message)

                # Show detailed error dialog
                from gui.components.error_dialog import GenerationErrorDialog
                dlg = GenerationErrorDialog(self)
                dlg.show_validation_errors(pipeline_result.validations, stage="pipeline validation")

                self.set_state(ProgramState.READY)
                return

            plan_result = pipeline_result.plan_result

            # 6. Material simulation DISABLED — still buggy, not accurately reflecting
            #    real material removal. See .kiro/specs/material-sim-accuracy-fix/ and
            #    .kiro/specs/material-removal-simulation/ for specs + progress notes.
            #    Falls back to raster zone shading instead.
            sim_data = None

            # 7. Convert to graph data
            stage = "graph_convert"
            graph_data = graph_convert(plan_result, material_sim_data=sim_data)

            # 8. Generate G-code
            stage = "gcode_write"
            gcode_text = GCodeWriter().write(plan_result, unit_mode=unit_state.mode.value)

            # 9. Parse for sim and load into SimViewerWidget
            stage = "sim_load"
            from gui.components.sim_viewer import parse_gcode_for_sim
            sim_moves = parse_gcode_for_sim(gcode_text)
            self._sim_viewer.load(graph_data, gcode_text, sim_moves)

            # 9b. Pass profile contour for overlay toggle
            if hasattr(self, '_profile_contour_segments') and self._profile_contour_segments:
                self._sim_viewer.set_profile_overlay(self._profile_contour_segments)

            # 10. Emit signals
            self._last_gcode_text = gcode_text
            self.gcode_generated.emit(gcode_text)
            self.plan_result_ready.emit(plan_result)

            # 11. Transition to DISPLAYING
            self.set_state(ProgramState.DISPLAYING)

            # Show success with warning count if any
            warning_count = sum(1 for v in pipeline_result.validations
                                if v.severity.value == "warning")
            if warning_count > 0:
                self._status_label.setText(
                    f"Toolpath ready — {len(sim_moves)} moves, {warning_count} warning(s)"
                )
                self._status_label.setStyleSheet(
                    f"color: {COLORS['status_warning']}; font-size: {FONTS['small_size']}pt;"
                )
            else:
                self._status_label.setStyleSheet(
                    f"color: {COLORS['text_secondary']}; font-size: {FONTS['small_size']}pt;"
                )

        except Exception as e:
            import traceback as tb_module
            tb_str = tb_module.format_exc()

            # Log full traceback
            logger.error(
                "Generation failed at stage '%s': %s\n%s",
                stage, e, tb_str,
            )

            # Brief status label message
            error_msg = str(e) if str(e) else type(e).__name__
            # Truncate for status label (single line)
            display_msg = error_msg[:80] + "..." if len(error_msg) > 80 else error_msg
            self._status_label.setText(f"Error ({stage}): {display_msg}")
            self._status_label.setStyleSheet(
                f"color: {COLORS['status_error']}; font-size: {FONTS['small_size']}pt;"
            )

            # Show detailed error dialog
            from gui.components.error_dialog import GenerationErrorDialog
            dlg = GenerationErrorDialog(self)
            dlg.show_exception(e, tb_str, stage=stage)

            self.set_state(ProgramState.READY)

    # ------------------------------------------------------------------
    # State Machine Logic
    # ------------------------------------------------------------------

    def _check_ready(self):
        """Check if all required fields are valid → transition to READY."""
        if self._state != ProgramState.BUILDING:
            return

        if self._all_fields_valid():
            self.set_state(ProgramState.READY)

    def _all_fields_valid(self) -> bool:
        """Return True if all required fields have valid values."""
        # Check all numeric fields are valid
        numeric_fields = [
            self._stock_diameter, self._stock_x_start,
            self._stock_z_start, self._stock_z_end,
            self._stock_x_park, self._stock_z_park,
            self._rough_doc, self._rough_feed, self._rough_fin_allowance,
            self._rough_rpm,
            self._finish_passes, self._finish_doc, self._finish_feed,
            self._finish_rpm,
        ]

        # Include pilot hole if in ID mode
        if self._block_type_combo.currentIndex() == 1:
            numeric_fields.append(self._stock_pilot_hole)

        # Include peck length if peck is enabled
        if self._rough_peck_check.isChecked():
            numeric_fields.append(self._rough_peck_length)

        for field in numeric_fields:
            if not field.is_valid():
                return False

        # Must have at least one profile segment
        segments = self._segment_list.get_segments()
        if len(segments) < 1:
            return False

        return True

    def _update_ui_for_state(self):
        """Update UI elements based on current state."""
        state = self._state

        # Generate button — enabled in BUILDING or READY
        self._generate_btn.setEnabled(state in (ProgramState.READY, ProgramState.BUILDING))

        # Status label
        status_messages = {
            ProgramState.IDLE: "Define profile and parameters to begin",
            ProgramState.BUILDING: "Editing parameters...",
            ProgramState.READY: "Ready to generate",
            ProgramState.GENERATING: "Generating toolpath...",
            ProgramState.DISPLAYING: "Toolpath ready — use playback controls",
            ProgramState.PLAYING: "Playing...",
        }
        self._status_label.setText(status_messages.get(state, ""))

        # Generate button text during generation
        if state == ProgramState.GENERATING:
            self._generate_btn.setText("Generating...")
            self._generate_btn.setEnabled(False)
        else:
            self._generate_btn.setText("Generate Toolpath")

    # ------------------------------------------------------------------
    # File Operations
    # ------------------------------------------------------------------

    def _on_file_open(self):
        """Open a conversational program file (JSON) or G-code file.

        G-code files (.ngc, .nc, .gcode, .tap) are parsed and displayed
        directly on the graph with sim playback.
        Conversational files (.json, .cam) populate the input fields.
        """
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Program",
            "",
            "All Supported (*.json *.cam *.ngc *.nc *.gcode *.tap);;"
            "Conversational (*.json *.cam);;"
            "G-code (*.ngc *.nc *.gcode *.tap);;"
            "All Files (*)",
        )
        if not path:
            return

        ext = os.path.splitext(path)[1].lower()

        if ext in ('.ngc', '.nc', '.gcode', '.tap'):
            # G-code file — parse and display on graph
            self._open_gcode_file(path)
        else:
            # Conversational program file (JSON)
            self._open_conversational_file(path)

    def _open_gcode_file(self, path: str):
        """Load a G-code file, parse it, and display on the graph with sim."""
        try:
            gcode_text = self._read_text_file(path)

            moves = parse_gcode(gcode_text)
            if not moves:
                QMessageBox.information(
                    self, "No Moves",
                    "No motion commands found in the G-code file.",
                )
                return

            # Convert to graph data and load into SimViewerWidget
            from outputs.graph_adapter import convert_from_moves
            from gui.components.sim_viewer import parse_gcode_for_sim
            graph_data = convert_from_moves(moves)
            sim_moves = parse_gcode_for_sim(gcode_text)
            self._sim_viewer.load(graph_data, gcode_text, sim_moves)

            # Emit G-code to Edit tab
            self._last_gcode_text = gcode_text
            self.gcode_generated.emit(gcode_text)

            # Update state
            self.set_state(ProgramState.DISPLAYING)
            self._program_file_path = path
            self._program_file_label.setText(os.path.basename(path))
            self._program_file_label.setToolTip(path)
            self._status_label.setText(
                f"Loaded G-code: {len(moves)} moves from {os.path.basename(path)}"
            )
            self._status_label.setStyleSheet(
                f"color: {COLORS['text_secondary']}; font-size: {FONTS['small_size']}pt;"
            )

        except Exception as e:
            QMessageBox.warning(self, "Load Error", f"Failed to load G-code:\n{e}")

    def _open_conversational_file(self, path: str):
        """Load a conversational program file (JSON) into the input fields."""
        import json
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self._load_program_data(data)
            self._program_file_path = path
            self._program_file_label.setText(os.path.basename(path))
            self._program_file_label.setToolTip(path)
        except json.JSONDecodeError:
            QMessageBox.warning(self, "Load Error", f"Not a valid program file:\n{path}")
        except Exception as e:
            QMessageBox.warning(self, "Load Error", f"Failed to load:\n{e}")

    def _on_file_save(self):
        """Save program to current file path, or prompt Save As."""
        if self._program_file_path:
            self._write_program_file(self._program_file_path)
        else:
            self._on_file_save_as()

    def _on_file_save_as(self):
        """Save program to a new file."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Program As",
            "",
            "Program Files (*.json);;All Files (*)",
        )
        if not path:
            return
        if not path.endswith('.json'):
            path += '.json'
        self._write_program_file(path)
        self._program_file_path = path
        self._program_file_label.setText(os.path.basename(path))
        self._program_file_label.setToolTip(path)

    def _write_program_file(self, path: str):
        """Serialize current program state to JSON and save G-code as .ngc companion.

        Saves two files:
            - <name>.json — conversational program parameters (reloadable)
            - <name>.ngc — G-code output (loadable by Run tab)
        """
        import json
        data = {
            "version": 1,
            "block_type": self.get_block_type(),
            "stock": self.get_stock_values(),
            "roughing": self.get_roughing_values(),
            "finishing": self.get_finishing_values(),
            "segments": self.get_segments(),
            "corner_breaks": self.get_corner_breaks(),
        }
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            QMessageBox.warning(self, "Save Error", f"Failed to save program:\n{e}")
            return

        # Save companion .ngc file with the generated G-code
        if self._last_gcode_text:
            ngc_path = os.path.splitext(path)[0] + '.ngc'
            try:
                with open(ngc_path, 'w', encoding='utf-8') as f:
                    f.write(self._last_gcode_text)
                logger.info("Saved G-code companion: %s", ngc_path)
            except Exception as e:
                QMessageBox.warning(
                    self, "Save Warning",
                    f"Program saved, but G-code file failed:\n{e}",
                )

    def _load_program_data(self, data: dict):
        """Deserialize program state from JSON dict into fields."""
        # Block type
        block_type = data.get("block_type", "OD Profile")
        idx = self._block_type_combo.findText(block_type)
        if idx >= 0:
            self._block_type_combo.setCurrentIndex(idx)

        # Stock
        stock = data.get("stock", {})
        if "diameter" in stock:
            self._stock_diameter.set_value(stock["diameter"])
        if "z_start" in stock:
            self._stock_z_start.set_value(stock["z_start"])
        if "z_end" in stock:
            self._stock_z_end.set_value(stock["z_end"])
        if "x_park" in stock:
            self._stock_x_park.set_value(stock["x_park"])
        if "z_park" in stock:
            self._stock_z_park.set_value(stock["z_park"])
        if "pilot_hole_dia" in stock:
            self._stock_pilot_hole.set_value(stock["pilot_hole_dia"])

        # Roughing
        roughing = data.get("roughing", {})
        if "doc_dia" in roughing:
            self._rough_doc.set_value(roughing["doc_dia"])
        if "feed" in roughing:
            self._rough_feed.set_value(roughing["feed"])
        if "strategy" in roughing:
            strategy_text = roughing["strategy"].replace("_", " ").title()
            idx = self._rough_strategy.findText(strategy_text)
            if idx >= 0:
                self._rough_strategy.setCurrentIndex(idx)
        if "fin_allowance" in roughing:
            self._rough_fin_allowance.set_value(roughing["fin_allowance"])
        if "peck_enabled" in roughing:
            self._rough_peck_check.setChecked(roughing["peck_enabled"])
        if "peck_length" in roughing and roughing["peck_length"] is not None:
            self._rough_peck_length.set_value(roughing["peck_length"])
        if "spindle_rpm" in roughing:
            self._rough_rpm.set_value(roughing["spindle_rpm"])
        if "tool_number" in roughing:
            self._rough_tool_num.setValue(int(roughing["tool_number"]))

        # Finishing
        finishing = data.get("finishing", {})
        if "tool_number" in finishing:
            self._finish_tool_num.setValue(int(finishing["tool_number"]))
        if "passes" in finishing:
            self._finish_passes.set_value(float(finishing["passes"]))
        if "doc_dia" in finishing:
            self._finish_doc.set_value(finishing["doc_dia"])
        if "feed" in finishing:
            self._finish_feed.set_value(finishing["feed"])
        if "spindle_rpm" in finishing:
            self._finish_rpm.set_value(finishing["spindle_rpm"])
        if "spring_pass" in finishing:
            self._finish_spring_pass.setChecked(finishing["spring_pass"])

        # Segments
        segments = data.get("segments", [])
        if segments:
            corner_breaks = data.get("corner_breaks", None)
            self._segment_list.set_segments(segments, corner_breaks=corner_breaks)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_machining_mode(self) -> str:
        """Return 'od' or 'id' based on block type selection."""
        if self._block_type_combo.currentIndex() == 1:
            return "id"
        return "od"

    @staticmethod
    def _read_text_file(path: str) -> str:
        """Read a text file, trying UTF-8 first then falling back to Latin-1."""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        except UnicodeDecodeError:
            with open(path, 'r', encoding='latin-1') as f:
                return f.read()

    # ------------------------------------------------------------------
    # Preview & Validation
    # ------------------------------------------------------------------

    def _update_preview(self):
        """Real-time profile preview — draw segments as lines/arcs on graph.

        Pure Qt geometry, no kernel call. Target < 16ms.
        Only draws when in BUILDING or READY state (no toolpath loaded).
        Renders corner breaks (chamfers/fillets) at segment junctions.
        """
        if self._state not in (ProgramState.BUILDING, ProgramState.READY):
            return

        segments = self._segment_list.get_segments()
        if not segments:
            return

        import math
        import pyqtgraph as pg
        from pyqtgraph.Qt import QtCore as _QtCore

        corner_breaks = self._segment_list.get_corner_breaks()

        # Build per-segment polylines for drawing (avoids pyqtgraph bounding-box
        # rendering artifacts that occur with a single large PlotCurveItem containing
        # many arc interpolation points).
        # Each entry: (list_of_z, list_of_x) for one continuous sub-path.
        segments_to_draw: List[tuple] = []
        current_z: List[float] = []
        current_x: List[float] = []
        all_z: List[float] = []
        all_x: List[float] = []

        # Track point-index boundaries per segment for highlight rendering.
        # Each entry is (start_idx, end_idx) into current_x/current_z.
        seg_point_ranges: List[tuple] = []

        # Pre-compute segment endpoints (radius coords) for corner break geometry
        seg_endpoints = [(0.0, 0.0)]  # origin as implicit start

        for seg in segments:
            seg_endpoints.append((float(seg.get("x", 0.0)) / 2.0,
                                  float(seg.get("z", 0.0))))

        prev_x_r = 0.0
        prev_z = 0.0

        for seg_idx, seg in enumerate(segments):
            # Record where this segment's points start
            _seg_start_idx = len(current_x)

            x_dia = float(seg.get("x", 0.0))
            z = float(seg.get("z", 0.0))
            x_r = x_dia / 2.0
            raw_radius = seg.get("radius", 0.0)
            if isinstance(raw_radius, str) and raw_radius.strip().upper() in ("Q", "-Q"):
                radius = raw_radius.strip().upper()  # "Q" or "-Q"
            else:
                radius = float(raw_radius)
            seg_type = seg.get("type", "line")

            # Determine if there's a corner break BEFORE this segment
            # (i.e., at the junction between seg_idx-1 and seg_idx)
            cb_before = None
            if seg_idx > 0 and corner_breaks and seg_idx - 1 < len(corner_breaks):
                cb_before = corner_breaks[seg_idx - 1]

            # Compute arrival point (may be trimmed by corner break)
            # and departure point for this segment
            trim_start_x = prev_x_r
            trim_start_z = prev_z
            trim_end_x = x_r
            trim_end_z = z

            # Apply corner break at the START of this segment (junction with previous)
            if cb_before and cb_before.get("type", "none") != "none":
                cb_type = cb_before["type"]
                # Compute direction vectors at the junction point (prev_x_r, prev_z)
                # Arrival direction: from previous segment's start toward junction
                prev_seg_start_x, prev_seg_start_z = seg_endpoints[seg_idx - 1]
                arr_dx = prev_x_r - prev_seg_start_x
                arr_dz = prev_z - prev_seg_start_z
                arr_len = math.sqrt(arr_dx * arr_dx + arr_dz * arr_dz)

                # Departure direction: from junction toward this segment's end
                dep_dx = x_r - prev_x_r
                dep_dz = z - prev_z
                dep_len = math.sqrt(dep_dx * dep_dx + dep_dz * dep_dz)

                if arr_len > 1e-9 and dep_len > 1e-9:
                    # Normalize
                    arr_ux = arr_dx / arr_len
                    arr_uz = arr_dz / arr_len
                    dep_ux = dep_dx / dep_len
                    dep_uz = dep_dz / dep_len

                    if cb_type == "chamfer":
                        size = float(cb_before.get("size", 0.015))
                        # Trim point on arriving segment (back from junction)
                        trim_back = min(size, arr_len * 0.4)
                        trim_fwd = min(size, dep_len * 0.4)
                        p1_x = prev_x_r - arr_ux * trim_back
                        p1_z = prev_z - arr_uz * trim_back
                        # Trim point on departing segment (forward from junction)
                        p2_x = prev_x_r + dep_ux * trim_fwd
                        p2_z = prev_z + dep_uz * trim_fwd

                        # Truncate the current path at p1 (trim arriving segment)
                        if current_z:
                            # Replace last point with trimmed point
                            current_x[-1] = p1_x
                            current_z[-1] = p1_z
                        else:
                            current_x.append(p1_x)
                            current_z.append(p1_z)
                        # Draw chamfer line from p1 to p2
                        current_x.append(p2_x)
                        current_z.append(p2_z)
                        all_x.append(p2_x)
                        all_z.append(p2_z)
                        # Update start of this segment to p2
                        trim_start_x = p2_x
                        trim_start_z = p2_z

                    elif cb_type == "fillet":
                        fillet_r = float(cb_before.get("radius", 0.015))
                        # Compute fillet tangent points
                        # Half-angle between the two directions (reversed arrival)
                        dot = (-arr_ux) * dep_ux + (-arr_uz) * dep_uz
                        dot = max(-1.0, min(1.0, dot))
                        half_angle = math.acos(dot) / 2.0
                        if half_angle > 1e-6:
                            # Distance from junction to tangent point
                            tan_dist = fillet_r / math.tan(half_angle)
                            tan_dist_arr = min(tan_dist, arr_len * 0.4)
                            tan_dist_dep = min(tan_dist, dep_len * 0.4)
                            # Tangent points
                            t1_x = prev_x_r - arr_ux * tan_dist_arr
                            t1_z = prev_z - arr_uz * tan_dist_arr
                            t2_x = prev_x_r + dep_ux * tan_dist_dep
                            t2_z = prev_z + dep_uz * tan_dist_dep

                            # Truncate arriving path at t1
                            if current_z:
                                current_x[-1] = t1_x
                                current_z[-1] = t1_z
                            else:
                                current_x.append(t1_x)
                                current_z.append(t1_z)

                            # Interpolate fillet arc from t1 to t2
                            # Find arc center (offset from junction along bisector)
                            bis_x = (-arr_ux + dep_ux)
                            bis_z = (-arr_uz + dep_uz)
                            bis_len = math.sqrt(bis_x * bis_x + bis_z * bis_z)
                            if bis_len > 1e-9:
                                bis_x /= bis_len
                                bis_z /= bis_len
                                center_dist = fillet_r / math.sin(half_angle)
                                fc_x = prev_x_r + bis_x * center_dist
                                fc_z = prev_z + bis_z * center_dist

                                a_start = math.atan2(t1_z - fc_z, t1_x - fc_x)
                                a_end = math.atan2(t2_z - fc_z, t2_x - fc_x)
                                sweep = a_end - a_start
                                # Take the short arc (< pi)
                                if sweep > math.pi:
                                    sweep -= 2 * math.pi
                                elif sweep < -math.pi:
                                    sweep += 2 * math.pi

                                n_fillet = max(16, int(abs(sweep) * fillet_r * 200))
                                for fi in range(1, n_fillet):
                                    t = fi / float(n_fillet)
                                    a = a_start + sweep * t
                                    current_x.append(fc_x + fillet_r * math.cos(a))
                                    current_z.append(fc_z + fillet_r * math.sin(a))
                                current_x.append(t2_x)
                                current_z.append(t2_z)
                                all_x.append(t2_x)
                                all_z.append(t2_z)
                            # Update start of this segment to t2
                            trim_start_x = t2_x
                            trim_start_z = t2_z
                        # else: angle too small, skip fillet

            if seg_type == "arc" and radius in ("Q", "-Q"):
                # Tangent-bounded quadrant arc — use Build123d kernel geometry
                # and parametric sampling for display points (single source of truth).
                quadrant_sign = -1 if radius == "-Q" else 1
                points = _quadrant_arc_kernel_points(
                    trim_start_x, trim_start_z, x_r, z, quadrant_sign
                )
                if not current_z:
                    current_x.append(points[0][0])
                    current_z.append(points[0][1])
                for px_r, pz in points[1:]:
                    current_x.append(px_r)
                    current_z.append(pz)
                all_x.append(x_r)
                all_z.append(z)

            elif seg_type == "arc" and isinstance(radius, (int, float)) and abs(radius) > 0.0001:
                # Interpolate arc from trim_start to current endpoint
                # Signed radius: +R = CW on screen, -R = CCW on screen
                r_abs = abs(radius)
                is_cw = radius > 0

                dx_r = x_r - trim_start_x
                dz = z - trim_start_z
                chord = math.sqrt(dx_r * dx_r + dz * dz)

                if chord > 0.0001 and r_abs >= chord / 2.0 - 1e-9:
                    if r_abs < chord / 2.0:
                        r_abs = chord / 2.0

                    mid_x_r = (trim_start_x + x_r) / 2.0
                    mid_z = (trim_start_z + z) / 2.0
                    h = math.sqrt(max(0.0, r_abs * r_abs - (chord / 2.0) ** 2))

                    px = -dz / chord
                    pz = dx_r / chord

                    # Compute both candidate centers
                    c1_x = mid_x_r + h * px
                    c1_z = mid_z + h * pz
                    c2_x = mid_x_r - h * px
                    c2_z = mid_z - h * pz

                    # Pick center based on CW/CCW direction on screen.
                    def _cross(cx, cz):
                        ax = trim_start_x - cx
                        az = trim_start_z - cz
                        bx = x_r - cx
                        bz = z - cz
                        return ax * bz - az * bx

                    cr1 = _cross(c1_x, c1_z)
                    if is_cw:
                        cx_r, cz_arc = (c1_x, c1_z) if cr1 < 0 else (c2_x, c2_z)
                        other_cx, other_cz = (c2_x, c2_z) if cr1 < 0 else (c1_x, c1_z)
                    else:
                        cx_r, cz_arc = (c1_x, c1_z) if cr1 > 0 else (c2_x, c2_z)
                        other_cx, other_cz = (c2_x, c2_z) if cr1 > 0 else (c1_x, c1_z)

                    # Bounds-aware center selection
                    if not is_arc_within_x_bounds(
                        cx_r, cz_arc, r_abs,
                        trim_start_x, trim_start_z, x_r, z, is_cw
                    ):
                        if is_arc_within_x_bounds(
                            other_cx, other_cz, r_abs,
                            trim_start_x, trim_start_z, x_r, z, is_cw
                        ):
                            cx_r, cz_arc = other_cx, other_cz

                    # Compute sweep angle
                    angle_start = math.atan2(trim_start_z - cz_arc, trim_start_x - cx_r)
                    angle_end = math.atan2(z - cz_arc, x_r - cx_r)
                    diff = angle_end - angle_start

                    if is_cw:
                        if diff > 0:
                            diff -= 2 * math.pi
                    else:
                        if diff < 0:
                            diff += 2 * math.pi

                    r_display = math.sqrt((trim_start_x - cx_r) ** 2 + (trim_start_z - cz_arc) ** 2)

                    n_pts = max(32, int(abs(diff) * r_display * 200))
                    if not current_z:
                        current_x.append(trim_start_x)
                        current_z.append(trim_start_z)
                    for i in range(1, n_pts):
                        t = i / float(n_pts)
                        angle = angle_start + diff * t
                        ax = cx_r + r_display * math.cos(angle)
                        az = cz_arc + r_display * math.sin(angle)
                        current_x.append(ax)
                        current_z.append(az)
                    current_x.append(x_r)
                    current_z.append(z)
                    all_x.extend([x_r])
                    all_z.extend([z])
                else:
                    # Degenerate arc — draw as line
                    if not current_z:
                        current_x.append(trim_start_x)
                        current_z.append(trim_start_z)
                    current_x.append(x_r)
                    current_z.append(z)
                    all_x.append(x_r)
                    all_z.append(z)
            else:
                # LINE segment — from trim_start to endpoint
                if not current_z:
                    current_z.append(trim_start_z)
                    current_x.append(trim_start_x)
                current_z.append(z)
                current_x.append(x_r)
                all_z.append(z)
                all_x.append(x_r)

            prev_x_r = x_r
            prev_z = z

            # Record where this segment's points end
            seg_point_ranges.append((_seg_start_idx, len(current_x)))

        # Flush remaining line sub-path
        if len(current_z) > 1:
            segments_to_draw.append((current_z, current_x))

        # Store for profile overlay in toolpath display
        self._profile_contour_segments = segments_to_draw

        if not all_z:
            return

        # Clear and redraw
        self._graph_widget.clear()
        self._graph_widget._setup_crosshair()

        try:
            stock_dia = self._stock_diameter.value()
            z_start = self._stock_z_start.value()
            z_end = self._stock_z_end.value()
            stock_r = stock_dia / 2.0

            if stock_r > 0 and z_start != z_end:
                # Stock rectangle (dashed outline)
                stock_pen = pg.mkPen(COLORS['graph_stock'], width=1, style=_QtCore.Qt.DashLine)
                stock_z = [z_end, z_start, z_start, z_end, z_end]
                stock_x = [0.0, 0.0, stock_r, stock_r, 0.0]
                self._graph_widget.plot(stock_z, stock_x, pen=stock_pen)

            # Profile segments (bold white) — each sub-path is its own PlotCurveItem
            # to avoid pyqtgraph bounding-box rendering artifacts.
            # Alpha=254 (not 255) disables pyqtgraph's segmented line optimization
            # which causes ghost line artifacts (pyqtgraph issue #2178).
            from PyQt5.QtGui import QColor
            profile_color = QColor(COLORS['graph_profile'])
            profile_color.setAlpha(254)
            profile_pen = pg.mkPen(profile_color, width=2)
            for seg_z, seg_x in segments_to_draw:
                self._graph_widget.plot(seg_z, seg_x, pen=profile_pen)

            # Highlight selected segment with a brighter, slightly thicker pen
            sel_idx = self._selected_segment_index
            if (0 <= sel_idx < len(seg_point_ranges)
                    and len(current_z) > 1):
                start_i, end_i = seg_point_ranges[sel_idx]
                # Include the previous point for continuity (the segment
                # starts from where the prior one ended)
                draw_start = max(0, start_i - 1) if start_i > 0 else start_i
                if end_i > draw_start:
                    hi_z = current_z[draw_start:end_i]
                    hi_x = current_x[draw_start:end_i]
                    highlight_color = QColor(COLORS['status_info'])
                    highlight_color.setAlpha(254)
                    highlight_pen = pg.mkPen(highlight_color, width=3)
                    item = self._graph_widget.plot(hi_z, hi_x, pen=highlight_pen)
                    item.setZValue(6)  # Above normal profile

            # X=0 centerline (subtle, behind profile)
            z_min = min(all_z) if all_z else z_end
            z_max = max(all_z) if all_z else z_start
            # Extend slightly beyond part
            z_extent = z_max - z_min
            cl_z_min = z_min - z_extent * 0.1
            cl_z_max = z_max + z_extent * 0.1
            cl_pen = pg.mkPen('#60809A', width=1, style=_QtCore.Qt.DashDotLine)
            self._graph_widget.plot([cl_z_min, cl_z_max], [0, 0], pen=cl_pen)

            # Auto-fit
            self._graph_widget.getViewBox().autoRange()
        except Exception:
            pass  # Preview is best-effort, never block UI

    def _validate_inline(self):
        """Show/clear validation errors as user types.

        Checks each numeric field's is_valid() and highlights the first error
        in the status label.
        """
        if self._state not in (ProgramState.BUILDING, ProgramState.IDLE):
            return

        # Ordered list of (field, label) for validation
        field_labels = [
            (self._stock_diameter, "Stock Diameter"),
            (self._stock_z_start, "Z Start"),
            (self._stock_z_end, "Z End"),
            (self._rough_doc, "Roughing DOC"),
            (self._rough_feed, "Roughing Feed"),
            (self._rough_fin_allowance, "Finish Allowance"),
            (self._rough_rpm, "Spindle RPM"),
            (self._finish_passes, "Finish Passes"),
            (self._finish_doc, "Finish DOC"),
            (self._finish_feed, "Finish Feed"),
        ]

        # Include pilot hole if in ID mode
        if self._block_type_combo.currentIndex() == 1:
            field_labels.append((self._stock_pilot_hole, "Pilot Hole Ø"))

        # Include peck length if peck is enabled
        if self._rough_peck_check.isChecked():
            field_labels.append((self._rough_peck_length, "Peck Length"))

        # Find first invalid field
        for field_widget, label in field_labels:
            if not field_widget.is_valid():
                self._status_label.setText(f"⚠ {label}: value out of range")
                self._status_label.setStyleSheet(
                    f"color: {COLORS['status_warning']}; font-size: {FONTS['small_size']}pt;"
                )
                return

        # All fields valid — clear error display
        if self._state == ProgramState.BUILDING:
            self._status_label.setText("Editing parameters...")
            self._status_label.setStyleSheet(
                f"color: {COLORS['text_secondary']}; font-size: {FONTS['small_size']}pt;"
            )
