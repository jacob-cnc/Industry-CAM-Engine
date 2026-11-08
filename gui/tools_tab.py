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
import hashlib
from copy import deepcopy
from pathlib import Path
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
        self._table_revision = None
        self._loaded_tools = []
        self._table_sync_failed = False

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
        if self._autosave():
            self.tool_changed.emit(tool_number)

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
        """Live reload uses only the INI table; offline mode can select a table."""
        if self._linuxcnc_command is not None:
            try:
                self._require_idle_table_edit()
                path = self._live_table_path()
                # Validate before telling the controller to load an ambiguous table.
                tools = load_tool_table(path)
                self._linuxcnc_command.load_tool_table()
                self._wait_table_command()
                self._verify_controller_table(tools)
                self._refresh_active_offset()
                self._accept_table(path, tools)
                self._table_sync_failed = False
            except Exception as exc:
                QMessageBox.warning(self, "Tool Table Not Loaded", str(exc))
            return
        path, _ = QFileDialog.getOpenFileName(self, "Load Tool Table", "", "Tool Table Files (*.tbl);;All Files (*)")
        if not path:
            return
        try:
            self._accept_table(path, load_tool_table(path))
            self._save_settings()
        except Exception as exc:
            QMessageBox.warning(self, "Tool Table Not Loaded", str(exc))

    def _on_save_as_clicked(self) -> None:
        """Export a table; in live mode the INI table remains authoritative."""
        path, _ = QFileDialog.getSaveFileName(self, "Save Tool Table As", "", "Tool Table Files (*.tbl);;All Files (*)")
        if not path:
            return
        try:
            if self._linuxcnc_command is not None:
                self._require_idle_table_edit()
                if os.path.realpath(path) == os.path.realpath(self._live_table_path()):
                    self._persist_table()
                    return
            if os.path.exists(path):
                create_backup(path)
            save_tool_table(self.get_tools(), path)
            if self._linuxcnc_command is None:
                self._accept_table(path, self.get_tools())
                self._save_settings()
        except Exception as exc:
            QMessageBox.warning(self, "Tool Table Not Saved", str(exc))

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
        """Handle Set X touch-off button click — sets the G54 X origin.

        Sends `G7 G10 L20 P1 X<value>` (diameter mode) which shifts the G54 work coordinate system
        so that the current machine position reads `<value>` in X (diameter).
        This is a WCS origin edit — it does NOT modify the tool table and does
        NOT command any motion.

        P in `G10 L20` is the coordinate system number (1 = G54). Hardcoded
        here because registering the workpiece in G54 is the only operation
        this button is meant to perform.

        Args:
            value: The X diameter value from the touch-off spinbox.
        """
        if self._linuxcnc_command is None:
            return

        # G7 in the same block guarantees the value is read as DIAMETER even if
        # something left the interpreter in G8 (radius) mode.
        command = f"G7 G10 L20 P1 X{value:.6f}"
        self._send_mdi_command(command)

    def _on_set_z_clicked(self, value: float) -> None:
        """Handle Set Z touch-off button click — sets the G54 Z origin.

        Sends `G10 L20 P1 Z<value>` which shifts the G54 work coordinate system
        so that the current machine position reads `<value>` in Z. This is a
        WCS origin edit — it does NOT modify the tool table and does NOT
        command any motion.

        Args:
            value: The Z value from the touch-off spinbox.
        """
        if self._linuxcnc_command is None:
            return

        command = f"G10 L20 P1 Z{value:.6f}"
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

        # Combined X = (geometry_x + wear_x) in radius, convert to diameter for G10.
        # LinuxCNC halves X words while G7 is active (interp_read.cc read_x), so
        # G10 L1 stores this as a RADIUS machine-unit offset, which is what the
        # tool table holds ("units ... are in machine units", 2.9.6 manual).
        # Under G8 the same command would store 2x the intended offset, so G7
        # is put in the same block (G7 executes before G10 in one block,
        # interp_convert.cc convert_g).
        combined_x_diameter = (tool_data.x_offset + tool_data.x_wear) * 2.0
        combined_z = tool_data.z_offset + tool_data.z_wear

        command = (f"G7 G10 L1 P{tool_number} "
                   f"X{combined_x_diameter:.6f} Z{combined_z:.6f}")
        self._send_mdi_command(command)

    # ------------------------------------------------------------------
    # LinuxCNC MDI
    # ------------------------------------------------------------------

    def _send_mdi_command(self, command: str) -> None:
        """Send an MDI command to LinuxCNC and return to MANUAL mode.

        Returning to MANUAL after the MDI completes is required so the MPG
        jog counts are accepted again — LinuxCNC ignores jog counts in MDI
        and AUTO modes.

        Args:
            command: The G-code command string to send.
        """
        if self._linuxcnc_command is None:
            return

        try:
            self._linuxcnc_command.mode(linuxcnc.MODE_MDI)
            self._linuxcnc_command.wait_complete()
            self._linuxcnc_command.mdi(command)
            self._linuxcnc_command.wait_complete()
            self._linuxcnc_command.mode(linuxcnc.MODE_MANUAL)
        except Exception as e:
            logger.error(f"MDI command failed: {command!r} — {e}")

    # ------------------------------------------------------------------
    # Autosave
    # ------------------------------------------------------------------

    def _autosave(self) -> bool:
        """Persist combined offsets, then reload/verify the live controller."""
        if self._linuxcnc_command is None and not self._active_file_path:
            return True
        try:
            self._persist_table()
            return True
        except Exception as exc:
            # Restore the last accepted values, so unapplied edits are not shown
            # as active geometry or handed to CAM through get_tool().
            self.set_cards(deepcopy(self._loaded_tools))
            QMessageBox.warning(self, "Tool Change Not Applied", str(exc))
            return False

    @staticmethod
    def _revision(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest() if os.path.exists(path) else None

    def _accept_table(self, path, tools):
        self._active_file_path = os.path.realpath(path)
        self._table_revision = self._revision(path)
        self._loaded_tools = deepcopy(tools)
        self.set_cards(tools)
        self._button_bar.set_table_name(os.path.basename(path))

    def _live_table_path(self):
        ini_name = os.environ.get("INI_FILE_NAME") or getattr(self._linuxcnc_stat, "ini_filename", None)
        if not ini_name or not os.path.isfile(ini_name):
            raise RuntimeError("Live tool table requires the active INI_FILE_NAME; no settings-path fallback is allowed.")
        table_name = linuxcnc.ini(ini_name).find("EMCIO", "TOOL_TABLE")
        if not table_name:
            raise RuntimeError("Active INI has no [EMCIO] TOOL_TABLE.")
        return os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(ini_name)), os.path.expanduser(table_name)))

    def _require_idle_table_edit(self):
        self._linuxcnc_stat.poll()
        if (self._linuxcnc_stat.interp_state != linuxcnc.INTERP_IDLE or
                self._linuxcnc_stat.task_mode != linuxcnc.MODE_MANUAL or
                getattr(self._linuxcnc_stat, "paused", False)):
            raise RuntimeError("Tool table edits require an idle controller in MANUAL mode; no file was saved.")
        modes = getattr(self._linuxcnc_stat, "gcodes", ())
        if any(code in modes for code in (410, 420, 431, 432)):
            raise RuntimeError("Cancel cutter/dynamic tool compensation before editing the tool table.")

        if 430 in getattr(self._linuxcnc_stat, "gcodes", ()):
            active = next((t for t in self._loaded_tools
                           if t.tool_number == self._linuxcnc_stat.tool_in_spindle), None)
            actual = self._linuxcnc_stat.tool_offset
            if active is None or abs(actual[0] - (active.x_offset + active.x_wear)) > 0.000001 or abs(actual[2] - (active.z_offset + active.z_wear)) > 0.000001:
                raise RuntimeError("Active G43 does not match the spindle tool; cancel G43 before editing.")

    def _wait_table_command(self):
        result = self._linuxcnc_command.wait_complete()
        if result != linuxcnc.RCS_DONE:
            raise RuntimeError("LinuxCNC did not confirm the tool-table command.")

    def _refresh_active_offset(self):
        # Reloading the table does not reapply an already active G43 offset.
        self._linuxcnc_stat.poll()
        if 430 not in getattr(self._linuxcnc_stat, "gcodes", ()):
            return
        active_tool = self._linuxcnc_stat.tool_in_spindle
        if active_tool <= 0:
            raise RuntimeError("Cannot refresh G43 without an identified active tool.")
        self._linuxcnc_command.mode(linuxcnc.MODE_MDI)
        try:
            self._wait_table_command()
            self._linuxcnc_command.mdi(f"G43 H{active_tool}")
            self._wait_table_command()
            self._linuxcnc_stat.poll()
            expected = next(entry for entry in self._linuxcnc_stat.tool_table if entry.id == active_tool)
            actual = self._linuxcnc_stat.tool_offset
            if abs(actual[0] - expected.xoffset) > 0.000001 or abs(actual[2] - expected.zoffset) > 0.000001:
                raise RuntimeError("Active G43 offsets do not match the reloaded tool table.")
        finally:
            self._linuxcnc_command.mode(linuxcnc.MODE_MANUAL)
            self._wait_table_command()

    def _verify_controller_table(self, tools):
        self._linuxcnc_stat.poll()
        entries = self._linuxcnc_stat.tool_table
        expected_ids = {tool.tool_number for tool in tools}
        actual_ids = {entry.id for entry in entries if entry.id > 0}
        if expected_ids != actual_ids:
            raise RuntimeError("LinuxCNC tool IDs do not match the saved table.")
        for tool in tools:
            matches = [entry for entry in entries if entry.id == tool.tool_number]
            if not any(abs(entry.xoffset - (tool.x_offset + tool.x_wear)) < 0.000001 and
                       abs(entry.zoffset - (tool.z_offset + tool.z_wear)) < 0.000001 and
                       abs(entry.diameter - tool.nose_radius * 2) < 0.000001 and
                       abs(entry.frontangle - tool.front_angle) < 0.051 and
                       abs(entry.backangle - tool.back_angle) < 0.051 and
                       entry.orientation == tool.orientation
                       for entry in matches):
                raise RuntimeError(f"LinuxCNC table does not match saved offsets for T{tool.tool_number}.")

    def _persist_table(self):
        live = self._linuxcnc_command is not None
        if self._table_sync_failed:
            raise RuntimeError("Tool table synchronization failed; reload and verify the controller table before editing.")
        path = self._live_table_path() if live else self._active_file_path
        if live:
            self._require_idle_table_edit()
        if not path or os.path.realpath(path) != os.path.realpath(self._active_file_path or ""):
            raise RuntimeError("Active tool table is not the controller's INI table. Reload it first.")
        if self._revision(path) != self._table_revision:
            raise RuntimeError("Tool table changed outside the editor. Reload it before reapplying edits.")
        tools = self.get_tools()
        if live and self._linuxcnc_stat.tool_in_spindle > 0 and not any(
                t.tool_number == self._linuxcnc_stat.tool_in_spindle for t in tools):
            raise RuntimeError("Unload the active tool before deleting or renumbering it.")
        previous = Path(path).read_bytes() if os.path.exists(path) else None
        if previous is not None:
            create_backup(path)
        save_tool_table(tools, path)
        try:
            if live:
                self._require_idle_table_edit()
                self._linuxcnc_command.load_tool_table()
                self._wait_table_command()
                self._verify_controller_table(tools)
                self._refresh_active_offset()
        except Exception as error:
            # Restore the disk snapshot and attempt to restore controller state.
            if previous is not None:
                rollback = Path(path + ".rollback")
                rollback.write_bytes(previous)
                os.replace(rollback, path)
            else:
                os.unlink(path)
            if live:
                self._table_sync_failed = True
                try:
                    self._require_idle_table_edit()
                    self._linuxcnc_command.load_tool_table()
                    self._wait_table_command()
                    self._verify_controller_table(self._loaded_tools)
                    self._refresh_active_offset()
                    self._table_sync_failed = False
                except Exception:
                    logger.exception("Tool-table rollback could not be verified; further edits blocked")
            if self._table_sync_failed:
                self._button_bar.set_table_name("Sync failed — reload required")
                raise RuntimeError("Tool table synchronization/rollback could not be verified; further edits are blocked. Reload and verify the controller table before continuing.") from error
            raise
        self._table_revision = self._revision(path)
        self._loaded_tools = deepcopy(tools)

    # ------------------------------------------------------------------
    # Settings Persistence
    # ------------------------------------------------------------------

    def _get_settings_path(self) -> str:
        """Return the path to the settings JSON file.

        The ignored file in the working directory is local to this machine.
        """
        return os.path.join(os.getcwd(), _SETTINGS_FILE)

    def _load_settings(self) -> Optional[str]:
        """Load settings from .tool_tab_settings.json.

        Searches for the settings file in the current working directory.

        Returns:
            The last_table_path if found, None otherwise.
        """
        # Try current working directory first
        settings_path = self._get_settings_path()
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

        # Read and write the same ignored per-machine convenience file.
        settings_path = self._get_settings_path()
        try:
            with open(settings_path, "w", encoding="utf-8") as f:
                json.dump(settings_data, f, indent=2)
        except OSError as e:
            logger.warning(f"Failed to save settings: {e}")

    def _load_settings_and_auto_load(self) -> None:
        try:
            if self._linuxcnc_command is not None:
                path = self._live_table_path()
            else:
                last_path = self._load_settings()
                path = last_path if last_path and os.path.isfile(last_path) else os.path.join(os.getcwd(), "tool.tbl")
            if os.path.isfile(path):
                if self._linuxcnc_command is not None:
                    self._verify_controller_table(load_tool_table(path))
                self._accept_table(path, load_tool_table(path))
        except Exception as exc:
            logger.warning("Tool table not loaded: %s", exc)
            self._button_bar.set_table_name("Tool table not loaded")
            self._button_bar._table_name_label.setToolTip(str(exc))

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
