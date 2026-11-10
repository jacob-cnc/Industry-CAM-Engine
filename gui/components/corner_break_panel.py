"""Corner-break tool panel (Program tab).

Shown in place of the segment builder while the Corner Breaks tool is on.
Top: the break to apply (Chamfer / Fillet, one size per Apply) and actions.
Below: one row per vertex V1..V(n-1) with location, OD convex/concave,
current break and engine status (ok / trimmed / skipped / unvalidated) -
the row's tooltip carries the engine's full message.

Selection is shared with the graph: picking vertices on the graph selects
rows here and vice versa (ProgramTab wires both directions). Vertices are
identified by POINT INDEX (0-based); V number = point index + 1.
"""

from typing import List, Optional

from PyQt5.QtCore import QItemSelectionModel, Qt, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QAbstractItemView, QComboBox, QHBoxLayout, QHeaderView, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from gui.colors import COLORS, FONTS
from gui.components.numeric_field import NumericField, NumericFieldConfig
from gui.unit_state import unit_state

COLUMNS = ["V", "Z", "Ø", "Corner", "Break", "Status"]
STATUS_COLORS = {
    "ok": COLORS["text_primary"],
    "trimmed": COLORS["status_warning"],
    "skipped": COLORS["status_error"],
    "unvalidated": COLORS["text_disabled"],
}


class CornerBreakPanel(QWidget):
    """Vertex list + break settings for the corner-break tool."""

    selection_changed = pyqtSignal(list)        # point indices, sorted
    apply_requested = pyqtSignal(str, float)    # ("chamfer"|"fillet", size in inches)
    remove_requested = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._rows: List[dict] = []
        self._updating = False
        self._setup_ui()
        unit_state.unit_changed.connect(lambda _m: self._refill())

    # -- UI --------------------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        settings = QHBoxLayout()
        settings.setSpacing(4)
        self._kind = QComboBox()
        self._kind.addItems(["Chamfer", "Fillet"])
        self._kind.setToolTip("Equal-leg chamfer or fillet (one size per Apply)")
        self._size = NumericField(NumericFieldConfig(
            min_value=0.0005, max_value=1.0, decimals=4, default_value=0.010, suffix="in"))
        self._size.setToolTip("Chamfer leg / fillet radius (true length, not diameter)")
        settings.addWidget(self._kind, stretch=1)
        settings.addWidget(self._size, stretch=2)
        layout.addLayout(settings)

        actions = QHBoxLayout()
        actions.setSpacing(4)
        pad = "QPushButton { padding-left: 6px; padding-right: 6px; }"
        self._btn_apply = QPushButton("Apply")
        self._btn_remove = QPushButton("Remove")
        self._btn_all = QPushButton("All")
        self._btn_none = QPushButton("None")
        self._btn_apply.setToolTip("Apply this break to the selected vertices")
        self._btn_remove.setToolTip("Remove the break from the selected vertices")
        self._btn_all.setToolTip("Select every vertex")
        self._btn_none.setToolTip("Clear the selection")
        for b in (self._btn_apply, self._btn_remove, self._btn_all, self._btn_none):
            b.setStyleSheet(pad)
            actions.addWidget(b, stretch=1)
        layout.addLayout(actions)

        self._hint = QLabel("Click vertices on the graph (Ctrl+click adds / removes) "
                            "or select rows below.")
        self._hint.setWordWrap(True)
        self._hint.setStyleSheet(
            f"color: {COLORS['text_secondary']}; font-size: {FONTS['small_size']}pt;")
        layout.addWidget(self._hint)

        self._table = QTableWidget(0, len(COLUMNS))
        self._table.setHorizontalHeaderLabels(COLUMNS)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setWordWrap(False)
        # Selection must read clearly even when the table has no focus (the
        # user is usually clicking on the graph).
        self._table.setStyleSheet(
            f"QTableWidget::item:selected {{ background: {COLORS['btn_primary']};"
            f" color: {COLORS['text_primary']}; }}")
        hdr = self._table.horizontalHeader()
        for c in range(len(COLUMNS)):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(len(COLUMNS) - 1, QHeaderView.Stretch)
        layout.addWidget(self._table, stretch=1)

        self._btn_apply.clicked.connect(
            lambda: self.apply_requested.emit(self.kind(), self._size.value()))
        self._btn_remove.clicked.connect(self.remove_requested.emit)
        self._btn_all.clicked.connect(self._table.selectAll)
        self._btn_none.clicked.connect(self._table.clearSelection)
        self._table.itemSelectionChanged.connect(self._on_table_selection)

    # -- API -------------------------------------------------------------

    def kind(self) -> str:
        return "chamfer" if self._kind.currentIndex() == 0 else "fillet"

    def set_vertices(self, rows: List[dict]) -> None:
        """rows: one dict per vertex, in order:
        {"index", "z", "x_dia", "corner", "badge", "status", "message"}.
        The selection is kept for vertices that still exist."""
        keep = set(self.selected_vertices())
        self._rows = list(rows)
        self._refill(keep)

    def selected_vertices(self) -> List[int]:
        rows = sorted({i.row() for i in self._table.selectionModel().selectedRows()})
        return [self._rows[r]["index"] for r in rows if r < len(self._rows)]

    def set_selected(self, indices) -> None:
        """Select exactly these point indices (from graph picking)."""
        wanted = set(indices)
        self._updating = True
        try:
            self._table.clearSelection()
            sel = self._table.selectionModel()
            for r, row in enumerate(self._rows):
                if row["index"] in wanted:
                    sel.select(self._table.model().index(r, 0),
                               QItemSelectionModel.Select | QItemSelectionModel.Rows)
            hits = [r for r, row in enumerate(self._rows) if row["index"] in wanted]
            if hits and self._table.item(hits[0], 0) is not None:
                self._table.scrollToItem(self._table.item(hits[0], 0))
        finally:
            self._updating = False
        self.selection_changed.emit(self.selected_vertices())

    # -- internals -------------------------------------------------------

    def _refill(self, keep=None):
        if keep is None:
            keep = set(self.selected_vertices())
        self._updating = True
        try:
            self._table.setRowCount(len(self._rows))
            dec = unit_state.decimals
            for r, row in enumerate(self._rows):
                vals = [
                    f"V{row['index'] + 1}",
                    f"{unit_state.to_display(row['z']):.{dec}f}",
                    f"{unit_state.to_display(row['x_dia']):.{dec}f}",
                    row.get("corner", ""),
                    row.get("badge", "") or "—",
                    row.get("status", "") if row.get("badge") else "",
                ]
                tip = row.get("message", "")
                color = QColor(STATUS_COLORS.get(row.get("status", "ok"),
                                                 COLORS["text_primary"]))
                for c, v in enumerate(vals):
                    item = self._table.item(r, c) or QTableWidgetItem()
                    item.setText(v)
                    item.setToolTip(tip)
                    item.setTextAlignment(
                        Qt.AlignRight | Qt.AlignVCenter if c in (1, 2) else Qt.AlignCenter)
                    if c == 5:
                        item.setForeground(color)
                    self._table.setItem(r, c, item)
        finally:
            self._updating = False
        self.set_selected(keep)

    def _on_table_selection(self):
        if not self._updating:
            self.selection_changed.emit(self.selected_vertices())
