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

import sys
import logging

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPalette, QColor
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QTabWidget, QLabel,
)

from gui.colors import COLORS, FONTS, STYLESHEET
from gui.components.status_bar import StatusBar
from gui.program_tab import ProgramTab
from gui.edit_tab import EditTab
from gui.tools_tab import ToolsTab
from gui.debug_tab import DebugTab
from gui.manual import ManualTab
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

        # --- P1 Tabs (fully implemented) ---
        self._program_tab = ProgramTab(self)
        self._edit_tab = EditTab(self)
        self._tools_tab = ToolsTab(self)
        self._debug_tab = DebugTab(self)

        self._tab_widget.addTab(self._program_tab, "Program")
        self._tab_widget.addTab(self._edit_tab, "Edit")
        self._tab_widget.addTab(self._tools_tab, "Tools")
        self._tab_widget.addTab(self._debug_tab, "Debug")

        # --- P2 Placeholder Tabs ---
        self._manual_tab = ManualTab(self)
        self._tab_widget.addTab(
            self._make_placeholder("Coming in Phase 2"), "Run"
        )
        self._tab_widget.addTab(self._manual_tab, "Manual")

        # --- P3 Placeholder Tabs ---
        self._setup_tab = SetupTab(
            backend=self._backend,
            ini_path=self._get_ini_path(),
        )
        self._tab_widget.addTab(self._setup_tab, "Setup")
        self._tab_widget.addTab(
            self._make_placeholder("Coming in Phase 3"), "Help"
        )

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

        # 6. Tab change → activate/deactivate Setup tab polling
        self._tab_widget.currentChanged.connect(self._on_tab_changed)

    # ------------------------------------------------------------------
    # Signal Slots
    # ------------------------------------------------------------------

    def _on_tool_changed(self, tool_number: int):
        """Handle tool table change — log and mark program tab stale.

        Args:
            tool_number: The tool number that was modified.
        """
        logger.info("Tool T%d modified in tool table", tool_number)
        # If the modified tool is the active tool, mark program stale
        if hasattr(self._program_tab, '_active_tool'):
            active = self._program_tab._active_tool
            if active and active.tool_number == tool_number:
                updated = self._tools_tab.get_tool(tool_number)
                if updated:
                    self._program_tab.set_active_tool(updated)

    def _on_tool_selected(self, tool_def):
        """Handle tool selection in Tools tab — update Program tab's active tool.

        Args:
            tool_def: The ToolDef that was selected.
        """
        logger.info("Tool T%d selected in tool table", tool_def.tool_number)
        self._program_tab.set_active_tool(tool_def)

    def _on_tab_changed(self, index: int):
        """Handle main tab switch — activate/deactivate Setup tab polling."""
        is_setup = (self._tab_widget.widget(index) is self._setup_tab)
        self._setup_tab.set_active(is_setup)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_ini_path(self) -> str:
        """Resolve path to machine INI file.

        Searches for the INI in standard locations relative to the project.
        Returns empty string if not found (offline development without INI).
        """
        import os
        candidates = [
            # Workspace-relative (development)
            os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "..", "linuxcnc", "industry-cam.ini"),
            # Ship to LinuxPC folder
            os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "..", "Ship to LinuxPC", "industry-cam.ini"),
            # Linux deploy path
            "/home/linuxcnc/linuxcnc/industry-cam/industry-cam.ini",
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
    def tools_tab(self) -> ToolsTab:
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
# Application Entry Point
# --------------------------------------------------------------------------

def main():
    """Launch the Industry CAM Engine GUI application."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    app = QApplication(sys.argv)
    app.setApplicationName("Industry CAM Engine")

    # Apply dark palette and stylesheet
    _apply_dark_palette(app)
    app.setStyleSheet(STYLESHEET)

    # Create and show main window
    window = MainWindow()
    window.showMaximized()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
