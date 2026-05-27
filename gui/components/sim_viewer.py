"""Simulation viewer widget — extracted from proven _visual_test_arc.py.

Provides: SimViewer (QWidget), GCodePanel, SimMove, parse_gcode_for_sim.

This is the EXACT architecture that worked during debug testing:
  G-code text → parse_gcode_for_sim (stamps line_idx) → interpolated path → timer playback
  Playback emits line_idx → GCodePanel highlights that line.
  Smooth motion via pre-computed dense interpolated path (80 pts/inch feed, 20 pts/inch rapid).
  Arcs interpolated along actual arc geometry.

Usage:
    viewer = SimViewerWidget()
    viewer.load(graph_data, gcode_text, sim_moves)
"""

import math
from dataclasses import dataclass
from typing import List, Optional

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QComboBox, QSlider, QSplitter, QPlainTextEdit,
    QTextEdit,
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QTextCursor, QColor, QTextCharFormat

from gui.components.graph_widget import MachiningGraphWidget
from gui.colors import COLORS, FONTS
from outputs.graph_adapter import GraphData
from models.moves import MoveType


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
    center_i: float = 0.0
    center_k: float = 0.0


# ---------------------------------------------------------------------------
# Parser — stamps each move with line_idx
# ---------------------------------------------------------------------------

def parse_gcode_for_sim(gcode_text: str) -> List[SimMove]:
    """Parse G-code into SimMoves, each stamped with its source line index."""
    moves: List[SimMove] = []
    x = 0.0
    z = 0.0
    feed = 0.0
    modal_motion = "G00"

    lines = gcode_text.splitlines()
    for line_idx, raw_line in enumerate(lines):
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

        tokens = line.split()
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

        new_x, new_z, new_f, new_i, new_k = None, None, None, None, None
        for token in tokens:
            if token[0] == "N":
                continue
            if token[0] == "X" and len(token) > 1:
                try: new_x = float(token[1:])
                except ValueError: pass
            elif token[0] == "Z" and len(token) > 1:
                try: new_z = float(token[1:])
                except ValueError: pass
            elif token[0] == "F" and len(token) > 1:
                try: new_f = float(token[1:])
                except ValueError: pass
            elif token[0] == "I" and len(token) > 1:
                try: new_i = float(token[1:])
                except ValueError: pass
            elif token[0] == "K" and len(token) > 1:
                try: new_k = float(token[1:])
                except ValueError: pass

        if new_f is not None:
            feed = new_f
        if new_x is None and new_z is None:
            continue

        end_x = new_x if new_x is not None else x
        end_z = new_z if new_z is not None else z
        if abs(end_x - x) < 0.00001 and abs(end_z - z) < 0.00001:
            continue

        if modal_motion == "G00": move_type = "rapid"
        elif modal_motion == "G01": move_type = "feed"
        elif modal_motion == "G02": move_type = "arc_cw"
        elif modal_motion == "G03": move_type = "arc_ccw"
        else: move_type = "feed"

        moves.append(SimMove(
            move_type=move_type, start_x=x, start_z=z,
            end_x=end_x, end_z=end_z, line_idx=line_idx,
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
        """Highlight a specific line (0-based) and scroll to keep it centered."""
        if line_idx == self._current_line:
            return
        self._current_line = line_idx

        if line_idx < 0:
            self.setExtraSelections([])
            return

        doc = self.document()
        if line_idx >= doc.blockCount():
            return

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

        # Scroll to keep highlighted line in the CENTER of the viewport
        scroll_cursor = QTextCursor(block)
        self.setTextCursor(scroll_cursor)
        self.centerCursor()


# ---------------------------------------------------------------------------
# SimViewerWidget — the proven viewer as an embeddable QWidget
# ---------------------------------------------------------------------------

class SimViewerWidget(QWidget):
    """Graph + G-code panel with timer-driven smooth playback.

    Drop-in widget version of the proven _visual_test_arc.py SimViewer.
    Embed in any tab layout. Call load() to populate with data.

    Args:
        show_gcode_panel: If True (default), shows the G-code text panel on the right.
            Set to False when the parent already has its own editor (e.g., Edit tab).
    """

    sim_line_changed = pyqtSignal(int)
    editor_toggle_requested = pyqtSignal()

    def __init__(self, parent=None, show_gcode_panel: bool = True):
        super().__init__(parent)
        self._show_gcode_panel = show_gcode_panel
        self._sim_moves: List[SimMove] = []
        self._sim_step = 0
        self._sim_timer = QTimer(self)
        self._sim_timer.timeout.connect(self._sim_advance)
        self._sim_speed = 16  # ms per frame (~60fps)
        self._steps_per_tick = 4  # default 1x

        self._path: List[tuple] = []
        self._path_len = 0

        self._material_enabled: bool = False  # DISABLED — material sim not accurate yet

        # SimMove-to-tool_moves index mapping (built in load())
        self._sim_to_toolmoves: dict = {}

        self._setup_ui()

    def load(self, graph_data: GraphData, gcode_text: str, sim_moves: List[SimMove]):
        """Load data into the viewer. Call after pipeline or file open."""
        self._sim_moves = sim_moves
        self._sim_step = 0

        # Pre-compute interpolated path
        self._path = self._build_interpolated_path(sim_moves)
        self._path_len = len(self._path)

        # Build SimMove-to-tool_moves index mapping
        self._sim_to_toolmoves = self._build_sim_to_toolmoves_mapping(
            sim_moves, graph_data
        )

        # Load graph
        self._graph.set_graph_data(graph_data)

        # Load G-code panel (if present) and auto-expand it
        if self._gcode_panel:
            self._gcode_panel.setPlainText(gcode_text)
            # Show the G-code panel if it was hidden
            if self._gcode_collapsed and self._splitter:
                self._splitter.setSizes([700, 350])
                self._btn_toggle_code.setText("Hide Code")
                self._gcode_collapsed = False

        # Update slider
        self._slider.setMaximum(self._path_len - 1 if self._path_len > 0 else 0)
        self._frame_label.setText(f"0 / {self._path_len}")
        self._info_label.setText("Ready")

    def _build_sim_to_toolmoves_mapping(
        self, sim_moves: List[SimMove], graph_data: GraphData
    ) -> dict:
        """Build a mapping from SimMove indices to tool_moves indices.

        Correlates endpoint coordinates (X, Z) between SimMove path entries
        and PlanResult.tool_moves entries (via graph_data.playback_frames).

        Handles cases where SimMove count differs from tool_moves count due to
        G-code comments, tool changes, and M-codes producing SimMoves without
        corresponding tool_moves (or vice versa).

        Returns:
            dict[int, int]: Mapping from SimMove index to tool_moves index.
                Only contains entries for SimMoves that have a matching tool_move.
        """
        mapping: dict = {}

        if not sim_moves or not graph_data or not graph_data.playback_frames:
            return mapping

        # playback_frames[i] corresponds to tool_moves[i]
        # Each has .x (radius) and .z
        frames = graph_data.playback_frames

        # Coordinate tolerance for matching endpoints (in inches)
        COORD_TOL = 0.001

        # Use a greedy forward-matching approach:
        # Walk through SimMoves and tool_moves in order, matching by endpoint.
        # This preserves ordering and handles extra SimMoves (comments/M-codes
        # that produce motion) or missing ones gracefully.
        tm_idx = 0  # Current position in tool_moves (playback_frames)
        n_frames = len(frames)

        for sim_idx, sm in enumerate(sim_moves):
            if tm_idx >= n_frames:
                break

            # SimMove endpoint in radius coordinates
            sm_x_r = sm.end_x / 2.0
            sm_z = sm.end_z

            # Check if current tool_move matches this SimMove's endpoint
            frame = frames[tm_idx]
            dx = abs(sm_x_r - frame.x)
            dz = abs(sm_z - frame.z)

            if dx < COORD_TOL and dz < COORD_TOL:
                mapping[sim_idx] = tm_idx
                tm_idx += 1
            else:
                # Look ahead in tool_moves for a match (handles cases where
                # tool_moves has entries that don't correspond to any SimMove)
                found = False
                for lookahead in range(1, min(5, n_frames - tm_idx)):
                    f = frames[tm_idx + lookahead]
                    if (abs(sm_x_r - f.x) < COORD_TOL and
                            abs(sm_z - f.z) < COORD_TOL):
                        # Skip unmatched tool_moves and map to this one
                        tm_idx = tm_idx + lookahead
                        mapping[sim_idx] = tm_idx
                        tm_idx += 1
                        found = True
                        break
                # If no match found, this SimMove has no corresponding tool_move
                # (e.g., it's from a G-code line that the planner didn't produce)

        return mapping

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        if self._show_gcode_panel:
            # Splitter: graph (left) + gcode panel (right, collapsible)
            self._splitter = QSplitter(Qt.Horizontal)
            layout.addWidget(self._splitter, stretch=1)

            self._graph = MachiningGraphWidget()
            self._splitter.addWidget(self._graph)

            self._gcode_panel = GCodePanel()
            self._splitter.addWidget(self._gcode_panel)

            self._splitter.setCollapsible(0, False)
            self._splitter.setCollapsible(1, True)
            self._splitter.setSizes([700, 350])
            self._gcode_collapsed = False
        else:
            # No G-code panel — just the graph
            self._graph = MachiningGraphWidget()
            layout.addWidget(self._graph, stretch=1)
            self._gcode_panel = None
            self._splitter = None
            self._gcode_collapsed = True  # effectively always collapsed

        # Connect line signal (only if panel exists)
        if self._gcode_panel:
            self.sim_line_changed.connect(self._gcode_panel.highlight_line)

        # Controls bar
        bar = self._build_controls()
        layout.addWidget(bar)

    def _build_controls(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(48)
        bar.setStyleSheet(f"background-color: {COLORS['bg_panel']};")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(6, 4, 6, 4)
        bar_layout.setSpacing(4)

        btn_style = (
            f"QPushButton {{ background-color: {COLORS['bg_surface']};"
            f" color: {COLORS['text_primary']}; border: 1px solid {COLORS['border_normal']};"
            f" border-radius: 4px; padding: 4px 8px; min-height: 28px;"
            f" font-weight: bold; }}"
            f"QPushButton:hover {{ background-color: {COLORS['btn_primary_hover']}; }}"
        )

        self._btn_play = QPushButton("Play")
        self._btn_play.setStyleSheet(btn_style)
        self._btn_play.clicked.connect(self._toggle_play)
        bar_layout.addWidget(self._btn_play)

        btn_reset = QPushButton("Reset")
        btn_reset.setStyleSheet(btn_style)
        btn_reset.clicked.connect(self._sim_stop)
        bar_layout.addWidget(btn_reset)

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

        self._btn_toggle_code = QPushButton("Hide Code")
        self._btn_toggle_code.setStyleSheet(btn_style)
        self._btn_toggle_code.clicked.connect(self._toggle_gcode_panel)
        if self._show_gcode_panel:
            bar_layout.addWidget(self._btn_toggle_code)
        else:
            self._btn_toggle_code.hide()

        # "Hide Editor" button — shown only when there's no internal gcode panel
        # (i.e., Edit tab mode where the parent has its own editor)
        self._btn_toggle_editor = QPushButton("Hide Editor")
        self._btn_toggle_editor.setStyleSheet(btn_style)
        self._btn_toggle_editor.clicked.connect(self._on_toggle_editor_clicked)
        if not self._show_gcode_panel:
            bar_layout.addWidget(self._btn_toggle_editor)
        else:
            self._btn_toggle_editor.hide()

        self._btn_toggle_rapids = QPushButton("Hide Rapids")
        self._btn_toggle_rapids.setStyleSheet(btn_style)
        self._btn_toggle_rapids.clicked.connect(self._toggle_rapids)
        bar_layout.addWidget(self._btn_toggle_rapids)
        self._rapids_visible = True

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
        self._slider.setMaximum(0)
        self._slider.valueChanged.connect(self._on_slider)
        bar_layout.addWidget(self._slider, stretch=1)

        self._frame_label = QLabel("0 / 0")
        self._frame_label.setStyleSheet(
            f"color: {COLORS['text_primary']};"
            f" font-family: {FONTS['mono_family']}, {FONTS['fallback_mono']};"
            f" font-size: 10pt; min-width: 80px;"
        )
        bar_layout.addWidget(self._frame_label)

        self._info_label = QLabel("Ready")
        self._info_label.setStyleSheet(
            f"color: {COLORS['text_secondary']}; font-size: 9pt; min-width: 240px;"
        )
        bar_layout.addWidget(self._info_label)

        return bar

    def _toggle_gcode_panel(self):
        """Toggle the G-code panel between collapsed and visible."""
        if self._splitter is None:
            return
        if self._gcode_collapsed:
            self._splitter.setSizes([700, 350])
            self._btn_toggle_code.setText("Hide Code")
            self._gcode_collapsed = False
        else:
            self._splitter.setSizes([1000, 0])
            self._btn_toggle_code.setText("Show Code")
            self._gcode_collapsed = True

    def _on_toggle_editor_clicked(self):
        """Emit signal for parent to toggle its editor panel."""
        self.editor_toggle_requested.emit()
        # Flip button text
        if self._btn_toggle_editor.text() == "Hide Editor":
            self._btn_toggle_editor.setText("Show Editor")
        else:
            self._btn_toggle_editor.setText("Hide Editor")

    def _toggle_rapids(self):
        """Toggle rapid move lines on/off."""
        if self._rapids_visible:
            self._graph.set_rapids_visible(False)
            self._btn_toggle_rapids.setText("Show Rapids")
            self._rapids_visible = False
        else:
            self._graph.set_rapids_visible(True)
            self._btn_toggle_rapids.setText("Hide Rapids")
            self._rapids_visible = True

    # --- Path interpolation (identical to proven _visual_test_arc.py) ---

    def _build_interpolated_path(self, sim_moves: List[SimMove]) -> List[tuple]:
        """Pre-compute dense interpolated path for smooth tool dot motion."""
        POINTS_PER_INCH_FEED = 80
        POINTS_PER_INCH_RAPID = 20
        MIN_POINTS = 3

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
                ci_r = mv.center_i / 2.0
                ck = mv.center_k
                cx_r = sx_r + ci_r
                cz = sz + ck
                radius = math.sqrt((sx_r - cx_r)**2 + (sz - cz)**2)
                if radius > 0.0001:
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

            dist = math.sqrt((ex_r - sx_r)**2 + (ez - sz)**2)
            n_pts = max(MIN_POINTS, int(dist * density))
            for j in range(n_pts):
                t = j / float(n_pts - 1) if n_pts > 1 else 0.0
                px = sx_r + (ex_r - sx_r) * t
                pz = sz + (ez - sz) * t
                path.append((px, pz, i))

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
        self._graph.hide_all_toolpath()
        self._emit_line()
        self._update_display()
        if self._material_enabled:
            self._graph.set_material_to_stock()

    def _step_fwd(self):
        if self._sim_step < self._path_len - 1:
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
        self._graph.show_all_toolpath()
        self._emit_line()
        self._update_display()
        if self._material_enabled:
            self._graph.set_material_to_final()

    def _sim_advance(self):
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

            # Update material state for slider scrubbing
            if self._material_enabled:
                ms = self._graph._graph_data.material_states if self._graph._graph_data else None
                if ms:
                    # Determine current move_index from the interpolated path
                    move_index = 0
                    if self._path and self._sim_step < len(self._path):
                        _, _, move_index = self._path[self._sim_step]

                    # Find last completed pass at or before current move_index
                    last_completed = -1
                    for i, ps in enumerate(ms.pass_states):
                        if ps.move_end <= move_index:
                            last_completed = i

                    if last_completed >= 0:
                        self._graph.set_material_state(last_completed)
                    else:
                        self._graph.set_material_to_stock()

    # --- Sync ---

    def _emit_line(self):
        if self._sim_step > 0 and self._path:
            _, _, move_idx = self._path[min(self._sim_step, self._path_len - 1)]
            if move_idx < len(self._sim_moves):
                self.sim_line_changed.emit(self._sim_moves[move_idx].line_idx)
            else:
                self.sim_line_changed.emit(-1)
        else:
            self.sim_line_changed.emit(-1)

    def _update_display(self):
        if self._sim_step > 0 and self._path:
            x_r, z, move_idx = self._path[min(self._sim_step, self._path_len - 1)]
            self._graph.set_tool_position(x_r, z)
            # Reveal toolpath segments up to current move
            # Convert sim_moves index to tool_moves index (toolpath_segments align with tool_moves)
            toolpath_idx = self._sim_to_toolmoves.get(move_idx, None)
            if toolpath_idx is not None:
                self._graph.reveal_toolpath_up_to(toolpath_idx)
            else:
                # No direct mapping — find the highest mapped index at or below move_idx
                mapped = [tm for sm, tm in self._sim_to_toolmoves.items() if sm <= move_idx]
                if mapped:
                    self._graph.reveal_toolpath_up_to(max(mapped))
        else:
            self._graph.set_tool_position(0, 0)

        self._slider.blockSignals(True)
        self._slider.setValue(self._sim_step)
        self._slider.blockSignals(False)

        self._frame_label.setText(f"{self._sim_step} / {self._path_len}")

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

        # --- Material removal state update ---
        if self._material_enabled and self._sim_step > 0 and self._path:
            self._update_material_state(move_idx)

    def _update_material_state(self, move_idx: int):
        """Update material polygon display based on current move index.

        Uses the pre-computed sim_to_toolmoves mapping to convert the SimMove
        index to a tool_moves index, then checks move_states for a pre-computed
        polygon at that index. If found, renders it directly for per-move
        granularity. Otherwise falls back to pass-state logic.

        This fixes sub-condition 1 (move_states not rendered) and sub-condition 4
        (index misalignment) from the bug specification.
        """
        graph_data = self._graph._graph_data
        if not graph_data or not graph_data.material_states:
            return

        # Map SimMove index to tool_moves index using pre-computed mapping
        tool_moves_idx = self._sim_to_toolmoves.get(move_idx)

        # If no mapping exists for this SimMove (e.g., G-code comment, M-code),
        # skip material update (similar to rapid move behavior)
        if tool_moves_idx is None:
            return

        # Get the toolpath segment using the MAPPED tool_moves index
        segments = graph_data.toolpath_segments
        if tool_moves_idx >= len(segments):
            return

        segment = segments[tool_moves_idx]

        # Skip material updates during rapid moves (preservation: requirement 3.3)
        if segment.move_type == MoveType.RAPID:
            return

        # Check if pre-computed move_states entry exists for this tool_moves index
        move_states = graph_data.material_states.move_states
        if tool_moves_idx in move_states:
            # Render the pre-computed per-move polygon directly
            # This provides per-move granularity instead of snapping to pass states
            self._graph.render_move_state(move_states[tool_moves_idx])
            return

        # Fallback: no move_states entry (pass boundary or edge case)
        # Use existing pass-state logic (preservation: requirements 3.1, 3.2)
        pass_states = graph_data.material_states.pass_states
        target_pass_index = segment.pass_index

        # Find the PassState matching this pass_index and compute progress
        for ps_idx, ps in enumerate(pass_states):
            if ps.pass_index == target_pass_index:
                # Compute progress within this pass (0.0 to 1.0)
                move_range = ps.move_end - ps.move_start
                if move_range > 0:
                    progress = (tool_moves_idx - ps.move_start) / float(move_range)
                    progress = max(0.0, min(1.0, progress))
                else:
                    progress = 1.0
                self._graph.set_partial_material(ps_idx, progress)
                return

        # If no matching pass found, show the last completed pass state
        # (tool_moves_idx is beyond all known passes)
        if pass_states:
            self._graph.set_material_state(len(pass_states) - 1)
