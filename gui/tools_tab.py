# -*- coding: utf-8 -*-
"""Tools Tab for Industry CAM Engine — Mazak-style card-based tool geometry editor.

Displays tools as a vertically scrollable list of ToolGeometryRow cards.
Each card shows all fields inline (wear offsets, geometry offsets, type/insert/
orientation dropdowns, angles, and a live orientation graphic).

A TopButtonBar provides file operations, tool addition, touch-off controls,
and active tool display.

This tab is usable in offline mode (no LinuxCNC dependency).
"""

import json
import os
import logging
from typing import Optional, List

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QScrollArea,
    QFileDialog,
    QMessageBox,
)

from gui.colors import COLORS
from gui.components.top_button_bar import TopButtonBar
from gui.components.tool_geometry_row import ToolGeometryRow
from gui.unit_state import unit_state
from pipeline.tool_card_data import ToolCardData
from pipeline.tool_table_io import load_tool_table, save_tool_table, create_backup

# LinuxCNC detection — offline mode when unavailable
try:
    import linuxcnc
    HAS_LINUXCNC = True
except ImportError:
    HAS_LINUXCNC = False

logger = logging.getLogger(__name__)

# Settings file name (stored alongside .tbl files / project directory)
_SETTINGS_FILE = ".tool_tab_settings.json"


class Tools_Tab(QWidget):
    """Mazak-style card-based tool geometry editor tab.

    Architecture:
        Tools_Tab (QWidget)
        ├── TopButtonBar
        └── QScrollArea
            └── QWidget (container)
                └── QVBoxLayout
                    ├── ToolGeometryRow(tool_1)
                    ├── ToolGeometryRow(tool_2)
                    └── ...

    Signals:
        tool_changed(int): Emitted with tool_number when any tool field is edited.
        tool_selected(object): Emitted with ToolCardData when user clicks a card.
    """

    tool_changed = pyqtSignal(int)
    tool_selected = pyqtSignal(object)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._cards: List[ToolGeometryRow] = []
        self._selected_index: int = -1
        self._active_file_path: Optional[str] = None

        # LinuxCNC stat/command channels (None in offline mode)
        self._linuxcnc_stat = None
        self._linuxcnc_command = None
        if HAS_LINUXCNC:
            try:
                self._linuxcnc_stat = linuxcnc.stat()
                self._linuxcnc_command = linuxcnc.command()
            except Exception:
                # If connection fails, fall back to offline mode
                self._linuxcnc_stat = None
                self._linuxcnc_command = None

        self._setup_ui()
        self._connect_button_bar_signals()
        self._setup_offline_mode()

        # Subscribe to unit mode changes to refresh displayed tool geometry
        unit_state.unit_changed.connect(self._on_unit_changed)

        # Load settings and auto-load last table
        self._load_settings_and_auto_load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_tools(self) -> List[ToolCardData]:
        """Return a list of ToolCardData for all tool cards.

        Returns:
            List of ToolCardData instances, one per card in display order.
        """
        return [card.get_data() for card in self._cards]

    def get_tool(self, tool_number: int) -> Optional[ToolCardData]:
        """Return the ToolCardData for a specific tool number, or None.

        Args:
            tool_number: The tool number to look up (e.g. 1, 2, 3...).

        Returns:
            ToolCardData if found, None otherwise.
        """
        for card in self._cards:
            data = card.get_data()
            if data.tool_number == tool_number:
                return data
        return None

    def get_selected_tool(self) -> Optional[ToolCardData]:
        """Return the ToolCardData for the currently selected card, or None.

        Returns:
            ToolCardData of the selected card, or None if no card is selected.
        """
        if 0 <= self._selected_index < len(self._cards):
            return self._cards[self._selected_index].get_data()
        return None

    def refresh_current_tool_display(self) -> None:
        """Refresh the current tool display in the TopButtonBar.

        In offline mode, shows "Offline". When LinuxCNC is connected,
        reads the active tool from the stat channel.
        """
        if self._linuxcnc_stat is not None:
            try:
                self._linuxcnc_stat.poll()
                tool_in_spindle = self._linuxcnc_stat.tool_in_spindle
                if tool_in_spindle > 0:
                    # Look up description from our cards
                    tool_data = self.get_tool(tool_in_spindle)
                    desc = tool_data.description if tool_data else ""
                    self._button_bar.set_current_tool(tool_in_spindle, desc)
                else:
                    self._button_bar.set_current_tool(0, "No tool")
            except Exception:
                self._button_bar._current_tool_label.setText("Offline")
        else:
            self._button_bar._current_tool_label.setText("Offline")

    # ------------------------------------------------------------------
    # Unit Mode Change
    # ------------------------------------------------------------------

    def _on_unit_changed(self, mode: str) -> None:
        """Refresh all displayed tool geometry values on unit mode change.

        The NumericField widgets in each ToolGeometryRow handle their own
        display conversion (nose radius, X offset, Z offset are unit_aware).
        This method ensures any additional tab-level displays are refreshed.

        Stored tool data is never modified — only the display is updated.
        """
        # NumericField widgets already re-display via their own unit_changed
        # subscription. Force a repaint of all cards to ensure visual consistency.
        for card in self._cards:
            card.update()

    # ------------------------------------------------------------------
    # Card Management
    # ------------------------------------------------------------------

    def add_card(self, tool_data: ToolCardData) -> None:
        """Create a ToolGeometryRow for the given data and append it to the scroll area.

        Args:
            tool_data: The ToolCardData to populate the new card with.
        """
        card = ToolGeometryRow(tool_data)
        self._wire_card_signals(card)
        self._cards.append(card)
        self._card_layout.addWidget(card)

    def clear_cards(self) -> None:
        """Remove all tool cards from the scroll area."""
        for card in self._cards:
            card.setParent(None)
            card.deleteLater()
        self._cards.clear()
        self._selected_index = -1

    def set_cards(self, tools: List[ToolCardData]) -> None:
        """Replace all cards with a new list of tool data.

        Args:
            tools: List of ToolCardData to display.
        """
        self.clear_cards()
        for tool_data in tools:
            self.add_card(tool_data)
        # Select first card if available
        if self._cards:
            self._select_card(0)
        self._update_delete_buttons()

    # ------------------------------------------------------------------
    # UI Setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        """Build the tab layout: TopButtonBar + QScrollArea with card container."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- Top Button Bar ---
        self._button_bar = TopButtonBar()
        main_layout.addWidget(self._button_bar)

        # --- Scroll Area containing tool cards ---
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll_area.setStyleSheet(
            f"QScrollArea {{ background-color: {COLORS['bg_base']}; border: none; }}"
        )

        # Container widget inside scroll area
        self._card_container = QWidget()
        self._card_container.setStyleSheet(
            f"background-color: {COLORS['bg_base']};"
        )
        self._card_layout = QVBoxLayout(self._card_container)
        self._card_layout.setContentsMargins(12, 12, 12, 12)
        self._card_layout.setSpacing(8)
        self._card_layout.addStretch()  # Push cards to top

        self._scroll_area.setWidget(self._card_container)
        main_layout.addWidget(self._scroll_area, stretch=1)

    def _setup_offline_mode(self) -> None:
        """Configure offline mode: disable touch-off buttons and show 'Offline'."""
        if not HAS_LINUXCNC or self._linuxcnc_command is None:
            # Disable touch-off buttons
            self._button_bar._set_x_btn.setEnabled(False)
            self._button_bar._set_z_btn.setEnabled(False)
            self._button_bar._x_spinbox.setEnabled(False)
            self._button_bar._z_spinbox.setEnabled(False)
            # Show "Offline" in current tool display
            self._button_bar._current_tool_label.setText("Offline")

    # ------------------------------------------------------------------
    # Signal Wiring
    # ------------------------------------------------------------------

    def _connect_button_bar_signals(self) -> None:
        """Wire TopButtonBar signals to handler methods."""
        self._button_bar.load_clicked.connect(self._on_load_clicked)
        self._button_bar.save_as_clicked.connect(self._on_save_as_clicked)
        self._button_bar.add_tool_clicked.connect(self._on_add_tool_clicked)
        self._button_bar.set_x_clicked.connect(self._on_set_x_clicked)
        self._button_bar.set_z_clicked.connect(self._on_set_z_clicked)

    def _wire_card_signals(self, card: ToolGeometryRow) -> None:
        """Connect a ToolGeometryRow's signals to tab-level handlers.

        Args:
            card: The ToolGeometryRow to wire up.
        """
        card.field_changed.connect(self._on_card_field_changed)
        card.clicked.connect(self._on_card_clicked)
        card.delete_requested.connect(self._on_card_delete_requested)

    # ------------------------------------------------------------------
    # Card Signal Handlers
    # ------------------------------------------------------------------

    def _on_card_field_changed(self, tool_number: int) -> None:
        """Handle field_changed from a ToolGeometryRow.

        Emits tool_changed signal and triggers autosave.

        Args:
            tool_number: The tool number of the card that changed.
        """
        self.tool_changed.emit(tool_number)
        self._autosave()

    def _on_card_clicked(self, tool_number: int) -> None:
        """Handle clicked from a ToolGeometryRow.

        Selects the card and emits tool_selected signal.

        Args:
            tool_number: The tool number of the clicked card.
        """
        for i, card in enumerate(self._cards):
            data = card.get_data()
            if data.tool_number == tool_number:
                self._select_card(i)
                self.tool_selected.emit(data)
                break

    def _on_card_delete_requested(self, tool_number: int) -> None:
        """Handle delete_requested from a ToolGeometryRow.

        Shows confirmation dialog, removes the card, renumbers remaining
        tools sequentially from T1, and autosaves.

        Args:
            tool_number: The tool number of the card requesting deletion.
        """
        # Don't allow deletion if only 1 tool remains
        if len(self._cards) <= 1:
            return

        # Show confirmation dialog
        reply = QMessageBox.question(
            self,
            "Delete Tool",
            f"Delete tool T{tool_number}?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        # Find and remove the card
        card_to_remove = None
        for i, card in enumerate(self._cards):
            data = card.get_data()
            if data.tool_number == tool_number:
                card_to_remove = card
                self._cards.pop(i)
                card.setParent(None)
                card.deleteLater()
                break

        if card_to_remove is None:
            return

        # Update selection
        if self._selected_index >= len(self._cards):
            self._selected_index = len(self._cards) - 1
        if self._cards:
            self._select_card(max(0, self._selected_index))

        self._update_delete_buttons()
        self._autosave()

    # ------------------------------------------------------------------
    # TopButtonBar Signal Handlers
    # ------------------------------------------------------------------

    def _on_load_clicked(self) -> None:
        """Handle Load Table button click.

        Opens a file dialog filtered to .tbl files, loads the selected
        tool table, and populates the card list.
        """
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Tool Table",
            "",
            "Tool Table Files (*.tbl);;All Files (*)",
        )
        if not file_path:
            return

        try:
            tools = load_tool_table(file_path)
        except FileNotFoundError:
            QMessageBox.warning(self, "File Not Found", f"Could not find: {file_path}")
            return
        except Exception as e:
            QMessageBox.warning(self, "Load Error", f"Error loading tool table:\n{e}")
            return

        self._active_file_path = file_path
        self.set_cards(tools)
        self._button_bar.set_table_name(os.path.basename(file_path))
        self._save_settings()

    def _on_save_as_clicked(self) -> None:
        """Handle Save Table As button click.

        Opens a file dialog for save path, creates a backup of the existing
        file if it exists, then saves the current tool data.
        """
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Tool Table As",
            "",
            "Tool Table Files (*.tbl);;All Files (*)",
        )
        if not file_path:
            return

        # Create backup if the target file already exists
        if os.path.exists(file_path):
            try:
                create_backup(file_path)
            except Exception as e:
                logger.warning(f"Backup creation failed: {e}")

        # Save the tool table
        tools = self.get_tools()
        try:
            save_tool_table(tools, file_path)
        except Exception as e:
            QMessageBox.warning(self, "Save Error", f"Error saving tool table:\n{e}")
            return

        self._active_file_path = file_path
        self._button_bar.set_table_name(os.path.basename(file_path))
        self._save_settings()

    def _on_add_tool_clicked(self) -> None:
        """Handle Add Tool button click.

        Appends a new blank tool card with the next available tool number.
        """
        # Determine next tool number — first unused integer starting from 1
        existing = {card.get_data().tool_number for card in self._cards}
        next_number = 1
        while next_number in existing:
            next_number += 1

        # Create blank ToolCardData with defaults
        new_tool = ToolCardData(
            tool_number=next_number,
            tool_type="Turning RH",
            insert_code="CNMG",
            orientation=1,
            description="",
            nose_radius=0.0160,
            front_angle=95.0,
            back_angle=175.0,
            x_offset=0.0,
            z_offset=0.0,
            x_wear=0.0,
            z_wear=0.0,
            blade_width=0.0,
        )

        self.add_card(new_tool)
        self._update_delete_buttons()
        self._autosave()

    def _on_set_x_clicked(self, value: float) -> None:
        """Handle Set X touch-off button click.

        Sends G10 L1 MDI command with the entered X diameter value
        for the currently selected tool.

        Args:
            value: The X diameter value from the touch-off spinbox.
        """
        if self._linuxcnc_command is None:
            return

        selected_tool = self.get_selected_tool()
        if selected_tool is None:
            return

        tool_number = selected_tool.tool_number
        # G10 L20 P<tool> X<diameter>: sets offset so current position reads <value>
        command = f"G10 L20 P{tool_number} X{value:.6f}"
        self._send_mdi_command(command)

    def _on_set_z_clicked(self, value: float) -> None:
        """Handle Set Z touch-off button click.

        Sends G10 L1 MDI command with the entered Z value
        for the currently selected tool.

        Args:
            value: The Z value from the touch-off spinbox.
        """
        if self._linuxcnc_command is None:
            return

        selected_tool = self.get_selected_tool()
        if selected_tool is None:
            return

        tool_number = selected_tool.tool_number
        # G10 L20 P<tool> Z<value>: sets offset so current position reads <value>
        command = f"G10 L20 P{tool_number} Z{value:.6f}"
        self._send_mdi_command(command)

    # ------------------------------------------------------------------
    # Wear Offset → G10 Integration
    # ------------------------------------------------------------------

    def _on_wear_offset_changed(self, tool_number: int) -> None:
        """Combine wear + geometry offsets and write via G10 L1 MDI.

        Called when a wear field changes. Combines the wear offset with
        the geometry offset and sends the combined value to LinuxCNC.

        Args:
            tool_number: The tool number whose wear offset changed.
        """
        if self._linuxcnc_command is None:
            return

        tool_data = self.get_tool(tool_number)
        if tool_data is None:
            return

        # Combined X = (geometry_x + wear_x) in radius, convert to diameter for G10
        combined_x_diameter = (tool_data.x_offset + tool_data.x_wear) * 2.0
        combined_z = tool_data.z_offset + tool_data.z_wear

        command = f"G10 L1 P{tool_number} X{combined_x_diameter:.6f} Z{combined_z:.6f}"
        self._send_mdi_command(command)

    # ------------------------------------------------------------------
    # LinuxCNC MDI
    # ------------------------------------------------------------------

    def _send_mdi_command(self, command: str) -> None:
        """Send an MDI command to LinuxCNC.

        Args:
            command: The G-code command string to send.
        """
        if self._linuxcnc_command is None:
            return

        try:
            self._linuxcnc_command.mode(linuxcnc.MODE_MDI)
            self._linuxcnc_command.wait_complete()
            self._linuxcnc_command.mdi(command)
        except Exception as e:
            logger.error(f"MDI command failed: {command!r} — {e}")

    # ------------------------------------------------------------------
    # Autosave
    # ------------------------------------------------------------------

    def _autosave(self) -> None:
        """Save the entire tool table to the active file path.

        Silent failure — does not block the UI on write errors.
        """
        if not self._active_file_path:
            return

        tools = self.get_tools()
        try:
            save_tool_table(tools, self._active_file_path)
        except Exception as e:
            logger.warning(f"Autosave failed: {e}")

    # ------------------------------------------------------------------
    # Settings Persistence
    # ------------------------------------------------------------------

    def _get_settings_path(self) -> str:
        """Return the path to the settings JSON file.

        Uses the directory of the active file if available, otherwise
        the current working directory.
        """
        if self._active_file_path:
            directory = os.path.dirname(self._active_file_path)
        else:
            directory = os.getcwd()
        return os.path.join(directory, _SETTINGS_FILE)

    def _load_settings(self) -> Optional[str]:
        """Load settings from .tool_tab_settings.json.

        Searches for the settings file in the current working directory.

        Returns:
            The last_table_path if found, None otherwise.
        """
        # Try current working directory first
        settings_path = os.path.join(os.getcwd(), _SETTINGS_FILE)
        if not os.path.exists(settings_path):
            return None

        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("last_table_path")
        except (json.JSONDecodeError, OSError, KeyError):
            return None

    def _save_settings(self) -> None:
        """Persist the current active file path to .tool_tab_settings.json."""
        if not self._active_file_path:
            return

        settings_data = {"last_table_path": self._active_file_path}

        # Save in the directory of the active file
        settings_path = os.path.join(
            os.path.dirname(self._active_file_path) or os.getcwd(),
            _SETTINGS_FILE,
        )
        try:
            with open(settings_path, "w", encoding="utf-8") as f:
                json.dump(settings_data, f, indent=2)
        except OSError as e:
            logger.warning(f"Failed to save settings: {e}")

    def _load_settings_and_auto_load(self) -> None:
        """On startup, load settings and auto-load the previously active table.

        If the file does not exist, displays an empty list and clears
        the table name label.
        """
        last_path = self._load_settings()
        if not last_path:
            return

        if not os.path.exists(last_path):
            # File not found — display empty list, clear table name
            self._button_bar.set_table_name("")
            return

        try:
            tools = load_tool_table(last_path)
            self._active_file_path = last_path
            self.set_cards(tools)
            self._button_bar.set_table_name(os.path.basename(last_path))
        except Exception as e:
            logger.warning(f"Auto-load failed for {last_path}: {e}")
            self._button_bar.set_table_name("")

    # ------------------------------------------------------------------
    # Delete Button Management
    # ------------------------------------------------------------------

    def _update_delete_buttons(self) -> None:
        """Disable delete button on all cards when only 1 tool remains."""
        only_one = len(self._cards) <= 1
        for card in self._cards:
            card._delete_btn.setEnabled(not only_one)

    # ------------------------------------------------------------------
    # Internal Helpers
    # ------------------------------------------------------------------

    def _select_card(self, index: int) -> None:
        """Update the selected card index and apply visual selection styling.

        Args:
            index: The index of the card to select in self._cards.
        """
        # Deselect previous
        if 0 <= self._selected_index < len(self._cards):
            self._cards[self._selected_index].setStyleSheet(
                f"ToolGeometryRow {{"
                f"  background-color: {COLORS['bg_surface']};"
                f"  border: 1px solid {COLORS['border_normal']};"
                f"  border-radius: 6px;"
                f"}}"
            )

        self._selected_index = index

        # Highlight new selection
        if 0 <= self._selected_index < len(self._cards):
            self._cards[self._selected_index].setStyleSheet(
                f"ToolGeometryRow {{"
                f"  background-color: {COLORS['bg_surface']};"
                f"  border: 2px solid {COLORS['border_focused']};"
                f"  border-radius: 6px;"
                f"}}"
            )
