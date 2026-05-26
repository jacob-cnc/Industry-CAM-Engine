"""Run Tab — Load, preview, and execute G-code programs.

Layout:
    Top: SimViewerWidget (graph + G-code panel with playback — proven architecture)
    Bottom bar: Machine execution controls (Open, Preview, Start, Pause, Stop, Run From Line)

Architecture:
    - Uses SimViewerWidget for toolpath preview and G-code display (same as Edit tab)
    - Uses HALBackend for real program control (open, run, pause, resume, stop)
    - Polls MachineState for current_line/motion_line to drive live highlighting
    - Works in offline mode with mock backend (preview works, execution is no-op)
"""

import os
import logging
from typing import Optional, List

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QSpinBox,
    QFrame, QMessageBox,
)

from gui.colors import COLORS, FONTS
from gui.components.sim_viewer import SimViewerWidget, parse_gcode_for_sim, GCodePanel
from outputs.graph_adapter import convert_from_moves
from outputs.gcode_parser import parse as parse_gcode
from hal import get_backend
from hal.interface import HALBackend, InterpState, TaskMode, TaskState

logger = logging.getLogger(__name__)


class RunTab(QWidget):
    """G-code program execution tab.

    Features:
        - Open and display G-code files
        - Toolpath preview via SimViewerWidget (proven playback architecture)
        - Current-line highlighting synchronized to machine execution
        - Start / Pause / Resume / Stop controls
        - Run-from-line with line number input
        - Live tool position dot during execution
    """

    program_loaded = pyqtSignal(str)  # Emitted with file path when loaded

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._backend: HALBackend = get_backend()
        self._gcode_text: str = ""
        self._gcode_path: str = ""
        self._active = False
        self._last_motion_line = -1
        self._is_running = False

        self._build_ui()
        self._connect_signals()

        # Poll timer for live updates during execution
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll)
        self._poll_timer.setInterval(100)  # 10 Hz

    # =================================================================
    # UI Construction
    # =================================================================

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- Main content: SimViewerWidget (graph + gcode + sim playback) ---
        self._sim_viewer = SimViewerWidget(show_gcode_panel=True)
        layout.addWidget(self._sim_viewer, stretch=1)

        # --- Bottom control bar: machine execution controls ---
        bar = self._build_control_bar()
        layout.addWidget(bar)

    def _build_control_bar(self) -> QWidget:
        """Build the machine execution control bar at the bottom."""
        bar = QWidget()
        bar.setFixedHeight(56)
        bar.setStyleSheet(f"background-color: {COLORS['bg_panel']};")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(8, 4, 8, 4)
        bar_layout.setSpacing(6)

        btn_style = (
            f"QPushButton {{ background-color: {COLORS['bg_surface']};"
            f" color: {COLORS['text_primary']}; border: 1px solid {COLORS['border_normal']};"
            f" border-radius: 4px; padding: 4px 12px; min-height: 36px;"
            f" font-weight: bold; }}"
            f"QPushButton:hover {{ background-color: {COLORS['btn_primary_hover']}; }}"
            f"QPushButton:disabled {{ color: {COLORS['text_disabled']};"
            f" background-color: {COLORS['bg_panel']}; }}"
        )

        # Open file
        self._btn_open = QPushButton("Open")
        self._btn_open.setStyleSheet(btn_style)
        self._btn_open.setToolTip("Open a G-code file (.ngc, .nc, .gcode)")
        bar_layout.addWidget(self._btn_open)

        # Preview toolpath
        self._btn_preview = QPushButton("Preview")
        self._btn_preview.setStyleSheet(btn_style)
        self._btn_preview.setToolTip("Parse and display the toolpath preview")
        self._btn_preview.setEnabled(False)
        bar_layout.addWidget(self._btn_preview)

        # Separator
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.VLine)
        sep1.setStyleSheet(f"color: {COLORS['border_normal']};")
        bar_layout.addWidget(sep1)

        # Start
        self._btn_start = QPushButton("Cycle Start")
        self._btn_start.setStyleSheet(
            f"QPushButton {{ background-color: {COLORS['status_ok']};"
            f" color: {COLORS['bg_base']}; border: none;"
            f" border-radius: 4px; padding: 4px 12px; min-height: 36px;"
            f" font-weight: bold; }}"
            f"QPushButton:hover {{ background-color: #6FB8A8; }}"
            f"QPushButton:disabled {{ color: {COLORS['text_disabled']};"
            f" background-color: {COLORS['bg_panel']}; }}"
        )
        self._btn_start.setEnabled(False)
        bar_layout.addWidget(self._btn_start)

        # Pause / Resume
        self._btn_pause = QPushButton("Pause")
        self._btn_pause.setStyleSheet(btn_style)
        self._btn_pause.setEnabled(False)
        bar_layout.addWidget(self._btn_pause)

        # Stop
        self._btn_stop = QPushButton("Stop")
        self._btn_stop.setStyleSheet(
            f"QPushButton {{ background-color: {COLORS['btn_danger']};"
            f" color: {COLORS['text_primary']}; border: none;"
            f" border-radius: 4px; padding: 4px 12px; min-height: 36px;"
            f" font-weight: bold; }}"
            f"QPushButton:hover {{ background-color: #A52535; }}"
            f"QPushButton:disabled {{ color: {COLORS['text_disabled']};"
            f" background-color: {COLORS['bg_panel']}; }}"
        )
        self._btn_stop.setEnabled(False)
        bar_layout.addWidget(self._btn_stop)

        # Separator
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.VLine)
        sep2.setStyleSheet(f"color: {COLORS['border_normal']};")
        bar_layout.addWidget(sep2)

        # Run from line
        lbl_from = QLabel("From line:")
        lbl_from.setStyleSheet(f"color: {COLORS['text_secondary']};")
        bar_layout.addWidget(lbl_from)

        self._line_spin = QSpinBox()
        self._line_spin.setMinimum(1)
        self._line_spin.setMaximum(99999)
        self._line_spin.setValue(1)
        self._line_spin.setFixedWidth(80)
        self._line_spin.setFixedHeight(36)
        bar_layout.addWidget(self._line_spin)

        self._btn_run_from = QPushButton("Run From")
        self._btn_run_from.setStyleSheet(btn_style)
        self._btn_run_from.setEnabled(False)
        self._btn_run_from.setToolTip("Start execution from the specified line")
        bar_layout.addWidget(self._btn_run_from)

        bar_layout.addStretch()

        # Status indicators
        self._status_state = QLabel("IDLE")
        self._status_state.setStyleSheet(
            f"color: {COLORS['status_info']}; font-weight: bold;"
            f" font-family: {FONTS['mono_family']}, {FONTS['fallback_mono']};"
        )
        bar_layout.addWidget(self._status_state)

        sep3 = QLabel("|")
        sep3.setStyleSheet(f"color: {COLORS['border_normal']};")
        bar_layout.addWidget(sep3)

        self._status_line = QLabel("Line: —")
        self._status_line.setStyleSheet(
            f"color: {COLORS['text_secondary']};"
            f" font-family: {FONTS['mono_family']}, {FONTS['fallback_mono']};"
        )
        self._status_line.setMinimumWidth(80)
        bar_layout.addWidget(self._status_line)

        sep4 = QLabel("|")
        sep4.setStyleSheet(f"color: {COLORS['border_normal']};")
        bar_layout.addWidget(sep4)

        self._status_file = QLabel("No file loaded")
        self._status_file.setStyleSheet(
            f"color: {COLORS['text_disabled']}; font-size: 9pt;"
        )
        self._status_file.setMaximumWidth(300)
        bar_layout.addWidget(self._status_file)

        return bar

    # =================================================================
    # Signal Connections
    # =================================================================

    def _connect_signals(self):
        self._btn_open.clicked.connect(self._on_open)
        self._btn_preview.clicked.connect(self._on_preview)
        self._btn_start.clicked.connect(self._on_start)
        self._btn_pause.clicked.connect(self._on_pause_resume)
        self._btn_stop.clicked.connect(self._on_stop)
        self._btn_run_from.clicked.connect(self._on_run_from_line)

    # =================================================================
    # Public API
    # =================================================================

    def set_active(self, active: bool):
        """Start/stop polling based on tab visibility."""
        self._active = active
        if active:
            self._poll_timer.start()
        else:
            self._poll_timer.stop()

    def load_file(self, path: str):
        """Load a G-code file programmatically (e.g., from Edit tab)."""
        if not os.path.isfile(path):
            return
        self._load_gcode_file(path)

    # =================================================================
    # File Loading
    # =================================================================

    def _on_open(self):
        """Open file dialog to select a G-code program."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Open G-code Program",
            "",
            "G-code Files (*.ngc *.nc *.gcode *.tap);;All Files (*)",
        )
        if path:
            self._load_gcode_file(path)

    def _load_gcode_file(self, path: str):
        """Load and display a G-code file."""
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                self._gcode_text = f.read()
        except OSError as e:
            QMessageBox.warning(self, "File Error", f"Cannot read file:\n{e}")
            return

        self._gcode_path = path
        filename = os.path.basename(path)

        # Update line spin max
        line_count = self._gcode_text.count('\n') + 1
        self._line_spin.setMaximum(line_count)

        # Tell the backend to open the file (for actual execution)
        self._backend.program_open(path)

        # Update UI state
        self._btn_start.setEnabled(True)
        self._btn_preview.setEnabled(True)
        self._btn_run_from.setEnabled(True)
        self._status_file.setText(filename)
        self._status_file.setToolTip(path)
        self._status_file.setStyleSheet(
            f"color: {COLORS['text_primary']}; font-size: 9pt;"
        )

        # Auto-preview on load
        self._on_preview()

        self.program_loaded.emit(path)
        logger.info("Loaded G-code: %s (%d lines)", filename, line_count)

    # =================================================================
    # Preview — uses the same proven pattern as Edit tab
    # =================================================================

    def _on_preview(self):
        """Parse G-code and load into the SimViewerWidget (proven architecture)."""
        if not self._gcode_text.strip():
            return

        try:
            # Parse for the graph display (returns List[ToolMove])
            moves = parse_gcode(self._gcode_text)
            if not moves:
                QMessageBox.information(
                    self, "No Moves",
                    "No motion commands found in the G-code.",
                )
                return

            # Build graph data from moves
            graph_data = convert_from_moves(moves)

            # Parse for sim (with line_idx tracking for highlighting)
            sim_moves = parse_gcode_for_sim(self._gcode_text)

            # Load everything into the SimViewerWidget
            self._sim_viewer.load(graph_data, self._gcode_text, sim_moves)

            logger.info("Preview loaded: %d moves, %d sim moves",
                        len(moves), len(sim_moves))

        except Exception as e:
            QMessageBox.warning(
                self, "Preview Error",
                f"Could not parse G-code for preview:\n{e}",
            )

    # =================================================================
    # Program Control
    # =================================================================

    def _on_start(self):
        """Start program execution from line 1."""
        if not self._gcode_path:
            return
        success = self._backend.program_run(start_line=0)
        if success:
            self._set_running_state()
        else:
            logger.warning("program_run failed")

    def _on_pause_resume(self):
        """Toggle pause/resume."""
        state = self._backend.state
        if state.interp_state == InterpState.PAUSED:
            self._backend.program_resume()
            self._btn_pause.setText("Pause")
        else:
            self._backend.program_pause()
            self._btn_pause.setText("Resume")

    def _on_stop(self):
        """Stop program execution."""
        self._backend.program_stop()
        self._set_idle_state()

    def _on_run_from_line(self):
        """Start execution from the specified line number."""
        if not self._gcode_path:
            return
        line = self._line_spin.value() - 1  # Convert 1-based to 0-based
        success = self._backend.program_run(start_line=max(0, line))
        if success:
            self._set_running_state()
        else:
            logger.warning("program_run from line %d failed", line + 1)

    def _set_running_state(self):
        """Update UI for running state."""
        self._is_running = True
        self._btn_start.setEnabled(False)
        self._btn_pause.setEnabled(True)
        self._btn_stop.setEnabled(True)
        self._btn_run_from.setEnabled(False)
        self._btn_open.setEnabled(False)
        self._btn_preview.setEnabled(False)
        self._btn_pause.setText("Pause")

    def _set_idle_state(self):
        """Update UI for idle state."""
        self._is_running = False
        has_file = bool(self._gcode_path)
        self._btn_start.setEnabled(has_file)
        self._btn_pause.setEnabled(False)
        self._btn_stop.setEnabled(False)
        self._btn_run_from.setEnabled(has_file)
        self._btn_open.setEnabled(True)
        self._btn_preview.setEnabled(has_file)
        self._btn_pause.setText("Pause")

    # =================================================================
    # Polling — Live Updates During Execution
    # =================================================================

    def _poll(self):
        """Timer callback — update line highlighting and status from machine state."""
        state = self._backend.state

        # Update interpreter state display
        interp_name = state.interp_state.value.upper()
        if state.interp_state == InterpState.IDLE:
            color = COLORS['text_disabled']
        elif state.interp_state == InterpState.PAUSED:
            color = COLORS['status_warning']
        else:
            color = COLORS['status_ok']
        self._status_state.setText(interp_name)
        self._status_state.setStyleSheet(
            f"color: {color}; font-weight: bold;"
            f" font-family: {FONTS['mono_family']}, {FONTS['fallback_mono']};"
        )

        # Update current line display and highlighting
        motion_line = state.motion_line
        if motion_line != self._last_motion_line:
            self._last_motion_line = motion_line
            if motion_line > 0:
                # motion_line is 1-based from LinuxCNC, sim_line_changed expects 0-based
                self._sim_viewer.sim_line_changed.emit(motion_line - 1)
                self._status_line.setText(f"Line: {motion_line}")
            else:
                self._sim_viewer.sim_line_changed.emit(-1)
                self._status_line.setText("Line: —")

        # Detect program completion (was running, now idle)
        if state.interp_state == InterpState.IDLE and self._is_running:
            self._set_idle_state()

        # Update button state for pause
        if state.interp_state == InterpState.PAUSED:
            self._btn_pause.setText("Resume")
        elif state.interp_state == InterpState.READING:
            self._btn_pause.setText("Pause")

        # Live tool position from machine state during execution
        if state.interp_state in (InterpState.READING, InterpState.PAUSED):
            x_r = state.x.position / 2.0  # diameter → radius
            z = state.z.position
            self._sim_viewer._graph.set_tool_position(x_r, z)
