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

# Pipeline imports
from pipeline.pipeline import execute as pipeline_execute
from pipeline.model_builder import build_from_fields
from outputs.gcode_writer import GCodeWriter
from outputs.graph_adapter import convert as graph_convert
from outputs.gcode_parser import parse as parse_gcode
from outputs import material_sim
from models.tool import ToolDef, ToolOrientation, ToolDirection, ToolType
from models.validation import PipelineStatus

logger = logging.getLogger(__name__)


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
            "spring_pass": self._finish_spring_pass.isChecked(),
        }

    def get_segments(self) -> list:
        """Return current profile segments from the segment list widget."""
        return self._segment_list.get_segments()

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

        # Splitter proportions: left panel fixed ~220px, right gets the rest
        self._splitter.setSizes([220, 780])
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._left_panel.setMinimumWidth(210)

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
            default_value=2.0, suffix="dia",
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
            default_value=0.008, suffix="ipr",
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
            default_value=1200.0, suffix="rpm",
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
            default_value=1.0, suffix="",
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

        # Segment list
        self._segment_list.segments_changed.connect(self._on_segments_changed)

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

    def _on_peck_toggled(self, checked: bool):
        """Enable/disable peck length field based on checkbox."""
        self._rough_peck_length.setEnabled(checked)
        self._on_field_changed()

    def _on_generate_clicked(self):
        """Generate button clicked — execute pipeline and display results."""
        # Allow generate from BUILDING or READY (user may not have triggered validation)
        if self._state not in (ProgramState.READY, ProgramState.BUILDING):
            return

        self.set_state(ProgramState.GENERATING)
        self.generate_requested.emit()

        try:
            # 1. Gather field values
            stock = self.get_stock_values()
            roughing = self.get_roughing_values()
            finishing = self.get_finishing_values()
            segments = self.get_segments()

            # 2. Default tool (T1, 0.016 TNR, 80° tip, 0.375 edge, OD_FRONT_RIGHT, RIGHT)
            tool_def = self._active_tool if self._active_tool else ToolDef(
                tool_number=1,
                nose_radius=0.016,
                tip_angle=80.0,
                edge_length=0.375,
                orientation=ToolOrientation.OD_FRONT_RIGHT,
                direction=ToolDirection.RIGHT,
                tool_type=ToolType.TURNING,
                description="Default T1 CNMG",
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
            )

            # 4. Execute pipeline
            pipeline_result = pipeline_execute(
                profile=profile,
                stock=stock_def,
                tool=tool_def,
                roughing_params=roughing_params,
                finishing_params=finishing_params,
            )

            # 5. Check result status
            if pipeline_result.status not in (PipelineStatus.SUCCESS, PipelineStatus.SUCCESS_WITH_WARNINGS):
                # Show validation errors
                error_msgs = [v.message for v in pipeline_result.validations]
                error_text = "\n".join(error_msgs[:5])  # Show first 5
                self._status_label.setText(f"Error: {error_msgs[0] if error_msgs else 'Pipeline failed'}")
                self._status_label.setStyleSheet(
                    f"color: {COLORS['status_error']}; font-size: {FONTS['small_size']}pt;"
                )
                self.set_state(ProgramState.READY)
                return

            plan_result = pipeline_result.plan_result

            # 6. Material simulation DISABLED — still buggy, not accurately reflecting
            #    real material removal. See .kiro/specs/material-sim-accuracy-fix/ and
            #    .kiro/specs/material-removal-simulation/ for specs + progress notes.
            #    Falls back to raster zone shading instead.
            sim_data = None

            # 7. Convert to graph data
            graph_data = graph_convert(plan_result, material_sim_data=sim_data)

            # 8. Generate G-code
            gcode_text = GCodeWriter().write(plan_result)

            # 9. Parse for sim and load into SimViewerWidget
            from gui.components.sim_viewer import parse_gcode_for_sim
            sim_moves = parse_gcode_for_sim(gcode_text)
            self._sim_viewer.load(graph_data, gcode_text, sim_moves)

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
            # On error, show message and return to READY
            error_msg = str(e) if str(e) else type(e).__name__
            self._status_label.setText(f"Error: {error_msg}")
            self._status_label.setStyleSheet(
                f"color: {COLORS['status_error']}; font-size: {FONTS['small_size']}pt;"
            )
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
            self._rough_doc, self._rough_feed, self._rough_fin_allowance,
            self._rough_rpm,
            self._finish_passes, self._finish_doc, self._finish_feed,
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
        if "spring_pass" in finishing:
            self._finish_spring_pass.setChecked(finishing["spring_pass"])

        # Segments
        segments = data.get("segments", [])
        if segments:
            self._segment_list.set_segments(segments)

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
        """
        if self._state not in (ProgramState.BUILDING, ProgramState.READY):
            return

        segments = self._segment_list.get_segments()
        if not segments:
            return

        import math
        import pyqtgraph as pg
        from pyqtgraph.Qt import QtCore as _QtCore

        # Build per-segment polylines for drawing (avoids pyqtgraph bounding-box
        # rendering artifacts that occur with a single large PlotCurveItem containing
        # many arc interpolation points).
        # Each entry: (list_of_z, list_of_x) for one continuous sub-path.
        segments_to_draw: List[tuple] = []
        current_z: List[float] = []
        current_x: List[float] = []
        all_z: List[float] = []
        all_x: List[float] = []

        prev_x_r = 0.0
        prev_z = 0.0

        for seg in segments:
            x_dia = float(seg.get("x", 0.0))
            z = float(seg.get("z", 0.0))
            x_r = x_dia / 2.0
            radius = float(seg.get("radius", 0.0))
            seg_type = seg.get("type", "line")

            if seg_type == "arc" and abs(radius) > 0.0001:
                # End the current line sub-path (include prev point as arc start)
                if current_z:
                    segments_to_draw.append((list(current_z), list(current_x)))
                current_z = []
                current_x = []

                # Interpolate arc from prev to current
                r_abs = abs(radius)
                is_cw = radius > 0

                dx_r = x_r - prev_x_r
                dz = z - prev_z
                chord = math.sqrt(dx_r * dx_r + dz * dz)

                arc_z: List[float] = []
                arc_x: List[float] = []

                if chord > 0.0001 and r_abs >= chord / 2.0 - 1e-9:
                    if r_abs < chord / 2.0:
                        r_abs = chord / 2.0

                    mid_x_r = (prev_x_r + x_r) / 2.0
                    mid_z = (prev_z + z) / 2.0
                    h = math.sqrt(max(0.0, r_abs * r_abs - (chord / 2.0) ** 2))

                    px = -dz / chord
                    pz = dx_r / chord

                    if is_cw:
                        cx_r = mid_x_r + h * px
                        cz_arc = mid_z + h * pz
                    else:
                        cx_r = mid_x_r - h * px
                        cz_arc = mid_z - h * pz

                    angle_start = math.atan2(prev_z - cz_arc, prev_x_r - cx_r)
                    angle_end = math.atan2(z - cz_arc, x_r - cx_r)
                    r_display = math.sqrt((prev_x_r - cx_r) ** 2 + (prev_z - cz_arc) ** 2)

                    diff = angle_end - angle_start
                    if diff > math.pi:
                        diff -= 2 * math.pi
                    elif diff < -math.pi:
                        diff += 2 * math.pi

                    n_pts = max(10, int(abs(diff) * r_display * 40))
                    for i in range(n_pts + 1):
                        t = i / float(n_pts)
                        angle = angle_start + diff * t
                        ax = cx_r + r_display * math.cos(angle)
                        az = cz_arc + r_display * math.sin(angle)
                        arc_x.append(ax)
                        arc_z.append(az)
                else:
                    # Degenerate arc — draw as line from prev to endpoint
                    arc_x = [prev_x_r, x_r]
                    arc_z = [prev_z, z]

                if arc_z:
                    segments_to_draw.append((arc_z, arc_x))
                    all_z.extend(arc_z)
                    all_x.extend(arc_x)
                    # Start next line sub-path from arc endpoint
                    current_z = [arc_z[-1]]
                    current_x = [arc_x[-1]]
            else:
                # LINE segment — add endpoint to current sub-path
                if not current_z:
                    # Start sub-path from previous point for continuity
                    current_z.append(prev_z)
                    current_x.append(prev_x_r)
                current_z.append(z)
                current_x.append(x_r)
                all_z.append(z)
                all_x.append(x_r)

            prev_x_r = x_r
            prev_z = z

        # Flush remaining line sub-path
        if len(current_z) > 1:
            segments_to_draw.append((current_z, current_x))

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
