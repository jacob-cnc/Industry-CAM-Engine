"""Generation Error Dialog for Industry CAM Engine.

Shows detailed error information when toolpath generation fails.
Categorizes errors by source (validation, geometry, zone construction, etc.)
and provides actionable recommendations.
"""

import traceback
from typing import List, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QTextEdit, QPushButton, QFrame, QSizePolicy,
)
from PyQt5.QtGui import QFont, QTextCursor

from gui.colors import COLORS, FONTS


class GenerationErrorDialog(QDialog):
    """Modal dialog showing detailed toolpath generation error info.

    Displays:
    - Error category (validation, geometry kernel, zone construction, etc.)
    - Primary error message
    - Recommendations for fixing
    - Full traceback (collapsible)
    - Validation results list (if pipeline returned them)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Toolpath Generation Failed")
        self.setMinimumSize(560, 340)
        self.resize(620, 440)
        self.setModal(True)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # Header with icon-style label
        header = QLabel("⚠  Generation Failed")
        header.setStyleSheet(
            f"color: {COLORS['status_error']}; "
            f"font-size: 14pt; font-weight: bold;"
        )
        layout.addWidget(header)

        # Category label
        self._category_label = QLabel("")
        self._category_label.setStyleSheet(
            f"color: {COLORS['text_secondary']}; font-size: {FONTS['small_size']}pt;"
        )
        layout.addWidget(self._category_label)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color: {COLORS.get('border', '#3a3a3a')};")
        layout.addWidget(sep)

        # Primary message
        self._message_label = QLabel("")
        self._message_label.setWordWrap(True)
        self._message_label.setStyleSheet(
            f"color: {COLORS['text_primary']}; font-size: {FONTS.get('body_size', 10)}pt;"
        )
        layout.addWidget(self._message_label)

        # Recommendation
        self._recommendation_label = QLabel("")
        self._recommendation_label.setWordWrap(True)
        self._recommendation_label.setStyleSheet(
            f"color: {COLORS.get('accent_blue', '#5b9bd5')}; "
            f"font-size: {FONTS.get('body_size', 10)}pt;"
        )
        layout.addWidget(self._recommendation_label)

        # Validation list (for pipeline validation errors)
        self._validation_text = QTextEdit()
        self._validation_text.setReadOnly(True)
        self._validation_text.setVisible(False)
        self._validation_text.setMaximumHeight(140)
        self._validation_text.setStyleSheet(
            f"background-color: {COLORS.get('bg_secondary', '#1e1e1e')}; "
            f"color: {COLORS['text_primary']}; "
            f"border: 1px solid {COLORS.get('border', '#3a3a3a')}; "
            f"font-family: 'JetBrains Mono', 'Consolas', monospace; "
            f"font-size: 9pt;"
        )
        layout.addWidget(self._validation_text)

        # Traceback section (collapsible)
        self._traceback_toggle = QPushButton("▶ Show Technical Details")
        self._traceback_toggle.setFlat(True)
        self._traceback_toggle.setStyleSheet(
            f"color: {COLORS['text_secondary']}; "
            f"font-size: {FONTS['small_size']}pt; "
            "text-align: left; padding: 2px;"
        )
        self._traceback_toggle.clicked.connect(self._toggle_traceback)
        layout.addWidget(self._traceback_toggle)

        self._traceback_text = QTextEdit()
        self._traceback_text.setReadOnly(True)
        self._traceback_text.setVisible(False)
        self._traceback_text.setMinimumHeight(120)
        self._traceback_text.setStyleSheet(
            f"background-color: {COLORS.get('bg_secondary', '#1e1e1e')}; "
            f"color: {COLORS.get('text_dim', '#808080')}; "
            f"border: 1px solid {COLORS.get('border', '#3a3a3a')}; "
            f"font-family: 'JetBrains Mono', 'Consolas', monospace; "
            f"font-size: 8pt;"
        )
        layout.addWidget(self._traceback_text)

        # Spacer
        layout.addStretch()

        # Close button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setMinimumWidth(80)
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def _toggle_traceback(self):
        """Toggle traceback visibility."""
        visible = not self._traceback_text.isVisible()
        self._traceback_text.setVisible(visible)
        self._traceback_toggle.setText(
            "▼ Hide Technical Details" if visible else "▶ Show Technical Details"
        )
        # Resize dialog to fit
        if visible:
            self.resize(self.width(), max(self.height(), 560))

    def show_exception(self, exception: Exception, tb_str: str,
                       stage: str = "unknown"):
        """Populate dialog from an unhandled exception.

        Args:
            exception: The caught exception
            tb_str: Formatted traceback string
            stage: Pipeline stage where failure occurred
                   ("model_build", "pipeline", "zone_construction",
                    "gcode_write", "graph_convert")
        """
        category, recommendation = _categorize_exception(exception, stage)

        self._category_label.setText(f"Stage: {stage}  •  Category: {category}")

        # Primary message
        msg = str(exception) if str(exception) else type(exception).__name__
        self._message_label.setText(msg)

        # Recommendation
        if recommendation:
            self._recommendation_label.setText(f"💡 {recommendation}")
            self._recommendation_label.setVisible(True)
        else:
            self._recommendation_label.setVisible(False)

        # Traceback
        self._traceback_text.setPlainText(tb_str)
        self._traceback_toggle.setVisible(True)

        # Hide validation list for exceptions
        self._validation_text.setVisible(False)

        self.exec_()

    def show_validation_errors(self, validations: list, stage: str = "validation"):
        """Populate dialog from pipeline validation results.

        Args:
            validations: List of ValidationResult objects from the pipeline
            stage: Which validation stage caught the errors
        """
        errors = [v for v in validations if v.severity.value == "error"]
        warnings = [v for v in validations if v.severity.value == "warning"]

        self._category_label.setText(
            f"Stage: {stage}  •  {len(errors)} error(s), {len(warnings)} warning(s)"
        )

        # Primary message from first error
        if errors:
            first = errors[0]
            self._message_label.setText(first.message)
            if first.recommendation:
                self._recommendation_label.setText(f"💡 {first.recommendation}")
                self._recommendation_label.setVisible(True)
            else:
                self._recommendation_label.setVisible(False)
        else:
            self._message_label.setText("Pipeline blocked by validation errors.")
            self._recommendation_label.setVisible(False)

        # Full validation list
        lines = []
        for v in validations:
            icon = "❌" if v.severity.value == "error" else "⚠️"
            loc_str = ""
            if v.location:
                loc_str = f" @ X={v.location[0]:.4f}, Z={v.location[1]:.4f}"
            lines.append(f"{icon} [{v.category}] {v.message}{loc_str}")
            if v.recommendation:
                lines.append(f"   → {v.recommendation}")
            if v.consequence:
                lines.append(f"   ⚡ {v.consequence}")
            lines.append("")

        if lines:
            self._validation_text.setPlainText("\n".join(lines))
            self._validation_text.setVisible(True)
        else:
            self._validation_text.setVisible(False)

        # No traceback for validation errors
        self._traceback_toggle.setVisible(False)
        self._traceback_text.setVisible(False)

        self.exec_()


def _categorize_exception(exception: Exception, stage: str) -> tuple:
    """Categorize an exception and provide a user-friendly recommendation.

    Returns:
        (category_name, recommendation_text)
    """
    exc_type = type(exception).__name__
    msg = str(exception).lower()

    # Zone construction / Build123d / OCCT errors
    if "wire" in msg or "boundary_wire_extraction" in msg:
        return (
            "Zone Construction",
            "The profile geometry could not form a valid solid. "
            "Check that the profile doesn't self-intersect and that "
            "all segments connect end-to-end without gaps."
        )

    if "occt" in msg or "ocp" in msg or "topods" in msg or "brep" in msg:
        return (
            "Geometry Kernel (OCCT)",
            "The geometry kernel failed to construct a solid from the profile. "
            "This usually means the profile has degenerate geometry — "
            "zero-length segments, overlapping edges, or arcs that can't be resolved."
        )

    if "build123d" in msg or "sketch" in msg or "extrude" in msg:
        return (
            "Geometry Construction (Build123d)",
            "Build123d failed during zone construction. "
            "Check for zero-length segments or arcs with radius smaller than chord/2."
        )

    # Model building errors
    if stage == "model_build":
        return (
            "Input Validation",
            "One or more input fields have invalid values. "
            "Check that all numeric fields are within range and segments are defined."
        )

    # Contour intersect / fiber errors
    if "fiber" in msg or "intersect" in msg or "contour_intersect" in msg:
        return (
            "Contour Intersection",
            "The roughing planner couldn't compute intersections with the profile. "
            "This may indicate a degenerate profile shape at the reported location."
        )

    # Planner errors
    if "planner" in msg or stage in ("face_plan", "roughing_plan", "cleanup_plan", "finish_plan"):
        return (
            "Toolpath Planning",
            "The planner failed to generate passes. "
            "Check that the tool can physically reach all profile features "
            "(nose radius vs. internal corner radii, edge length vs. depth)."
        )

    # G-code writer errors
    if stage == "gcode_write":
        return (
            "G-code Generation",
            "Toolpath was planned but G-code generation failed. "
            "This is likely a bug — the planned moves contain invalid geometry."
        )

    # Graph conversion errors
    if stage == "graph_convert":
        return (
            "Display Conversion",
            "Toolpath was generated but couldn't be displayed. "
            "The G-code should still be valid — try saving and loading in LinuxCNC."
        )

    # ValueError from model_builder or pipeline
    if exc_type == "ValueError":
        return (
            "Invalid Parameter",
            "A parameter value is out of range or incompatible. "
            "Check the error message for which field needs adjustment."
        )

    # RuntimeError (often from zone_builder assertions)
    if exc_type == "RuntimeError":
        return (
            "Pipeline Runtime Error",
            "An internal assertion failed. This usually indicates "
            "the profile geometry is valid but creates a degenerate zone "
            "(e.g., zero-area material removal region)."
        )

    # Generic fallback
    return (
        f"Unexpected ({exc_type})",
        "An unexpected error occurred. Check the technical details "
        "for the full traceback and report this as a bug if it persists."
    )
