"""Debug Tab for Industry CAM Engine.

Sub-panels via horizontal tab bar: Fibers, Swept, Heatmap, Diagnostic, Round-Trip, Export.
Lazy rendering: compute panel content only when the sub-tab is selected.
Stores PlanResult reference, marks panels as "dirty" when new result arrives.
"""

from typing import Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QLabel, QPushButton, QPlainTextEdit, QFileDialog,
    QMessageBox,
)
from PyQt5.QtGui import QFont

from gui.colors import COLORS, FONTS
from models.results import PlanResult
from outputs.dxf_exporter import export as export_dxf, export_from_gcode
from outputs.svg_exporter import export as export_svg
from outputs.gcode_writer import GCodeWriter
from gui.unit_state import unit_state


class DebugTab(QWidget):
    """Debug tab with 6 sub-panels for toolpath inspection and export.

    Sub-panels:
        Fibers — Interval chart visualization (text list of X levels and Z intervals)
        Swept — Cumulative swept region display (text list per pass)
        Heatmap — Placeholder for future material removal heatmap
        Diagnostic — Structured text dump of PlanResult
        Round-Trip — G-code fidelity comparison overlay
        Export — DXF, SVG, PNG, G-code→DXF buttons

    Signals:
        export_requested(str, str): Emitted with (format, path) when export button clicked
    """

    export_requested = pyqtSignal(str, str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._plan_result: Optional[PlanResult] = None
        self._dirty = [True] * 6  # One dirty flag per sub-panel
        self._setup_ui()
        self._connect_signals()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_panels(self, plan_result: PlanResult) -> None:
        """Store PlanResult, invalidate all panels, render current panel.

        Args:
            plan_result: The immutable PlanResult from pipeline.execute()
        """
        self._plan_result = plan_result
        self._dirty = [True] * 6
        self._render_current_panel()

    # ------------------------------------------------------------------
    # UI Setup
    # ------------------------------------------------------------------

    def _setup_ui(self):
        """Build the debug tab layout with sub-tab widget."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Sub-tab widget (horizontal tab bar at top)
        self._tab_widget = QTabWidget()
        self._tab_widget.setTabPosition(QTabWidget.North)
        self._tab_widget.setStyleSheet(self._tab_stylesheet())
        layout.addWidget(self._tab_widget)

        # Create sub-panels
        self._fibers_panel = self._build_text_panel()
        self._swept_panel = self._build_text_panel()
        self._heatmap_panel = self._build_placeholder_panel("Coming soon")
        self._diagnostic_panel = self._build_text_panel()
        self._roundtrip_panel = self._build_text_panel()
        self._export_panel = self._build_export_panel()

        # Add tabs
        self._tab_widget.addTab(self._fibers_panel, "Fibers")
        self._tab_widget.addTab(self._swept_panel, "Swept")
        self._tab_widget.addTab(self._heatmap_panel, "Heatmap")
        self._tab_widget.addTab(self._diagnostic_panel, "Diagnostic")
        self._tab_widget.addTab(self._roundtrip_panel, "Round-Trip")
        self._tab_widget.addTab(self._export_panel, "Export")

        # Show empty state initially
        self._show_no_data_all()

    def _build_text_panel(self) -> QWidget:
        """Build a panel with a QPlainTextEdit for text content."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(0)

        text_edit = QPlainTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setFont(self._mono_font())
        text_edit.setStyleSheet(
            f"QPlainTextEdit {{"
            f"  background-color: {COLORS['bg_panel']};"
            f"  color: {COLORS['text_primary']};"
            f"  border: none;"
            f"  selection-background-color: {COLORS['bg_surface']};"
            f"}}"
        )
        text_edit.setPlainText("No data \u2014 generate a toolpath first")
        layout.addWidget(text_edit)

        # Store reference on the panel widget for easy access
        panel._text_edit = text_edit
        return panel

    def _build_placeholder_panel(self, message: str) -> QWidget:
        """Build a panel with a centered placeholder label."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        label = QLabel(message)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet(
            f"color: {COLORS['text_disabled']};"
            f" font-size: 14pt;"
            f" font-style: italic;"
        )
        layout.addWidget(label)
        return panel

    def _build_export_panel(self) -> QWidget:
        """Build the export panel with action buttons."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header
        header = QLabel("Export Toolpath")
        header.setStyleSheet(
            f"color: {COLORS['text_primary']};"
            f" font-size: 12pt;"
            f" font-weight: bold;"
        )
        layout.addWidget(header)

        desc = QLabel("Export the current toolpath in various formats.")
        desc.setStyleSheet(f"color: {COLORS['text_secondary']};")
        layout.addWidget(desc)

        # Buttons row
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        self._btn_export_dxf = self._make_export_button("Export DXF")
        self._btn_export_svg = self._make_export_button("Export SVG")
        self._btn_export_png = self._make_export_button("Export PNG")
        self._btn_export_gcode = self._make_export_button("Export G-code")
        self._btn_export_gcode_dxf = self._make_export_button("G-code\u2192DXF")

        btn_layout.addWidget(self._btn_export_dxf)
        btn_layout.addWidget(self._btn_export_svg)
        btn_layout.addWidget(self._btn_export_png)
        btn_layout.addWidget(self._btn_export_gcode)
        btn_layout.addWidget(self._btn_export_gcode_dxf)
        btn_layout.addStretch()

        layout.addLayout(btn_layout)

        # Status label for export feedback
        self._export_status = QLabel("")
        self._export_status.setStyleSheet(f"color: {COLORS['text_secondary']};")
        layout.addWidget(self._export_status)

        layout.addStretch()
        return panel

    def _make_export_button(self, text: str) -> QPushButton:
        """Create a styled export button."""
        btn = QPushButton(text)
        btn.setMinimumHeight(44)
        btn.setMinimumWidth(120)
        btn.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {COLORS['btn_primary']};"
            f"  color: {COLORS['text_primary']};"
            f"  border: none;"
            f"  border-radius: 4px;"
            f"  padding: 8px 16px;"
            f"  min-height: 44px;"
            f"  font-weight: bold;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background-color: {COLORS['btn_primary_hover']};"
            f"}}"
            f"QPushButton:disabled {{"
            f"  background-color: {COLORS['bg_surface']};"
            f"  color: {COLORS['text_disabled']};"
            f"}}"
        )
        return btn

    # ------------------------------------------------------------------
    # Signal Connections
    # ------------------------------------------------------------------

    def _connect_signals(self):
        """Wire up internal signals."""
        self._tab_widget.currentChanged.connect(self._on_tab_changed)

        # Export buttons
        self._btn_export_dxf.clicked.connect(lambda: self._on_export_clicked("dxf"))
        self._btn_export_svg.clicked.connect(lambda: self._on_export_clicked("svg"))
        self._btn_export_png.clicked.connect(lambda: self._on_export_clicked("png"))
        self._btn_export_gcode.clicked.connect(lambda: self._on_export_clicked("gcode"))
        self._btn_export_gcode_dxf.clicked.connect(lambda: self._on_export_clicked("gcode_dxf"))

    # ------------------------------------------------------------------
    # Event Handlers
    # ------------------------------------------------------------------

    def _on_tab_changed(self, index: int):
        """Sub-tab changed — lazy render if dirty."""
        if self._dirty[index]:
            self._render_panel(index)

    def _on_export_clicked(self, format_name: str):
        """Handle export button click — open file dialog and perform export."""
        if self._plan_result is None:
            QMessageBox.information(
                self, "No Data",
                "Generate a toolpath first before exporting."
            )
            return

        # File filter based on format
        filters = {
            "dxf": "DXF Files (*.dxf)",
            "svg": "SVG Files (*.svg)",
            "png": "PNG Files (*.png)",
            "gcode": "G-code Files (*.ngc *.nc *.gcode)",
            "gcode_dxf": "DXF Files (*.dxf)",
        }

        default_names = {
            "dxf": "toolpath.dxf",
            "svg": "toolpath.svg",
            "png": "toolpath.png",
            "gcode": "toolpath.ngc",
            "gcode_dxf": "gcode_roundtrip.dxf",
        }

        file_filter = filters.get(format_name, "All Files (*)")
        default_name = default_names.get(format_name, "export")

        path, _ = QFileDialog.getSaveFileName(
            self, f"Export {format_name.upper()}", default_name, file_filter
        )

        if not path:
            self._export_status.setText("Export cancelled.")
            return

        try:
            if format_name == "dxf":
                export_dxf(self._plan_result, path)
            elif format_name == "svg":
                export_svg(self._plan_result, path)
            elif format_name == "png":
                self._export_png(path)
            elif format_name == "gcode":
                gcode_text = GCodeWriter().write(self._plan_result, unit_mode=unit_state.mode.value)
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(gcode_text)
            elif format_name == "gcode_dxf":
                gcode_text = GCodeWriter().write(self._plan_result, unit_mode=unit_state.mode.value)
                export_from_gcode(gcode_text, path)

            self._export_status.setText(f"\u2713 Exported: {path}")
            self._export_status.setStyleSheet(
                f"color: {COLORS['status_ok']};"
            )
            self.export_requested.emit(format_name, path)

        except Exception as e:
            error_msg = str(e) if str(e) else type(e).__name__
            self._export_status.setText(f"\u2717 Export failed: {error_msg}")
            self._export_status.setStyleSheet(
                f"color: {COLORS['status_error']};"
            )
            QMessageBox.warning(
                self, "Export Error",
                f"Failed to export {format_name.upper()}:\n{error_msg}",
            )

    def _export_png(self, path: str):
        """Export the graph widget as a PNG screenshot.

        Grabs the graph from the parent window's program tab if available,
        otherwise raises an error.
        """
        # Walk up to MainWindow to access the program tab's graph widget
        from gui.main_window import MainWindow
        main_window = self.window()
        if isinstance(main_window, MainWindow):
            graph = main_window.program_tab.graph_widget
            pixmap = graph.grab()
            if not pixmap.save(path, "PNG"):
                raise IOError(f"Failed to save PNG to: {path}")
        else:
            raise RuntimeError("Cannot access graph widget for PNG export.")

    # ------------------------------------------------------------------
    # Lazy Rendering
    # ------------------------------------------------------------------

    def _render_current_panel(self):
        """Render the currently selected sub-tab."""
        index = self._tab_widget.currentIndex()
        self._render_panel(index)

    def _render_panel(self, index: int):
        """Render a specific panel by index. Marks it as clean after rendering."""
        renderers = [
            self._render_fibers,
            self._render_swept,
            self._render_heatmap,
            self._render_diagnostic,
            self._render_roundtrip,
            self._render_export,
        ]

        if self._plan_result is None:
            self._show_no_data(index)
            # Export panel needs special handling — disable buttons
            if index == 5:
                self._render_export()
            self._dirty[index] = False
            return

        if 0 <= index < len(renderers):
            renderers[index]()
            self._dirty[index] = False

    def _show_no_data_all(self):
        """Show 'no data' message on all text panels."""
        for i in range(6):
            self._show_no_data(i)

    def _show_no_data(self, index: int):
        """Show 'no data' message on a specific panel."""
        no_data_msg = "No data \u2014 generate a toolpath first"
        panels_with_text = [
            self._fibers_panel,
            self._swept_panel,
            None,  # Heatmap is a placeholder
            self._diagnostic_panel,
            self._roundtrip_panel,
            None,  # Export panel doesn't have a text edit
        ]
        panel = panels_with_text[index]
        if panel is not None and hasattr(panel, '_text_edit'):
            panel._text_edit.setPlainText(no_data_msg)

    # ------------------------------------------------------------------
    # Panel Renderers
    # ------------------------------------------------------------------

    def _render_fibers(self):
        """Render the Fibers panel — interval data at each X level."""
        pr = self._plan_result
        lines = []
        lines.append("=== Fiber Intervals (Roughing Pass X Levels) ===")
        lines.append("")

        if pr.roughing_passes:
            # Collect unique X levels from roughing passes
            seen_x = set()
            for p in pr.roughing_passes:
                x_level = p.x_level
                if x_level in seen_x:
                    continue
                seen_x.add(x_level)

                # Show Z intervals for this pass
                z_start = p.z_start
                z_end = p.z_end
                lines.append(f"X={x_level:.4f}: Z[{z_start:.4f} \u2192 {z_end:.4f}]")
        else:
            lines.append("No roughing passes in current plan.")

        # Also show face passes if present
        if pr.face_passes:
            lines.append("")
            lines.append("=== Face Pass Levels ===")
            lines.append("")
            for i, p in enumerate(pr.face_passes):
                lines.append(f"Face pass {i+1}: X={p.x_level:.4f}, Z[{p.z_start:.4f} \u2192 {p.z_end:.4f}]")

        self._fibers_panel._text_edit.setPlainText("\n".join(lines))

    def _render_swept(self):
        """Render the Swept panel — cumulative swept regions per pass."""
        pr = self._plan_result
        lines = []
        lines.append("=== Swept Regions (Material Removed Per Pass) ===")
        lines.append("")

        all_passes = []
        if pr.face_passes:
            all_passes.extend(("Face", p) for p in pr.face_passes)
        if pr.roughing_passes:
            all_passes.extend(("Rough", p) for p in pr.roughing_passes)
        if pr.cleanup_passes:
            all_passes.extend(("Cleanup", p) for p in pr.cleanup_passes)
        if pr.finish_passes:
            all_passes.extend(("Finish", p) for p in pr.finish_passes)

        if not all_passes:
            lines.append("No passes in current plan.")
        else:
            for label, p in all_passes:
                if p.swept_region is not None:
                    sr = p.swept_region
                    lines.append(
                        f"{label} pass {p.pass_index}: "
                        f"X[{sr.x_min:.4f} \u2192 {sr.x_max:.4f}], "
                        f"Z[{sr.z_start:.4f} \u2192 {sr.z_end:.4f}]"
                    )
                else:
                    lines.append(
                        f"{label} pass {p.pass_index}: "
                        f"X={p.x_level:.4f}, Z[{p.z_start:.4f} \u2192 {p.z_end:.4f}] "
                        f"(no swept region data)"
                    )

        self._swept_panel._text_edit.setPlainText("\n".join(lines))

    def _render_heatmap(self):
        """Render the Heatmap panel — placeholder, nothing to do."""
        pass  # Placeholder panel handles itself

    def _render_diagnostic(self):
        """Render the Diagnostic panel — structured text dump of PlanResult."""
        pr = self._plan_result
        lines = []
        lines.append("=== PlanResult Diagnostic ===")
        lines.append("")

        # Profile info
        lines.append(f"Profile segments:       {len(pr.profile.segments)}")
        lines.append(f"Machining mode:         {pr.mode.value.upper()}")
        lines.append("")

        # Stock info
        lines.append(f"Stock diameter:         {pr.stock.diameter:.4f} in (dia)")
        lines.append(f"Stock Z range:          {pr.stock.z_start:.4f} to {pr.stock.z_end:.4f} in")
        lines.append(f"Stock X start:          {pr.stock.x_start:.4f} in (dia)")
        lines.append("")

        # Tool info
        lines.append(f"Tool:                   T{pr.tool.tool_number} - {pr.tool.description}")
        lines.append(f"Nose radius:            {pr.tool.nose_radius:.4f} in")
        lines.append(f"Tip angle:              {pr.tool.tip_angle:.1f}\u00b0")
        lines.append("")

        # Pass counts
        lines.append("--- Pass Counts ---")
        lines.append(f"Face passes:            {len(pr.face_passes)}")
        lines.append(f"Roughing passes:        {len(pr.roughing_passes)}")
        lines.append(f"Cleanup passes:         {len(pr.cleanup_passes)}")
        lines.append(f"Finish passes:          {len(pr.finish_passes)}")
        lines.append(f"Total pass count:       {pr.pass_count}")
        lines.append("")

        # Move counts
        lines.append("--- Move Counts ---")
        lines.append(f"Total tool moves:       {pr.move_count}")
        lines.append(f"Tool moves (actual):    {len(pr.tool_moves)}")
        lines.append("")

        # Zone boundary vertex counts
        lines.append("--- Zone Boundary Vertices ---")
        lines.append(f"Finished part:          {len(pr.finished_part_boundary)} vertices")
        lines.append(f"Finish allowance:       {len(pr.finish_allowance_boundary)} vertices")
        lines.append(f"Material to rough:      {len(pr.material_to_rough_boundary)} vertices")
        lines.append(f"Stock boundary:         {len(pr.stock_boundary)} vertices")
        lines.append(f"Profile boundary:       {len(pr.profile_boundary)} vertices")
        lines.append("")

        # Validation results
        lines.append("--- Validation Results ---")
        if pr.validations:
            errors = [v for v in pr.validations if v.severity.value == "error"]
            warnings = [v for v in pr.validations if v.severity.value == "warning"]
            lines.append(f"Errors:                 {len(errors)}")
            lines.append(f"Warnings:               {len(warnings)}")
            lines.append(f"Warnings overridden:    {pr.warnings_overridden}")
            lines.append("")
            for v in pr.validations:
                prefix = "ERROR" if v.severity.value == "error" else "WARN"
                lines.append(f"  [{prefix}] {v.category}: {v.message}")
        else:
            lines.append("No validation issues.")
        lines.append("")

        # Generation time
        lines.append("--- Metadata ---")
        lines.append(f"Generation time:        {pr.generation_time_ms:.1f} ms")

        self._diagnostic_panel._text_edit.setPlainText("\n".join(lines))

    def _render_roundtrip(self):
        """Render the Round-Trip panel — G-code fidelity comparison."""
        pr = self._plan_result
        lines = []
        lines.append("=== G-code Round-Trip Fidelity Check ===")
        lines.append("")

        try:
            from outputs.gcode_writer import GCodeWriter
            from outputs.gcode_parser import parse as parse_gcode

            # Write G-code from PlanResult
            writer = GCodeWriter()
            gcode_text = writer.write(pr)

            # Parse it back
            parsed_moves = parse_gcode(gcode_text)

            # Compare
            original_count = len(pr.tool_moves)
            parsed_count = len(parsed_moves)

            lines.append(f"Original move count:    {original_count}")
            lines.append(f"Parsed move count:      {parsed_count}")
            lines.append(f"G-code lines:           {len(gcode_text.splitlines())}")
            lines.append("")

            if original_count == parsed_count:
                lines.append("\u2713 Move counts match — round-trip fidelity OK")
            else:
                diff = parsed_count - original_count
                direction = "more" if diff > 0 else "fewer"
                lines.append(
                    f"\u2717 DISCREPANCY: Parsed has {abs(diff)} {direction} moves "
                    f"than original"
                )
                lines.append("")
                lines.append("This may be due to:")
                lines.append("  - Transition moves added by the G-code writer")
                lines.append("  - Approach/retract moves not in tool_moves list")
                lines.append("  - Parser interpreting non-motion G-codes as moves")

            # Show first few discrepancies if any
            lines.append("")
            lines.append("--- Move Type Breakdown ---")
            from collections import Counter
            orig_types = Counter(m.move_type.value for m in pr.tool_moves)
            parsed_types = Counter(m.move_type.value for m in parsed_moves)

            all_types = sorted(set(list(orig_types.keys()) + list(parsed_types.keys())))
            lines.append(f"{'Type':<12} {'Original':<10} {'Parsed':<10}")
            lines.append("-" * 32)
            for mt in all_types:
                o = orig_types.get(mt, 0)
                p = parsed_types.get(mt, 0)
                marker = " \u2717" if o != p else ""
                lines.append(f"{mt:<12} {o:<10} {p:<10}{marker}")

        except Exception as e:
            lines.append(f"Round-trip check failed: {e}")

        self._roundtrip_panel._text_edit.setPlainText("\n".join(lines))

    def _render_export(self):
        """Render the Export panel — enable/disable buttons based on data."""
        has_data = self._plan_result is not None
        self._btn_export_dxf.setEnabled(has_data)
        self._btn_export_svg.setEnabled(has_data)
        self._btn_export_png.setEnabled(has_data)
        self._btn_export_gcode.setEnabled(has_data)
        self._btn_export_gcode_dxf.setEnabled(has_data)
        if has_data:
            self._export_status.setText("Ready to export.")
        else:
            self._export_status.setText("No data \u2014 generate a toolpath first.")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _mono_font(self) -> QFont:
        """Create the monospace font for text panels."""
        font = QFont(FONTS['mono_family'])
        font.setStyleHint(QFont.Monospace)
        font.setPointSize(FONTS['code_size'])
        # Set fallback
        if not font.exactMatch():
            font.setFamily(FONTS['fallback_mono'].split(",")[0].strip())
        return font

    def _tab_stylesheet(self) -> str:
        """Stylesheet for the sub-tab widget."""
        return (
            f"QTabWidget::pane {{"
            f"  background-color: {COLORS['bg_base']};"
            f"  border: none;"
            f"}}"
            f"QTabBar::tab {{"
            f"  background-color: {COLORS['bg_panel']};"
            f"  color: {COLORS['tab_inactive']};"
            f"  padding: 6px 14px;"
            f"  min-width: 50px;"
            f"  min-height: 36px;"
            f"  border: none;"
            f"  font-family: {FONTS['ui_family']}, {FONTS['fallback_sans']};"
            f"  font-size: {FONTS['ui_size']}pt;"
            f"}}"
            f"QTabBar::tab:selected {{"
            f"  background-color: {COLORS['bg_surface']};"
            f"  color: {COLORS['tab_active']};"
            f"  border-bottom: 2px solid {COLORS['tab_active']};"
            f"}}"
            f"QTabBar::tab:hover {{"
            f"  color: {COLORS['text_primary']};"
            f"}}"
        )
