"""Setup Tab — Container for commissioning sub-tabs.

This is the top-level widget that gets added to MainWindow's QTabWidget.
It contains three sub-tabs:
    1. HAL Monitor — pin browser, signal tracing, watch list
    2. Tuning — PID, following error graph, stepgen/encoder params
    3. Commission — guided checklist for machine validation

Timer management: only the active sub-tab polls. When the Setup tab itself
is not visible (user is on Program, Edit, etc.), ALL polling stops.
"""

import logging

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QTabWidget
from PyQt5.QtCore import Qt

from gui.colors import COLORS
from hal.interface import HALBackend

logger = logging.getLogger(__name__)


class SetupTab(QWidget):
    """Top-level Setup tab containing commissioning sub-tabs.

    Args:
        backend: HALBackend instance (Live or Mock) from hal.factory.
        ini_path: Path to industry-cam.ini for parameter load/save.
        parent: Parent widget.
    """

    def __init__(self, backend: HALBackend, ini_path: str = "", parent=None):
        super().__init__(parent)
        self._backend = backend
        self._ini_path = ini_path
        self._active = False

        self._build_ui()
        self._sub_tabs.currentChanged.connect(self._on_sub_tab_changed)

    def _build_ui(self):
        """Build the sub-tab container."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._sub_tabs = QTabWidget()
        self._sub_tabs.setDocumentMode(True)
        self._sub_tabs.setTabPosition(QTabWidget.South)

        # Lazy imports to avoid circular dependencies
        from gui.commissioning.hal_monitor_tab import HALMonitorTab
        from gui.commissioning.tuning_tab import TuningTab
        from gui.commissioning.commissioning_tab import CommissioningTab

        self._hal_monitor = HALMonitorTab(backend=self._backend)
        self._tuning = TuningTab(
            backend=self._backend,
            ini_path=self._ini_path,
        )
        self._commissioning = CommissioningTab(backend=self._backend)

        self._sub_tabs.addTab(self._hal_monitor, "HAL Monitor")
        self._sub_tabs.addTab(self._tuning, "Tuning")
        self._sub_tabs.addTab(self._commissioning, "Commission")

        layout.addWidget(self._sub_tabs)

    # ------------------------------------------------------------------
    # Public API — called by MainWindow
    # ------------------------------------------------------------------

    def set_active(self, active: bool):
        """Start/stop all polling based on parent tab visibility.

        Called by MainWindow._on_tab_changed() when the Setup tab
        becomes visible or hidden.
        """
        self._active = active
        if active:
            # Activate whichever sub-tab is currently selected
            self._activate_current_sub_tab()
        else:
            # Deactivate all sub-tabs
            self._hal_monitor.set_active(False)
            self._tuning.set_active(False)
            self._commissioning.set_active(False)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_sub_tab_changed(self, index: int):
        """Handle sub-tab switch — activate new, deactivate old."""
        if not self._active:
            return
        self._activate_current_sub_tab()

    def _activate_current_sub_tab(self):
        """Activate only the currently visible sub-tab."""
        current = self._sub_tabs.currentWidget()
        self._hal_monitor.set_active(current is self._hal_monitor)
        self._tuning.set_active(current is self._tuning)
        self._commissioning.set_active(current is self._commissioning)

    # ------------------------------------------------------------------
    # Accessors (for testing / external integration)
    # ------------------------------------------------------------------

    @property
    def hal_monitor(self):
        return self._hal_monitor

    @property
    def tuning(self):
        return self._tuning

    @property
    def commissioning(self):
        return self._commissioning
