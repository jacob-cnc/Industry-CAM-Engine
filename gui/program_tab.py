"""Program Tab for Industry CAM Engine.

Main machining program interface: input fields (left) + graph/playback (right).
Implements state machine: IDLE → BUILDING → READY → GENERATING → DISPLAYING ↔ PLAYING.

This tab is usable in offline mode (no LinuxCNC dependency).
"""

from enum import Enum, auto
from typing import Optional, List
import logging
import os

from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QSignalBlocker
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
        self._tool_resolver = None  # Callable[[int], Optional[ToolDef]] set by main_window
        self._generate_notes = []   # writer notes from the last Generate
        self._program_file_path: Optional[str] = None
        self._last_gcode_text: str = ""  # Last generated G-code for saving
        self._profile_contour_segments: list = []  # Profile overlay for toolpath display
        self._active_block_id: int = -1  # Currently displayed block ID
        self._selected_segment_index: int = -1  # Currently selected segment in builder
        # Corner-break tool state: point indices selected, graph overlay items.
        self._cb_selected: list = []
        self._cb_overlay_items: list = []
        self._cb_vertex_screen_cache = None
        self._setup_ui()
        self._connect_signals()
        self._update_ui_for_state()
        self._refresh_finish_doc()
        # Start with a default OD Profile block in the block list
        default_block = self._block_list.add_block("od_profile", select=True)
        self._active_block_id = default_block.block_id

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
        # A freshly loaded toolpath replaces the plot; put the tool's dots back.
        if getattr(self, "_btn_cb_tool", None) is not None:
            self._sync_cb_overlay()

    def get_stock_values(self) -> dict:
        """Return current stock field values as a dict."""
        return {
            "diameter": self._stock_diameter.value(),
            "x_start": self._stock_x_start.value(),
            "z_start": self._stock_z_start.value(),
            "z_end": self._stock_z_end.value(),
            "back_face_z": self._stock_back_z.value(),
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
            "passes": int(self._finish_passes.value()) if float(self._finish_passes.value()).is_integer() else self._finish_passes.value(),
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

    def set_tool_resolver(self, resolver) -> None:
        """Set the tool lookup callback for resolving tool numbers to ToolDef.

        Args:
            resolver: Callable[[int], Optional[ToolDef]] that looks up a tool
                      by number from the tool table.
        """
        self._tool_resolver = resolver

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

        # Programming column opens at 420 px every launch (nothing cut off at
        # that width); the user can drag it narrower (220 px min) or wider.
        # It also widens on its own when the segment table needs more room
        # (r column open for a selected ARC row) and returns afterwards; see
        # _fit_program_column.
        self._user_column_width = self.PROGRAM_COLUMN_WIDTH
        self._splitter.setSizes([self.PROGRAM_COLUMN_WIDTH, 1200])
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._left_panel.setMinimumWidth(220)
        self._splitter.splitterMoved.connect(self._on_splitter_moved)
        self._segment_list.required_width_changed.connect(
            lambda _w: self._fit_program_column())
        # Widening changes the chrome (scrollbars, margins) around the table:
        # re-check after every resize so the final fit has no overflow.
        self._segment_list.installEventFilter(self)
        for section in (self._section_parameters, self._section_profile):
            section.toggled.connect(lambda _e: self._fit_program_column())

    PROGRAM_COLUMN_WIDTH = 420   # px, default programming-column width

    def eventFilter(self, obj, event):  # noqa: N802 (Qt naming)
        from PyQt5.QtCore import QEvent
        if obj is getattr(self, "_segment_list", None) and \
                event.type() in (QEvent.Resize, QEvent.Show):
            self._fit_program_column()
        return super().eventFilter(obj, event)

    def _on_splitter_moved(self, pos: int, index: int):
        """A user drag sets the column width to return to."""
        self._user_column_width = self._splitter.sizes()[0]

    def _fit_program_column(self):
        """Column = the user's width, widened just enough that the segment
        table never overflows (e.g. +r column for a selected ARC row)."""
        sizes = self._splitter.sizes()
        if len(sizes) != 2 or sum(sizes) <= 0:
            return
        target = self._user_column_width
        seg = self._segment_list
        if seg.isVisible() and seg.width() > 0:
            chrome = self._left_panel.width() - seg.width()  # margins, scrollbar
            target = max(target, seg.required_width() + chrome)
        if target != sizes[0]:
            total = sum(sizes)
            self._splitter.setSizes([target, max(0, total - target)])

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
        from gui.components.block_list import BlockListWidget

        panel = QWidget()
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(4, 4, 4, 4)
        panel_layout.setSpacing(2)

        # File operations row (always visible)
        panel_layout.addWidget(self._build_file_ops_section())

        # Block list (multi-operation management) — inside a collapsible section
        from gui.components.collapsible_section import CollapsibleSection as CS
        # First view shows the whole workflow: Parameters and Profile Segments
        # open, the setup sections inside Parameters collapsed.
        self._section_blocks = CS("Blocks", expanded=False)
        self._block_list = BlockListWidget()
        self._section_blocks.add_widget(self._block_list)
        self._section_blocks.setMinimumHeight(240)

        # Parameters: one collapsible parent for everything defined before
        # the profile (Blocks, Stock, Roughing, Finishing, and the Threading/
        # Grooving/Parting panels). Collapse it once set, and Profile
        # Segments below gets nearly the whole column height. Order follows a
        # lathe program's decisions: toolpath type -> parameters -> profile.
        self._section_parameters = CS("Parameters", expanded=True)
        params_layout = self._section_parameters.content_layout()
        params_layout.setContentsMargins(8, 2, 0, 2)   # slight indent: nested
        # Exactly as tall as its contents: spare height goes to Profile
        # Segments (or below it), never into gaps between these sections.
        from PyQt5.QtWidgets import QSizePolicy
        self._section_parameters.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        params_layout.addWidget(self._section_blocks)

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

        # --- Toolpath Type section (hidden — replaced by block list, kept for internal state) ---
        self._section_type = CollapsibleSection("Toolpath Type", expanded=True)
        self._build_block_type_content(self._section_type)
        self._section_type.setVisible(False)
        params_layout.addWidget(self._section_type)

        # --- Stock section ---
        self._section_stock = CollapsibleSection("Stock", expanded=False)
        self._build_stock_content(self._section_stock)
        params_layout.addWidget(self._section_stock)

        # --- Roughing section ---
        self._section_roughing = CollapsibleSection("Roughing", expanded=False)
        self._build_roughing_content(self._section_roughing)
        params_layout.addWidget(self._section_roughing)

        # --- Finishing section ---
        self._section_finishing = CollapsibleSection("Finishing", expanded=False)
        self._build_finishing_content(self._section_finishing)
        params_layout.addWidget(self._section_finishing)

        # --- Threading Parameters section (hidden by default) ---
        from gui.components.threading_panel import ThreadingPanel
        self._section_threading = CollapsibleSection("Threading Parameters", expanded=True)
        self._threading_panel = ThreadingPanel()
        self._section_threading.add_widget(self._threading_panel)
        params_layout.addWidget(self._section_threading)
        self._section_threading.setVisible(False)

        # --- Grooving Parameters section (hidden by default) ---
        from gui.components.grooving_panel import GroovingPanel
        self._section_grooving = CollapsibleSection("Grooving Parameters", expanded=True)
        self._grooving_panel = GroovingPanel()
        self._section_grooving.add_widget(self._grooving_panel)
        params_layout.addWidget(self._section_grooving)
        self._section_grooving.setVisible(False)

        # --- Parting Parameters section (hidden by default) ---
        self._section_parting = CollapsibleSection("Parting Parameters", expanded=True)
        self._parting_panel = GroovingPanel(is_parting=True)
        self._section_parting.add_widget(self._parting_panel)
        params_layout.addWidget(self._section_parting)
        self._section_parting.setVisible(False)

        sections_layout.addWidget(self._section_parameters)

        # --- Profile Segments section (below Parameters; takes the height) ---
        self._section_profile = CollapsibleSection("Profile Segments", expanded=True)
        self._build_profile_content(self._section_profile)
        sections_layout.addWidget(self._section_profile, stretch=1)

        # Leftover height collects here, below the last section, so collapsed
        # headers stay packed at the top instead of being spread apart. An
        # expanded Profile Segments (stretch=1) still takes the height first.
        sections_layout.addStretch()

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
            min_value=-1000.0, max_value=0.0, decimals=4,
            default_value=0.0, suffix="in",
        ))
        self._stock_z_end.setReadOnly(True)
        self._stock_z_end.setToolTip("Derived from the active block contour, including arc extrema.")
        self._stock_z_end.set_value(0.0)
        form.addRow("Operation Z End:", self._stock_z_end)

        self._stock_back_z = NumericField(NumericFieldConfig(
            min_value=-1000.0, max_value=0.0, decimals=4,
            default_value=-1.0, suffix="in",
        ))
        self._stock_back_z.setToolTip("Physical back face of the stock, independent of cutting depth.")
        form.addRow("Stock Back Face:", self._stock_back_z)

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
            default_value=0.002, suffix="dia",
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
        form.addRow("Cutting passes:", self._finish_passes)

        self._finish_doc = NumericField(NumericFieldConfig(
            min_value=0.0, max_value=20.0, decimals=6,
            default_value=0.002, suffix="dia",   # = allowance 0.002 / 1 pass
        ))
        self._finish_doc.setReadOnly(True)
        self._finish_doc.setToolTip("Finish allowance divided by cutting passes; spring pass is excluded.")
        form.addRow("DOC (calculated):", self._finish_doc)

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
        """Populate the Profile Segments section.

        Corner Breaks toggle (top) switches between the segment builder and
        the corner-break tool panel; both fill the section's height.
        """
        from PyQt5.QtWidgets import QSizePolicy
        from gui.components.corner_break_panel import CornerBreakPanel

        self._btn_cb_tool = QPushButton("Corner Breaks")
        self._btn_cb_tool.setCheckable(True)
        self._btn_cb_tool.setToolTip(
            "Corner-break tool: pick vertices on the graph, then apply a chamfer "
            "or fillet. Click again to return to the segment builder.")
        self._btn_cb_tool.setStyleSheet(
            f"QPushButton {{ background: {COLORS['bg_surface']}; "
            f"border: 1px solid {COLORS['border_normal']}; border-radius: 5px; }}"
            f"QPushButton:checked {{ background: {COLORS['btn_primary']}; "
            f"border-color: {COLORS['border_focused']}; }}")
        section.add_widget(self._btn_cb_tool)

        self._segment_list = SegmentListWidget()
        # Make the segment list expand to fill available space
        self._segment_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        section.add_widget(self._segment_list)

        self._cb_panel = CornerBreakPanel()
        self._cb_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._cb_panel.setVisible(False)
        section.add_widget(self._cb_panel)

        # Builder and tool panel take the height (only one is visible).
        section.content_layout().setStretch(1, 1)
        section.content_layout().setStretch(2, 1)

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

        # Block list signals
        self._block_list.block_selected.connect(self._on_block_selected)
        self._block_list.block_added.connect(self._on_block_added)
        self._block_list.block_deleted.connect(self._on_block_deleted)

        # Threading/grooving panel changes
        self._threading_panel.params_changed.connect(self._on_field_changed)
        self._grooving_panel.params_changed.connect(self._on_field_changed)
        self._parting_panel.params_changed.connect(self._on_field_changed)

        # Stock fields
        self._stock_diameter.value_changed.connect(self._on_field_changed)
        self._stock_x_start.value_changed.connect(self._on_field_changed)
        self._stock_z_start.value_changed.connect(self._on_field_changed)
        self._stock_back_z.value_changed.connect(self._on_field_changed)
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
        self._finish_passes.value_changed.connect(self._refresh_finish_doc)
        self._rough_fin_allowance.value_changed.connect(self._refresh_finish_doc)
        self._finish_spring_pass.toggled.connect(self._on_field_changed)
        self._finish_feed.value_changed.connect(self._on_field_changed)
        self._finish_rpm.value_changed.connect(self._on_field_changed)

        # Segment list
        self._segment_list.segments_changed.connect(self._on_segments_changed)
        self._segment_list.corner_breaks_changed.connect(lambda *_: self._on_segments_changed(self.get_segments()))
        self._segment_list.selection_changed.connect(self._on_segment_selection_changed)

        # Corner-break tool (Esc anywhere on the Program tab leaves it)
        self._btn_cb_tool.toggled.connect(self._on_cb_tool_toggled)
        from PyQt5.QtWidgets import QShortcut
        from PyQt5.QtGui import QKeySequence
        self._cb_esc = QShortcut(QKeySequence(Qt.Key_Escape), self)
        self._cb_esc.setContext(Qt.WidgetWithChildrenShortcut)
        self._cb_esc.activated.connect(
            lambda: self._btn_cb_tool.setChecked(False) if self._btn_cb_tool.isChecked() else None)
        self._cb_panel.selection_changed.connect(self._on_cb_panel_selection)
        self._cb_panel.apply_requested.connect(self._on_cb_apply)
        self._cb_panel.remove_requested.connect(self._on_cb_remove)
        self._segment_list.segments_changed.connect(lambda *_: self._refresh_cb_state())
        self._segment_list.corner_breaks_changed.connect(lambda *_: self._refresh_cb_state())
        self._graph_widget.scene().sigMouseClicked.connect(self._on_graph_clicked_cb)
        # Vertex dots hide while a simulation plays and come back when it stops.
        self._sim_viewer.playing_changed.connect(lambda _playing: self._sync_cb_overlay())

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
        """Handle block type combo change — show/hide sections for the selected type."""
        is_id = index == 1  # "ID Profile"
        is_profile = index in (0, 1)  # OD or ID Profile
        is_threading = index == 2
        is_grooving = index == 3

        # Pilot hole (ID profile only)
        self._pilot_hole_label.setVisible(is_id)
        self._stock_pilot_hole.setVisible(is_id)

        # Show/hide profile-specific sections
        self._section_stock.setVisible(is_profile)
        self._section_roughing.setVisible(is_profile)
        self._section_finishing.setVisible(is_profile)
        self._section_profile.setVisible(is_profile)

        # Show/hide threading section
        self._section_threading.setVisible(is_threading)

        # Show/hide grooving/parting sections
        self._section_grooving.setVisible(is_grooving)
        self._section_parting.setVisible(False)  # Parting is a separate block type in the list

        self._on_field_changed()

    def _on_block_selected(self, block_id: int):
        """Handle block selection in the block list — save current, restore new."""
        block = self._block_list.get_block_by_id(block_id)
        if block is None:
            return

        # Save current block's field data before switching
        self._save_active_block_data()

        # Update the active block ID
        self._active_block_id = block_id

        # Map block_type to combo index
        type_to_index = {
            "od_profile": 0,
            "id_profile": 1,
            "threading_od": 2,
            "threading_id": 2,
            "grooving_od": 3,
            "grooving_id": 3,
            "parting": 3,
        }
        idx = type_to_index.get(block.block_type, 0)
        # Block the combo signal to avoid recursion
        self._block_type_combo.blockSignals(True)
        self._block_type_combo.setCurrentIndex(idx)
        self._block_type_combo.blockSignals(False)
        # Trigger the section visibility update (no _on_field_changed to avoid saving again)
        is_id = idx == 1
        is_profile = idx in (0, 1)
        is_threading = idx == 2
        is_grooving = idx == 3

        self._pilot_hole_label.setVisible(is_id)
        self._stock_pilot_hole.setVisible(is_id)
        self._section_stock.setVisible(is_profile)
        self._section_roughing.setVisible(is_profile)
        self._section_finishing.setVisible(is_profile)
        self._section_profile.setVisible(is_profile)
        self._section_threading.setVisible(is_threading)
        self._section_grooving.setVisible(is_grooving)
        self._section_parting.setVisible(False)

        # Restore the new block's saved field data
        self._restore_block_data(block)

    def _save_active_block_data(self):
        """Save current field values into the active block's params_data."""
        if self._active_block_id < 0:
            return
        block = self._block_list.get_block_by_id(self._active_block_id)
        if block is None:
            return

        if block.is_profile:
            block.params_data = {
                "stock": self.get_stock_values(),
                "roughing": self.get_roughing_values(),
                "finishing": self.get_finishing_values(),
                "segments": self.get_segments(),
                "corner_breaks": self.get_corner_breaks(),
            }
        elif block.is_threading:
            block.params_data = self._threading_panel.get_values()
        elif block.is_grooving:
            if block.block_type == "parting":
                block.params_data = self._parting_panel.get_values()
            else:
                block.params_data = self._grooving_panel.get_values()

    def _restore_block_data(self, block):
        """Restore field values from a block's params_data into the UI."""
        data = block.params_data
        if not data and not block.is_profile:
            return

        if block.is_profile:
            stock = data.get("stock", {})
            roughing = data.get("roughing", {})
            finishing = data.get("finishing", {})
            # Missing optional fields use widget defaults, never values left by
            # a different program or previously selected block.
            for key, field in (
                ("diameter", self._stock_diameter), ("x_start", self._stock_x_start),
                ("z_start", self._stock_z_start), ("x_park", self._stock_x_park),
                ("z_park", self._stock_z_park), ("pilot_hole_dia", self._stock_pilot_hole),
            ):
                field.set_value(stock.get(key, field._config.default_value))
            for key, field in (
                ("doc_dia", self._rough_doc), ("feed", self._rough_feed),
                ("fin_allowance", self._rough_fin_allowance), ("spindle_rpm", self._rough_rpm),
            ):
                field.set_value(roughing.get(key, field._config.default_value))
            strategy = roughing.get("strategy", "staircase").replace("_", " ").title()
            self._rough_strategy.setCurrentText(strategy)
            self._rough_peck_check.setChecked(bool(roughing.get("peck_enabled", False)))
            self._rough_peck_length.set_value(roughing.get("peck_length") or self._rough_peck_length._config.default_value)
            rough_tool = int(roughing.get("tool_number", block.tool_number))
            self._rough_tool_num.setValue(rough_tool)
            self._finish_tool_num.setValue(int(finishing.get("tool_number", rough_tool)))
            for key, field in (
                ("passes", self._finish_passes), ("feed", self._finish_feed),
                ("spindle_rpm", self._finish_rpm),
            ):
                field.set_value(finishing.get(key, field._config.default_value))

            # Restore segments
            segments = data.get("segments", [])
            corner_breaks = data.get("corner_breaks", [])
            self._segment_list.set_segments(segments, corner_breaks)
            self._refresh_operation_z_end(segments)
            self._finish_spring_pass.setChecked(bool(finishing.get("spring_pass", False)))
            self._refresh_finish_doc()

        elif block.is_threading:
            self._threading_panel.set_values(data)
        elif block.is_grooving:
            if block.block_type == "parting":
                self._parting_panel.set_values(data)
            else:
                self._grooving_panel.set_values(data)

    def _on_block_added(self, block_type: str):
        """Handle a new block being added to the list."""
        block = self._block_list.get_selected_block()
        if block:
            self._on_field_changed()

    def _on_block_deleted(self, block_id: int):
        """Handle a block being removed from the list."""
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
        self._refresh_operation_z_end(segments)
        self._on_field_changed()

    def _refresh_operation_z_end(self, segments=None):
        from pipeline.model_builder import profile_from_fields
        from geometry.zone_builder import contour_z_end
        if segments is None:
            segments = self.get_segments()
        if not segments:
            self._stock_z_end.set_value(0.0)
            self._stock_z_end.setText("—")
            return
        try:
            profile = profile_from_fields(segments, self._get_machining_mode(), self.get_corner_breaks())
            self._stock_z_end.set_value(contour_z_end(profile))
            self._stock_z_end.setToolTip("Derived from the active block contour, including arc extrema.")
        except (ValueError, RuntimeError) as exc:
            self._stock_z_end.set_value(0.0)
            self._stock_z_end.setText("Invalid contour")
            self._stock_z_end.setToolTip(str(exc))

    def _refresh_finish_doc(self, *_):
        from models.params import FinishingParams
        value = self._finish_passes.value()
        try:
            if not float(value).is_integer():
                raise ValueError("Finish passes must be a positive integer.")
            doc = FinishingParams.doc_from_allowance(self._rough_fin_allowance.value(), int(value))
            self._finish_doc.set_value(doc)
        except ValueError as exc:
            self._finish_doc.setText("Invalid finish settings")
            self._finish_doc.setToolTip(str(exc))

    def _on_segment_selection_changed(self, seg_index: int):
        """Segment selection changed in the builder — highlight on graph."""
        self._selected_segment_index = seg_index
        self._update_preview()

    def _on_peck_toggled(self, checked: bool):
        """Enable/disable peck length field based on checkbox."""
        self._rough_peck_length.setEnabled(checked)
        self._on_field_changed()

    def _on_generate_clicked(self):
        """Generate button clicked — execute all visible blocks and combine output.

        Iterates all enabled+visible blocks in order. Profile blocks run the
        full pipeline. Threading/grooving blocks run their respective planners.
        Tool changes (M0 + M6) are inserted between blocks with different tools.
        """
        if self._state not in (ProgramState.READY, ProgramState.BUILDING):
            return

        self.set_state(ProgramState.GENERATING)
        self.generate_requested.emit()

        # Save the currently displayed block's data before generating
        self._save_active_block_data()

        stage = "block_iteration"
        try:
            blocks = self._block_list.get_blocks()
            # Filter to visible + enabled blocks
            active_blocks = [b for b in blocks if b.enabled and b.visible]

            if not active_blocks:
                self._status_label.setText("No visible blocks to generate")
                self._status_label.setStyleSheet(
                    f"color: {COLORS['status_warning']}; font-size: {FONTS['small_size']}pt;"
                )
                self.set_state(ProgramState.READY)
                return

            # Generate each block — collect G-code sections and the first plan_result
            all_gcode_sections = []
            self._generate_notes = []
            first_plan_result = None
            prev_tool_number = None
            writer = GCodeWriter()

            for block_idx, block in enumerate(active_blocks):
                stage = f"block_{block_idx + 1}_{block.block_type}"

                if block.is_profile:
                    # Profile block — run the full pipeline
                    gcode_text, plan_result = self._generate_profile_block(block, writer)
                    if gcode_text is None:
                        # Error occurred — already displayed to user
                        self.set_state(ProgramState.READY)
                        return
                    if first_plan_result is None:
                        first_plan_result = plan_result
                    all_gcode_sections.append(gcode_text)

                elif block.is_threading:
                    # Threading block — emit G76 section
                    gcode_lines = self._generate_threading_block(block, writer, prev_tool_number)
                    all_gcode_sections.append("\n".join(gcode_lines) + "\n")

                elif block.is_grooving:
                    # Grooving/parting block — emit plunge section
                    gcode_lines = self._generate_grooving_block(block, writer, prev_tool_number)
                    all_gcode_sections.append("\n".join(gcode_lines) + "\n")

                prev_tool_number = block.tool_number

            # Combine all sections
            # For multi-block: the first profile block provides the full program
            # (with header, safety line, etc). Subsequent blocks are appended
            # before the program end.
            if len(all_gcode_sections) == 1:
                combined_gcode = all_gcode_sections[0]
            else:
                # First block is the full program — inject subsequent blocks before END
                combined_gcode = self._combine_gcode_sections(all_gcode_sections)

            # Load into viewer using the combined G-code
            stage = "graph_convert"
            from outputs.graph_adapter import convert_from_moves
            parsed_moves = parse_gcode(combined_gcode)
            if parsed_moves:
                graph_data = convert_from_moves(parsed_moves)
            else:
                graph_data = graph_convert(first_plan_result)

            stage = "sim_load"
            from gui.components.sim_viewer import parse_gcode_for_sim
            sim_moves = parse_gcode_for_sim(combined_gcode)
            self._sim_viewer.load(graph_data, combined_gcode, sim_moves)

            if hasattr(self, '_profile_contour_segments') and self._profile_contour_segments:
                self._sim_viewer.set_profile_overlay(self._profile_contour_segments)

            # Emit signals
            self._last_gcode_text = combined_gcode
            self.gcode_generated.emit(combined_gcode)
            if first_plan_result:
                self.plan_result_ready.emit(first_plan_result)

            self.set_state(ProgramState.DISPLAYING)

            block_count = len(active_blocks)
            ready = (f"Program ready — {block_count} block{'s' if block_count > 1 else ''}, "
                     f"{len(sim_moves)} moves")
            notes = getattr(self, "_generate_notes", [])
            if notes:
                # Not an error: the program runs. The part differs from the
                # drawing (e.g. a corner radius set by the tool nose).
                self._status_label.setText(
                    f"⚠ {ready} — {len(notes)} note{'s' if len(notes) > 1 else ''} "
                    f"(hover for details)")
                self._status_label.setToolTip("\n\n".join(notes))
                self._status_label.setStyleSheet(
                    f"color: {COLORS['status_warning']}; font-size: {FONTS['small_size']}pt;")
            else:
                self._status_label.setText(ready)
                self._status_label.setToolTip("")
                self._status_label.setStyleSheet(
                    f"color: {COLORS['text_secondary']}; font-size: {FONTS['small_size']}pt;"
                )

        except Exception as e:
            import traceback as tb_module
            tb_str = tb_module.format_exc()
            logger.error("Generation failed at stage '%s': %s\n%s", stage, e, tb_str)

            error_msg = str(e) if str(e) else type(e).__name__
            self._status_label.setText(f"Error: {error_msg[:80]}")
            self._status_label.setStyleSheet(
                f"color: {COLORS['status_error']}; font-size: {FONTS['small_size']}pt;"
            )

            from gui.components.error_dialog import GenerationErrorDialog
            dlg = GenerationErrorDialog(self)
            dlg.show_exception(e, tb_str, stage=stage)

            self.set_state(ProgramState.READY)

    def _generate_profile_block(self, block, writer):
        """Generate a profile block through the full pipeline.

        Returns (gcode_text, plan_result) or (None, None) on error.
        """
        data = block.params_data
        if not data or not data.get("segments"):
            self._status_label.setText(f"Error: Block '{block.display_label}' has no segments")
            self._status_label.setStyleSheet(
                f"color: {COLORS['status_error']}; font-size: {FONTS['small_size']}pt;"
            )
            return None, None

        stock = data.get("stock", {})
        roughing = data.get("roughing", {})
        finishing = data.get("finishing", {})
        segments = data.get("segments", [])
        corner_breaks = data.get("corner_breaks", [])

        # Resolve tool
        tool_num = roughing.get("tool_number", block.tool_number)
        tool_def = None
        if self._tool_resolver:
            # The tool table is authoritative: never substitute another tool or
            # a built-in default (TNR would silently differ from the machine).
            tool_def = self._require_tool(tool_num, block, "roughing")
        if tool_def is None:
            tool_def = self._active_tool
        if tool_def is None:
            tool_def = ToolDef(
                tool_number=tool_num,
                nose_radius=0.016, tip_angle=80.0, edge_length=0.375,
                orientation=ToolOrientation.OD_FRONT_RIGHT,
                direction=ToolDirection.RIGHT,
                tool_type=ToolType.TURNING,
                description=f"T{tool_num}",
            )

        # Determine mode from block type
        mode = "id" if block.block_type == "id_profile" else "od"

        profile, stock_def, roughing_params, finishing_params = build_from_fields(
            segments=segments,
            stock_dia=stock.get("diameter", 1.0),
            x_start=stock.get("x_start", 0.0),
            z_start=stock.get("z_start", 0.1),
            z_end=stock.get("z_end", -1.0),
            stock_back_z=self._stock_back_z.value(),
            mode=mode,
            pilot_hole_dia=stock.get("pilot_hole_dia", 0.0),
            doc_dia=roughing.get("doc_dia", 0.030),
            feed=roughing.get("feed", 0.005),
            strategy=roughing.get("strategy", "staircase"),
            fin_allowance=roughing.get("fin_allowance", 0.010),
            peck_enabled=roughing.get("peck_enabled", False),
            peck_length=roughing.get("peck_length", None),
            spindle_rpm=roughing.get("spindle_rpm", 1200.0),
            finish_passes=finishing.get("passes", 1),
            finish_doc_dia=finishing.get("doc_dia", 0.002),
            finish_feed=finishing.get("feed", 0.003),
            finish_spring_pass=bool(finishing.get("spring_pass", False)),
            tool_def=tool_def,
            x_park=stock.get("x_park", 3.0),
            z_park=stock.get("z_park", 3.0),
            corner_breaks=corner_breaks,
        )

        # Resolve finish tool
        finish_tool_def = None
        finish_tool_num = finishing.get("tool_number", tool_num)
        if finish_tool_num != tool_def.tool_number:
            if self._tool_resolver:
                finish_tool_def = self._require_tool(finish_tool_num, block, "finishing")
            if finish_tool_def is None:
                finish_tool_def = ToolDef(
                    tool_number=finish_tool_num,
                    nose_radius=0.008, tip_angle=35.0, edge_length=0.375,
                    orientation=ToolOrientation.OD_FRONT_RIGHT,
                    direction=ToolDirection.RIGHT,
                    tool_type=ToolType.TURNING,
                    description=f"Finish T{finish_tool_num}",
                )

        for role, td in (("roughing", tool_def), ("finishing", finish_tool_def)):
            if td is not None:
                self._check_tool_suits_mode(td, mode, block, role)

        pipeline_result = pipeline_execute(
            profile=profile, stock=stock_def, tool=tool_def,
            roughing_params=roughing_params, finishing_params=finishing_params,
            finish_tool=finish_tool_def,
        )

        if pipeline_result.status not in (PipelineStatus.SUCCESS, PipelineStatus.SUCCESS_WITH_WARNINGS):
            errors = [v for v in pipeline_result.validations if v.severity.value == "error"]
            first_msg = errors[0].message if errors else "Pipeline blocked"
            self._status_label.setText(f"Error in '{block.display_label}': {first_msg}")
            self._status_label.setStyleSheet(
                f"color: {COLORS['status_error']}; font-size: {FONTS['small_size']}pt;"
            )
            from gui.components.error_dialog import GenerationErrorDialog
            dlg = GenerationErrorDialog(self)
            dlg.show_validation_errors(pipeline_result.validations, stage=f"pipeline ({block.display_label})")
            return None, None

        plan_result = pipeline_result.plan_result
        block_writer = GCodeWriter()
        gcode_text = block_writer.write(plan_result, unit_mode=unit_state.mode.value)
        for note in block_writer.notes:
            logger.warning("Generate note (%s): %s", block.display_label, note)
            self._generate_notes.append(f"{block.display_label}: {note}")
        return gcode_text, plan_result

    def _generate_threading_block(self, block, writer, prev_tool_number):
        """Generate G-code lines for a threading block."""
        from models.program import ThreadingParams
        from planners.threading_planner import ThreadingPlanner

        data = block.params_data
        if not data:
            return [f"; === THREADING BLOCK (no parameters set) ==="]

        lines = []

        # Tool change if needed
        if prev_tool_number is not None and block.tool_number != prev_tool_number:
            tool_def = self._resolve_tool_for_block(block)
            rpm = data.get("spindle_rpm", 400)
            lines.extend(writer.write_tool_change(tool_def, rpm))

        # Build ThreadingParams
        params = ThreadingParams(
            thread_standard=data.get("thread_standard", "UNC"),
            designation=data.get("designation", ""),
            major_diameter=data.get("major_diameter", 0.5),
            pitch=data.get("pitch", 1.0 / 13.0),
            thread_depth=data.get("thread_depth", 0.0416),
            start_z=data.get("start_z", 0.05),
            end_z=data.get("end_z", -0.75),
            infeed_method=data.get("infeed_method", "modified_flank"),
            num_passes=data.get("num_passes", 6),
            spring_passes=data.get("spring_passes", 2),
            chamfer_threads=data.get("chamfer_threads", 1.0),
            is_internal=block.block_type == "threading_id",
            spindle_rpm=data.get("spindle_rpm", 400),
            tool_number=block.tool_number,
            num_starts=data.get("num_starts", 1),
        )

        tool_def = self._resolve_tool_for_block(block)
        # Use a reasonable stock diameter for safe_x calculation
        stock_dia = data.get("major_diameter", 0.5) + 0.1
        lines.extend(writer.write_threading_block(
            params, tool_def, stock_dia=stock_dia,
            unit_mode=unit_state.mode.value,
        ))
        return lines

    def _generate_grooving_block(self, block, writer, prev_tool_number):
        """Generate G-code lines for a grooving/parting block."""
        from models.program import GroovingParams

        data = block.params_data
        if not data:
            return [f"; === GROOVING BLOCK (no parameters set) ==="]

        lines = []

        # Tool change if needed
        if prev_tool_number is not None and block.tool_number != prev_tool_number:
            tool_def = self._resolve_tool_for_block(block)
            rpm = data.get("spindle_rpm", 800)
            lines.extend(writer.write_tool_change(tool_def, rpm))

        params = GroovingParams(
            groove_type=data.get("groove_type", "single"),
            is_internal=block.block_type == "grooving_id",
            z_start=data.get("z_start", -0.5),
            z_end=data.get("z_end", -0.625),
            groove_depth=data.get("groove_depth", 0.100),
            start_diameter=data.get("start_diameter", 1.0),
            peck_enabled=data.get("peck_enabled", True),
            peck_depth=data.get("peck_depth", 0.030),
            peck_retract=data.get("peck_retract", 0.010),
            feed=data.get("feed", 0.002),
            spindle_rpm=data.get("spindle_rpm", 800),
            tool_number=block.tool_number,
            blade_width=data.get("blade_width", 0.125),
        )

        tool_def = self._resolve_tool_for_block(block)
        stock_dia = data.get("start_diameter", 1.0) + 0.25
        lines.extend(writer.write_grooving_block(
            params, tool_def, stock_dia=stock_dia,
            unit_mode=unit_state.mode.value,
        ))
        return lines

    # LinuxCNC Fig 2.16 (front-tool lathe): cutting corner toward -X (OD) or +X (ID)
    _OD_ORIENTATIONS = {1, 2, 6}
    _ID_ORIENTATIONS = {3, 4, 8}

    def _check_tool_suits_mode(self, tool_def, mode: str, block, role: str) -> None:
        """Refuse a tool that cannot cut this side of the part.

        Owner slip 2026-11-09: a boring bar (T1, Q3) was selected for an OD
        profile and the program generated without complaint. The orientation
        says which way the cutting corner points; Q5/Q7/Q9 (pointing along Z,
        round) are not checked.
        """
        from models.tool import ToolType
        q = int(getattr(tool_def.orientation, "value", tool_def.orientation) or 0)
        name = f"T{tool_def.tool_number}"
        if mode == "od" and (tool_def.tool_type == ToolType.BORING or q in self._ID_ORIENTATIONS):
            raise ValueError(
                f"{name} ({role}) is an inside/boring tool (Q{q}) but block "
                f"'{block.display_label}' is an OD profile. Choose an OD turning tool.")
        if mode == "id" and q in self._OD_ORIENTATIONS:
            raise ValueError(
                f"{name} ({role}) is an OD tool (Q{q}) but block '{block.display_label}' "
                f"is an ID profile. Choose a boring tool (Q3/Q4/Q8).")

    def _require_tool(self, tool_number: int, block, role: str):
        """Resolve a tool from the Tools tab table or fail generation clearly."""
        tool_def = self._tool_resolver(tool_number)
        if tool_def is None:
            raise ValueError(
                f"Tool T{tool_number} ({role}) for block '{block.display_label}' is not in "
                f"the tool table. Add it in the Tools tab or choose another tool, then "
                f"regenerate.")
        return tool_def

    def _resolve_tool_for_block(self, block):
        """Look up ToolDef for a block from the tool table."""
        tool_def = None
        if self._tool_resolver:
            tool_def = self._require_tool(block.tool_number, block, "block")
        if tool_def is None:
            from models.tool import ToolType as TT
            tool_def = ToolDef(
                tool_number=block.tool_number,
                nose_radius=0.0, tip_angle=60.0, edge_length=0.375,
                orientation=ToolOrientation.OD_FRONT_RIGHT,
                direction=ToolDirection.RIGHT,
                tool_type=TT.TURNING,
                description=f"T{block.tool_number}",
            )
        return tool_def

    def _combine_gcode_sections(self, sections):
        """Combine multiple G-code sections into one program.

        The first section is assumed to be a complete program (with header,
        safety preamble, and M2 ending). Subsequent sections are inserted
        before the program end (before the '=== PROGRAM END ===' marker).
        """
        if len(sections) <= 1:
            return sections[0] if sections else ""

        first = sections[0]
        # Find the program end marker in the first section
        end_marker = "; === PROGRAM END ==="
        lines = first.split("\n")
        insert_idx = None
        for i, line in enumerate(lines):
            if end_marker in line:
                insert_idx = i
                break

        if insert_idx is None:
            # No marker found — just concatenate
            return "\n".join(sections)

        # Insert subsequent sections before the end marker
        before = lines[:insert_idx]
        after = lines[insert_idx:]

        # Add subsequent block sections
        for section in sections[1:]:
            before.append("")
            before.extend(section.strip().split("\n"))

        return "\n".join(before + [""] + after) + "\n"

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
            self._stock_z_start, self._stock_z_end, self._stock_back_z,
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

        Multi-block format: saves all blocks with their params_data.
        """
        import json

        # Save the active block's current field state first
        self._save_active_block_data()

        # Serialize all blocks
        blocks = self._block_list.get_blocks()
        blocks_data = []
        for block in blocks:
            block_entry = {
                "block_id": block.block_id,
                "block_type": block.block_type,
                "tool_number": block.tool_number,
                "enabled": block.enabled,
                "label": block.label,
                "visible": block.visible,
                "params": block.params_data,
            }
            blocks_data.append(block_entry)

        data = {
            "version": 2,
            "stock_back_face_z": self._stock_back_z.value(),
            "active_block_id": self._active_block_id,
            "blocks": blocks_data,
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
        """Restore legacy or multi-block conversation, including the edited block."""
        from copy import deepcopy
        from models.program import ProgramBlock
        from gui.components.block_list import BLOCK_TYPE_INFO
        from outputs.graph_adapter import GraphData
        if not isinstance(data, dict):
            raise ValueError("Conversational program must be a JSON object.")
        version = data.get("version", 1)
        if version not in (1, 2):
            raise ValueError(f"Unsupported conversational program version: {version}")
        if version == 1:
            if not isinstance(data.get("segments"), list):
                raise ValueError("This JSON has no conversational profile segments.")
            legacy_type = data.get("block_type", "ID Profile" if data.get("stock", {}).get("mode") == "id" else "OD Profile")
            type_map = {"OD Profile": "od_profile", "ID Profile": "id_profile",
                        "od_profile": "od_profile", "id_profile": "id_profile"}
            if legacy_type not in type_map:
                raise ValueError(f"Unsupported legacy profile type: {legacy_type}")
            blocks_data = [dict(block_id=1, block_type=type_map[legacy_type],
                                tool_number=data.get("roughing", {}).get("tool_number", 1), params=data)]
        else:
            blocks_data = data.get("blocks")
            if not isinstance(blocks_data, list):
                raise ValueError("Conversational program has no block list.")
        blocks = []
        ids = set()
        for index, entry in enumerate(blocks_data):
            if not isinstance(entry, dict):
                raise ValueError("Every conversational block must be an object.")
            block_id = entry.get("block_id", index + 1)
            if type(block_id) is not int or block_id < 0 or block_id in ids:
                raise ValueError("Conversational block IDs must be unique nonnegative integers.")
            ids.add(block_id)
            block_type = entry.get("block_type", "od_profile")
            if block_type not in BLOCK_TYPE_INFO:
                raise ValueError(f"Unsupported conversational block type: {block_type}")
            params = entry.get("params", {})
            if not isinstance(params, dict):
                raise ValueError("Conversational block parameters must be an object.")
            if block_type in ("od_profile", "id_profile"):
                for key in ("stock", "roughing", "finishing"):
                    if key in params and not isinstance(params[key], dict):
                        raise ValueError(f"Block {key} must be an object.")
                if not isinstance(params.get("segments", []), list):
                    raise ValueError("Profile segments must be a list.")
                if params.get("roughing", {}).get("strategy", "staircase") not in ("staircase", "offset_contour"):
                    raise ValueError("Unsupported saved roughing strategy.")
            block = ProgramBlock(block_id=block_id, block_type=block_type,
                tool_number=entry.get("tool_number", 1), enabled=entry.get("enabled", True),
                label=entry.get("label", ""), visible=entry.get("visible", True))
            block.params_data = deepcopy(params)
            blocks.append(block)
        selected = next((b for b in blocks if b.block_id == data.get("active_block_id")), None)
        if selected is None:
            selected = next((b for b in blocks if b.enabled and b.visible and b.params_data
                and (not b.is_profile or b.params_data.get("segments"))), None)
        if selected is None and blocks:
            selected = next((b for b in blocks if b.enabled and b.visible), blocks[0])
        depths = [b.params_data.get("stock", {}).get("back_face_z",
                  b.params_data.get("stock", {}).get("z_end", -1.0)) for b in blocks if b.is_profile]
        back_face = data.get("stock_back_face_z", min(depths, default=-1.0))
        # Suppress selection callbacks while replacing models. In particular,
        # never save fields from the old program into a new block with the same ID.
        self._active_block_id = -1
        self._stock_back_z.set_value(back_face)
        with QSignalBlocker(self._block_list):
            self._block_list.set_blocks(blocks)
            if selected is not None:
                self._block_list.select_block(selected.block_id)
        if selected is not None:
            self._on_block_selected(selected.block_id)
        else:
            self._block_type_combo.setCurrentIndex(0)
            blank = ProgramBlock(block_id=0, block_type="od_profile")
            blank.params_data = dict(stock={}, roughing={}, finishing={}, segments=[])
            self._restore_block_data(blank)
        # A JSON open restores conversation; it must not retain another program's
        # cached output or save it as the newly loaded program's companion .ngc.
        self._last_gcode_text = ""
        self._profile_contour_segments = []
        self._selected_segment_index = -1
        collapsed = self._sim_viewer._gcode_collapsed
        self._sim_viewer.load(GraphData(), "", [])
        self._sim_viewer._sim_stop()
        if collapsed:
            self._sim_viewer._splitter.setSizes([1000, 0])
            self._sim_viewer._gcode_collapsed = True
            self._sim_viewer._btn_toggle_code.setText("Show Code")
        self.set_state(ProgramState.BUILDING if blocks else ProgramState.IDLE)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _od_corner_result(self, segments=None, corner_breaks=None):
        """Engine corner-break result (geometry + per-vertex reports) for the
        current profile, or None for ID / an incomplete profile."""
        if self._get_machining_mode() != "od":
            return None
        if segments is None:
            segments = self._segment_list.get_segments()
        if corner_breaks is None:
            corner_breaks = self._segment_list.get_corner_breaks()
        if not segments:
            return None
        try:
            from pipeline.model_builder import profile_from_fields
            from geometry.corner_breaks_od import build_od_corner_coords
            profile = profile_from_fields(segments, "od", corner_breaks)
            return build_od_corner_coords(profile)
        except Exception:
            logger.debug("OD corner-break solve failed for preview", exc_info=True)
            return None

    def _od_corner_geometry(self, segments, corner_breaks) -> dict:
        result = self._od_corner_result(segments, corner_breaks)
        return result.geometry if result is not None else {}

    # ------------------------------------------------------------------
    # Corner-break tool (vertex model)
    # ------------------------------------------------------------------

    def _sharp_vertex_points(self):
        """(points, prev, next) in graph coordinates (z, r) for every vertex
        V1..V(n-1) = point indices 0..n-2. prev of V1 is the implied face
        start on the centreline."""
        segs = self._segment_list.get_segments()
        pts = [(float(s.get("z", 0.0)), float(s.get("x", 0.0)) / 2.0) for s in segs]
        if len(pts) < 2:
            return [], [], []
        verts = pts[:-1]
        prev = [(pts[0][0], 0.0)] + pts[:-2]
        nxt = pts[1:]
        return verts, prev, nxt

    def _refresh_cb_state(self):
        """Recompute engine status per vertex: row badges always, and the
        tool's vertex list when the tool is on."""
        segs = self._segment_list.get_segments()
        breaks = self._segment_list.get_corner_breaks()
        result = self._od_corner_result(segs, breaks)
        reports = {r.vertex - 1: r for r in (result.reports if result else [])}
        self._flag_fillets_within_nose_radius(result, reports)
        notes = {i: (r.status, r.message) for i, r in reports.items()}
        self._segment_list.set_vertex_notes(notes)
        if not self._btn_cb_tool.isChecked():
            return
        kinds = {}
        if result is not None:
            try:
                from pipeline.model_builder import profile_from_fields
                from geometry.corner_breaks_od import od_vertex_kinds
                kinds = od_vertex_kinds(profile_from_fields(segs, "od", breaks))
            except Exception:
                kinds = {}
        is_id = self._get_machining_mode() == "id"
        rows = []
        for i in range(max(0, len(segs) - 1)):
            rep = reports.get(i)
            badge = SegmentListWidget.break_badge(breaks[i] if i < len(breaks) else None)
            if is_id and badge:
                status, msg = "unvalidated", "ID corner breaks are not validated yet (legacy method)."
            elif rep is not None:
                status, msg = rep.status, rep.message
            else:
                status, msg = "ok", ""
            rows.append({"index": i, "z": float(segs[i].get("z", 0.0)),
                         "x_dia": float(segs[i].get("x", 0.0)),
                         "corner": "" if is_id else kinds.get(i, ""),
                         "badge": badge, "status": status, "message": msg})
        self._cb_panel.set_vertices(rows)

    def _finish_nose_radius(self) -> float:
        """Nose radius of the block's finishing tool (0 if unknown)."""
        if not self._tool_resolver:
            return 0.0
        try:
            tool = self._tool_resolver(self._finish_tool_num.value())
        except Exception:
            tool = None
        return float(getattr(tool, "nose_radius", 0.0) or 0.0)

    def _flag_fillets_within_nose_radius(self, result, reports: dict) -> None:
        """Mark concave fillets the finishing tool cannot follow.

        The writer cuts a concave fillet with R <= the nose radius as a sharp
        corner (the nose leaves its own radius there); say so on the vertex
        before Generate. Reports are updated in place (status 'tool radius').
        """
        tnr = self._finish_nose_radius()
        if result is None or tnr <= 0:
            return
        for i, rep in reports.items():
            if rep.break_type != "fillet" or rep.corner != "concave" \
                    or rep.status in ("skipped", "unvalidated"):
                continue
            g = result.geometry.get(i)
            radius = g.radius if g is not None and g.radius > 0 else rep.requested
            if radius > tnr + 0.0001:
                continue
            extra = (f"{rep.label}: concave R{radius:.4f} is not larger than the finishing "
                     f"tool's nose radius ({tnr:.4f}). It will be cut as a sharp inside "
                     f"corner: the tool leaves R{tnr:.4f} there, not R{radius:.4f}.")
            rep.message = f"{rep.message}\n{extra}" if rep.message else extra
            rep.status = "tool radius"

    CB_TOOL_LABEL_OFF = "Corner Breaks"
    CB_TOOL_LABEL_ON = "Done - Back to Segment Builder  (Esc)"

    def _on_cb_tool_toggled(self, on: bool):
        # The same button leaves the tool: say so while it is on.
        self._btn_cb_tool.setText(self.CB_TOOL_LABEL_ON if on else self.CB_TOOL_LABEL_OFF)
        self._segment_list.setVisible(not on)
        self._cb_panel.setVisible(on)
        if not on:
            self._cb_selected = []
        self._refresh_cb_state()
        self._update_preview()
        self._sync_cb_overlay()

    def _cb_overlay_blocked(self) -> bool:
        """True while a simulation is playing: no dots, no picking."""
        viewer = getattr(self, "_sim_viewer", None)
        return bool(viewer is not None and viewer.is_playing())

    def _remove_cb_overlay(self):
        for item in self._cb_overlay_items:
            try:
                self._graph_widget.removeItem(item)
            except Exception:
                pass                             # already gone with a plot clear
        self._cb_overlay_items = []

    def _sync_cb_overlay(self):
        """Show the tool's ghost profile and vertex dots whenever the tool is
        open and no simulation is playing, including over a generated
        toolpath. In BUILDING/READY the preview redraw owns the overlay."""
        if self._state in (ProgramState.BUILDING, ProgramState.READY):
            return
        self._remove_cb_overlay()
        if not self._btn_cb_tool.isChecked() or self._cb_overlay_blocked():
            return
        import pyqtgraph as pg
        self._draw_cb_overlay(pg)

    def _on_cb_panel_selection(self, indices: list):
        self._cb_selected = list(indices)
        self._draw_cb_selection()

    def _apply_vertex_breaks(self, new_breaks: list, touched: list):
        """Store the breaks, then pop up a note for every vertex the engine
        had to adjust: the ones just edited, and any other vertex whose
        status changed because of them."""
        segs = self._segment_list.get_segments()
        before = self._od_corner_result(segs, self._segment_list.get_corner_breaks())
        before_status = {r.vertex - 1: r.status for r in (before.reports if before else [])}
        self._segment_list.set_vertex_breaks(new_breaks)
        after = self._od_corner_result(segs, new_breaks)

        def notes_for(result):
            out = []
            for rep in (result.reports if result else []):
                i = rep.vertex - 1
                if rep.status != "ok" and (i in touched or before_status.get(i) != rep.status):
                    out.append(rep)
            return out

        notes = notes_for(after)
        # NX-style is the default. If fillets were cut short (leaving a kink),
        # offer to smooth them: roll each onto its earlier neighbour.
        smoothable = [r for r in (after.smoothable if after else []) if r in notes]
        if smoothable:
            listing = "\n\n".join(r.message for r in notes)
            answer = QMessageBox.question(
                self, "Corner breaks trimmed",
                f"{listing}\n\nSmooth the trimmed fillet"
                f"{'s' if len(smoothable) > 1 else ''} "
                f"({', '.join(r.label for r in smoothable)})?\n\n"
                "Yes: the fillet keeps its radius and rolls onto the earlier break "
                "(tangent, no kink; the earlier break is shortened or extended).\n"
                "No: keep it cut short (NX style).",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer == QMessageBox.Yes:
                breaks = self._segment_list.get_corner_breaks()
                for r in smoothable:
                    if breaks[r.vertex - 1]:
                        breaks[r.vertex - 1]["trim"] = "smooth"
                self._segment_list.set_vertex_breaks(breaks)
                result = self._od_corner_result(segs, breaks)
                QMessageBox.information(self, "Corner breaks smoothed",
                                        "\n\n".join(r.message for r in notes_for(result)))
            return
        if notes:
            QMessageBox.information(self, "Corner breaks adjusted",
                                    "\n\n".join(r.message for r in notes))

    def _on_cb_apply(self, kind: str, size: float):
        idx = [i for i in self._cb_selected]
        if not idx:
            QMessageBox.information(self, "Corner breaks",
                                    "Select one or more vertices first (click them on "
                                    "the graph or in the list).")
            return
        if not size or size <= 0:
            QMessageBox.warning(self, "Corner breaks", "Enter a size greater than zero.")
            return
        breaks = self._segment_list.get_corner_breaks()
        for i in idx:
            if i < len(breaks):
                breaks[i] = ({"type": "chamfer", "size": size, "angle": 45.0, "radius": 0.0}
                             if kind == "chamfer" else
                             {"type": "fillet", "radius": size, "size": 0.0, "angle": 45.0})
        self._apply_vertex_breaks(breaks, idx)

    def _on_cb_remove(self):
        breaks = self._segment_list.get_corner_breaks()
        for i in self._cb_selected:
            if i < len(breaks):
                breaks[i] = None
        self._apply_vertex_breaks(breaks, list(self._cb_selected))

    def _draw_cb_overlay(self, pg):
        """Tool on: faint sharp profile, every vertex as a small dot, selected
        vertices as larger highlighted dots. Called from _update_preview."""
        from PyQt5.QtGui import QColor
        verts, prev, _nxt = self._sharp_vertex_points()
        if not verts:
            return
        segs = self._segment_list.get_segments()
        sharp = [(verts[0][0], 0.0)] + [(float(s.get("z", 0.0)), float(s.get("x", 0.0)) / 2.0)
                                         for s in segs]
        ghost = QColor(COLORS['text_secondary'])
        ghost.setAlpha(150)
        from pyqtgraph.Qt import QtCore as _QtCore
        line = self._graph_widget.plot([p[0] for p in sharp], [p[1] for p in sharp],
                                       pen=pg.mkPen(ghost, width=1, style=_QtCore.Qt.DashLine))
        line.setZValue(4)
        dots = pg.ScatterPlotItem([p[0] for p in verts], [p[1] for p in verts], size=9,
                                  pen=pg.mkPen(COLORS['text_primary']),
                                  brush=pg.mkBrush(COLORS['bg_surface']))
        dots.setZValue(8)
        self._graph_widget.addItem(dots)
        sel = pg.ScatterPlotItem([], [], size=17, pen=pg.mkPen('#FFFFFF', width=2),
                                 brush=pg.mkBrush(COLORS['status_info']))
        sel.setZValue(9)
        self._graph_widget.addItem(sel)
        self._cb_overlay_items = [line, dots, sel]
        self._draw_cb_selection()

    def _draw_cb_selection(self):
        if len(self._cb_overlay_items) < 3:
            return
        sel_item = self._cb_overlay_items[2]
        verts, _p, _n = self._sharp_vertex_points()
        chosen = [verts[i] for i in self._cb_selected if i < len(verts)]
        try:
            sel_item.setData([p[0] for p in chosen], [p[1] for p in chosen])
        except RuntimeError:
            self._cb_overlay_items = []          # item was cleared with the plot

    def _on_graph_clicked_cb(self, ev):
        """Tool on: pick a vertex (pixel tolerance + tie-breakers); Ctrl adds /
        removes; a plain click on empty space clears the selection."""
        if not self._btn_cb_tool.isChecked() or ev.button() != Qt.LeftButton or ev.double():
            return
        if self._cb_overlay_blocked():
            return
        from PyQt5.QtCore import QPointF
        from gui.components.vertex_picking import pick_vertex
        verts, prev, nxt = self._sharp_vertex_points()
        if not verts:
            return
        vb = self._graph_widget.getViewBox()

        def scr(p):
            q = vb.mapViewToScene(QPointF(p[0], p[1]))
            return (q.x(), q.y())

        click = (ev.scenePos().x(), ev.scenePos().y())
        picked = pick_vertex(click, [scr(p) for p in verts], [scr(p) for p in prev],
                             [scr(p) for p in nxt], self._cb_selected)
        if len(picked) > 1:
            picked = self._choose_vertex(picked)
        ctrl = bool(ev.modifiers() & Qt.ControlModifier)
        sel = list(self._cb_selected)
        if not picked:
            if not ctrl:
                sel = []
        elif ctrl:
            v = picked[0]
            sel = [i for i in sel if i != v] if v in sel else sel + [v]
        else:
            sel = [picked[0]]
        ev.accept()
        self._cb_panel.set_selected(sorted(sel))

    def _choose_vertex(self, candidates: list) -> list:
        """Last-resort chooser when vertices are on top of each other."""
        from PyQt5.QtGui import QCursor
        from PyQt5.QtWidgets import QMenu
        menu = QMenu(self)
        actions = {menu.addAction(f"V{i + 1}"): i for i in candidates}
        chosen = menu.exec_(QCursor.pos())
        return [actions[chosen]] if chosen in actions else []

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

        # OD corner breaks come from the engine's validated vertex solver, so
        # the preview shows exactly what is machined (incl. V1 at the face and
        # NX-style trims). Point index -> VertexGeometry. ID and arc-adjacent
        # vertices are not in it and keep the legacy preview math below.
        od_geom = self._od_corner_geometry(segments, corner_breaks)

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
        # The profile implicitly starts at (first_segment_X, Z=0) — NOT at the origin.
        # Use the first segment's X as the starting point (profile always starts at Z=0).
        first_x_dia = float(segments[0].get("x", 0.0))
        first_x_r = first_x_dia / 2.0
        seg_endpoints = [(first_x_r, 0.0)]  # Profile start = first segment X at Z=0

        for seg in segments:
            seg_endpoints.append((float(seg.get("x", 0.0)) / 2.0,
                                  float(seg.get("z", 0.0))))

        prev_x_r = first_x_r
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
            vg = od_geom.get(seg_idx - 1) if seg_idx > 0 else None
            if vg is not None:
                # Engine geometry: trim the arriving path to t_in, draw the
                # break element, continue this segment from t_out.
                (tin_r, tin_z), (tout_r, tout_z) = vg.t_in, vg.t_out
                if seg_idx - 1 == 0:
                    # V1 is on the (undrawn) face: the drawn outline starts
                    # where the break starts, not at the sharp first point.
                    current_x[:] = [tin_r]
                    current_z[:] = [tin_z]
                    if seg_point_ranges:
                        seg_point_ranges[0] = (0, 1)
                    _seg_start_idx = 0
                elif current_z:
                    current_x[-1] = tin_r
                    current_z[-1] = tin_z
                else:
                    current_x.append(tin_r)
                    current_z.append(tin_z)
                if vg.kind == "fillet" and vg.center is not None:
                    fc_x, fc_z = vg.center
                    a_start = math.atan2(tin_z - fc_z, tin_r - fc_x)
                    a_end = math.atan2(tout_z - fc_z, tout_r - fc_x)
                    sweep = a_end - a_start
                    if sweep > math.pi:
                        sweep -= 2 * math.pi
                    elif sweep < -math.pi:
                        sweep += 2 * math.pi
                    n_fillet = max(16, int(abs(sweep) * vg.radius * 200))
                    for fi in range(1, n_fillet):
                        a = a_start + sweep * fi / float(n_fillet)
                        current_x.append(fc_x + vg.radius * math.cos(a))
                        current_z.append(fc_z + vg.radius * math.sin(a))
                current_x.append(tout_r)
                current_z.append(tout_z)
                all_x.append(tout_r)
                all_z.append(tout_z)
                trim_start_x, trim_start_z = tout_r, tout_z
            elif cb_before and cb_before.get("type", "none") != "none":
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
            z_end = self._stock_back_z.value()
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

            # Draw OTHER visible profile blocks' profiles (dimmer, behind active)
            self._draw_other_block_profiles(pg)

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

            # Corner-break tool overlay (sharp profile ghost + vertex dots)
            self._cb_overlay_items = []
            if self._btn_cb_tool.isChecked():
                self._draw_cb_overlay(pg)

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

    def _draw_other_block_profiles(self, pg):
        """Draw profile lines for all OTHER visible profile blocks (dimmer style).

        Called during _update_preview to show all visible profiles simultaneously,
        not just the active block's.
        """
        import math
        from PyQt5.QtGui import QColor

        blocks = self._block_list.get_blocks()
        active_id = self._active_block_id

        # Dimmer pen for non-active profiles
        dim_color = QColor(COLORS['graph_profile'])
        dim_color.setAlpha(100)
        dim_pen = pg.mkPen(dim_color, width=1.5)

        for block in blocks:
            # Skip the active block (already drawn in bold), hidden blocks, and non-profile blocks
            if block.block_id == active_id:
                continue
            if not block.visible or not block.enabled:
                continue
            if not block.is_profile:
                continue

            # Get saved segments for this block
            data = block.params_data
            if not data:
                continue
            segments = data.get("segments", [])
            if not segments:
                continue

            # Build simple polyline from segments (no corner break rendering for non-active)
            first_x_dia = float(segments[0].get("x", 0.0))
            prev_x_r = first_x_dia / 2.0
            prev_z = 0.0
            z_pts = [prev_z]
            x_pts = [prev_x_r]

            for seg in segments:
                x_dia = float(seg.get("x", 0.0))
                z = float(seg.get("z", 0.0))
                x_r = x_dia / 2.0
                seg_type = seg.get("type", "line")
                raw_radius = seg.get("radius", 0.0)

                if seg_type == "arc" and raw_radius:
                    # Simple arc interpolation for display
                    try:
                        if isinstance(raw_radius, str):
                            radius_val = 0.0
                        else:
                            radius_val = float(raw_radius)
                        if abs(radius_val) > 0.001:
                            r = abs(radius_val)
                            dx = x_r - prev_x_r
                            dz = z - prev_z
                            chord = math.sqrt(dx*dx + dz*dz)
                            if chord < 2 * r:
                                n_pts = max(8, int(chord / r * 16))
                                for i in range(1, n_pts + 1):
                                    t = i / n_pts
                                    # Linear interpolation (approximate for preview)
                                    z_pts.append(prev_z + dz * t)
                                    x_pts.append(prev_x_r + dx * t)
                            else:
                                z_pts.append(z)
                                x_pts.append(x_r)
                        else:
                            z_pts.append(z)
                            x_pts.append(x_r)
                    except (ValueError, TypeError):
                        z_pts.append(z)
                        x_pts.append(x_r)
                else:
                    z_pts.append(z)
                    x_pts.append(x_r)

                prev_x_r = x_r
                prev_z = z

            if len(z_pts) > 1:
                self._graph_widget.plot(z_pts, x_pts, pen=dim_pen)

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
            (self._stock_z_end, "Operation Z End"),
            (self._stock_back_z, "Stock Back Face"),
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
