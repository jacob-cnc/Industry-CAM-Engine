"""Main Window for Industry CAM Engine.

QMainWindow with StatusBar (top), QTabWidget (below) containing:
  P1: Program, Edit, Tools, Debug
  P2: Run (placeholder), Manual (placeholder)
  P3: Setup (placeholder), Help (placeholder)

Signal wiring connects tabs for data flow:
  program_tab.gcode_generated → edit_tab.receive_gcode
  program_tab.plan_result_ready → debug_tab.update_panels
  program_tab.state_changed → status_bar.update_state
  tools_tab.tool_changed → _on_tool_changed (log/mark stale)
  edit_tab.preview_requested → _on_preview_requested (future wiring)

Works in offline mode (no LinuxCNC dependency).
"""

import os
import sys
import logging

from PyQt5.QtCore import Qt, QEvent, QPoint
from PyQt5.QtGui import QPalette, QColor
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QTabWidget, QLabel,
)

from gui.colors import COLORS, FONTS, STYLESHEET
from gui.components.status_bar import StatusBar
from gui.program_tab import ProgramTab
from gui.edit_tab import EditTab
from gui.tools_tab import Tools_Tab
from gui.debug_tab import DebugTab
from gui.manual import ManualTab
from gui.run_tab import RunTab
from gui.help_tab import HelpTab
from gui.commissioning import SetupTab
from hal.factory import get_backend

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Industry CAM Engine main application window.

    Layout:
        - StatusBar (fixed 48px, top)
        - QTabWidget with all tabs below
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Industry CAM Engine")
        self.resize(1400, 900)

        # HAL backend (Live on LinuxCNC, Mock on Windows)
        self._backend = get_backend()

        self._setup_ui()
        self._wire_signals()
        self._set_initial_tool()

        self._prev_estop = False
        self._auto_idle_polls = 0

        # Status bar poll timer — updates position, RPM, feed, tool, gcodes
        from PyQt5.QtCore import QTimer
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._poll_status_bar)
        self._status_timer.start(200)  # 5 Hz

        # Green cycle button (TB3 P10). Measured presses are ~150 ms, so poll
        # at 20 ms. HAL resumes a paused program and red pauses (both in
        # industry-cam.hal, GUI-independent); the GUI only STARTS a program
        # when nothing is queued, after its tool-table check.
        self._cycle_btn_prev = False
        self._cycle_btn_busy = False
        self._cycle_btn_timer = QTimer(self)
        self._cycle_btn_timer.timeout.connect(self._poll_cycle_button)
        self._cycle_btn_timer.start(20)

        logger.info("MainWindow initialized (offline preview mode)")

    # ------------------------------------------------------------------
    # UI Setup
    # ------------------------------------------------------------------

    def _setup_ui(self):
        """Build the main window layout: status bar + tab widget."""
        # Central widget container
        central = QWidget(self)
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- Status Bar (top, fixed height) ---
        self._status_bar = StatusBar(self)
        layout.addWidget(self._status_bar)

        # --- Tab Widget ---
        self._tab_widget = QTabWidget(self)
        self._tab_widget.setDocumentMode(True)
        layout.addWidget(self._tab_widget)

        # --- Tabs in operator-priority order ---
        self._manual_tab = ManualTab(self)
        self._run_tab = RunTab(self)
        self._program_tab = ProgramTab(self)
        self._edit_tab = EditTab(self)
        self._tools_tab = Tools_Tab(self)
        self._debug_tab = DebugTab(self)
        self._setup_tab = SetupTab(
            backend=self._backend,
            ini_path=self._get_ini_path(),
        )

        self._tab_widget.addTab(self._manual_tab, "Manual")
        self._tab_widget.addTab(self._tools_tab, "Tools")
        self._tab_widget.addTab(self._run_tab, "Run")
        self._tab_widget.addTab(self._program_tab, "Program")
        self._tab_widget.addTab(self._edit_tab, "Edit")
        self._tab_widget.addTab(self._debug_tab, "Debug")
        self._tab_widget.addTab(self._setup_tab, "Setup")
        self._help_tab = HelpTab(self)
        self._tab_widget.addTab(self._help_tab, "Help")

        # Default to Manual tab
        self._tab_widget.setCurrentWidget(self._manual_tab)

        # Errors (LinuxCNC error channel, E-STOP, ...) show in the empty right
        # side of the tab row, so a long message never widens the ribbon or
        # pushes the window past the 1920 px screen. StatusBar keeps the
        # show_error()/clear_error() API; only the label's home moves.
        self._error_label = self._status_bar.error_label
        self._error_label.setParent(self._tab_widget)
        self._tab_widget.installEventFilter(self)
        self._tab_widget.tabBar().installEventFilter(self)

    # Gap between the last tab and the error label, and to the right edge.
    _ERROR_GAP_LEFT = 16
    _ERROR_GAP_RIGHT = 8

    def eventFilter(self, obj, event):
        """Keep the error label placed in the tab row as things resize."""
        tabs = getattr(self, "_tab_widget", None)
        if tabs is not None and obj in (tabs, tabs.tabBar()) and \
                event.type() in (QEvent.Resize, QEvent.Show, QEvent.LayoutRequest):
            self._place_error_label()
        return super().eventFilter(obj, event)

    def _place_error_label(self):
        """Fill the tab row from the last tab's right edge to the window edge,
        vertically centred, 40 px tall (or less if the tab row is shorter)."""
        tabs = self._tab_widget
        bar = tabs.tabBar()
        if bar.count() == 0:
            return
        last = bar.tabRect(bar.count() - 1)
        left = bar.mapTo(tabs, last.topRight()).x() + 1 + self._ERROR_GAP_LEFT
        top = bar.mapTo(tabs, bar.rect().topLeft()).y()
        width = tabs.width() - left - self._ERROR_GAP_RIGHT
        height = min(40, max(0, bar.height() - 8))
        self._error_label.setGeometry(
            left, top + (bar.height() - height) // 2, max(0, width), height)
        self._error_label.raise_()

    def _make_placeholder(self, text: str) -> QWidget:
        """Create a placeholder tab widget with a centered label.

        Args:
            text: Message to display (e.g., "Coming in Phase 2").

        Returns:
            QWidget with centered QLabel.
        """
        widget = QWidget(self)
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignCenter)

        label = QLabel(text)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet(
            f"color: {COLORS['text_disabled']};"
            f"font-size: 16pt;"
            f"font-style: italic;"
        )
        layout.addWidget(label)
        return widget

    # ------------------------------------------------------------------
    # Signal Wiring
    # ------------------------------------------------------------------

    def _wire_signals(self):
        """Connect inter-tab signals for data flow."""
        # 1. Program generates G-code → auto-populate Edit tab
        self._program_tab.gcode_generated.connect(
            self._edit_tab.receive_gcode
        )

        # 2. Program produces PlanResult → update Debug panels
        self._program_tab.plan_result_ready.connect(
            self._debug_tab.update_panels
        )

        # 3. Tool table edited → log and mark program stale
        self._tools_tab.tool_changed.connect(self._on_tool_changed)

        # 4. Program state changes → update status bar state indicator
        self._program_tab.state_changed.connect(
            self._status_bar.update_state
        )

        # 5. Tool selected in Tools tab → update Program tab's active tool
        self._tools_tab.tool_selected.connect(self._on_tool_selected)

        # 5b. Tool resolver — lets Program tab look up any tool by number
        self._program_tab.set_tool_resolver(self._resolve_tool_by_number)

        # 6. Tab change → activate/deactivate Setup tab polling
        self._tab_widget.currentChanged.connect(self._on_tab_changed)

        # 7. E-Stop button → trigger estop on backend
        self._status_bar.estop_clicked.connect(self._on_estop_clicked)

        # 8. Machine control buttons (Reset, ON, OFF) in status bar
        self._status_bar.reset_clicked.connect(self._backend.estop_reset)
        self._status_bar.machine_on_clicked.connect(self._backend.machine_on)
        self._status_bar.machine_off_clicked.connect(self._backend.machine_off)
        self._status_bar.mode_clicked.connect(self._on_mode_clicked)

    # ------------------------------------------------------------------
    # Signal Slots
    # ------------------------------------------------------------------

    def _on_tool_changed(self, tool_number: int):
        """Handle tool table change — log and mark program tab stale.

        Args:
            tool_number: The tool number that was modified.
        """
        from pipeline.tool_card_data import tool_card_to_tool_def
        logger.info("Tool T%d modified in tool table", tool_number)
        # If the modified tool is the active tool, mark program stale
        if hasattr(self._program_tab, '_active_tool'):
            active = self._program_tab._active_tool
            if active and active.tool_number == tool_number:
                updated = self._tools_tab.get_tool(tool_number)
                if updated:
                    self._program_tab.set_active_tool(tool_card_to_tool_def(updated))

    def _set_initial_tool(self):
        """Set the first tool from the tool table as the active tool on startup.

        Prevents the Program tab from falling back to a hardcoded T1 default
        when the user generates without explicitly selecting a tool first.
        """
        from pipeline.tool_card_data import tool_card_to_tool_def
        tools = self._tools_tab.get_tools()
        if tools:
            # Use the first non-reference tool (skip T99 master reference)
            for card in tools:
                if card.tool_number != 99:
                    self._program_tab.set_active_tool(tool_card_to_tool_def(card))
                    logger.info("Initial active tool set to T%d", card.tool_number)
                    return
            # If only T99 exists, use it anyway
            self._program_tab.set_active_tool(tool_card_to_tool_def(tools[0]))
            logger.info("Initial active tool set to T%d (only tool available)", tools[0].tool_number)

    def _on_tool_selected(self, tool_def):
        """Handle tool selection in Tools tab — update Program tab's active tool.

        Converts ToolCardData to ToolDef before passing to the Program tab,
        ensuring proper field mapping (radius→diameter, direction derivation).

        Args:
            tool_def: The ToolCardData that was selected.
        """
        from pipeline.tool_card_data import tool_card_to_tool_def
        converted = tool_card_to_tool_def(tool_def)
        logger.info("Tool T%d selected in tool table", converted.tool_number)
        self._program_tab.set_active_tool(converted)

    def _resolve_tool_by_number(self, tool_number: int):
        """Look up a ToolDef by tool number from the tool table.

        Used by Program tab to resolve finish tool when it differs from
        the roughing tool.

        Returns:
            ToolDef or None if tool not found.
        """
        from pipeline.tool_card_data import tool_card_to_tool_def
        card = self._tools_tab.get_tool(tool_number)
        if card is not None:
            return tool_card_to_tool_def(card)
        return None

    def _on_tab_changed(self, index: int):
        """Handle main tab switch — activate/deactivate polling tabs."""
        current = self._tab_widget.widget(index)
        self._setup_tab.set_active(current is self._setup_tab)
        self._run_tab.set_active(current is self._run_tab)

    def _poll_cycle_button(self):
        """Rising edge of the green button -> cycle start when idle."""
        if not hasattr(self._backend, "read_cycle_start"):
            return
        pressed = self._backend.read_cycle_start()
        rising = pressed and not self._cycle_btn_prev
        self._cycle_btn_prev = pressed
        if not rising or self._cycle_btn_busy:
            return
        self._cycle_btn_busy = True          # modal dialogs re-enter the event loop
        try:
            self._backend.poll()
            s = self._backend.state
            if s.paused or s.program_busy:
                logger.info("Green button: program %s - handled in HAL / ignored",
                            "paused" if s.paused else "running")
                return
            self._tab_widget.setCurrentWidget(self._run_tab)
            result = self._run_tab.cycle_start("green button")
            logger.info("Green button: %s", result)
        except Exception:
            logger.exception("Green button handler failed")
        finally:
            self._cycle_btn_busy = False

    def _on_mode_clicked(self):
        """Ribbon mode chip clicked: return to MANUAL, but never interrupt a
        running or paused program."""
        from hal.interface import InterpState, TaskMode
        self._backend.poll()
        s = self._backend.state
        if s.task_mode == TaskMode.MANUAL:
            return
        if s.program_busy:
            self._status_bar.show_error("Program active - stop it before leaving AUTO")
            logger.info("Mode chip click ignored: interpreter %s", s.interp_state.value)
            return
        logger.info("Mode chip click: returning to MANUAL from %s", s.task_mode.value)
        self._backend.set_mode_manual()

    def _on_estop_clicked(self):
        """Handle E-Stop button press — trigger estop on backend.

        This is a software E-Stop that commands LinuxCNC into ESTOP state.
        It does NOT replace the hardware E-Stop button but provides a
        convenient always-visible trigger from any tab.
        """
        # Was machine_off() (STATE_OFF) until 2026-11-10: the machine turned
        # off but LinuxCNC never entered ESTOP, and the ribbon stayed IDLE.
        ok = self._backend.estop()
        logger.warning("Software E-Stop triggered from status bar (%s)",
                       "ESTOP" if ok else "FAILED - machine off only")
        if not ok:
            self._status_bar.show_error("Software E-Stop failed - machine turned OFF only")

    def _poll_status_bar(self):
        """Update the status bar with live machine data (runs at 5 Hz)."""
        try:
            self._poll_status_bar_inner()
        except Exception:
            logger.exception("_poll_status_bar raised unexpectedly")

    def _poll_status_bar_inner(self):
        self._backend.poll()
        s = self._backend.state
        take = getattr(self._backend, "take_state_warning", None)
        warning = take() if take is not None else ""
        if warning:
            self._status_bar.show_error(warning)

        # Position
        self._status_bar.update_position(s.x.position, s.z.position)

        # Machine state
        from hal.interface import InterpState, TaskState, TaskMode
        if s.estop_active:
            state_str = "ESTOP"
        elif not s.machine_on:
            state_str = "OFF"      # E-stop reset but machine off: not ready
        elif s.interp_state == InterpState.READING:
            state_str = "RUN"
        elif s.interp_state == InterpState.PAUSED:
            state_str = "PAUSE"
        else:
            state_str = "IDLE"
        self._status_bar.update_state(state_str)

        # Task mode (MANUAL / MDI / AUTO) — flags MDI wedging that silently
        # disables MPG jogging.
        self._status_bar.update_mode(s.task_mode.value)

        # Return to MANUAL when LinuxCNC sits in AUTO with NO program work left
        # (finished, stopped, or rejected at cycle start). LinuxCNC ignores MPG
        # jog counts outside MANUAL. program_busy covers interpreter, task exec,
        # motion queue and pause — interp IDLE alone is true mid-cut once the
        # whole file has been read (lathe, 2026-11-08). Two consecutive polls.
        if s.task_mode == TaskMode.AUTO and not s.program_busy:
            self._auto_idle_polls += 1
            if self._auto_idle_polls == 2:
                logger.info("AUTO and idle: returning to MANUAL")
                if hasattr(self._backend, "restore_lathe_modes"):
                    self._backend.restore_lathe_modes()   # M2 leaves G17
                self._backend.set_mode_manual()
        else:
            self._auto_idle_polls = 0

        # Spindle
        rpm = int(s.spindle.speed)
        direction = ""
        from hal.interface import SpindleDirection
        if s.spindle.direction == SpindleDirection.FORWARD:
            direction = "FWD"
        elif s.spindle.direction == SpindleDirection.REVERSE:
            direction = "REV"
        self._status_bar.update_rpm(rpm, direction)

        # Feed rate (from active feed override × programmed, or just show override)
        self._status_bar.update_feed(s.feed_override)

        # Tool
        self._status_bar.update_tool(s.tool_in_spindle)

        # G-codes
        if s.active_gcodes:
            self._status_bar.update_gcodes(s.active_gcodes)

        # Errors: prefer the error channel message; fall back to ESTOP transition
        if s.error_message:
            self._status_bar.show_error(s.error_message)
            self._run_tab.show_error(s.error_message)
        elif s.estop_active and not self._prev_estop:
            self._status_bar.show_error("E-STOP")

        self._prev_estop = s.estop_active

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_ini_path(self) -> str:
        """Resolve path to machine INI file.

        Searches for the INI in standard locations relative to the project.
        Returns empty string if not found (offline development without INI).
        """
        import os
        # The project root is one level up from gui/
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        candidates = [
            # Same directory as project root (deployed layout)
            os.path.join(project_root, "industry-cam.ini"),
            # Linux deploy path
            "/home/jacob/linuxcnc/configs/industry-cam/industry-cam.ini",
            # Workspace-relative (development)
            os.path.join(project_root, "linuxcnc", "industry-cam.ini"),
        ]
        for path in candidates:
            if os.path.isfile(path):
                return os.path.abspath(path)
        return ""

    # ------------------------------------------------------------------
    # Public Accessors (for testing / external integration)
    # ------------------------------------------------------------------

    @property
    def status_bar(self) -> StatusBar:
        """The top status bar widget."""
        return self._status_bar

    @property
    def program_tab(self) -> ProgramTab:
        """The Program tab instance."""
        return self._program_tab

    @property
    def edit_tab(self) -> EditTab:
        """The Edit tab instance."""
        return self._edit_tab

    @property
    def tools_tab(self) -> Tools_Tab:
        """The Tools tab instance."""
        return self._tools_tab

    @property
    def debug_tab(self) -> DebugTab:
        """The Debug tab instance."""
        return self._debug_tab

    @property
    def tab_widget(self) -> QTabWidget:
        """The main QTabWidget."""
        return self._tab_widget


# --------------------------------------------------------------------------
# Dark Palette Helper
# --------------------------------------------------------------------------

def _apply_dark_palette(app: QApplication):
    """Apply a dark color palette to the application.

    Uses COLORS from gui/colors.py for consistency with the stylesheet.
    """
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(COLORS["bg_base"]))
    palette.setColor(QPalette.WindowText, QColor(COLORS["text_primary"]))
    palette.setColor(QPalette.Base, QColor(COLORS["bg_panel"]))
    palette.setColor(QPalette.AlternateBase, QColor(COLORS["bg_surface"]))
    palette.setColor(QPalette.ToolTipBase, QColor(COLORS["bg_surface"]))
    palette.setColor(QPalette.ToolTipText, QColor(COLORS["text_primary"]))
    palette.setColor(QPalette.Text, QColor(COLORS["text_primary"]))
    palette.setColor(QPalette.Button, QColor(COLORS["bg_panel"]))
    palette.setColor(QPalette.ButtonText, QColor(COLORS["text_primary"]))
    palette.setColor(QPalette.BrightText, QColor(COLORS["status_error"]))
    palette.setColor(QPalette.Link, QColor(COLORS["status_info"]))
    palette.setColor(QPalette.Highlight, QColor(COLORS["btn_primary"]))
    palette.setColor(QPalette.HighlightedText, QColor(COLORS["text_primary"]))
    app.setPalette(palette)


# --------------------------------------------------------------------------
# Live-screen emulation (offline preview on a dev PC)
# --------------------------------------------------------------------------

# The lathe's display: 15.6" FHD panel, Linux/X11 at 96 DPI, window maximized.
LIVE_SCREEN_SIZE = (1920, 1080)


def _enable_live_dpi_emulation():
    """Draw the GUI 1:1 at 96 DPI on Windows, exactly like the lathe.

    Without this, Qt 5 on a 125-150 % Windows display draws point-sized text
    at 120-144 DPI while px-sized widgets (fixed buttons, ribbon chips) stay
    the same, so text crowds the layout in a way the lathe never shows.
    Pinning the font DPI to 96 (no Windows display scaling) gives the same
    layout AND the same pixel count as the lathe: the window is 1920 real
    pixels wide, so its physical size depends only on the monitor's pixel
    density (about the lathe's on a 32" 4K). Set QT_FONT_DPI yourself to
    override. Must run before QApplication is created. Windows-only: the
    lathe (Linux, 96 DPI) is left exactly as it is.
    """
    if sys.platform != "win32":
        return
    os.environ.setdefault("QT_FONT_DPI", "96")


def _show_at_live_size(window: QMainWindow):
    """Show maximized on a 1920x1080 screen; on a larger one, as a 1920x1080
    window so the offline preview matches what the lathe shows."""
    screen = window.screen() or QApplication.primaryScreen()
    avail = screen.availableGeometry()
    target_w, target_h = LIVE_SCREEN_SIZE
    if avail.width() <= target_w or avail.height() <= target_h:
        window.showMaximized()
        return
    # Open ON the target screen. Moving a shown window onto a monitor with a
    # different Windows scale makes Windows rescale it (e.g. 1918 -> 2301 px
    # going from a 125 % to a 150 % monitor), undoing the size set below.
    window.move(avail.topLeft() + QPoint(20, 20))
    window.show()
    # Size the outer frame (title bar included) to 1920x1080, then centre it.
    frame_extra_w = window.frameGeometry().width() - window.width()
    frame_extra_h = window.frameGeometry().height() - window.height()
    window.resize(target_w - frame_extra_w, target_h - frame_extra_h)
    frame = window.frameGeometry()
    frame.moveCenter(avail.center())
    window.move(frame.topLeft())
    logger.info("Window sized to the lathe's %dx%d screen (this screen: %dx%d)",
                target_w, target_h, avail.width(), avail.height())


# --------------------------------------------------------------------------
# Application Entry Point
# --------------------------------------------------------------------------

def main():
    """Launch the Industry CAM Engine GUI application."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    _enable_live_dpi_emulation()
    app = QApplication(sys.argv)
    app.setApplicationName("Industry CAM Engine")

    # Apply dark palette and stylesheet
    _apply_dark_palette(app)
    app.setStyleSheet(STYLESHEET)

    # Create and show main window
    window = MainWindow()
    import os as _os
    _reason = _os.environ.get("INDUSTRY_CAM_OFFLINE_REASON")
    if _reason:
        from PyQt5.QtCore import QTimer as _QT
        from PyQt5.QtWidgets import QMessageBox as _MB
        _QT.singleShot(500, lambda: _MB.warning(
            window, "Offline preview mode",
            f"{_reason}.\n\nThe GUI is running OFFLINE with simulated data - no "
            "machine control. Check the Mesa card power/cable and relaunch."))
    _show_at_live_size(window)

    # Layout debugging aid (ID tags, outlines, inspector, ruler, snapshots).
    from gui.debug_overlay import debug_ui_enabled, install_debug_overlay
    if debug_ui_enabled():
        window._debug_overlay = install_debug_overlay(window)

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
