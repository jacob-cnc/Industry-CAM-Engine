"""Unit tests for gui/debug_tab.py — DebugTab."""

import pytest
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

from gui.debug_tab import DebugTab
from models.results import PlanResult, TurningPass, SweptRegion
from models.moves import ToolMove, MoveType, PassType
from models.profile import ClosedProfile, ProfileMove, SegmentType, MachiningMode
from models.stock import StockDef
from models.tool import ToolDef, ToolOrientation, ToolDirection, ToolType
from models.params import RoughingParams, FinishingParams, RoughingStrategy

# QApplication must exist before creating any QWidget
_app = QApplication.instance() or QApplication([])


def _make_plan_result() -> PlanResult:
    """Create a minimal PlanResult for testing."""
    profile = ClosedProfile(
        segments=[
            ProfileMove(segment_type=SegmentType.LINE, x=2.0, z=0.0),
            ProfileMove(segment_type=SegmentType.LINE, x=2.0, z=-1.0),
        ],
        corner_breaks=[None],
        mode=MachiningMode.OD,
        z_start=0.0,
        z_end=-1.0,
    )
    stock = StockDef(
        diameter=2.5,
        z_start=0.1,
        z_end=-1.1,
        x_start=0.0,
        mode=MachiningMode.OD,
    )
    tool = ToolDef(
        tool_number=1,
        nose_radius=0.016,
        tip_angle=55.0,
        edge_length=0.5,
        orientation=ToolOrientation.OD_FRONT_RIGHT,
        direction=ToolDirection.RIGHT,
        tool_type=ToolType.TURNING,
        description="DNMG 55deg",
    )
    roughing_params = RoughingParams(
        doc_dia=0.050,
        feed=0.008,
        strategy=RoughingStrategy.STAIRCASE,
        fin_allowance=0.005,
        spindle_rpm=1200.0,
    )
    finishing_params = FinishingParams(passes=1, doc_dia=0.002, feed=0.003)

    # Create some test moves
    moves = [
        ToolMove(move_type=MoveType.RAPID, x=2.5, z=0.1),
        ToolMove(move_type=MoveType.FEED, x=2.45, z=0.0, feed=0.008),
        ToolMove(move_type=MoveType.FEED, x=2.45, z=-1.0, feed=0.008),
    ]

    roughing_pass = TurningPass(
        x_level=2.45,
        z_start=0.0,
        z_end=-1.0,
        pass_index=1,
        pass_type=PassType.ROUGH,
        moves=moves[1:],
        swept_region=SweptRegion(x_min=2.45, x_max=2.5, z_start=0.0, z_end=-1.0),
    )

    return PlanResult(
        profile=profile,
        stock=stock,
        tool=tool,
        roughing_params=roughing_params,
        finishing_params=finishing_params,
        mode=MachiningMode.OD,
        face_passes=[],
        roughing_passes=[roughing_pass],
        cleanup_passes=[],
        finish_passes=[],
        tool_moves=moves,
        finished_part_boundary=[(1.0, 0.0), (1.0, -1.0), (0.0, -1.0), (0.0, 0.0)],
        finish_allowance_boundary=[(1.005, 0.0), (1.005, -1.0)],
        material_to_rough_boundary=[(1.25, 0.0), (1.25, -1.0)],
        stock_boundary=[(1.25, 0.1), (1.25, -1.1), (0.0, -1.1), (0.0, 0.1)],
        profile_boundary=[(1.0, 0.0), (1.0, -1.0)],
        validations=[],
        generation_time_ms=42.5,
        pass_count=1,
        move_count=3,
    )


class TestDebugTabCreation:
    """Tests for DebugTab instantiation."""

    def test_creates_without_error(self):
        tab = DebugTab()
        assert tab is not None

    def test_has_six_sub_tabs(self):
        tab = DebugTab()
        assert tab._tab_widget.count() == 6

    def test_sub_tab_names(self):
        tab = DebugTab()
        names = [tab._tab_widget.tabText(i) for i in range(6)]
        assert names == ["Fibers", "Swept", "Heatmap", "Diagnostic", "Round-Trip", "Export"]

    def test_initial_state_shows_no_data(self):
        tab = DebugTab()
        text = tab._fibers_panel._text_edit.toPlainText()
        assert "No data" in text

    def test_export_signal_exists(self):
        tab = DebugTab()
        # Signal should be connectable
        received = []
        tab.export_requested.connect(lambda fmt, path: received.append((fmt, path)))
        # Emit manually to verify signal works
        tab.export_requested.emit("dxf", "/tmp/test.dxf")
        assert received == [("dxf", "/tmp/test.dxf")]


class TestDebugTabUpdatePanels:
    """Tests for update_panels() and lazy rendering."""

    def test_update_panels_stores_plan_result(self):
        tab = DebugTab()
        pr = _make_plan_result()
        tab.update_panels(pr)
        assert tab._plan_result is pr

    def test_update_panels_marks_all_dirty(self):
        tab = DebugTab()
        pr = _make_plan_result()
        # First update cleans current panel
        tab.update_panels(pr)
        # Current panel (index 0) should be clean, others dirty
        assert tab._dirty[0] is False
        # Others should still be dirty (lazy)
        assert tab._dirty[1] is True
        assert tab._dirty[2] is True
        assert tab._dirty[3] is True
        assert tab._dirty[4] is True
        assert tab._dirty[5] is True

    def test_switching_tab_renders_panel(self):
        tab = DebugTab()
        pr = _make_plan_result()
        tab.update_panels(pr)

        # Switch to Diagnostic tab (index 3)
        tab._tab_widget.setCurrentIndex(3)
        assert tab._dirty[3] is False

        # Diagnostic panel should have content
        text = tab._diagnostic_panel._text_edit.toPlainText()
        assert "PlanResult Diagnostic" in text

    def test_fibers_panel_shows_x_levels(self):
        tab = DebugTab()
        pr = _make_plan_result()
        tab.update_panels(pr)

        text = tab._fibers_panel._text_edit.toPlainText()
        assert "X=2.4500" in text
        assert "\u2192" in text  # Arrow character

    def test_swept_panel_shows_regions(self):
        tab = DebugTab()
        pr = _make_plan_result()
        tab.update_panels(pr)

        # Switch to Swept tab
        tab._tab_widget.setCurrentIndex(1)
        text = tab._swept_panel._text_edit.toPlainText()
        assert "Swept Regions" in text
        assert "Rough pass 1" in text

    def test_diagnostic_panel_shows_metadata(self):
        tab = DebugTab()
        pr = _make_plan_result()
        tab.update_panels(pr)

        # Switch to Diagnostic tab
        tab._tab_widget.setCurrentIndex(3)
        text = tab._diagnostic_panel._text_edit.toPlainText()
        assert "42.5 ms" in text
        assert "Profile segments" in text
        assert "2" in text  # 2 segments
        assert "OD" in text

    def test_roundtrip_panel_shows_comparison(self):
        tab = DebugTab()
        pr = _make_plan_result()
        tab.update_panels(pr)

        # Switch to Round-Trip tab
        tab._tab_widget.setCurrentIndex(4)
        text = tab._roundtrip_panel._text_edit.toPlainText()
        assert "Round-Trip" in text
        assert "Original move count" in text

    def test_no_plan_result_shows_no_data(self):
        tab = DebugTab()
        # Switch tabs without setting plan result
        tab._tab_widget.setCurrentIndex(3)
        text = tab._diagnostic_panel._text_edit.toPlainText()
        assert "No data" in text


class TestDebugTabExportPanel:
    """Tests for the Export panel."""

    def test_export_buttons_exist(self):
        tab = DebugTab()
        assert tab._btn_export_dxf is not None
        assert tab._btn_export_svg is not None
        assert tab._btn_export_png is not None
        assert tab._btn_export_gcode_dxf is not None

    def test_export_buttons_disabled_without_data(self):
        tab = DebugTab()
        # Switch to export tab to trigger render
        tab._tab_widget.setCurrentIndex(5)
        # Buttons should be disabled (no plan result)
        # Note: render_export is called which disables them
        assert tab._btn_export_dxf.isEnabled() is False

    def test_export_buttons_enabled_with_data(self):
        tab = DebugTab()
        pr = _make_plan_result()
        tab.update_panels(pr)

        # Switch to export tab
        tab._tab_widget.setCurrentIndex(5)
        assert tab._btn_export_dxf.isEnabled() is True
        assert tab._btn_export_svg.isEnabled() is True
        assert tab._btn_export_png.isEnabled() is True
        assert tab._btn_export_gcode_dxf.isEnabled() is True
