"""Edit Tab for Industry CAM Engine.

G-code text editor with syntax highlighting, line numbers, find/replace,
file operations, and integrated graph/sim preview.
Works in offline mode (no LinuxCNC dependency).

Layout: QSplitter — editor (left) + graph+playback (right).
The Preview button parses G-code and loads toolpath into the local graph.

Signals:
    gcode_modified(): Emitted when text is edited by user
"""

import os
from typing import List, Optional

from PyQt5.QtCore import Qt, pyqtSignal, QRegExp, QRect, QSize
from PyQt5.QtGui import (
    QColor, QFont, QFontMetrics, QPainter, QSyntaxHighlighter,
    QTextCharFormat, QTextCursor, QTextDocument, QPen,
)
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPlainTextEdit, QTextEdit,
    QPushButton, QLabel, QLineEdit, QFileDialog, QSplitter,
    QShortcut, QToolBar, QAction, QMessageBox, QComboBox,
)

from gui.colors import COLORS, FONTS
from outputs.gcode_parser import parse as parse_gcode


# ---------------------------------------------------------------------------
# Syntax Highlighter
# ---------------------------------------------------------------------------

class GCodeHighlighter(QSyntaxHighlighter):
    """Syntax highlighter for G-code with per-code color differentiation.

    Color scheme:
        G00/G0  — Red (rapid, danger-awareness)
        G01/G1  — Green (linear feed, safe cutting)
        G02/G2  — Cyan (arc CW)
        G03/G3  — Magenta/purple (arc CCW)
        G20/G21 — Gray (units)
        G28/G30 — Orange-red (machine home/reference)
        G40-G43 — Teal (cutter comp / tool length)
        G54-G59 — Slate blue (work offsets)
        G90/G91 — Muted gold (absolute/incremental)
        G96/G97 — Warm amber (CSS/RPM)
        Other G  — Default blue
        M-codes — Sage green (spindle, coolant, program)
        Axis words — Amber (X, Z, I, K, R, F + values)
        N-numbers — Subtle gray
        Comments — Dim green italic
    """

    def __init__(self, document: QTextDocument):
        super().__init__(document)
        self._rules = []          # (QRegExp, QTextCharFormat) — general rules
        self._g_code_formats = {} # {pattern_str: QTextCharFormat} — specific G-codes
        self._setup_rules()

    def _setup_rules(self):
        """Define highlighting rules with per-G-code colors."""

        # --- Specific G-code colors (matched first, highest priority) ---
        # Rapid: red
        self._add_g_code_rule(r'\bG0?0\b', "#E06060", bold=True)
        # Linear feed: green
        self._add_g_code_rule(r'\bG0?1\b', "#5EBB7A", bold=True)
        # Arc CW: cyan
        self._add_g_code_rule(r'\bG0?2\b', "#5EC4D4", bold=True)
        # Arc CCW: purple/magenta
        self._add_g_code_rule(r'\bG0?3\b', "#C07ADB", bold=True)
        # Dwell: muted orange
        self._add_g_code_rule(r'\bG0?4\b', "#D4A054", bold=True)
        # Units (G20/G21): gray
        self._add_g_code_rule(r'\bG2[01]\b', "#9AAFC2", bold=True)
        # Machine home/reference (G28/G30): orange-red
        self._add_g_code_rule(r'\bG(28|30)\b', "#E08050", bold=True)
        # Cutter comp / tool length (G40-G43): teal
        self._add_g_code_rule(r'\bG4[0-3]\b', "#4DB8A8", bold=True)
        # Work offsets (G54-G59): slate blue
        self._add_g_code_rule(r'\bG5[4-9]\b', "#7B9ED4", bold=True)
        # Absolute/Incremental (G90/G91): muted gold
        self._add_g_code_rule(r'\bG9[01]\b', "#C4A84D", bold=True)
        # CSS/RPM (G96/G97): warm amber
        self._add_g_code_rule(r'\bG9[67]\b', "#E5A84D", bold=True)
        # Cancel canned cycle (G80): gray
        self._add_g_code_rule(r'\bG80\b', "#9AAFC2", bold=True)
        # Canned cycles (G81-G89): light blue
        self._add_g_code_rule(r'\bG8[1-9]\b', "#7BB9EE", bold=True)

        # --- Fallback: any other G-code not matched above → default blue ---
        g_fallback = QTextCharFormat()
        g_fallback.setForeground(QColor("#7BB9EE"))
        g_fallback.setFontWeight(QFont.Bold)
        self._rules.append((
            QRegExp(r'\bG\d{1,3}(\.\d+)?\b', Qt.CaseInsensitive),
            g_fallback,
        ))

        # --- M-codes: sage green ---
        m_format = QTextCharFormat()
        m_format.setForeground(QColor("#5E9E91"))
        m_format.setFontWeight(QFont.Bold)
        self._rules.append((
            QRegExp(r'\bM\d{1,3}\b', Qt.CaseInsensitive),
            m_format,
        ))

        # --- Axis words (X, Z, I, K, R, F + value): amber ---
        axis_format = QTextCharFormat()
        axis_format.setForeground(QColor("#E5A84D"))
        self._rules.append((
            QRegExp(r'\b[XZIKRF][+-]?\d*\.?\d+\b', Qt.CaseInsensitive),
            axis_format,
        ))

        # --- S-word (spindle speed): warm pink ---
        s_format = QTextCharFormat()
        s_format.setForeground(QColor("#D4789A"))
        self._rules.append((
            QRegExp(r'\bS\d+\.?\d*\b', Qt.CaseInsensitive),
            s_format,
        ))

        # --- T-word (tool number): light orange ---
        t_format = QTextCharFormat()
        t_format.setForeground(QColor("#E0A060"))
        t_format.setFontWeight(QFont.Bold)
        self._rules.append((
            QRegExp(r'\bT\d{1,4}\b', Qt.CaseInsensitive),
            t_format,
        ))

        # --- N-numbers: subtle gray ---
        n_format = QTextCharFormat()
        n_format.setForeground(QColor("#7A8A9A"))
        self._rules.append((
            QRegExp(r'\bN\d+\b', Qt.CaseInsensitive),
            n_format,
        ))

        # --- Parenthetical comments: dim green italic ---
        comment_paren_format = QTextCharFormat()
        comment_paren_format.setForeground(QColor("#6B9E6B"))
        comment_paren_format.setFontItalic(True)
        self._rules.append((
            QRegExp(r'\([^)]*\)'),
            comment_paren_format,
        ))

        # --- Semicolon comments: dim green italic ---
        comment_semi_format = QTextCharFormat()
        comment_semi_format.setForeground(QColor("#6B9E6B"))
        comment_semi_format.setFontItalic(True)
        self._rules.append((
            QRegExp(r';.*$'),
            comment_semi_format,
        ))

    def _add_g_code_rule(self, pattern: str, color: str, bold: bool = False):
        """Add a specific G-code highlighting rule (high priority)."""
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        if bold:
            fmt.setFontWeight(QFont.Bold)
        self._g_code_formats[pattern] = (QRegExp(pattern, Qt.CaseInsensitive), fmt)

    def highlightBlock(self, text: str):
        """Apply highlighting rules to a block of text.

        Order: general rules first, then specific G-code rules override.
        Comments applied last to override everything inside them.
        """
        # 1. Apply general rules (fallback G-codes, M-codes, axis words, etc.)
        for pattern, fmt in self._rules:
            index = pattern.indexIn(text)
            while index >= 0:
                length = pattern.matchedLength()
                self.setFormat(index, length, fmt)
                index = pattern.indexIn(text, index + length)

        # 2. Apply specific G-code rules (override the fallback blue)
        for _, (pattern, fmt) in self._g_code_formats.items():
            index = pattern.indexIn(text)
            while index >= 0:
                length = pattern.matchedLength()
                self.setFormat(index, length, fmt)
                index = pattern.indexIn(text, index + length)

        # 3. Re-apply comments last (they override everything)
        for pattern, fmt in self._rules[-2:]:  # Last two rules are comments
            index = pattern.indexIn(text)
            while index >= 0:
                length = pattern.matchedLength()
                self.setFormat(index, length, fmt)
                index = pattern.indexIn(text, index + length)


# ---------------------------------------------------------------------------
# Line Number Area
# ---------------------------------------------------------------------------

class LineNumberArea(QWidget):
    """Custom widget for displaying line numbers alongside the editor."""

    def __init__(self, editor: "GCodeEditor"):
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self._editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self._editor.line_number_area_paint_event(event)


# ---------------------------------------------------------------------------
# G-code Editor Widget
# ---------------------------------------------------------------------------

class GCodeEditor(QPlainTextEdit):
    """QPlainTextEdit subclass with line numbers and current line highlight."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._line_number_area = LineNumberArea(self)

        # Connect signals for line number updates
        self.blockCountChanged.connect(self._update_line_number_area_width)
        self.updateRequest.connect(self._update_line_number_area)
        self.cursorPositionChanged.connect(self._highlight_current_line)

        self._update_line_number_area_width(0)
        self._highlight_current_line()

        # Configure editor
        font = QFont(FONTS["mono_family"], FONTS["code_size"])
        font.setStyleHint(QFont.Monospace)
        self.setFont(font)
        self.setTabStopDistance(
            QFontMetrics(font).horizontalAdvance(' ') * 4
        )

        # Style
        self.setStyleSheet(
            f"QPlainTextEdit {{"
            f"  background-color: {COLORS['bg_panel']};"
            f"  color: {COLORS['text_primary']};"
            f"  border: none;"
            f"  selection-background-color: {COLORS['bg_surface']};"
            f"  selection-color: {COLORS['text_primary']};"
            f"}}"
        )

    def line_number_area_width(self) -> int:
        """Calculate the width needed for line numbers."""
        digits = max(1, len(str(self.blockCount())))
        space = 3 + QFontMetrics(self.font()).horizontalAdvance('9') * (digits + 1)
        return space

    def _update_line_number_area_width(self, _new_block_count: int):
        """Update viewport margins when block count changes."""
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def _update_line_number_area(self, rect, dy):
        """Scroll or repaint the line number area."""
        if dy:
            self._line_number_area.scroll(0, dy)
        else:
            self._line_number_area.update(0, rect.y(),
                                          self._line_number_area.width(),
                                          rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_line_number_area_width(0)

    def _highlight_current_line(self):
        """Highlight the current line with a subtle background."""
        extra_selections = []
        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            line_color = QColor(COLORS["bg_surface"])
            line_color.setAlpha(80)
            selection.format.setBackground(line_color)
            selection.format.setProperty(
                QTextCharFormat.FullWidthSelection, True
            )
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extra_selections.append(selection)
        self.setExtraSelections(extra_selections)

    def resizeEvent(self, event):
        """Resize the line number area when the editor is resized."""
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._line_number_area.setGeometry(
            QRect(cr.left(), cr.top(),
                  self.line_number_area_width(), cr.height())
        )

    def line_number_area_paint_event(self, event):
        """Paint line numbers in the line number area."""
        painter = QPainter(self._line_number_area)
        painter.fillRect(event.rect(), QColor(COLORS["bg_base"]))

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(self.blockBoundingGeometry(block)
                  .translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())

        font = self.font()
        painter.setFont(font)

        current_line = self.textCursor().blockNumber()

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                if block_number == current_line:
                    painter.setPen(QColor(COLORS["text_primary"]))
                else:
                    painter.setPen(QColor(COLORS["text_disabled"]))
                painter.drawText(
                    0, top,
                    self._line_number_area.width() - 4,
                    int(self.blockBoundingRect(block).height()),
                    Qt.AlignRight | Qt.AlignVCenter,
                    number,
                )
            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            block_number += 1

        painter.end()


# ---------------------------------------------------------------------------
# Find/Replace Bar
# ---------------------------------------------------------------------------

class FindReplaceBar(QWidget):
    """Find and Replace bar widget, hidden by default."""

    def __init__(self, editor: GCodeEditor, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._editor = editor
        self.setVisible(False)
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        self.setStyleSheet(
            f"QWidget {{ background-color: {COLORS['bg_surface']}; }}"
        )

        # Find field
        find_label = QLabel("Find:")
        find_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        layout.addWidget(find_label)

        self._find_field = QLineEdit()
        self._find_field.setPlaceholderText("Search...")
        self._find_field.setMinimumWidth(160)
        self._find_field.returnPressed.connect(self.find_next)
        layout.addWidget(self._find_field)

        # Find buttons
        btn_next = QPushButton("Next")
        btn_next.setFixedHeight(32)
        btn_next.clicked.connect(self.find_next)
        layout.addWidget(btn_next)

        btn_prev = QPushButton("Prev")
        btn_prev.setFixedHeight(32)
        btn_prev.clicked.connect(self.find_prev)
        layout.addWidget(btn_prev)

        # Separator
        sep = QLabel("|")
        sep.setStyleSheet(f"color: {COLORS['border_normal']};")
        layout.addWidget(sep)

        # Replace field
        replace_label = QLabel("Replace:")
        replace_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        layout.addWidget(replace_label)

        self._replace_field = QLineEdit()
        self._replace_field.setPlaceholderText("Replace with...")
        self._replace_field.setMinimumWidth(160)
        layout.addWidget(self._replace_field)

        # Replace buttons
        btn_replace = QPushButton("Replace")
        btn_replace.setFixedHeight(32)
        btn_replace.clicked.connect(self.replace_current)
        layout.addWidget(btn_replace)

        btn_replace_all = QPushButton("Replace All")
        btn_replace_all.setFixedHeight(32)
        btn_replace_all.clicked.connect(self.replace_all)
        layout.addWidget(btn_replace_all)

        layout.addStretch()

        # Close button
        btn_close = QPushButton("✕")
        btn_close.setFixedSize(28, 28)
        btn_close.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {COLORS['text_secondary']};"
            f" border: none; font-size: 14px; }}"
            f"QPushButton:hover {{ color: {COLORS['text_primary']}; }}"
        )
        btn_close.clicked.connect(self.hide)
        layout.addWidget(btn_close)

    def show_bar(self):
        """Show the find/replace bar and focus the search field."""
        self.setVisible(True)
        self._find_field.setFocus()
        self._find_field.selectAll()

    def find_next(self):
        """Find the next occurrence of the search text."""
        text = self._find_field.text()
        if not text:
            return
        if not self._editor.find(text):
            # Wrap around to beginning
            cursor = self._editor.textCursor()
            cursor.movePosition(QTextCursor.Start)
            self._editor.setTextCursor(cursor)
            self._editor.find(text)

    def find_prev(self):
        """Find the previous occurrence of the search text."""
        text = self._find_field.text()
        if not text:
            return
        if not self._editor.find(text, QTextDocument.FindBackward):
            # Wrap around to end
            cursor = self._editor.textCursor()
            cursor.movePosition(QTextCursor.End)
            self._editor.setTextCursor(cursor)
            self._editor.find(text, QTextDocument.FindBackward)

    def replace_current(self):
        """Replace the current selection if it matches the search text."""
        text = self._find_field.text()
        replacement = self._replace_field.text()
        if not text:
            return
        cursor = self._editor.textCursor()
        if cursor.hasSelection() and cursor.selectedText() == text:
            cursor.insertText(replacement)
        self.find_next()

    def replace_all(self):
        """Replace all occurrences of the search text."""
        text = self._find_field.text()
        replacement = self._replace_field.text()
        if not text:
            return
        # Use document-level replace for efficiency
        doc = self._editor.document()
        cursor = QTextCursor(doc)
        cursor.beginEditBlock()
        count = 0
        while True:
            cursor = doc.find(text, cursor)
            if cursor.isNull():
                break
            cursor.insertText(replacement)
            count += 1
        cursor.endEditBlock()


# ---------------------------------------------------------------------------
# Edit Tab
# ---------------------------------------------------------------------------

class EditTab(QWidget):
    """G-code editor tab with syntax highlighting, find/replace, file ops,
    and integrated graph/sim preview.

    Layout: QSplitter — editor+toolbar (left) + graph+playback (right).

    Signals:
        gcode_modified(): Emitted when text is edited by user
    """

    gcode_modified = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._current_file_path: Optional[str] = None
        self._move_line_map: List[int] = []
        self._setup_ui()
        self._connect_signals()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def receive_gcode(self, gcode_text: str) -> None:
        """Populate editor with G-code text from Program Tab.

        Args:
            gcode_text: Complete G-code program as string.
        """
        self._editor.setPlainText(gcode_text)
        # Move cursor to start
        cursor = self._editor.textCursor()
        cursor.movePosition(QTextCursor.Start)
        self._editor.setTextCursor(cursor)

    def get_text(self) -> str:
        """Return the current editor text."""
        return self._editor.toPlainText()

    def get_line_count(self) -> int:
        """Return the number of lines in the editor."""
        return self._editor.blockCount()

    # ------------------------------------------------------------------
    # UI Setup
    # ------------------------------------------------------------------

    def _setup_ui(self):
        """Build the complete tab layout: editor (left) + SimViewerWidget (right)."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Main splitter: editor panel (left) + sim viewer (right)
        self._splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(self._splitter)

        # Left panel: toolbar + find bar + editor
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        # Toolbar
        self._toolbar = self._build_toolbar()
        left_layout.addWidget(self._toolbar)

        # Find/Replace bar (hidden by default)
        self._editor = GCodeEditor()
        self._find_bar = FindReplaceBar(self._editor, self)
        left_layout.addWidget(self._find_bar)

        # Editor (main area)
        left_layout.addWidget(self._editor, stretch=1)

        # Syntax highlighter
        self._highlighter = GCodeHighlighter(self._editor.document())

        self._splitter.addWidget(left_panel)

        # Right panel: SimViewerWidget without its own G-code panel
        # (the editor on the left IS the code)
        from gui.components.sim_viewer import SimViewerWidget
        self._sim_viewer = SimViewerWidget(show_gcode_panel=False)
        self._splitter.addWidget(self._sim_viewer)

        # The sim_line_changed signal highlights lines in OUR editor
        self._sim_viewer.sim_line_changed.connect(self._highlight_editor_line)
        # The editor toggle button lives in the sim viewer's control bar
        self._sim_viewer.editor_toggle_requested.connect(self.toggle_editor)

        # Splitter proportions: 35% editor, 65% viewer
        self._splitter.setSizes([350, 650])
        # Both sides collapsible by dragging
        self._splitter.setCollapsible(0, True)
        self._splitter.setCollapsible(1, True)

        # Keyboard shortcuts
        self._shortcut_find = QShortcut(Qt.CTRL + Qt.Key_F, self)
        self._shortcut_find.activated.connect(self._find_bar.show_bar)

        self._shortcut_save = QShortcut(Qt.CTRL + Qt.Key_S, self)
        self._shortcut_save.activated.connect(self._save_file)

        self._shortcut_open = QShortcut(Qt.CTRL + Qt.Key_O, self)
        self._shortcut_open.activated.connect(self._open_file)

    def _build_toolbar(self) -> QWidget:
        """Build the toolbar with file operations and preview button."""
        toolbar = QWidget()
        toolbar.setFixedHeight(44)
        toolbar.setStyleSheet(
            f"QWidget {{ background-color: {COLORS['bg_surface']}; }}"
        )
        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        btn_style = (
            f"QPushButton {{"
            f"  background-color: {COLORS['bg_panel']};"
            f"  color: {COLORS['text_primary']};"
            f"  border: 1px solid {COLORS['border_normal']};"
            f"  border-radius: 3px;"
            f"  padding: 4px 12px;"
            f"  min-height: 30px;"
            f"  font-size: {FONTS['ui_size']}pt;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background-color: {COLORS['btn_primary_hover']};"
            f"  border-color: {COLORS['border_focused']};"
            f"}}"
        )

        # Open
        self._btn_open = QPushButton("Open")
        self._btn_open.setToolTip("Open G-code file (Ctrl+O)")
        self._btn_open.setStyleSheet(btn_style)
        layout.addWidget(self._btn_open)

        # Save
        self._btn_save = QPushButton("Save")
        self._btn_save.setToolTip("Save file (Ctrl+S)")
        self._btn_save.setStyleSheet(btn_style)
        layout.addWidget(self._btn_save)

        # Save As
        self._btn_save_as = QPushButton("Save As")
        self._btn_save_as.setToolTip("Save file as...")
        self._btn_save_as.setStyleSheet(btn_style)
        layout.addWidget(self._btn_save_as)

        # Clear
        self._btn_clear = QPushButton("Clear")
        self._btn_clear.setToolTip("Clear editor content")
        self._btn_clear.setStyleSheet(btn_style)
        layout.addWidget(self._btn_clear)

        # Reload
        self._btn_reload = QPushButton("Reload")
        self._btn_reload.setToolTip("Reload from last opened file")
        self._btn_reload.setStyleSheet(btn_style)
        layout.addWidget(self._btn_reload)

        # Separator
        sep = QLabel("|")
        sep.setStyleSheet(f"color: {COLORS['border_normal']}; padding: 0 4px;")
        layout.addWidget(sep)

        # Find
        self._btn_find = QPushButton("Find")
        self._btn_find.setToolTip("Find/Replace (Ctrl+F)")
        self._btn_find.setStyleSheet(btn_style)
        layout.addWidget(self._btn_find)

        # Preview
        preview_style = (
            f"QPushButton {{"
            f"  background-color: {COLORS['btn_generate']};"
            f"  color: {COLORS['text_primary']};"
            f"  border: none;"
            f"  border-radius: 3px;"
            f"  padding: 4px 16px;"
            f"  min-height: 30px;"
            f"  font-weight: bold;"
            f"  font-size: {FONTS['ui_size']}pt;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background-color: {COLORS['status_ok']};"
            f"}}"
        )
        self._btn_preview = QPushButton("Preview")
        self._btn_preview.setToolTip("Parse G-code and preview toolpath")
        self._btn_preview.setStyleSheet(preview_style)
        layout.addWidget(self._btn_preview)

        layout.addStretch()

        # File path label
        self._file_label = QLabel("")
        self._file_label.setStyleSheet(
            f"color: {COLORS['text_subtle']};"
            f" font-size: {FONTS['small_size']}pt;"
            f" font-family: {FONTS['mono_family']}, {FONTS['fallback_mono']};"
        )
        layout.addWidget(self._file_label)

        return toolbar

    # ------------------------------------------------------------------
    # Signal Connections
    # ------------------------------------------------------------------

    def _connect_signals(self):
        """Wire up toolbar buttons and editor signals."""
        self._btn_open.clicked.connect(self._open_file)
        self._btn_save.clicked.connect(self._save_file)
        self._btn_save_as.clicked.connect(self._save_file_as)
        self._btn_clear.clicked.connect(self._clear_editor)
        self._btn_reload.clicked.connect(self._reload_file)
        self._btn_find.clicked.connect(self._find_bar.show_bar)
        self._btn_preview.clicked.connect(self._on_preview)

        # Emit gcode_modified when text changes
        self._editor.textChanged.connect(self._on_text_changed)

    # ------------------------------------------------------------------
    # File Operations
    # ------------------------------------------------------------------

    def _open_file(self):
        """Open a G-code file or conversational program file.

        G-code files are loaded directly into the editor.
        Conversational files (.json, .cam) are parsed — if they contain
        G-code text it's loaded; otherwise the segments are displayed as info.
        """
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open File",
            "",
            "All Supported (*.ngc *.nc *.gcode *.tap *.json *.cam);;"
            "G-code (*.ngc *.nc *.gcode *.tap);;"
            "Conversational (*.json *.cam);;"
            "All Files (*)",
        )
        if not file_path:
            return

        ext = os.path.splitext(file_path)[1].lower()

        if ext in ('.json', '.cam'):
            self._open_conversational_in_editor(file_path)
        else:
            self._load_file(file_path)

    def _open_conversational_in_editor(self, path: str):
        """Open a conversational program file — run pipeline to get G-code.

        If the file contains valid program data, builds the pipeline inputs
        and generates G-code to display in the editor.
        """
        import json
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError, OSError) as e:
            QMessageBox.warning(self, "Load Error", f"Could not read file:\n{e}")
            return

        # Try to run the pipeline from the conversational data
        try:
            from pipeline.pipeline import execute as pipeline_execute
            from pipeline.model_builder import build_from_fields
            from outputs.gcode_writer import GCodeWriter
            from models.tool import ToolDef, ToolOrientation, ToolDirection, ToolType
            from gui.unit_state import unit_state

            stock = data.get("stock", {})
            roughing = data.get("roughing", {})
            finishing = data.get("finishing", {})
            segments = data.get("segments", [])

            if not segments:
                QMessageBox.information(
                    self, "No Segments",
                    "Conversational file has no profile segments.",
                )
                return

            # Default tool
            tool_def = ToolDef(
                tool_number=1, nose_radius=0.016, tip_angle=80.0,
                edge_length=0.375, orientation=ToolOrientation.OD_FRONT_RIGHT,
                direction=ToolDirection.RIGHT, tool_type=ToolType.TURNING,
                description="Default T1",
            )

            profile, stock_def, roughing_params, finishing_params = build_from_fields(
                segments=segments,
                stock_dia=stock.get("diameter", 2.0),
                x_start=stock.get("diameter", 2.0),
                z_start=stock.get("z_start", 0.1),
                z_end=stock.get("z_end", -1.0),
                mode=stock.get("mode", "od"),
                pilot_hole_dia=stock.get("pilot_hole_dia", 0.0),
                doc_dia=roughing.get("doc_dia", 0.050),
                feed=roughing.get("feed", 0.005),
                strategy=roughing.get("strategy", "staircase"),
                fin_allowance=roughing.get("fin_allowance", 0.005),
                peck_enabled=roughing.get("peck_enabled", False),
                peck_length=roughing.get("peck_length", None),
                spindle_rpm=roughing.get("spindle_rpm", 1200.0),
                finish_passes=int(finishing.get("passes", 1)),
                finish_doc_dia=finishing.get("doc_dia", 0.002),
                finish_feed=finishing.get("feed", 0.003),
                tool_def=tool_def,
            )

            result = pipeline_execute(profile, stock_def, tool_def,
                                      roughing_params, finishing_params)

            from models.validation import PipelineStatus
            if result.status not in (PipelineStatus.SUCCESS, PipelineStatus.SUCCESS_WITH_WARNINGS):
                errors = [v.message for v in result.validations[:3]]
                QMessageBox.warning(
                    self, "Pipeline Error",
                    f"Could not generate G-code from conversational file:\n" +
                    "\n".join(errors),
                )
                return

            gcode_text = GCodeWriter().write(result.plan_result, unit_mode=unit_state.mode.value)
            self._editor.setPlainText(gcode_text)
            self._current_file_path = path
            self._update_file_label()

            # Auto-preview
            self._on_preview()

        except Exception as e:
            QMessageBox.warning(
                self, "Load Error",
                f"Failed to generate G-code from conversational file:\n{e}",
            )

    def _save_file(self):
        """Save to the current file path, or prompt Save As if none."""
        if self._current_file_path:
            self._write_file(self._current_file_path)
        else:
            self._save_file_as()

    def _save_file_as(self):
        """Save the editor content to a new file via file dialog."""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save G-code File",
            "",
            "G-code Files (*.ngc *.nc *.gcode *.tap);;All Files (*)",
        )
        if file_path:
            self._write_file(file_path)
            self._current_file_path = file_path
            self._update_file_label()

    def _clear_editor(self):
        """Clear the editor content."""
        self._editor.clear()

    def _reload_file(self):
        """Reload from the last opened file path."""
        if self._current_file_path and os.path.isfile(self._current_file_path):
            self._load_file(self._current_file_path)

    def _load_file(self, file_path: str):
        """Load a file into the editor. Tries UTF-8, falls back to Latin-1."""
        try:
            content = self._read_text_file(file_path)
            self._editor.setPlainText(content)
            self._current_file_path = file_path
            self._update_file_label()
            # Move cursor to start
            cursor = self._editor.textCursor()
            cursor.movePosition(QTextCursor.Start)
            self._editor.setTextCursor(cursor)
        except (IOError, OSError) as e:
            QMessageBox.warning(
                self, "File Error",
                f"Could not open file:\n{e}",
            )

    @staticmethod
    def _read_text_file(path: str) -> str:
        """Read a text file, trying UTF-8 first then falling back to Latin-1."""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        except UnicodeDecodeError:
            with open(path, 'r', encoding='latin-1') as f:
                return f.read()

    def _write_file(self, file_path: str):
        """Write editor content to a file."""
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(self._editor.toPlainText())
        except (IOError, OSError) as e:
            QMessageBox.warning(
                self, "File Error",
                f"Could not save file:\n{e}",
            )

    def _update_file_label(self):
        """Update the file path label in the toolbar."""
        if self._current_file_path:
            name = os.path.basename(self._current_file_path)
            self._file_label.setText(name)
            self._file_label.setToolTip(self._current_file_path)
        else:
            self._file_label.setText("")
            self._file_label.setToolTip("")

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------

    def _on_preview(self):
        """Parse G-code and load into the SimViewerWidget (proven architecture)."""
        from gui.components.sim_viewer import parse_gcode_for_sim
        from outputs.graph_adapter import convert_from_moves

        text = self._editor.toPlainText()
        if not text.strip():
            return
        try:
            # Parse for the graph display
            moves = parse_gcode(text)
            if not moves:
                QMessageBox.information(
                    self, "No Moves",
                    "No motion commands found in the G-code.",
                )
                return

            # Build graph data from moves
            graph_data = convert_from_moves(moves)

            # Parse for sim (with line_idx tracking)
            sim_moves = parse_gcode_for_sim(text)

            # Load everything into the proven SimViewerWidget
            self._sim_viewer.load(graph_data, text, sim_moves)

        except Exception as e:
            QMessageBox.warning(
                self, "Parse Error",
                f"Could not parse G-code:\n{e}",
            )

    # ------------------------------------------------------------------
    # Text Change Handling
    # ------------------------------------------------------------------

    def _on_text_changed(self):
        """Emit gcode_modified signal when text is edited."""
        self.gcode_modified.emit()

    # ------------------------------------------------------------------
    # Editor Line Highlighting (synced to sim playback)
    # ------------------------------------------------------------------

    def _highlight_editor_line(self, line_idx: int):
        """Highlight a line in the editor during sim playback and center it."""
        from PyQt5.QtGui import QTextCursor, QColor, QTextCharFormat
        from PyQt5.QtWidgets import QTextEdit

        doc = self._editor.document()
        if line_idx < 0 or line_idx >= doc.blockCount():
            self._editor.setExtraSelections([])
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

        self._editor.setExtraSelections([selection])

        # Keep highlighted line centered
        scroll_cursor = QTextCursor(block)
        self._editor.setTextCursor(scroll_cursor)
        self._editor.centerCursor()

    def toggle_editor(self):
        """Toggle the editor panel between collapsed and visible (for external use)."""
        sizes = self._splitter.sizes()
        if sizes[0] < 10:
            self._splitter.setSizes([350, 650])
        else:
            self._splitter.setSizes([0, 1000])
