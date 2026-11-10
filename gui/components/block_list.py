"""Block list widget for multi-operation program management.

Displays an ordered list of machining operation blocks (profile, threading,
grooving, parting) with controls for add, delete, duplicate, and reorder.

Each block shows its type, tool number, and has a visibility toggle for
the graph display.
"""

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QListWidget,
    QListWidgetItem, QMenu, QAction, QLabel, QAbstractItemView,
    QSizePolicy,
)
from PyQt5.QtGui import QColor, QFont

from gui.colors import COLORS, FONTS
from models.program import ProgramBlock

# Control button sizing (px). Bubble radius matches the ribbon readouts.
BTN_W = 52          # Dup / Up / Dn / Vis / Del width, and "+ Add" minimum
BTN_H = 36          # their height, including the 1 px border
BTN_ROW_PAD = 6     # space above and below them in the button row
ADD_BTN_H = 30      # "+ Add" height (borderless)
BUBBLE_RADIUS = 5


# Block type display info — using ASCII-safe labels and distinct colors
BLOCK_TYPE_INFO = {
    "od_profile": {"label": "OD Profile", "color": "#5E9E91"},
    "id_profile": {"label": "ID Profile", "color": "#5494DA"},
    "threading_od": {"label": "Threading OD", "color": "#B88AD6"},
    "threading_id": {"label": "Threading ID", "color": "#9B6FC0"},
    "grooving_od": {"label": "Grooving OD", "color": "#E5A84B"},
    "grooving_id": {"label": "Grooving ID", "color": "#C98A30"},
    "parting": {"label": "Parting", "color": "#E56E72"},
}

# What block types are available in the Add menu
ADDABLE_BLOCK_TYPES = [
    "od_profile", "id_profile",
    "threading_od", "threading_id",
    "grooving_od", "grooving_id",
    "parting",
]


class BlockListWidget(QWidget):
    """Ordered list of program blocks with management controls.

    Signals:
        block_selected(int): Emitted when user clicks a block (block_id).
        block_added(str): Emitted when a new block type is added (block_type string).
        block_deleted(int): Emitted when a block is removed (block_id).
        block_duplicated(int): Emitted when a block is duplicated (source block_id).
        blocks_reordered(): Emitted when block order changes.
        block_visibility_changed(int, bool): Emitted when eye toggle changes (block_id, visible).
    """

    block_selected = pyqtSignal(int)        # block_id
    block_added = pyqtSignal(str)           # block_type
    block_deleted = pyqtSignal(int)         # block_id
    block_duplicated = pyqtSignal(int)      # source block_id
    blocks_reordered = pyqtSignal()
    block_visibility_changed = pyqtSignal(int, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._blocks: list = []  # List[ProgramBlock]
        self._next_id: int = 1
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 10)
        layout.setSpacing(0)

        # Header row: Add button only (title provided by parent CollapsibleSection)
        # Heights are set in QSS (min/max-height): the app-wide QPushButton
        # rule (min-height 44 + 8 px padding) otherwise beats setFixedHeight,
        # which made "+ Add" draw 48 px tall in this 34 px row and overlap
        # the list below it.
        header = QWidget()
        header.setFixedHeight(ADD_BTN_H + 8)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 4, 0, 4)
        header_layout.setSpacing(4)

        header_layout.addStretch()

        self._add_btn = QPushButton("+ Add")
        self._add_btn.setMinimumWidth(BTN_W)
        self._add_btn.setToolTip("Add operation block")
        self._add_btn.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {COLORS['btn_generate']};"
            f"  color: {COLORS['text_primary']};"
            f"  border: none; border-radius: {BUBBLE_RADIUS}px;"
            f"  padding: 0px 10px;"
            f"  min-height: {ADD_BTN_H}px; max-height: {ADD_BTN_H}px;"
            f"  font-size: {FONTS['small_size']}pt; font-weight: bold;"
            f"}}"
            f"QPushButton:hover {{ background-color: {COLORS['status_ok']}; }}"
        )
        self._add_btn.clicked.connect(self._show_add_menu)
        header_layout.addWidget(self._add_btn)

        layout.addWidget(header)

        # Block list
        self._list = QListWidget()
        self._list.setDragDropMode(QAbstractItemView.InternalMove)
        self._list.setDefaultDropAction(Qt.MoveAction)
        self._list.setMinimumHeight(80)
        self._list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._list.setStyleSheet(
            f"QListWidget {{"
            f"  background-color: {COLORS['bg_panel']};"
            f"  color: {COLORS['text_primary']};"
            f"  border: none;"
            f"  font-size: {FONTS['ui_size']}pt;"
            f"  outline: none;"
            f"}}"
            f"QListWidget::item {{"
            f"  padding: 6px 8px;"
            f"  border-bottom: 1px solid {COLORS['bg_base']};"
            f"}}"
            f"QListWidget::item:selected {{"
            f"  background-color: {COLORS['btn_primary']};"
            f"  color: {COLORS['text_primary']};"
            f"}}"
            f"QListWidget::item:hover:!selected {{"
            f"  background-color: {COLORS['bg_surface']};"
            f"}}"
        )
        self._list.currentRowChanged.connect(self._on_row_changed)
        self._list.model().rowsMoved.connect(self._on_rows_moved)
        layout.addWidget(self._list)

        # Control buttons row
        # Row style scoped to the row itself (#blockBtnRow): unscoped, the
        # border-top leaked onto every button and drew a stray top edge.
        btn_row = QWidget()
        btn_row.setObjectName("blockBtnRow")
        btn_row.setAttribute(Qt.WA_StyledBackground, True)
        btn_row.setFixedHeight(BTN_H + 2 * BTN_ROW_PAD)
        btn_row.setStyleSheet(
            f"QWidget#blockBtnRow {{ background-color: {COLORS['bg_surface']};"
            f" border-top: 1px solid {COLORS['border_normal']}; }}")
        btn_layout = QHBoxLayout(btn_row)
        btn_layout.setContentsMargins(6, BTN_ROW_PAD, 6, BTN_ROW_PAD)
        btn_layout.setSpacing(4)

        self._dup_btn = self._make_btn("Dup", "Duplicate selected block")
        self._dup_btn.clicked.connect(self._on_duplicate)
        btn_layout.addWidget(self._dup_btn)

        self._up_btn = self._make_btn("Up", "Move up")
        self._up_btn.clicked.connect(self._on_move_up)
        btn_layout.addWidget(self._up_btn)

        self._down_btn = self._make_btn("Dn", "Move down")
        self._down_btn.clicked.connect(self._on_move_down)
        btn_layout.addWidget(self._down_btn)

        btn_layout.addStretch()

        self._vis_btn = self._make_btn("Vis", "Toggle graph visibility")
        self._vis_btn.clicked.connect(self._on_toggle_visibility)
        btn_layout.addWidget(self._vis_btn)

        # Same size and bubble shape as the others; red fill marks it.
        self._del_btn = self._make_btn(
            "Del", "Delete selected block",
            fill=COLORS['btn_danger'], text_color=COLORS['text_primary'],
            hover="#A03040")
        self._del_btn.clicked.connect(self._on_delete)
        btn_layout.addWidget(self._del_btn)

        layout.addWidget(btn_row)

    def _make_btn(self, text: str, tooltip: str, fill: str = None,
                  text_color: str = None, hover: str = None) -> QPushButton:
        """Block-list control button: the ribbon's bubble look (panel fill,
        1 px border, 5 px radius) at one fixed size, BTN_W x BTN_H.

        QSS heights are the content box: BTN_H - 2 px border. Setting them in
        QSS (not setFixedHeight) is what beats the app-wide QPushButton rule
        that made these draw 48-50 px tall and get cut off.
        """
        btn = QPushButton(text)
        btn.setFixedWidth(BTN_W)
        btn.setToolTip(tooltip)
        inner = BTN_H - 2
        btn.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {fill or COLORS['bg_panel']};"
            f"  color: {text_color or COLORS['text_primary']};"
            f"  border: 1px solid {COLORS['border_normal']};"
            f"  border-radius: {BUBBLE_RADIUS}px;"
            f"  padding: 0px;"
            f"  min-height: {inner}px; max-height: {inner}px;"
            f"  font-size: {FONTS['small_size']}pt; font-weight: bold;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background-color: {hover or COLORS['btn_primary']};"
            f"  color: {COLORS['text_primary']};"
            f"  border-color: {hover or COLORS['btn_primary']};"
            f"}}"
        )
        return btn

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_block(self, block_type: str, select: bool = True) -> ProgramBlock:
        """Add a new block of the given type. Returns the created block."""
        block = ProgramBlock(
            block_id=self._next_id,
            block_type=block_type,
            tool_number=self._default_tool_for_type(block_type),
        )
        self._next_id += 1
        self._blocks.append(block)
        self._refresh_list()
        if select:
            self._list.setCurrentRow(len(self._blocks) - 1)
        self.block_added.emit(block_type)
        return block

    def get_blocks(self) -> list:
        """Return the ordered list of ProgramBlock objects."""
        return list(self._blocks)

    def get_selected_block(self) -> ProgramBlock | None:
        """Return the currently selected block, or None."""
        row = self._list.currentRow()
        if 0 <= row < len(self._blocks):
            return self._blocks[row]
        return None

    def get_block_by_id(self, block_id: int) -> ProgramBlock | None:
        """Find a block by its unique ID."""
        for b in self._blocks:
            if b.block_id == block_id:
                return b
        return None

    def update_block_tool(self, block_id: int, tool_number: int):
        """Update the displayed tool number for a block."""
        for i, b in enumerate(self._blocks):
            if b.block_id == block_id:
                b.tool_number = tool_number
                self._refresh_item(i)
                break

    def update_block_label(self, block_id: int, label: str):
        """Update the display label for a block."""
        for i, b in enumerate(self._blocks):
            if b.block_id == block_id:
                b.label = label
                self._refresh_item(i)
                break

    def select_block(self, block_id: int):
        """Programmatically select a block by ID."""
        for i, b in enumerate(self._blocks):
            if b.block_id == block_id:
                self._list.setCurrentRow(i)
                break

    def clear(self):
        """Remove all blocks."""
        self._blocks.clear()
        self._list.clear()

    def set_blocks(self, blocks: list):
        """Replace all blocks with a new list (for file load)."""
        self._blocks = list(blocks)
        if blocks:
            self._next_id = max(b.block_id for b in blocks) + 1
        self._refresh_list()
        if self._blocks:
            self._list.setCurrentRow(0)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _refresh_list(self):
        """Rebuild the QListWidget from self._blocks."""
        self._list.clear()
        for i, b in enumerate(self._blocks):
            item = QListWidgetItem(self._format_block_text(b, i))
            if not b.visible or not b.enabled:
                item.setForeground(QColor(COLORS['text_disabled']))
            self._list.addItem(item)

    def _refresh_item(self, row: int):
        """Update a single item's display text."""
        if 0 <= row < self._list.count():
            b = self._blocks[row]
            self._list.item(row).setText(self._format_block_text(b, row))

    def _format_block_text(self, block: ProgramBlock, index: int) -> str:
        """Format the display text for a block list item."""
        info = BLOCK_TYPE_INFO.get(block.block_type, {"label": block.block_type})
        label = block.label if block.label else info["label"]
        vis = "  [hidden]" if not block.visible else ""
        return f"{index + 1}. {label}{vis}"

    def _default_tool_for_type(self, block_type: str) -> int:
        """Sensible default tool number for each block type."""
        defaults = {
            "od_profile": 1,
            "id_profile": 1,
            "threading_od": 3,
            "threading_id": 3,
            "grooving_od": 4,
            "grooving_id": 4,
            "parting": 5,
        }
        return defaults.get(block_type, 1)

    def _show_add_menu(self):
        """Show dropdown menu for adding a new block type."""
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{"
            f"  background-color: {COLORS['bg_panel']};"
            f"  color: {COLORS['text_primary']};"
            f"  border: 1px solid {COLORS['border_normal']};"
            f"  padding: 4px;"
            f"  font-size: {FONTS['ui_size']}pt;"
            f"}}"
            f"QMenu::item {{"
            f"  padding: 6px 16px;"
            f"}}"
            f"QMenu::item:selected {{"
            f"  background-color: {COLORS['btn_primary']};"
            f"}}"
        )
        for bt in ADDABLE_BLOCK_TYPES:
            info = BLOCK_TYPE_INFO[bt]
            action = menu.addAction(info['label'])
            action.setData(bt)

        action = menu.exec_(self._add_btn.mapToGlobal(self._add_btn.rect().bottomLeft()))
        if action:
            self.add_block(action.data())

    def _on_row_changed(self, row: int):
        """User selected a different block."""
        if 0 <= row < len(self._blocks):
            self.block_selected.emit(self._blocks[row].block_id)

    def _on_rows_moved(self):
        """Drag-drop reorder completed — rebuild internal list to match UI order."""
        new_order = []
        for i in range(self._list.count()):
            text = self._list.item(i).text()
            for b in self._blocks:
                if self._format_block_text(b, self._blocks.index(b)) == text and b not in new_order:
                    new_order.append(b)
                    break
        if len(new_order) == len(self._blocks):
            self._blocks = new_order
            self._refresh_list()
            self.blocks_reordered.emit()

    def _on_duplicate(self):
        """Duplicate the selected block."""
        block = self.get_selected_block()
        if block is None:
            return
        new_block = ProgramBlock(
            block_id=self._next_id,
            block_type=block.block_type,
            tool_number=block.tool_number,
            enabled=block.enabled,
            label=f"{block.display_label} (copy)",
            visible=block.visible,
        )
        self._next_id += 1
        row = self._list.currentRow()
        self._blocks.insert(row + 1, new_block)
        self._refresh_list()
        self._list.setCurrentRow(row + 1)
        self.block_duplicated.emit(block.block_id)

    def _on_move_up(self):
        """Move selected block up one position."""
        row = self._list.currentRow()
        if row <= 0:
            return
        self._blocks[row], self._blocks[row - 1] = self._blocks[row - 1], self._blocks[row]
        self._refresh_list()
        self._list.setCurrentRow(row - 1)
        self.blocks_reordered.emit()

    def _on_move_down(self):
        """Move selected block down one position."""
        row = self._list.currentRow()
        if row < 0 or row >= len(self._blocks) - 1:
            return
        self._blocks[row], self._blocks[row + 1] = self._blocks[row + 1], self._blocks[row]
        self._refresh_list()
        self._list.setCurrentRow(row + 1)
        self.blocks_reordered.emit()

    def _on_toggle_visibility(self):
        """Toggle graph visibility for selected block."""
        row = self._list.currentRow()
        if 0 <= row < len(self._blocks):
            block = self._blocks[row]
            block.visible = not block.visible
            self._refresh_item(row)
            self.block_visibility_changed.emit(block.block_id, block.visible)

    def _on_delete(self):
        """Delete the selected block."""
        row = self._list.currentRow()
        if row < 0 or not self._blocks:
            return
        block = self._blocks.pop(row)
        self._refresh_list()
        if self._blocks:
            new_row = min(row, len(self._blocks) - 1)
            self._list.setCurrentRow(new_row)
        self.block_deleted.emit(block.block_id)
