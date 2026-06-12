"""Unit tests for GCodeWriter unit_mode parameter.

Tests the metric/inch toggle behavior in G-code output:
- G20/G21 preamble selection
- Coordinate and feed value scaling (×25.4 for metric)
- Decimal place formatting (4dp inch, 3dp metric)
- ValueError for invalid unit_mode strings
"""

import re
import pytest

from models.profile import ClosedProfile, ProfileMove, SegmentType, MachiningMode
from models.stock import StockDef
from models.tool import ToolDef, ToolOrientation, ToolDirection
from models.params import RoughingParams, FinishingParams, RoughingStrategy
from models.moves import ToolMove, MoveType, PassType
from models.results import PlanResult, TurningPass
from outputs.gcode_writer import GCodeWriter


def _make_simple_plan_result():
    """Create a minimal PlanResult for testing GCodeWriter."""
    profile = ClosedProfile(
        segments=[
            ProfileMove(SegmentType.LINE, x=1.0, z=0.0),
            ProfileMove(SegmentType.LINE, x=1.0, z=-1.0),
        ],
        corner_breaks=[None],
        mode=MachiningMode.OD,
        z_start=0.0,
        z_end=-1.0,
    )
    stock = StockDef(
        diameter=2.0,
        x_start=1.0,
        z_start=0.1,
        z_end=-1.0,
        mode=MachiningMode.OD,
        x_park=3.0,
        z_park=3.0,
    )
    tool = ToolDef(
        tool_number=1,
        nose_radius=0.0156,
        tip_angle=55.0,
        edge_length=0.5,
        orientation=ToolOrientation.OD_FRONT_RIGHT,
        direction=ToolDirection.RIGHT,
        description="DNMG 55deg",
    )
    roughing = RoughingParams(
        doc_dia=0.050,
        feed=0.008,
        strategy=RoughingStrategy.STAIRCASE,
        fin_allowance=0.005,
        spindle_rpm=1200.0,
    )
    finishing = FinishingParams(feed=0.003)

    # Create a simple roughing pass with one feed move
    rough_move = ToolMove(
        move_type=MoveType.FEED,
        x=1.95,
        z=-1.0,
        feed=0.008,
        pass_type=PassType.ROUGH,
    )
    rough_pass = TurningPass(
        x_level=1.95,
        z_start=0.1,
        z_end=-1.0,
        pass_index=0,
        pass_type=PassType.ROUGH,
        moves=[rough_move],
    )

    return PlanResult(
        profile=profile,
        stock=stock,
        tool=tool,
        roughing_params=roughing,
        finishing_params=finishing,
        mode=MachiningMode.OD,
        face_passes=[],
        roughing_passes=[rough_pass],
        cleanup_passes=[],
        finish_passes=[],
        tool_moves=[rough_move],
        finished_part_boundary=[],
        finish_allowance_boundary=[],
        material_to_rough_boundary=[],
        stock_boundary=[],
        profile_boundary=[],
        validations=[],
    )


def _make_arc_plan_result():
    """Create a PlanResult with an arc move for testing I/K conversion."""
    profile = ClosedProfile(
        segments=[
            ProfileMove(SegmentType.LINE, x=1.0, z=0.0),
            ProfileMove(SegmentType.ARC, x=1.0, z=-0.5, radius=0.25),
        ],
        corner_breaks=[None],
        mode=MachiningMode.OD,
        z_start=0.0,
        z_end=-0.5,
    )
    stock = StockDef(
        diameter=2.0,
        x_start=1.0,
        z_start=0.1,
        z_end=-0.5,
        mode=MachiningMode.OD,
        x_park=3.0,
        z_park=3.0,
    )
    tool = ToolDef(
        tool_number=1,
        nose_radius=0.0156,
        tip_angle=55.0,
        edge_length=0.5,
        orientation=ToolOrientation.OD_FRONT_RIGHT,
        direction=ToolDirection.RIGHT,
        description="DNMG 55deg",
    )
    roughing = RoughingParams(
        doc_dia=0.050,
        feed=0.008,
        strategy=RoughingStrategy.STAIRCASE,
        fin_allowance=0.005,
        spindle_rpm=1200.0,
    )
    finishing = FinishingParams(feed=0.003)

    # Arc move with I/K offsets
    arc_move = ToolMove(
        move_type=MoveType.ARC_CW,
        x=1.5,
        z=-0.5,
        feed=0.003,
        radius=0.25,
        center_i=0.25,
        center_k=-0.25,
        pass_type=PassType.FINISH,
    )
    finish_pass = TurningPass(
        x_level=1.0,
        z_start=0.0,
        z_end=-0.5,
        pass_index=0,
        pass_type=PassType.FINISH,
        moves=[arc_move],
    )

    return PlanResult(
        profile=profile,
        stock=stock,
        tool=tool,
        roughing_params=roughing,
        finishing_params=finishing,
        mode=MachiningMode.OD,
        face_passes=[],
        roughing_passes=[],
        cleanup_passes=[],
        finish_passes=[finish_pass],
        tool_moves=[arc_move],
        finished_part_boundary=[],
        finish_allowance_boundary=[],
        material_to_rough_boundary=[],
        stock_boundary=[],
        profile_boundary=[],
        validations=[],
    )


class TestGCodeWriterUnitMode:
    """Tests for GCodeWriter.write() unit_mode parameter."""

    def test_default_mode_is_inch(self):
        """Default unit_mode emits G20."""
        writer = GCodeWriter()
        pr = _make_simple_plan_result()
        output = writer.write(pr)
        assert "G20" in output
        assert "G21" not in output

    def test_inch_mode_emits_g20(self):
        """Explicit inch mode emits G20."""
        writer = GCodeWriter()
        pr = _make_simple_plan_result()
        output = writer.write(pr, unit_mode="inch")
        assert "G20" in output
        assert "G21" not in output

    def test_metric_mode_emits_g21(self):
        """Metric mode emits G21 instead of G20."""
        writer = GCodeWriter()
        pr = _make_simple_plan_result()
        output = writer.write(pr, unit_mode="metric")
        assert "G21" in output
        assert "G20" not in output

    def test_invalid_unit_mode_raises_valueerror(self):
        """Invalid unit_mode raises ValueError."""
        writer = GCodeWriter()
        pr = _make_simple_plan_result()
        with pytest.raises(ValueError, match="Invalid unit_mode"):
            writer.write(pr, unit_mode="millimeter")

    def test_invalid_unit_mode_empty_string(self):
        """Empty string unit_mode raises ValueError."""
        writer = GCodeWriter()
        pr = _make_simple_plan_result()
        with pytest.raises(ValueError):
            writer.write(pr, unit_mode="")

    def test_metric_coordinates_scaled_by_25_4(self):
        """Metric mode multiplies X, Z coordinates by 25.4."""
        writer = GCodeWriter()
        pr = _make_simple_plan_result()

        inch_output = writer.write(pr, unit_mode="inch")
        metric_output = writer.write(pr, unit_mode="metric")

        # Parse a known coordinate from the roughing pass feed move
        # The rough move goes to X1.9500 Z-1.0000 in inch mode
        assert "X1.9500" in inch_output
        assert "Z-1.0000" in inch_output

        # In metric: 1.95 * 25.4 = 49.530, -1.0 * 25.4 = -25.400
        assert "X49.530" in metric_output
        assert "Z-25.400" in metric_output

    def test_metric_feed_scaled_by_25_4(self):
        """Metric mode multiplies F values by 25.4."""
        writer = GCodeWriter()
        pr = _make_simple_plan_result()

        inch_output = writer.write(pr, unit_mode="inch")
        metric_output = writer.write(pr, unit_mode="metric")

        # Feed 0.008 in inch mode
        assert "F0.0080" in inch_output

        # In metric: 0.008 * 25.4 = 0.2032 → formatted as .3f = 0.203
        assert "F0.203" in metric_output

    def test_inch_mode_4_decimal_places(self):
        """Inch mode formats coordinates with 4 decimal places."""
        writer = GCodeWriter()
        pr = _make_simple_plan_result()
        output = writer.write(pr, unit_mode="inch")

        # Find G-code coordinate values (before the comment semicolon)
        found_any = False
        for line in output.split('\n'):
            if ';' in line:
                gcode_part = line.split(';')[0]
            else:
                gcode_part = line
            coord_pattern = re.compile(r'(?<=[XZIKF])(-?\d+\.\d+)')
            matches = coord_pattern.findall(gcode_part)
            for val in matches:
                found_any = True
                decimal_part = val.split('.')[1]
                assert len(decimal_part) == 4, f"Expected 4 decimals, got '{val}' in line: {line.strip()}"
        assert found_any, "No coordinate values found in output"

    def test_metric_mode_3_decimal_places(self):
        """Metric mode formats coordinates with 3 decimal places."""
        writer = GCodeWriter()
        pr = _make_simple_plan_result()
        output = writer.write(pr, unit_mode="metric")

        # Find G-code coordinate values (before the comment semicolon)
        # Match X, Z, I, K, F followed by a number in the G-code portion
        for line in output.split('\n'):
            if ';' in line:
                gcode_part = line.split(';')[0]
            else:
                gcode_part = line
            # Match coordinate words in the G-code portion only
            coord_pattern = re.compile(r'(?<=[XZIKF])(-?\d+\.\d+)')
            matches = coord_pattern.findall(gcode_part)
            for val in matches:
                decimal_part = val.split('.')[1]
                assert len(decimal_part) == 3, f"Expected 3 decimals, got '{val}' in line: {line.strip()}"

    def test_metric_arc_ik_scaled(self):
        """Metric mode multiplies I and K arc center offsets by 25.4."""
        writer = GCodeWriter()
        pr = _make_arc_plan_result()

        inch_output = writer.write(pr, unit_mode="inch")
        metric_output = writer.write(pr, unit_mode="metric")

        # Arc move has center_i=0.25, center_k=-0.25
        assert "I0.2500" in inch_output
        assert "K-0.2500" in inch_output

        # In metric: 0.25 * 25.4 = 6.350, -0.25 * 25.4 = -6.350
        assert "I6.350" in metric_output
        assert "K-6.350" in metric_output

    def test_metric_preamble_comment_says_mm(self):
        """Metric mode safety line comment says 'mm' not 'inch'."""
        writer = GCodeWriter()
        pr = _make_simple_plan_result()
        output = writer.write(pr, unit_mode="metric")
        assert "Safety line - mm" in output

    def test_inch_preamble_comment_says_inch(self):
        """Inch mode safety line comment says 'inch'."""
        writer = GCodeWriter()
        pr = _make_simple_plan_result()
        output = writer.write(pr, unit_mode="inch")
        assert "Safety line - inch" in output

    def test_park_position_scaled_in_metric(self):
        """Park position (X3.0, Z3.0) is scaled in metric mode."""
        writer = GCodeWriter()
        pr = _make_simple_plan_result()
        output = writer.write(pr, unit_mode="metric")

        # Park is X3.0, Z3.0 in inches → X76.200, Z76.200 in mm
        assert "X76.200" in output
        assert "Z76.200" in output
