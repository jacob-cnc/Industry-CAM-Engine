"""HAL Monitor Tab — Pin browser, signal tracing, and watch list.

Provides:
    - Hierarchical pin tree (split on '.' separators)
    - Preset filter buttons for quick access to pin groups
    - Text filter with substring matching
    - Signal tracing: click a signal → see all connected pins
    - Watch list with live value polling and change highlighting
    - Configurable refresh rate

Architecture:
    - Uses PinProvider for data access (Live or Offline)
    - Timer-based polling (only when tab is active)
    - Pure helper functions in hal_utils.py for tree building/formatting
"""

import logging
from typing import List, Set

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTreeWidget,
    QTreeWidgetItem, QTableWidget, QTableWidgetItem, QLineEdit,
    QPushButton, QLabel, QHeaderView, QAbstractItemView, QFrame,
    QComboBox,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QColor

from gui.colors import COLORS, FONTS
from gui.commissioning.pin_providers import PinProvider, PinInfo, get_pin_provider
from gui.commissioning.hal_utils import (
    build_pin_tree, format_pin_value, filter_pins, match_preset,
    FILTER_PRESETS, REFRESH_INTERVALS,
)
from hal.interface import HALBackend

logger = logging.getLogger(__name__)


class HALMonitorTab(QWidget):
    """HAL signal monitor — browse, filter, trace, and watch HAL pins."""

    def __init__(self, backend: HALBackend, parent=None):
        super().__init__(parent)
        self._backend = backend
        self._provider = get_pin_provider()
        self._all_pins: List[PinInfo] = []
        self._pin_lookup = {}
        self._watch_pins: List[str] = []
        self._prev_values = {}
        self._active = False

        self._build_ui()
        self._connect_signals()

        # Polling timer
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll_watch_values)
        self._timer.setInterval(100)

        # Initial load
        self._refresh_pins()

    # =================================================================
    # UI Construction
    # =================================================================

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(6, 6, 6, 6)

        # --- Offline banner ---
        if not self._backend.connected:
            banner = QLabel("OFFLINE — Demo Data")
            banner.setAlignment(Qt.AlignCenter)
            banner.setStyleSheet(
                f"background-color: {COLORS['status_warning']};"
                f"color: {COLORS['bg_base']};"
                f"padding: 4px; border-radius: 4px;"
                f"font-weight: bold;"
            )
            banner.setFixedHeight(26)
            layout.addWidget(banner)

        # --- Filter bar ---
        filter_row = QHBoxLayout()
        filter_row.setSpacing(4)
        lbl = QLabel("Filter:")
        lbl.setStyleSheet(f"color: {COLORS['text_secondary']};")
        filter_row.addWidget(lbl)

        self._filter_input = QLineEdit()
        self._filter_input.setPlaceholderText("Type to filter pins…")
        self._filter_input.setFixedHeight(32)
        filter_row.addWidget(self._filter_input, stretch=1)
        layout.addLayout(filter_row)

        # --- Preset buttons ---
        preset_row = QHBoxLayout()
        preset_row.setSpacing(3)
        self._preset_buttons = []
        for key in FILTER_PRESETS:
            btn = QPushButton(key)
            btn.setFixedHeight(28)
            btn.setStyleSheet(
                f"QPushButton {{ padding: 2px 8px; font-size: 9pt;"
                f"  min-width: 0px; min-height: 0px; }}"
            )
            btn.setProperty("preset_name", key)
            btn.clicked.connect(self._on_preset_clicked)
            self._preset_buttons.append(btn)
            preset_row.addWidget(btn)
        preset_row.addStretch()
        layout.addLayout(preset_row)

        # --- Main splitter: tree (left) | watch list (right) ---
        splitter = QSplitter(Qt.Horizontal)

        # Left: pin tree + detail panel
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(2)

        self._pin_tree = QTreeWidget()
        self._pin_tree.setHeaderLabels(["Pin", "Type", "Value"])
        self._pin_tree.setAlternatingRowColors(True)
        header = self._pin_tree.header()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        left_layout.addWidget(self._pin_tree, stretch=1)

        # Detail panel (shows selected pin info + signal trace)
        self._detail_frame = QFrame()
        self._detail_frame.setStyleSheet(
            f"QFrame {{ background-color: {COLORS['bg_panel']};"
            f"  border: 1px solid {COLORS['border_normal']};"
            f"  border-radius: 4px; padding: 4px; }}"
        )
        detail_layout = QVBoxLayout(self._detail_frame)
        detail_layout.setContentsMargins(6, 4, 6, 4)
        detail_layout.setSpacing(2)

        self._detail_name = QLabel("Select a pin to view details")
        self._detail_name.setStyleSheet(
            f"color: {COLORS['status_info']}; font-weight: bold; border: none;"
        )
        detail_layout.addWidget(self._detail_name)

        self._detail_info = QLabel("")
        self._detail_info.setStyleSheet(
            f"color: {COLORS['text_primary']}; border: none;"
        )
        detail_layout.addWidget(self._detail_info)

        self._detail_signal = QLabel("")
        self._detail_signal.setWordWrap(True)
        self._detail_signal.setStyleSheet(
            f"color: {COLORS['text_secondary']}; border: none; font-size: 9pt;"
        )
        detail_layout.addWidget(self._detail_signal)

        self._detail_frame.setFixedHeight(90)
        left_layout.addWidget(self._detail_frame)

        splitter.addWidget(left)

        # Right: watch list
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(2)

        watch_label = QLabel("Watch List")
        watch_label.setStyleSheet(
            f"color: {COLORS['status_info']}; font-weight: bold;"
        )
        right_layout.addWidget(watch_label)

        self._watch_table = QTableWidget(0, 4)
        self._watch_table.setHorizontalHeaderLabels(
            ["Name", "Type", "Dir", "Value"]
        )
        self._watch_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._watch_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._watch_table.setAlternatingRowColors(True)
        wh = self._watch_table.horizontalHeader()
        wh.setSectionResizeMode(0, QHeaderView.Stretch)
        wh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        wh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        wh.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self._watch_table.verticalHeader().setVisible(False)
        right_layout.addWidget(self._watch_table, stretch=1)

        # Watch list controls
        watch_btns = QHBoxLayout()
        self._btn_clear_watch = QPushButton("Clear All")
        self._btn_clear_watch.setFixedHeight(28)
        self._btn_clear_watch.setStyleSheet(
            "QPushButton { padding: 2px 10px; min-height: 0px; }"
        )
        watch_btns.addWidget(self._btn_clear_watch)
        watch_btns.addStretch()
        right_layout.addLayout(watch_btns)

        splitter.addWidget(right)
        splitter.setSizes([450, 550])
        layout.addWidget(splitter, stretch=1)

        # --- Bottom controls ---
        bottom = QHBoxLayout()
        bottom.setSpacing(6)

        self._btn_refresh = QPushButton("Refresh")
        self._btn_refresh.setFixedHeight(32)
        self._btn_refresh.setStyleSheet(
            "QPushButton { padding: 2px 12px; min-height: 0px; }"
        )
        bottom.addWidget(self._btn_refresh)

        rate_label = QLabel("Rate:")
        rate_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        bottom.addWidget(rate_label)

        self._rate_combo = QComboBox()
        self._rate_combo.setFixedHeight(32)
        for ms, label in REFRESH_INTERVALS:
            self._rate_combo.addItem(label, ms)
        self._rate_combo.setCurrentIndex(1)  # 100ms default
        bottom.addWidget(self._rate_combo)

        bottom.addStretch()

        self._status_label = QLabel("Ready")
        self._status_label.setStyleSheet(f"color: {COLORS['text_disabled']};")
        bottom.addWidget(self._status_label)

        layout.addLayout(bottom)

    # =================================================================
    # Signal Connections
    # =================================================================

    def _connect_signals(self):
        self._filter_input.textChanged.connect(self._apply_filter)
        self._pin_tree.itemSelectionChanged.connect(self._on_tree_selection)
        self._pin_tree.itemDoubleClicked.connect(self._on_tree_double_click)
        self._btn_refresh.clicked.connect(self._refresh_pins)
        self._btn_clear_watch.clicked.connect(self._clear_watch)
        self._rate_combo.currentIndexChanged.connect(self._on_rate_changed)

    # =================================================================
    # Public API
    # =================================================================

    def set_active(self, active: bool):
        """Start/stop polling based on tab visibility."""
        self._active = active
        if active and self._watch_pins:
            self._timer.start()
        else:
            self._timer.stop()

    # =================================================================
    # Pin Loading & Tree
    # =================================================================

    def _refresh_pins(self):
        """Re-enumerate all HAL pins and rebuild the tree."""
        try:
            self._all_pins = self._provider.get_all_pins()
            self._pin_lookup = {p.name: p for p in self._all_pins}
        except Exception as e:
            self._all_pins = []
            self._pin_lookup = {}
            self._status_label.setText(f"Error: {e}")
            return

        self._build_tree(self._all_pins)
        self._status_label.setText(f"{len(self._all_pins)} pins loaded")

    def _build_tree(self, pins: List[PinInfo]):
        """Populate QTreeWidget from flat pin list."""
        self._pin_tree.clear()
        tree_dict = build_pin_tree(pins)
        self._populate_tree(self._pin_tree.invisibleRootItem(), tree_dict)
        self._pin_tree.expandToDepth(0)

    def _populate_tree(self, parent_item, node: dict):
        """Recursively add QTreeWidgetItems from nested dict."""
        for key in sorted(node.keys()):
            value = node[key]
            if isinstance(value, PinInfo):
                # Leaf node
                item = QTreeWidgetItem(parent_item)
                item.setText(0, key)
                item.setText(1, value.pin_type)
                item.setText(2, format_pin_value(value.value, value.pin_type))
                item.setData(0, Qt.UserRole, value.name)
                # Color-code bit values
                if value.pin_type == "bit":
                    color = COLORS['status_ok'] if value.value else COLORS['text_disabled']
                    item.setForeground(2, QColor(color))
            elif isinstance(value, dict):
                # Branch node
                item = QTreeWidgetItem(parent_item)
                item.setText(0, key)
                item.setForeground(0, QColor(COLORS['status_info']))
                self._populate_tree(item, value)

    # =================================================================
    # Filtering
    # =================================================================

    def _apply_filter(self, text: str):
        if not text:
            self._show_all_items(self._pin_tree.invisibleRootItem())
            return
        matching = {p.name for p in filter_pins(self._all_pins, text)}
        self._filter_tree(self._pin_tree.invisibleRootItem(), matching)

    def _on_preset_clicked(self):
        btn = self.sender()
        if btn:
            preset_name = btn.property("preset_name")
            patterns = FILTER_PRESETS.get(preset_name, [])
            self._filter_input.blockSignals(True)
            self._filter_input.setText(f"[{preset_name}]")
            self._filter_input.blockSignals(False)
            matching = {
                p.name for p in self._all_pins
                if match_preset(p.name, patterns)
            }
            self._filter_tree(self._pin_tree.invisibleRootItem(), matching)

    def _filter_tree(self, parent, matching: Set[str]) -> bool:
        any_visible = False
        for i in range(parent.childCount()):
            child = parent.child(i)
            pin_name = child.data(0, Qt.UserRole)
            if pin_name:
                visible = pin_name in matching
                child.setHidden(not visible)
                if visible:
                    any_visible = True
            else:
                child_visible = self._filter_tree(child, matching)
                child.setHidden(not child_visible)
                if child_visible:
                    child.setExpanded(True)
                    any_visible = True
        return any_visible

    def _show_all_items(self, parent):
        for i in range(parent.childCount()):
            child = parent.child(i)
            child.setHidden(False)
            if child.childCount() > 0:
                self._show_all_items(child)

    # =================================================================
    # Tree Selection & Signal Tracing
    # =================================================================

    def _on_tree_selection(self):
        items = self._pin_tree.selectedItems()
        if not items:
            return
        pin_name = items[0].data(0, Qt.UserRole)
        if pin_name:
            self._show_pin_detail(pin_name)

    def _on_tree_double_click(self, item, column):
        """Double-click adds pin to watch list."""
        pin_name = item.data(0, Qt.UserRole)
        if pin_name:
            self._add_to_watch(pin_name)

    def _show_pin_detail(self, pin_name: str):
        """Show pin info and signal trace in detail panel."""
        pin = self._pin_lookup.get(pin_name)
        if not pin:
            self._detail_name.setText("Pin not found")
            self._detail_info.setText("")
            self._detail_signal.setText("")
            return

        self._detail_name.setText(pin.name)
        val_str = format_pin_value(pin.value, pin.pin_type)
        self._detail_info.setText(
            f"Type: {pin.pin_type}  |  Dir: {pin.direction}  |  "
            f"Value: {val_str}"
        )

        # Signal tracing
        if pin.signal:
            connected = self._provider.get_signal_pins(pin.signal)
            if connected:
                names = [p.name for p in connected if p.name != pin.name]
                trace_text = (
                    f"Signal: [{pin.signal}] → "
                    + ", ".join(names[:5])
                )
                if len(names) > 5:
                    trace_text += f" (+{len(names) - 5} more)"
            else:
                trace_text = f"Signal: [{pin.signal}]"
            self._detail_signal.setText(trace_text)
        else:
            self._detail_signal.setText("Signal: (unconnected)")

    # =================================================================
    # Watch List
    # =================================================================

    def _add_to_watch(self, pin_name: str):
        if pin_name in self._watch_pins:
            return
        pin = self._pin_lookup.get(pin_name)
        if not pin:
            return

        self._watch_pins.append(pin_name)
        row = self._watch_table.rowCount()
        self._watch_table.insertRow(row)

        self._watch_table.setItem(row, 0, QTableWidgetItem(pin.name))
        self._watch_table.setItem(row, 1, QTableWidgetItem(pin.pin_type))
        self._watch_table.setItem(row, 2, QTableWidgetItem(pin.direction))
        val_item = QTableWidgetItem(format_pin_value(pin.value, pin.pin_type))
        self._watch_table.setItem(row, 3, val_item)

        # Start polling if active
        if self._active and not self._timer.isActive():
            self._timer.start()

    def _clear_watch(self):
        self._watch_pins.clear()
        self._watch_table.setRowCount(0)
        self._prev_values.clear()
        self._timer.stop()

    # =================================================================
    # Polling
    # =================================================================

    def _poll_watch_values(self):
        """Timer callback — update watch list values."""
        for row, pin_name in enumerate(self._watch_pins):
            try:
                value = self._provider.get_pin_value(pin_name)
            except (KeyError, Exception):
                continue

            pin = self._pin_lookup.get(pin_name)
            pin_type = pin.pin_type if pin else "float"
            val_str = format_pin_value(value, pin_type)

            val_item = self._watch_table.item(row, 3)
            if val_item:
                val_item.setText(val_str)

                # Change highlighting for bits
                if pin_type == "bit":
                    prev = self._prev_values.get(pin_name)
                    if prev is not None and prev != value:
                        val_item.setBackground(QColor(COLORS['status_warning']))
                        QTimer.singleShot(
                            300,
                            lambda r=row: self._reset_cell_bg(r)
                        )

            self._prev_values[pin_name] = value

    def _reset_cell_bg(self, row: int):
        if row < self._watch_table.rowCount():
            item = self._watch_table.item(row, 3)
            if item:
                item.setBackground(QColor(0, 0, 0, 0))

    def _on_rate_changed(self, index: int):
        ms = self._rate_combo.itemData(index)
        if ms:
            self._timer.setInterval(ms)
