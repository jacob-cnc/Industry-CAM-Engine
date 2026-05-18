"""
HAL Monitor Tab — Browse, filter, and watch HAL pins in real time.

Provides a hierarchical pin tree, preset filter buttons, a watch list
with live value polling, and offline demo mode for development.
"""

from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QSplitter, QTreeWidget,
    QTreeWidgetItem, QTableWidget, QTableWidgetItem, QLineEdit,
    QPushButton, QComboBox, QLabel, QHeaderView, QAbstractItemView,
    QFrame,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QColor

from theme import COLORS, TOUCH_SIZES, ui_font, mono_font
from hal_monitor_utils import (
    build_pin_tree, format_pin_value, filter_pins, match_preset,
    FILTER_PRESETS, REFRESH_INTERVALS,
)
from hal_providers import LiveHALProvider, OfflineHALProvider


class HALMonitorTab(QWidget):
    """HAL signal monitor tab — browse, filter, and watch HAL pins live."""

    def __init__(self, has_linuxcnc=False, parent=None):
        super().__init__(parent)
        self._has_linuxcnc = has_linuxcnc
        self._all_pins = []
        self._pin_lookup = {}
        self._watch_pins = []
        self._prev_values = {}
        self._connected = True

        # --- Select provider ---
        if has_linuxcnc:
            try:
                self._provider = LiveHALProvider()
            except Exception:
                self._provider = OfflineHALProvider()
                self._has_linuxcnc = False
        else:
            self._provider = OfflineHALProvider()

        self._build_ui()
        self._connect_signals()

        # --- Polling timer ---
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_watch_values)
        self._timer.setInterval(100)

        # --- Initial pin load ---
        self.refresh_pins()

    # =================================================================
    # UI Construction
    # =================================================================

    def _build_ui(self):
        """Build the complete tab layout."""
        root = QVBoxLayout(self)
        root.setSpacing(4)
        root.setContentsMargins(6, 6, 6, 6)

        # --- Offline banner ---
        if not self._has_linuxcnc:
            banner = QLabel("OFFLINE — Demo Data")
            banner.setAlignment(Qt.AlignCenter)
            banner.setFont(ui_font(12, QFont.Bold))
            banner.setStyleSheet(
                f"background-color: {COLORS['accent_orange']};"
                f"color: {COLORS['bg_dark']};"
                f"padding: 4px; border-radius: 4px;"
            )
            banner.setFixedHeight(26)
            root.addWidget(banner)

        # --- Filter bar + preset buttons ---
        filter_row = QHBoxLayout()
        filter_row.setSpacing(4)
        lbl = QLabel("Filter:")
        lbl.setFont(ui_font(11))
        lbl.setStyleSheet(f"color: {COLORS['text_secondary']};")
        filter_row.addWidget(lbl)

        self._filter_input = QLineEdit()
        self._filter_input.setPlaceholderText("Type to filter pins…")
        self._filter_input.setFont(mono_font(11))
        self._filter_input.setFixedHeight(28)
        filter_row.addWidget(self._filter_input, stretch=1)
        root.addLayout(filter_row)

        # Preset buttons — single row
        preset_keys = list(FILTER_PRESETS.keys())
        self._preset_buttons = []
        preset_row = QHBoxLayout()
        preset_row.setSpacing(3)
        for key in preset_keys:
            btn = QPushButton(key)
            btn.setFont(ui_font(9))
            btn.setFixedHeight(24)
            btn.setStyleSheet(
                f"QPushButton {{ padding: 2px 6px; font-size: 12px;"
                f"  border-radius: 4px; min-width: 0px; }}"
            )
            btn.setProperty("preset_name", key)
            self._preset_buttons.append(btn)
            preset_row.addWidget(btn)
        preset_row.addStretch()
        root.addLayout(preset_row)

        # --- Main splitter: tree (left) | watch list (right) ---
        splitter = QSplitter(Qt.Horizontal)
        splitter.setStyleSheet(
            f"QSplitter::handle {{ background: {COLORS['border']}; width: 3px; }}"
        )

        # Left side — pin tree
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(2)

        self._pin_tree = QTreeWidget()
        self._pin_tree.setHeaderLabels(["Pin", "Type", "Value"])
        self._pin_tree.setFont(mono_font(10))
        self._pin_tree.setAlternatingRowColors(True)
        self._pin_tree.setStyleSheet(
            f"QTreeWidget {{ background-color: {COLORS['bg_mid']};"
            f"  alternate-background-color: {COLORS['bg_dark']};"
            f"  color: {COLORS['text']};"
            f"  border: 1px solid {COLORS['border']}; border-radius: 4px; }}"
            f"QTreeWidget::item:selected {{ background-color: {COLORS['accent_blue']}; }}"
            f"QHeaderView::section {{ background-color: {COLORS['bg_light']};"
            f"  color: {COLORS['text_secondary']}; border: none;"
            f"  padding: 3px 6px; font-size: 11px; }}"
        )
        header = self._pin_tree.header()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        left_layout.addWidget(self._pin_tree, stretch=1)

        # Detail panel below tree
        self._detail_frame = QFrame()
        self._detail_frame.setStyleSheet(
            f"QFrame {{ background-color: {COLORS['bg_dark']};"
            f"  border: 1px solid {COLORS['border']}; border-radius: 4px;"
            f"  padding: 4px; }}"
        )
        detail_layout = QVBoxLayout(self._detail_frame)
        detail_layout.setContentsMargins(6, 4, 6, 4)
        detail_layout.setSpacing(2)

        self._detail_name = QLabel("Select a pin to view details")
        self._detail_name.setFont(mono_font(10, QFont.Bold))
        self._detail_name.setStyleSheet(f"color: {COLORS['accent_blue_lt']}; border: none;")
        detail_layout.addWidget(self._detail_name)

        self._detail_info = QLabel("")
        self._detail_info.setFont(ui_font(10))
        self._detail_info.setStyleSheet(f"color: {COLORS['text']}; border: none;")
        detail_layout.addWidget(self._detail_info)

        self._detail_frame.setFixedHeight(80)
        left_layout.addWidget(self._detail_frame)

        splitter.addWidget(left_widget)

        # Right side — watch list
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(2)

        watch_label = QLabel("Watch List")
        watch_label.setFont(ui_font(11, QFont.Bold))
        watch_label.setStyleSheet(f"color: {COLORS['accent_blue_lt']};")
        right_layout.addWidget(watch_label)

        self._watch_table = QTableWidget(0, 5)
        self._watch_table.setHorizontalHeaderLabels(
            ["Name", "Type", "Dir", "Value", ""]
        )
        self._watch_table.setFont(mono_font(10))
        self._watch_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._watch_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._watch_table.setAlternatingRowColors(True)
        self._watch_table.setStyleSheet(
            f"QTableWidget {{ background-color: {COLORS['bg_mid']};"
            f"  alternate-background-color: {COLORS['bg_dark']};"
            f"  color: {COLORS['text']};"
            f"  border: 1px solid {COLORS['border']}; border-radius: 4px; }}"
            f"QTableWidget::item:selected {{ background-color: {COLORS['accent_blue']}; }}"
            f"QHeaderView::section {{ background-color: {COLORS['bg_light']};"
            f"  color: {COLORS['text_secondary']}; border: none;"
            f"  padding: 3px 6px; font-size: 11px; }}"
        )
        wh = self._watch_table.horizontalHeader()
        wh.setSectionResizeMode(0, QHeaderView.Stretch)
        wh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        wh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        wh.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        wh.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self._watch_table.verticalHeader().setVisible(False)
        right_layout.addWidget(self._watch_table, stretch=1)

        clear_btn = QPushButton("Clear All")
        clear_btn.setFont(ui_font(10))
        clear_btn.setFixedHeight(26)
        clear_btn.setStyleSheet("QPushButton { padding: 2px 10px; font-size: 12px; }")
        clear_btn.clicked.connect(self._clear_watch)
        right_layout.addWidget(clear_btn)

        splitter.addWidget(right_widget)
        splitter.setSizes([450, 550])
        root.addWidget(splitter, stretch=1)

        # --- Bottom controls ---
        bottom = QHBoxLayout()
        bottom.setSpacing(6)

        self._btn_refresh = QPushButton("Refresh Pins")
        self._btn_refresh.setFont(ui_font(10))
        self._btn_refresh.setFixedHeight(28)
        self._btn_refresh.setStyleSheet("QPushButton { padding: 2px 12px; font-size: 12px; }")
        bottom.addWidget(self._btn_refresh)

        rate_label = QLabel("Rate:")
        rate_label.setFont(ui_font(10))
        rate_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        bottom.addWidget(rate_label)

        self._rate_combo = QComboBox()
        self._rate_combo.setFont(ui_font(10))
        self._rate_combo.setFixedHeight(TOUCH_SIZES['target_min'])
        for ms, label in REFRESH_INTERVALS:
            self._rate_combo.addItem(label, ms)
        # Default to 100ms (index 1)
        self._rate_combo.setCurrentIndex(1)
        bottom.addWidget(self._rate_combo)

        bottom.addStretch()

        self._status_label = QLabel("Ready")
        self._status_label.setFont(ui_font(10))
        self._status_label.setStyleSheet(f"color: {COLORS['text_dim']};")
        bottom.addWidget(self._status_label)

        root.addLayout(bottom)

    # =================================================================
    # Signal Connections
    # =================================================================

    def _connect_signals(self):
        """Wire up all UI signals."""
        self._filter_input.textChanged.connect(self._apply_filter)
        self._pin_tree.itemSelectionChanged.connect(self._on_tree_selection)
        self._pin_tree.itemDoubleClicked.connect(self._on_tree_double_click)
        self._btn_refresh.clicked.connect(self.refresh_pins)
        self._rate_combo.currentIndexChanged.connect(self._on_rate_changed)

        for btn in self._preset_buttons:
            btn.clicked.connect(self._on_preset_clicked)

    # =================================================================
    # Public API
    # =================================================================

    def set_active(self, active):
        """Start or stop polling based on tab visibility."""
        if active:
            if not self._connected:
                # Attempt reconnect
                try:
                    self.refresh_pins()
                    self._connected = True
                    self._status_label.setText("Reconnected")
                    self._status_label.setStyleSheet(
                        f"color: {COLORS['accent_green']};"
                    )
                except Exception:
                    self._status_label.setText("Connection Lost — retry failed")
                    self._status_label.setStyleSheet(
                        f"color: {COLORS['accent']};"
                    )
                    return
            if self._watch_pins:
                self._timer.start()
        else:
            self._timer.stop()

    def refresh_pins(self):
        """Re-enumerate all HAL pins and rebuild the tree."""
        try:
            self._all_pins = self._provider.get_all_pins()
            self._pin_lookup = {p["name"]: p for p in self._all_pins}
        except Exception as e:
            # Enumeration failure — clear tree, show error, preserve watch list
            self._all_pins = []
            self._pin_lookup = {}
            self._pin_tree.clear()
            self._status_label.setText(f"Enumeration error: {e}")
            self._status_label.setStyleSheet(f"color: {COLORS['accent']};")
            return

        self._build_tree(self._all_pins)

        # Preserve watch list — remove pins that no longer exist
        removed = []
        surviving = []
        for name in self._watch_pins:
            if name in self._pin_lookup:
                surviving.append(name)
            else:
                removed.append(name)

        if removed:
            self._watch_pins = surviving
            self._rebuild_watch_table()
            self._status_label.setText(
                f"Removed {len(removed)} stale pin(s): {', '.join(removed)}"
            )
            self._status_label.setStyleSheet(f"color: {COLORS['accent_orange']};")
        else:
            count = len(self._all_pins)
            self._status_label.setText(f"{count} pins loaded")
            self._status_label.setStyleSheet(f"color: {COLORS['text_dim']};")

    # =================================================================
    # Tree Building (Task 4.2)
    # =================================================================

    def _build_tree(self, pins):
        """Populate QTreeWidget from flat pin list."""
        self._pin_tree.clear()
        tree_dict = build_pin_tree(pins)
        self._populate_tree_items(self._pin_tree.invisibleRootItem(), tree_dict)
        self._pin_tree.expandToDepth(0)

    def _populate_tree_items(self, parent_item, node):
        """Recursively add QTreeWidgetItems from nested dict."""
        for key in sorted(node.keys()):
            value = node[key]
            if isinstance(value, dict) and "name" in value:
                # Leaf pin node
                item = QTreeWidgetItem(parent_item)
                item.setText(0, key)
                item.setText(1, value["type"])
                item.setText(2, format_pin_value(value["value"], value["type"]))
                item.setData(0, Qt.UserRole, value["name"])
                item.setFont(0, mono_font(10))
                item.setFont(1, mono_font(9))
                item.setFont(2, mono_font(9))
                # Style the value column
                self._style_tree_value(item, value["value"], value["type"])
            elif isinstance(value, dict):
                # Branch node
                item = QTreeWidgetItem(parent_item)
                item.setText(0, key)
                item.setFont(0, mono_font(10, QFont.Bold))
                item.setForeground(0, QColor(COLORS["accent_blue_lt"]))
                self._populate_tree_items(item, value)

    def _style_tree_value(self, item, value, pin_type):
        """Apply color styling to a tree leaf's value column."""
        if pin_type == "bit":
            if value:
                item.setForeground(2, QColor(COLORS["accent_green"]))
            else:
                item.setForeground(2, QColor(COLORS["text_dim"]))
        else:
            item.setForeground(2, QColor(COLORS["text"]))

    # =================================================================
    # Filtering (Task 4.3)
    # =================================================================

    def _apply_filter(self, text):
        """Filter tree nodes by substring match."""
        if not text:
            # Show all
            self._show_all_tree_items(self._pin_tree.invisibleRootItem())
            return

        matching_names = {p["name"] for p in filter_pins(self._all_pins, text)}
        self._filter_tree_items(self._pin_tree.invisibleRootItem(), matching_names)

    def _filter_tree_items(self, parent, matching_names):
        """Recursively show/hide tree items based on matching pin names."""
        any_visible = False
        for i in range(parent.childCount()):
            child = parent.child(i)
            pin_name = child.data(0, Qt.UserRole)
            if pin_name:
                # Leaf node
                visible = pin_name in matching_names
                child.setHidden(not visible)
                if visible:
                    any_visible = True
            else:
                # Branch node — recurse
                child_visible = self._filter_tree_items(child, matching_names)
                child.setHidden(not child_visible)
                if child_visible:
                    child.setExpanded(True)
                    any_visible = True
        return any_visible

    def _show_all_tree_items(self, parent):
        """Unhide all tree items."""
        for i in range(parent.childCount()):
            child = parent.child(i)
            child.setHidden(False)
            if child.childCount() > 0:
                self._show_all_tree_items(child)

    def _on_preset_clicked(self):
        """Handle preset button click."""
        btn = self.sender()
        if btn:
            preset_name = btn.property("preset_name")
            self._apply_preset(preset_name)

    def _apply_preset(self, preset_name):
        """Set filter bar from preset patterns and apply."""
        patterns = FILTER_PRESETS.get(preset_name, [])
        if not patterns:
            return

        # Build a filter string that shows the preset name
        # But actually filter using the preset patterns directly
        self._filter_input.blockSignals(True)
        self._filter_input.setText(f"[{preset_name}]")
        self._filter_input.blockSignals(False)

        # Filter using match_preset
        matching_names = {
            p["name"] for p in self._all_pins
            if match_preset(p["name"], patterns)
        }
        self._filter_tree_items(self._pin_tree.invisibleRootItem(), matching_names)

    # =================================================================
    # Tree Selection & Detail (Task 4.2)
    # =================================================================

    def _on_tree_selection(self):
        """Handle tree item selection — show detail panel."""
        items = self._pin_tree.selectedItems()
        if not items:
            return
        item = items[0]
        pin_name = item.data(0, Qt.UserRole)
        if pin_name:
            self._show_pin_detail(pin_name)

    def _on_tree_double_click(self, item, column):
        """Handle double-click — add leaf pin to watch list."""
        pin_name = item.data(0, Qt.UserRole)
        if pin_name:
            self._add_to_watch(pin_name)

    def _show_pin_detail(self, pin_name):
        """Display full pin info in the detail panel."""
        pin = self._pin_lookup.get(pin_name)
        if not pin:
            self._detail_name.setText("Pin not found")
            self._detail_info.setText("")
            return

        self._detail_name.setText(pin["name"])
        val_str = format_pin_value(pin["value"], pin["type"])
        signal_str = pin.get("signal", "") or "(none)"
        self._detail_info.setText(
            f"Type: {pin['type']}  |  Dir: {pin['direction']}  |  "
            f"Value: {val_str}  |  Signal: {signal_str}"
        )

    # =================================================================
    # Watch List (Task 4.4)
    # =================================================================

    def _add_to_watch(self, pin_name):
        """Add a pin to the watch list. Prevents duplicates."""
        if pin_name in self._watch_pins:
            return
        pin = self._pin_lookup.get(pin_name)
        if not pin:
            return

        self._watch_pins.append(pin_name)
        row = self._watch_table.rowCount()
        self._watch_table.insertRow(row)
        self._populate_watch_row(row, pin)

        # Start timer if not running and we have pins
        if not self._timer.isActive() and self._connected:
            self._timer.start()

    def _populate_watch_row(self, row, pin):
        """Fill a watch table row with pin data and a remove button."""
        name_item = QTableWidgetItem(pin["name"])
        name_item.setFont(mono_font(10))
        self._watch_table.setItem(row, 0, name_item)

        type_item = QTableWidgetItem(pin["type"])
        type_item.setFont(mono_font(9))
        type_item.setTextAlignment(Qt.AlignCenter)
        self._watch_table.setItem(row, 1, type_item)

        dir_item = QTableWidgetItem(pin["direction"])
        dir_item.setFont(mono_font(9))
        dir_item.setTextAlignment(Qt.AlignCenter)
        self._watch_table.setItem(row, 2, dir_item)

        # Value cell
        val_str = format_pin_value(pin["value"], pin["type"])
        val_item = QTableWidgetItem(val_str)
        val_item.setFont(mono_font(10))
        self._style_value_item(val_item, pin["value"], pin["type"])
        self._watch_table.setItem(row, 3, val_item)

        # Remove button
        remove_btn = QPushButton("✕")
        remove_btn.setFixedSize(24, 24)
        remove_btn.setStyleSheet(
            f"QPushButton {{ background: {COLORS['accent']}; color: white;"
            f"  border: none; border-radius: 12px; font-size: 12px;"
            f"  font-weight: bold; padding: 0px; }}"
            f"QPushButton:hover {{ background: #d44637; }}"
        )
        remove_btn.clicked.connect(lambda checked, r=row: self._remove_from_watch_by_name(
            self._watch_table.item(r, 0).text() if self._watch_table.item(r, 0) else None
        ))
        # Use a more robust approach: store pin name and find row at removal time
        remove_btn.setProperty("pin_name", pin["name"])
        remove_btn.clicked.disconnect()
        remove_btn.clicked.connect(lambda checked, name=pin["name"]: self._remove_from_watch_by_name(name))
        self._watch_table.setCellWidget(row, 4, remove_btn)

    def _remove_from_watch(self, row):
        """Remove a pin from the watch list by row index."""
        if row < 0 or row >= len(self._watch_pins):
            return
        self._watch_pins.pop(row)
        self._watch_table.removeRow(row)

        # Stop timer if no pins left
        if not self._watch_pins:
            self._timer.stop()

    def _remove_from_watch_by_name(self, pin_name):
        """Remove a pin from the watch list by name."""
        if pin_name is None or pin_name not in self._watch_pins:
            return
        idx = self._watch_pins.index(pin_name)
        self._watch_pins.pop(idx)
        self._watch_table.removeRow(idx)

        # Reconnect remove buttons to correct names
        self._reconnect_remove_buttons()

        if not self._watch_pins:
            self._timer.stop()

    def _reconnect_remove_buttons(self):
        """Reconnect remove buttons after row removal."""
        for row in range(self._watch_table.rowCount()):
            btn = self._watch_table.cellWidget(row, 4)
            if btn:
                name = self._watch_pins[row] if row < len(self._watch_pins) else None
                try:
                    btn.clicked.disconnect()
                except Exception:
                    pass
                if name:
                    btn.clicked.connect(
                        lambda checked, n=name: self._remove_from_watch_by_name(n)
                    )

    def _clear_watch(self):
        """Remove all watched pins."""
        self._watch_pins.clear()
        self._watch_table.setRowCount(0)
        self._prev_values.clear()
        self._timer.stop()

    def _rebuild_watch_table(self):
        """Rebuild the watch table from self._watch_pins."""
        self._watch_table.setRowCount(0)
        for i, name in enumerate(self._watch_pins):
            pin = self._pin_lookup.get(name)
            if pin:
                self._watch_table.insertRow(i)
                self._populate_watch_row(i, pin)

    # =================================================================
    # Polling Engine (Task 5.1)
    # =================================================================

    def _update_watch_values(self):
        """Poll current values for all watched pins (timer callback)."""
        for row, pin_name in enumerate(self._watch_pins):
            try:
                value = self._provider.get_pin_value(pin_name)
            except KeyError:
                # Pin not found — show ERR
                self._set_error_cell(row)
                continue
            except Exception:
                # Connection loss — stop polling
                self._timer.stop()
                self._connected = False
                self._status_label.setText("Connection Lost")
                self._status_label.setStyleSheet(f"color: {COLORS['accent']};")
                return

            pin = self._pin_lookup.get(pin_name, {})
            pin_type = pin.get("type", "float")
            val_str = format_pin_value(value, pin_type)

            val_item = self._watch_table.item(row, 3)
            if val_item is None:
                continue

            val_item.setText(val_str)
            val_item.setFont(mono_font(10))
            self._style_value_item(val_item, value, pin_type)

            # Bit change highlighting (Task 5.2)
            if pin_type == "bit":
                prev = self._prev_values.get(pin_name)
                if prev is not None and prev != value:
                    self._flash_cell(row, 3)
            self._prev_values[pin_name] = value

    def _set_error_cell(self, row):
        """Display ERR in the value cell for a failed pin read."""
        val_item = self._watch_table.item(row, 3)
        if val_item:
            val_item.setText("ERR")
            val_item.setForeground(QColor(COLORS["accent"]))
            val_item.setFont(mono_font(10, QFont.Bold))

    # =================================================================
    # Change Highlighting (Task 5.2)
    # =================================================================

    def _flash_cell(self, row, col):
        """Briefly flash a cell background to indicate value change."""
        item = self._watch_table.item(row, col)
        if not item:
            return
        item.setBackground(QColor(COLORS["accent_orange"]))
        QTimer.singleShot(
            300,
            lambda r=row, c=col: self._reset_cell_bg(r, c)
        )

    def _reset_cell_bg(self, row, col):
        """Reset cell background after flash."""
        if row < self._watch_table.rowCount():
            item = self._watch_table.item(row, col)
            if item:
                item.setBackground(QColor(0, 0, 0, 0))

    # =================================================================
    # Value Formatting & Styling (Task 5.3)
    # =================================================================

    def _style_value_item(self, item, value, pin_type):
        """Apply color and alignment styling to a value table cell."""
        if pin_type == "bit":
            item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            if value:
                item.setForeground(QColor(COLORS["accent_green"]))
            else:
                item.setForeground(QColor(COLORS["text_dim"]))
        else:
            # Numeric — right-align, mono font
            item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            item.setForeground(QColor(COLORS["text"]))
            item.setFont(mono_font(10))

    # =================================================================
    # Refresh Interval (Task 5.1)
    # =================================================================

    def _on_rate_changed(self, index):
        """Handle refresh rate combo box change."""
        ms = self._rate_combo.itemData(index)
        if ms:
            self._set_refresh_interval(ms)

    def _set_refresh_interval(self, ms):
        """Change the polling timer interval."""
        self._timer.setInterval(ms)
