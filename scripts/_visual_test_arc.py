"""Visual test for Arc OD profile — graph viewer with toolpath simulation + G-code panel.

Uses the proven sim architecture:
  G-code text -> Parser (with line_idx per move) -> Timer playback -> Signal -> Highlight

Each SimMove stores its source line_idx at parse time. Playback emits that index.
The text widget highlights the corresponding line. No reverse-mapping needed.
"""
import sys
import math
sys.path.insert(0, r'c:\Users\jhonick\linuxcnc\Industry CAM Engine')

from dataclasses import dataclass
from typing import List, Optional

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QComboBox, QSlider, QSplitter, QPlainTextEdit,
    QTextEdit,
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QTextCursor, QColor, QTextCharFormat

from models import *
from pipeline.pipeline import execute
from outputs.graph_adapter import convert as graph_convert
from outputs.gcode_writer import GCodeWriter
from gui.components.graph_widget import MachiningGraphWidget
from gui.colors import COLORS, FONTS


# ---------------------------------------------------------------------------
# SimMove — each parsed motion with its source line index
# ---------------------------------------------------------------------------

@dataclass
class SimMove:
    """A single simulation move with source line tracking."""
    move_type: str       # "rapid", "feed", "arc_cw", "arc_ccw"
    start_x: float       # diameter
    start_z: float
    end_x: float         # diameter
    end_z: float
    line_idx: int        # 0-based G-code source line number
    feed_rate: float = 0.0
    center_i: float = 0.0  # arc center X offset (diameter, incremental)
    center_k: float = 0.0  # arc center Z offset (inches, incremental)


# ---------------------------------------------------------------------------
# Parser — stamps each move with line_idx from enumerate()
# ---------------------------------------------------------------------------

def parse_gcode_for_sim(gcode_text: str) -> List[SimMove]:
    """Parse G-code into SimMoves, each stamped with its source line index.

    This is the sync key: every move knows which line generated it.
    """
    moves: List[SimMove] = []
    x = 0.0  # current X (diameter)
    z = 0.0  # current Z
    feed = 0.0
    modal_motion = "G00"  # modal G-code group 1

    lines = gcode_text.splitlines()
    for line_idx, raw_line in enumerate(lines):
        # Strip comments (parentheses and semicolons)
        line = raw_line
        paren = line.find("(")
        if paren >= 0:
            line = line[:paren]
        semi = line.find(";")
        if semi >= 0:
            line = line[:semi]
        line = line.strip().upper()

        if not line:
            continue

        # Parse tokens
        tokens = line.split()

        # Detect motion G-code on this line
        new_motion = None
        for token in tokens:
            if token in ("G00", "G0"):
                new_motion = "G00"
            elif token in ("G01", "G1"):
                new_motion = "G01"
            elif token in ("G02", "G2"):
                new_motion = "G02"
            elif token in ("G03", "G3"):
                new_motion = "G03"

        if new_motion:
            modal_motion = new_motion

        # Extract axis words
        new_x = None
        new_z = None
        new_f = None
        new_i = None
        new_k = None
        for token in tokens:
            if token[0] == "N":
                continue  # skip N-number
            if token[0] == "X" and len(token) > 1:
                try:
                    new_x = float(token[1:])
                except ValueError:
                    pass
            elif token[0] == "Z" and len(token) > 1:
                try:
                    new_z = float(token[1:])
                except ValueError:
                    pass
            elif token[0] == "F" and len(token) > 1:
                try:
                    new_f = float(token[1:])
                except ValueError:
                    pass
            elif token[0] == "I" and len(token) > 1:
                try:
                    new_i = float(token[1:])
                except ValueError:
                    pass
            elif token[0] == "K" and len(token) > 1:
                try:
                    new_k = float(token[1:])
                except ValueError:
                    pass

        if new_f is not None:
            feed = new_f

        # Only create a SimMove if this line has axis motion
        if new_x is None and new_z is None:
            continue

        # Determine end position
        end_x = new_x if new_x is not None else x
        end_z = new_z if new_z is not None else z

        # Skip zero-length moves
        if abs(end_x - x) < 0.00001 and abs(end_z - z) < 0.00001:
            continue

        # Map modal motion to move type
        if modal_motion == "G00":
            move_type = "rapid"
        elif modal_motion == "G01":
            move_type = "feed"
        elif modal_motion == "G02":
            move_type = "arc_cw"
        elif modal_motion == "G03":
            move_type = "arc_ccw"
        else:
            move_type = "feed"

        moves.append(SimMove(
            move_type=move_type,
            start_x=x,
            start_z=z,
            end_x=end_x,
            end_z=end_z,
            line_idx=line_idx,
            feed_rate=feed,
            center_i=new_i if new_i is not None else 0.0,
            center_k=new_k if new_k is not None else 0.0,
        ))

        x = end_x
        z = end_z

    return moves


# ---------------------------------------------------------------------------
# G-code Panel with line highlighting
# ---------------------------------------------------------------------------

class GCodePanel(QPlainTextEdit):
    """Read-only G-code display with line highlighting."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        font = QFont(FONTS["mono_family"], 10)
        font.setStyleHint(QFont.Monospace)
        self.setFont(font)
        self.setStyleSheet(
            f"QPlainTextEdit {{"
            f"  background-color: {COLORS['bg_panel']};"
            f"  color: {COLORS['text_primary']};"
            f"  border: none;"
            f"}}"
        )
        self._current_line = -1

    def highlight_line(self, line_idx: int):
        """Highlight a specific line (0-based) and scroll to it."""
        if line_idx == self._current_line:
            return
        self._current_line = line_idx

        if line_idx < 0:
            # Clear highlighting
            self.setExtraSelections([])
            return

        doc = self.document()
        if line_idx >= doc.blockCount():
            return

        # Build highlight selection
        block = doc.findBlockByNumber(line_idx)
        cursor = QTextCursor(block)
        cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)

        selection = QTextEdit.ExtraSelection()
        highlight_color = QColor("#4a90d9")
        highlight_color.setAlpha(100)
        fmt = QTextCharFormat()
        fmt.setBackground(highlight_color)
        fmt.setForeground(QColor("#FFFFFF"))
        fmt.setProperty(QTextCharFormat.FullWidthSelection, True)
        selection.format = fmt
        selection.cursor = cursor

        self.setExtraSelections([selection])

        # Auto-scroll to keep highlighted line visible
        scroll_cursor = QTextCursor(block)
        self.setTextCursor(scroll_cursor)
        self.ensureCursorVisible()


# ---------------------------------------------------------------------------
# Simulation Viewer
# ---------------------------------------------------------------------------

class SimViewer(QMainWindow):
    """Graph + G-code panel with timer-driven playback."""

    sim_line_changed = pyqtSignal(int)

    def __init__(self, graph_data, gcode_text, sim_moves: List[SimMove]):
        super().__init__()
        self.setWindowTitle("Arc OD Profile — Toolpath Simulation")
        self.resize(1500, 900)

        self._sim_moves = sim_moves
        self._sim_step = 0  # current step in interpolated path
        self._sim_timer = QTimer(self)
        self._sim_timer.timeout.connect(self._sim_advance)
        self._sim_speed = 16  # ms per frame (~60fps)
        self._steps_per_tick = 1

        # Pre-compute interpolated path for smooth motion
        self._path = self._build_interpolated_path(sim_moves)
        self._path_len = len(self._path)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Splitter: graph (left) + gcode panel (right)
        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter, stretch=1)

        # Graph widget
        self._graph = MachiningGraphWidget()
        self._graph.set_graph_data(graph_data)
        splitter.addWidget(self._graph)

        # G-code panel
        self._gcode_panel = GCodePanel()
        self._gcode_panel.setPlainText(gcode_text)
        self._gcode_panel.setMinimumWidth(380)
        splitter.addWidget(self._gcode_panel)

        splitter.setSizes([950, 550])

        # Connect line signal to highlight
        self.sim_line_changed.connect(self._gcode_panel.highlight_line)

        # Controls bar
        bar = self._build_controls()
        layout.addWidget(bar)

        # Show initial state
        self._emit_line()

    def _build_controls(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(56)
        bar.setStyleSheet(f"background-color: {COLORS['bg_panel']};")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(12, 8, 12, 8)
        bar_layout.setSpacing(10)

        btn_style = (
            f"QPushButton {{ background-color: {COLORS['bg_surface']};"
            f" color: {COLORS['text_primary']}; border: 1px solid {COLORS['border_normal']};"
            f" border-radius: 4px; padding: 6px 14px; min-height: 32px; font-size: 11pt; }}"
            f"QPushButton:hover {{ background-color: {COLORS['btn_primary_hover']}; }}"
        )

        self._btn_play = QPushButton("Play")
        self._btn_play.setStyleSheet(btn_style)
        self._btn_play.clicked.connect(self._toggle_play)
        bar_layout.addWidget(self._btn_play)

        btn_stop = QPushButton("Stop")
        btn_stop.setStyleSheet(btn_style)
        btn_stop.clicked.connect(self._sim_stop)
        bar_layout.addWidget(btn_stop)

        btn_back = QPushButton("< Step")
        btn_back.setStyleSheet(btn_style)
        btn_back.clicked.connect(self._step_back)
        bar_layout.addWidget(btn_back)

        btn_fwd = QPushButton("Step >")
        btn_fwd.setStyleSheet(btn_style)
        btn_fwd.clicked.connect(self._step_fwd)
        bar_layout.addWidget(btn_fwd)

        btn_end = QPushButton("Show All")
        btn_end.setStyleSheet(btn_style)
        btn_end.clicked.connect(self._sim_show_all)
        bar_layout.addWidget(btn_end)

        speed_label = QLabel("Speed:")
        speed_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        bar_layout.addWidget(speed_label)
        self._speed_combo = QComboBox()
        self._speed_combo.addItems(["0.25x", "0.5x", "1x", "2x", "5x", "10x"])
        self._speed_combo.setCurrentIndex(2)
        self._speed_combo.currentTextChanged.connect(self._on_speed)
        bar_layout.addWidget(self._speed_combo)

        self._slider = QSlider(Qt.Horizontal)
        self._slider.setMinimum(0)
        self._slider.setMaximum(self._path_len - 1 if self._path_len > 0 else 0)
        self._slider.valueChanged.connect(self._on_slider)
        bar_layout.addWidget(self._slider, stretch=1)

        self._frame_label = QLabel(f"0 / {self._path_len}")
        self._frame_label.setStyleSheet(
            f"color: {COLORS['text_primary']};"
            f" font-family: {FONTS['mono_family']}, {FONTS['fallback_mono']};"
            f" font-size: 10pt; min-width: 80px;"
        )
        bar_layout.addWidget(self._frame_label)

        self._info_label = QLabel("")
        self._info_label.setStyleSheet(
            f"color: {COLORS['text_secondary']}; font-size: 9pt; min-width: 280px;"
        )
        bar_layout.addWidget(self._info_label)

        return bar

    # --- Path interpolation ---

    def _build_interpolated_path(self, sim_moves: List[SimMove]) -> List[tuple]:
        """Pre-compute dense interpolated path for smooth tool dot motion.

        Returns list of (x_radius, z, move_index) tuples.
        Rapids get fewer points (fast motion), feeds get more (slow motion).
        Arcs are interpolated along the actual arc path.
        """
        POINTS_PER_INCH_FEED = 80  # density for feed moves
        POINTS_PER_INCH_RAPID = 20  # density for rapids
        MIN_POINTS = 3  # minimum points per move

        path = []
        for i, mv in enumerate(sim_moves):
            sx_r = mv.start_x / 2.0
            sz = mv.start_z
            ex_r = mv.end_x / 2.0
            ez = mv.end_z

            is_rapid = mv.move_type == "rapid"
            is_arc = mv.move_type in ("arc_cw", "arc_ccw")
            density = POINTS_PER_INCH_RAPID if is_rapid else POINTS_PER_INCH_FEED

            if is_arc and (abs(mv.center_i) > 0.0001 or abs(mv.center_k) > 0.0001):
                # Arc interpolation
                ci_r = mv.center_i / 2.0
                ck = mv.center_k
                cx_r = sx_r + ci_r
                cz = sz + ck
                radius = math.sqrt((sx_r - cx_r)**2 + (sz - cz)**2)
                if radius > 0.0001:
                    # Compute arc length for point count
                    angle_start = math.atan2(sz - cz, sx_r - cx_r)
                    angle_end = math.atan2(ez - cz, ex_r - cx_r)
                    diff = angle_end - angle_start
                    if diff > math.pi:
                        diff -= 2 * math.pi
                    elif diff < -math.pi:
                        diff += 2 * math.pi
                    arc_length = abs(diff) * radius
                    n_pts = max(MIN_POINTS, int(arc_length * density))
                    for j in range(n_pts):
                        t = j / float(n_pts - 1) if n_pts > 1 else 0.0
                        angle = angle_start + diff * t
                        px = cx_r + radius * math.cos(angle)
                        pz = cz + radius * math.sin(angle)
                        path.append((px, pz, i))
                    continue

            # Linear interpolation (feed or rapid)
            dist = math.sqrt((ex_r - sx_r)**2 + (ez - sz)**2)
            n_pts = max(MIN_POINTS, int(dist * density))
            for j in range(n_pts):
                t = j / float(n_pts - 1) if n_pts > 1 else 0.0
                px = sx_r + (ex_r - sx_r) * t
                pz = sz + (ez - sz) * t
                path.append((px, pz, i))

        # Add final endpoint
        if sim_moves:
            last = sim_moves[-1]
            path.append((last.end_x / 2.0, last.end_z, len(sim_moves) - 1))

        return path

    # --- Playback controls ---

    def _toggle_play(self):
        if self._sim_timer.isActive():
            self._sim_timer.stop()
            self._btn_play.setText("Play")
        else:
            self._sim_timer.start(self._sim_speed)
            self._btn_play.setText("Pause")

    def _sim_stop(self):
        self._sim_timer.stop()
        self._btn_play.setText("Play")
        self._sim_step = 0
        self._emit_line()
        self._update_display()

    def _step_fwd(self):
        if self._sim_step < self._path_len - 1:
            # Jump to next move boundary
            current_move = self._path[min(self._sim_step, self._path_len - 1)][2]
            for i in range(self._sim_step + 1, self._path_len):
                if self._path[i][2] != current_move:
                    self._sim_step = i
                    break
            else:
                self._sim_step = self._path_len - 1
            self._emit_line()
            self._update_display()

    def _step_back(self):
        if self._sim_step > 0:
            current_move = self._path[self._sim_step][2]
            for i in range(self._sim_step - 1, -1, -1):
                if self._path[i][2] != current_move:
                    self._sim_step = i
                    break
            else:
                self._sim_step = 0
            self._emit_line()
            self._update_display()

    def _sim_show_all(self):
        self._sim_timer.stop()
        self._btn_play.setText("Play")
        self._sim_step = self._path_len - 1
        self._emit_line()
        self._update_display()

    def _sim_advance(self):
        """Timer tick — advance along interpolated path."""
        if self._sim_step >= self._path_len - 1:
            self._sim_timer.stop()
            self._btn_play.setText("Play")
            return
        self._sim_step = min(self._sim_step + self._steps_per_tick, self._path_len - 1)
        self._emit_line()
        self._update_display()

    def _on_speed(self, text):
        speed_map = {"0.25x": 1, "0.5x": 2, "1x": 4, "2x": 8, "5x": 16, "10x": 32}
        self._steps_per_tick = speed_map.get(text, 4)

    def _on_slider(self, value):
        if not self._sim_timer.isActive():
            self._sim_step = value
            self._emit_line()
            self._update_display()

    # --- Sync ---

    def _emit_line(self):
        """Emit the line_idx of the current move."""
        if self._sim_step > 0 and self._path:
            _, _, move_idx = self._path[min(self._sim_step, self._path_len - 1)]
            if move_idx < len(self._sim_moves):
                self.sim_line_changed.emit(self._sim_moves[move_idx].line_idx)
            else:
                self.sim_line_changed.emit(-1)
        else:
            self.sim_line_changed.emit(-1)

    def _update_display(self):
        """Update tool dot, slider, and info label."""
        # Tool dot position from interpolated path
        if self._sim_step > 0 and self._path:
            x_r, z, move_idx = self._path[min(self._sim_step, self._path_len - 1)]
            self._graph.set_tool_position(x_r, z)
        else:
            self._graph.set_tool_position(0, 0)

        # Slider
        self._slider.blockSignals(True)
        self._slider.setValue(self._sim_step)
        self._slider.blockSignals(False)

        # Frame label
        self._frame_label.setText(f"{self._sim_step} / {self._path_len}")

        # Info label
        if self._sim_step > 0 and self._path:
            x_r, z, move_idx = self._path[min(self._sim_step, self._path_len - 1)]
            if move_idx < len(self._sim_moves):
                mv = self._sim_moves[move_idx]
                self._info_label.setText(
                    f"{mv.move_type:5s}  X{x_r*2:.4f}  Z{z:.4f}  "
                    f"(line {mv.line_idx + 1})"
                )
            else:
                self._info_label.setText("")
        else:
            self._info_label.setText("Ready")


# ---------------------------------------------------------------------------
# Build and run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    segments = [
        ProfileMove(SegmentType.LINE, 0.000, 0.000),
        ProfileMove(SegmentType.LINE, 1.000, 0.000),
        ProfileMove(SegmentType.LINE, 1.000, -0.500),
        ProfileMove(SegmentType.ARC, 1.000, -1.500, radius=-1.000),
        ProfileMove(SegmentType.LINE, 1.000, -2.000),
    ]
    breaks = [None, None, None, None]
    profile = ClosedProfile(segments=segments, corner_breaks=breaks, mode=MachiningMode.OD, z_end=-2.0)
    stock = StockDef(diameter=1.500, x_start=0.0, z_start=0.1, z_end=-2.0, mode=MachiningMode.OD)
    tool = ToolDef(1, 0.016, 80.0, 0.375, ToolOrientation.OD_FRONT_RIGHT, ToolDirection.RIGHT)
    roughing = RoughingParams(doc_dia=0.050, feed=0.005, strategy=RoughingStrategy.STAIRCASE, fin_allowance=0.002)
    finishing = FinishingParams(passes=1, doc_dia=0.002, feed=0.003)

    print("Executing pipeline...")
    result = execute(profile, stock, tool, roughing, finishing)
    print(f"Status: {result.status.value}")

    if result.status not in (PipelineStatus.SUCCESS, PipelineStatus.SUCCESS_WITH_WARNINGS):
        for v in result.validations:
            print(f"  [{v.severity.value}] {v.message}")
        sys.exit(1)

    pr = result.plan_result
    graph_data = graph_convert(pr)
    gcode_text = GCodeWriter().write(pr)

    # Parse G-code into SimMoves with line_idx tracking
    sim_moves = parse_gcode_for_sim(gcode_text)

    print(f"G-code: {len(gcode_text.splitlines())} lines")
    print(f"SimMoves: {len(sim_moves)} motion commands")
    print(f"First 5 moves:")
    for i, mv in enumerate(sim_moves[:5]):
        print(f"  {i+1}: line {mv.line_idx+1:3d} | {mv.move_type:5s} | X{mv.end_x:.4f} Z{mv.end_z:.4f}")
    print("Launching viewer...")

    app = QApplication(sys.argv)
    viewer = SimViewer(graph_data, gcode_text, sim_moves)
    viewer.show()
    sys.exit(app.exec_())
