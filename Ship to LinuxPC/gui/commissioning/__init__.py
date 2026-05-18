"""Machine Commissioning Module — HAL Diagnostics, Tuning & Validation.

This module provides the Setup tab functionality for the Industry CAM Engine GUI.
It covers the full machine commissioning lifecycle:

1. HAL Monitor — Pin browser, signal tracing, watch list with live polling
2. Tuning — PID gains, following error graph, stepgen/encoder parameters
3. Commissioning Checklist — Guided step-by-step machine validation

Architecture:
    - Uses the existing hal/ backend for machine control (jog, home, MDI)
    - Adds a pin-level provider layer for raw HAL diagnostics
    - All UI works identically in offline mode (SimulatedTuningProvider)
    - Timer management via set_active() — no polling when tab is hidden

Integration:
    The SetupTab is a QTabWidget containing three sub-tabs:
        - HAL Monitor (pin browser + watch list)
        - Tuning (PID + following error graph)
        - Commissioning (guided checklist)

    Wire into MainWindow:
        from gui.commissioning import SetupTab
        self._setup_tab = SetupTab(backend=self._backend)
        self._tab_widget.addTab(self._setup_tab, "Setup")
"""

from gui.commissioning.setup_tab import SetupTab

__all__ = ["SetupTab"]
