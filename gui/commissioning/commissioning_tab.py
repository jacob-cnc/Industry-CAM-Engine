"""Commissioning Tab — Guided machine validation checklist.

Provides a step-by-step workflow for bringing a machine from "wired up"
to "ready to cut". Each step has:
    - Description of what to verify
    - Action buttons (where applicable)
    - Pass/Fail/Skip status
    - Notes field for recording observations

Steps:
    1. Verify I/O — confirm inputs read, outputs toggle
    2. E-Stop — verify emergency stop chain
    3. Jog Test — confirm axis direction, scale, soft limits
    4. Home Test — verify homing sequence
    5. Encoder Verify — compare stepgen vs encoder positions
    6. PID Tune — basic tuning (links to Tuning tab)
    7. FERROR Test — run at speed, confirm no faults
    8. Spindle — verify encoder reads RPM correctly
    9. Tool Change — verify tool table and offsets

The checklist state persists to a JSON file so progress survives restarts.
"""

import json
import os
import logging
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
    QLabel, QPushButton, QGroupBox, QTextEdit, QFrame,
    QMessageBox,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont

from gui.colors import COLORS, FONTS
from hal.interface import HALBackend

logger = logging.getLogger(__name__)


class StepStatus(Enum):
    """Status of a commissioning step."""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


# =============================================================================
# Step Definitions
# =============================================================================

COMMISSIONING_STEPS = [
    {
        "id": "verify_io",
        "title": "1. Verify I/O",
        "description": (
            "Confirm all physical inputs read correctly in HAL Monitor.\n"
            "• Press each home switch — verify pin toggles\n"
            "• Press each jog button — verify pin toggles\n"
            "• Press E-Stop — verify estop-ext signal\n"
            "• Spin MPG wheels — verify encoder counts change"
        ),
        "action": "Open HAL Monitor tab and check pins manually",
    },
    {
        "id": "estop_chain",
        "title": "2. E-Stop Chain",
        "description": (
            "Verify the emergency stop chain works end-to-end.\n"
            "• Press physical E-Stop button\n"
            "• Confirm LinuxCNC enters ESTOP state\n"
            "• Release E-Stop, reset in GUI\n"
            "• Confirm machine returns to ON state"
        ),
        "action": "Test E-Stop cycle",
    },
    {
        "id": "jog_test",
        "title": "3. Jog Test",
        "description": (
            "Verify axis motion direction and scale.\n"
            "• Jog X+ — tool should move AWAY from centerline\n"
            "• Jog X- — tool should move TOWARD centerline\n"
            "• Jog Z+ — tool should move AWAY from chuck\n"
            "• Jog Z- — tool should move TOWARD chuck\n"
            "• Verify DRO matches physical movement\n"
            "• Test soft limits — machine should stop at limits"
        ),
        "action": "Use Manual tab to jog each axis",
    },
    {
        "id": "home_test",
        "title": "4. Home Test",
        "description": (
            "Verify homing sequence for both axes.\n"
            "• Manually jog to approximate home position\n"
            "• Trigger home for X — verify it finds switch\n"
            "• Trigger home for Z — verify it finds switch\n"
            "• After homing, DRO should show correct coordinates\n"
            "• Jog away and re-home — should return to same position"
        ),
        "action": "Home each axis and verify repeatability",
    },
    {
        "id": "encoder_verify",
        "title": "5. Encoder Verification",
        "description": (
            "Compare stepgen position vs linear encoder position.\n"
            "• Home both axes\n"
            "• Jog X to several positions — compare stepgen.01.position-fb\n"
            "  vs encoder.00.position in HAL Monitor\n"
            "• Jog Z similarly — compare stepgen.00.position-fb\n"
            "  vs encoder.01.position\n"
            "• Difference should be < 0.001\" (encoder resolution)\n"
            "• If large discrepancy: check encoder scale, wiring, direction"
        ),
        "action": "Compare positions in HAL Monitor watch list",
    },
    {
        "id": "pid_tune",
        "title": "6. PID Tuning",
        "description": (
            "Basic PID tuning for closed-loop stepper correction.\n"
            "• Open Tuning tab\n"
            "• Load from INI to get current values\n"
            "• Verify FF1 = 1.0 (critical for velocity-mode stepgen)\n"
            "• Watch following error graph during motion\n"
            "• Adjust P gain: increase until oscillation, back off 20%\n"
            "• Adjust deadband to ignore encoder noise (~0.00005\")\n"
            "• Apply Live to test, Save to INI when satisfied"
        ),
        "action": "Switch to Tuning tab",
    },
    {
        "id": "ferror_test",
        "title": "7. Following Error Test",
        "description": (
            "Run at full speed and verify no FERROR faults.\n"
            "• Load a simple test program (rapid X and Z full travel)\n"
            "• Run at 100% feed override\n"
            "• Watch following error graph — should stay within limits\n"
            "• If faulting: reduce MAX_VELOCITY or increase FERROR\n"
            "• Typical good values: FERROR=0.005\", MIN_FERROR=0.001\""
        ),
        "action": "Run test program at full speed",
    },
    {
        "id": "spindle_verify",
        "title": "8. Spindle Encoder",
        "description": (
            "Verify spindle encoder reads RPM correctly.\n"
            "• Start spindle manually at a known speed\n"
            "• Check encoder.02.velocity in HAL Monitor\n"
            "• velocity × 60 should match actual RPM\n"
            "• Verify index pulse: encoder.02.index-enable should pulse\n"
            "  once per revolution\n"
            "• Test at multiple speeds (500, 1000, 1500 RPM)"
        ),
        "action": "Verify spindle RPM in HAL Monitor",
    },
    {
        "id": "tool_change",
        "title": "9. Tool Change & Offsets",
        "description": (
            "Verify tool table and tool change procedure.\n"
            "• Load tool table in Tools tab\n"
            "• Issue T1 M6 — verify tool change completes\n"
            "• Touch off a reference surface\n"
            "• Change to T2 — verify offset is applied correctly\n"
            "• DRO should show correct position with tool offset"
        ),
        "action": "Test tool change sequence via MDI",
    },
]


# =============================================================================
# Step Widget
# =============================================================================

class CommissioningStepWidget(QGroupBox):
    """UI widget for a single commissioning step."""

    STATUS_COLORS = {
        StepStatus.NOT_STARTED: COLORS['text_disabled'],
        StepStatus.IN_PROGRESS: COLORS['status_info'],
        StepStatus.PASSED: COLORS['status_ok'],
        StepStatus.FAILED: COLORS['status_error'],
        StepStatus.SKIPPED: COLORS['text_secondary'],
    }

    STATUS_LABELS = {
        StepStatus.NOT_STARTED: "○ Not Started",
        StepStatus.IN_PROGRESS: "◐ In Progress",
        StepStatus.PASSED: "● Passed",
        StepStatus.FAILED: "✕ Failed",
        StepStatus.SKIPPED: "⊘ Skipped",
    }

    def __init__(self, step_def: dict, parent=None):
        super().__init__(step_def["title"], parent)
        self._step_id = step_def["id"]
        self._status = StepStatus.NOT_STARTED
        self._notes = ""

        self._build_ui(step_def)

    def _build_ui(self, step_def: dict):
        layout = QVBoxLayout(self)
        layout.setSpacing(4)

        # Description
        desc = QLabel(step_def["description"])
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 9pt;")
        layout.addWidget(desc)

        # Action hint
        action = QLabel(f"→ {step_def['action']}")
        action.setStyleSheet(
            f"color: {COLORS['status_info']}; font-style: italic;"
        )
        layout.addWidget(action)

        # Status + buttons row
        btn_row = QHBoxLayout()

        self._status_label = QLabel(self.STATUS_LABELS[self._status])
        self._status_label.setStyleSheet(
            f"color: {self.STATUS_COLORS[self._status]}; font-weight: bold;"
        )
        btn_row.addWidget(self._status_label)

        btn_row.addStretch()

        self._btn_pass = QPushButton("Pass")
        self._btn_pass.setFixedSize(60, 28)
        self._btn_pass.setStyleSheet(
            f"QPushButton {{ background-color: {COLORS['status_ok']};"
            f"  color: {COLORS['bg_base']}; min-height: 0px; padding: 2px; }}"
        )
        self._btn_pass.clicked.connect(lambda: self.set_status(StepStatus.PASSED))
        btn_row.addWidget(self._btn_pass)

        self._btn_fail = QPushButton("Fail")
        self._btn_fail.setFixedSize(60, 28)
        self._btn_fail.setStyleSheet(
            f"QPushButton {{ background-color: {COLORS['status_error']};"
            f"  color: {COLORS['text_primary']}; min-height: 0px; padding: 2px; }}"
        )
        self._btn_fail.clicked.connect(lambda: self.set_status(StepStatus.FAILED))
        btn_row.addWidget(self._btn_fail)

        self._btn_skip = QPushButton("Skip")
        self._btn_skip.setFixedSize(60, 28)
        self._btn_skip.setStyleSheet(
            "QPushButton { min-height: 0px; padding: 2px; }"
        )
        self._btn_skip.clicked.connect(lambda: self.set_status(StepStatus.SKIPPED))
        btn_row.addWidget(self._btn_skip)

        layout.addLayout(btn_row)

        # Notes field (collapsible — starts hidden)
        self._notes_edit = QTextEdit()
        self._notes_edit.setPlaceholderText("Notes (optional)…")
        self._notes_edit.setMaximumHeight(60)
        self._notes_edit.setStyleSheet(
            f"QTextEdit {{ background-color: {COLORS['bg_panel']};"
            f"  color: {COLORS['text_primary']};"
            f"  border: 1px solid {COLORS['border_normal']};"
            f"  border-radius: 2px; font-size: 9pt; }}"
        )
        layout.addWidget(self._notes_edit)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def step_id(self) -> str:
        return self._step_id

    @property
    def status(self) -> StepStatus:
        return self._status

    def set_status(self, status: StepStatus):
        self._status = status
        self._status_label.setText(self.STATUS_LABELS[status])
        self._status_label.setStyleSheet(
            f"color: {self.STATUS_COLORS[status]}; font-weight: bold;"
        )

    def get_notes(self) -> str:
        return self._notes_edit.toPlainText()

    def set_notes(self, text: str):
        self._notes_edit.setPlainText(text)

    def get_state(self) -> dict:
        """Serialize step state for persistence."""
        return {
            "status": self._status.value,
            "notes": self.get_notes(),
        }

    def restore_state(self, state: dict):
        """Restore step state from persistence."""
        status_str = state.get("status", "not_started")
        try:
            self.set_status(StepStatus(status_str))
        except ValueError:
            self.set_status(StepStatus.NOT_STARTED)
        self.set_notes(state.get("notes", ""))


# =============================================================================
# Commissioning Tab
# =============================================================================

class CommissioningTab(QWidget):
    """Guided commissioning checklist with persistence."""

    def __init__(self, backend: HALBackend, parent=None):
        super().__init__(parent)
        self._backend = backend
        self._steps: List[CommissioningStepWidget] = []
        self._state_file = ""  # Set by caller or auto-detected

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # Header
        header = QHBoxLayout()
        title = QLabel("Machine Commissioning Checklist")
        title.setStyleSheet(
            f"color: {COLORS['status_info']}; font-size: 12pt; font-weight: bold;"
        )
        header.addWidget(title)
        header.addStretch()

        self._btn_save_state = QPushButton("Save Progress")
        self._btn_save_state.setFixedHeight(32)
        self._btn_save_state.clicked.connect(self._save_state)
        header.addWidget(self._btn_save_state)

        self._btn_reset = QPushButton("Reset All")
        self._btn_reset.setFixedHeight(32)
        self._btn_reset.setStyleSheet(
            f"QPushButton {{ background-color: {COLORS['btn_danger']}; }}"
        )
        self._btn_reset.clicked.connect(self._reset_all)
        header.addWidget(self._btn_reset)

        layout.addLayout(header)

        # Progress summary
        self._progress_label = QLabel("")
        self._progress_label.setStyleSheet(
            f"color: {COLORS['text_secondary']}; font-size: 10pt;"
        )
        layout.addWidget(self._progress_label)

        # Scrollable step list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            f"QScrollArea {{ border: none; }}"
        )

        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setSpacing(8)

        for step_def in COMMISSIONING_STEPS:
            widget = CommissioningStepWidget(step_def)
            self._steps.append(widget)
            container_layout.addWidget(widget)

        container_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll, stretch=1)

        self._update_progress()

    # =================================================================
    # Public API
    # =================================================================

    def set_active(self, active: bool):
        """No polling needed — just update progress display."""
        if active:
            self._update_progress()

    def set_state_file(self, path: str):
        """Set the path for persisting checklist state."""
        self._state_file = path
        if os.path.isfile(path):
            self._load_state()

    # =================================================================
    # Persistence
    # =================================================================

    def _save_state(self):
        """Save checklist state to JSON file."""
        if not self._state_file:
            # Default to alongside the INI file
            self._state_file = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "..", "..", "commissioning_state.json"
            )

        state = {
            "saved_at": datetime.now().isoformat(),
            "steps": {s.step_id: s.get_state() for s in self._steps},
        }

        try:
            os.makedirs(os.path.dirname(os.path.abspath(self._state_file)),
                        exist_ok=True)
            with open(self._state_file, 'w') as f:
                json.dump(state, f, indent=2)
            logger.info("Commissioning state saved to %s", self._state_file)
        except OSError as e:
            QMessageBox.warning(self, "Save Error", f"Could not save: {e}")

    def _load_state(self):
        """Load checklist state from JSON file."""
        try:
            with open(self._state_file, 'r') as f:
                state = json.load(f)

            steps_data = state.get("steps", {})
            for step_widget in self._steps:
                if step_widget.step_id in steps_data:
                    step_widget.restore_state(steps_data[step_widget.step_id])

            self._update_progress()
            logger.info("Commissioning state loaded from %s", self._state_file)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("Could not load commissioning state: %s", e)

    def _reset_all(self):
        """Reset all steps to NOT_STARTED."""
        reply = QMessageBox.question(
            self, "Reset Checklist",
            "Reset all commissioning steps?\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        for step in self._steps:
            step.set_status(StepStatus.NOT_STARTED)
            step.set_notes("")
        self._update_progress()

    def _update_progress(self):
        """Update the progress summary label."""
        total = len(self._steps)
        passed = sum(1 for s in self._steps if s.status == StepStatus.PASSED)
        failed = sum(1 for s in self._steps if s.status == StepStatus.FAILED)
        skipped = sum(1 for s in self._steps if s.status == StepStatus.SKIPPED)
        remaining = total - passed - failed - skipped

        self._progress_label.setText(
            f"Progress: {passed}/{total} passed"
            f"  |  {failed} failed  |  {skipped} skipped"
            f"  |  {remaining} remaining"
        )
