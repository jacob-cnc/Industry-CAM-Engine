"""Unit tests for G-code writer output of decomposed quadrant arc moves.

Verifies that ToolMoves produced by the finish planner's edge decomposition
(simulating quadrant arc segments) are emitted as standard G2/G3 with endpoint
(X, Z) and incremental center offsets (I, K) — identical format to regular arcs.

Validates Requirements: 8.1, 8.2, 8.3
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


def _make_plan_with_finish_arcs(arc_moves: list[ToolMove]) -> PlanResult:
    """Create a PlanResult with decomposed quadrant arc moves in the finish pass.

    This simulates what the finish planner produces after decomposing an
    elliptical/spline quadrant arc edge into multiple circular arc sub-segments.
    """
    profile = ClosedProfile(
        segments=[
            ProfileMove(SegmentType.LINE, x=2.0, z=0.0),
            ProfileMove(SegmentType.LINE, x=1.0, z=-1.0),
        ],
        corner_breaks=[None],
        mode=MachiningMode.OD,
        z_start=0.0,
        z_end=-1.0,
    )
    stock = StockDef(
        diameter=2.5,
        x_start=2.0,
        z_start=0.1,
        z_end=-1.0,
        mode=MachiningMode.OD,
        x_park=3.0,
        z_park=3.0,
    )
    tool = ToolDef(
        tool_number=1,
        nose_radius=0.0,
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

    finish_pass = TurningPass(
        x_level=2.0,
        z_start=0.0,
        z_end=-1.0,
        pass_index=0,
        pass_type=PassType.FINISH,
        moves=arc_moves,
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
        tool_moves=arc_moves,
        finished_part_boundary=[],
        finish_allowance_boundary=[],
        material_to_rough_boundary=[],
        stock_boundary=[],
        profile_boundary=[],
        validations=[],
    )


class TestGCodeWriterQuadrantArcOutput:
    """Verify G-code writer emits decomposed quadrant arc moves as standard G2/G3.

    The finish planner decomposes non-circular edges (elliptical arcs, splines)
    into sequences of ToolMove objects with move_type=ARC_CW or ARC_CCW.
    The G-code writer should handle these identically to regular circular arcs.
    """

    def test_single_cw_arc_emits_g02(self):
        """A single CW arc ToolMove (from decomposition) emits G02 X Z I K.

        **Validates: Requirements 8.1, 8.2, 8.3**
        """
        arc = ToolMove(
            move_type=MoveType.ARC_CW,
            x=1.8,
            z=-0.3,
            feed=0.003,
            center_i=0.0,
            center_k=-0.3,
            pass_type=PassType.FINISH,
        )
        pr = _make_plan_with_finish_arcs([arc])
        writer = GCodeWriter()
        output = writer.write(pr, unit_mode="inch")

        # Find the G02 line
        g02_lines = [l for l in output.split('\n') if 'G02' in l]
        assert len(g02_lines) == 1, f"Expected exactly one G02 line, got {len(g02_lines)}"

        line = g02_lines[0]
        # Verify X, Z, I, K are all present
        assert re.search(r'X1\.8000', line), f"Missing X1.8000 in: {line}"
        assert re.search(r'Z-0\.3000', line), f"Missing Z-0.3000 in: {line}"
        assert re.search(r'I0\.0000', line), f"Missing I0.0000 in: {line}"
        assert re.search(r'K-0\.3000', line), f"Missing K-0.3000 in: {line}"

    def test_single_ccw_arc_emits_g03(self):
        """A single CCW arc ToolMove (from decomposition) emits G03 X Z I K.

        **Validates: Requirements 8.1, 8.2, 8.3**
        """
        arc = ToolMove(
            move_type=MoveType.ARC_CCW,
            x=1.6,
            z=-0.5,
            feed=0.003,
            center_i=-0.2,
            center_k=-0.25,
            pass_type=PassType.FINISH,
        )
        pr = _make_plan_with_finish_arcs([arc])
        writer = GCodeWriter()
        output = writer.write(pr, unit_mode="inch")

        # Find the G03 line
        g03_lines = [l for l in output.split('\n') if 'G03' in l]
        assert len(g03_lines) == 1, f"Expected exactly one G03 line, got {len(g03_lines)}"

        line = g03_lines[0]
        assert re.search(r'X1\.6000', line), f"Missing X1.6000 in: {line}"
        assert re.search(r'Z-0\.5000', line), f"Missing Z-0.5000 in: {line}"
        assert re.search(r'I-0\.2000', line), f"Missing I-0.2000 in: {line}"
        assert re.search(r'K-0\.2500', line), f"Missing K-0.2500 in: {line}"

    def test_multiple_arcs_simulate_quadrant_decomposition(self):
        """Multiple arc ToolMoves (simulating a decomposed quarter-ellipse) emit G2/G3 sequence.

        This mimics the finish planner decomposing a quadrant arc into 3 sub-arcs.
        Each should emit its own G02/G03 line with X, Z, I, K.

        **Validates: Requirements 8.1, 8.2, 8.3**
        """
        # Simulate 3 CW arcs approximating a convex quadrant arc from (2.0, 0.0) to (1.0, -1.0)
        arcs = [
            ToolMove(
                move_type=MoveType.ARC_CW,
                x=1.85,
                z=-0.35,
                feed=0.003,
                center_i=-0.05,
                center_k=-0.38,
                pass_type=PassType.FINISH,
            ),
            ToolMove(
                move_type=MoveType.ARC_CW,
                x=1.45,
                z=-0.72,
                feed=0.003,
                center_i=-0.32,
                center_k=-0.28,
                pass_type=PassType.FINISH,
            ),
            ToolMove(
                move_type=MoveType.ARC_CW,
                x=1.0,
                z=-1.0,
                feed=0.003,
                center_i=-0.40,
                center_k=-0.15,
                pass_type=PassType.FINISH,
            ),
        ]
        pr = _make_plan_with_finish_arcs(arcs)
        writer = GCodeWriter()
        output = writer.write(pr, unit_mode="inch")

        # Should have exactly 3 G02 lines
        g02_lines = [l for l in output.split('\n') if 'G02' in l]
        assert len(g02_lines) == 3, f"Expected 3 G02 lines, got {len(g02_lines)}"

        # Each G02 line must have X, Z, I, K
        for line in g02_lines:
            assert re.search(r'X-?\d+\.\d{4}', line), f"Missing X in: {line}"
            assert re.search(r'Z-?\d+\.\d{4}', line), f"Missing Z in: {line}"
            assert re.search(r'I-?\d+\.\d{4}', line), f"Missing I in: {line}"
            assert re.search(r'K-?\d+\.\d{4}', line), f"Missing K in: {line}"

        # No G05/G06.1 or other non-standard ellipse codes
        assert 'G05' not in output
        assert 'G06' not in output
        assert 'G6.1' not in output

    def test_no_special_gcode_for_quadrant_arcs(self):
        """No native ellipse or spline G-codes are emitted — only G2/G3.

        **Validates: Requirement 8.1**
        """
        arcs = [
            ToolMove(
                move_type=MoveType.ARC_CCW,
                x=1.5,
                z=-0.5,
                feed=0.003,
                center_i=0.1,
                center_k=-0.5,
                pass_type=PassType.FINISH,
            ),
            ToolMove(
                move_type=MoveType.ARC_CCW,
                x=1.0,
                z=-1.0,
                feed=0.003,
                center_i=0.3,
                center_k=-0.3,
                pass_type=PassType.FINISH,
            ),
        ]
        pr = _make_plan_with_finish_arcs(arcs)
        writer = GCodeWriter()
        output = writer.write(pr, unit_mode="inch")

        # Only G00, G01, G02, G03 motion codes should appear (plus setup codes)
        motion_codes = re.findall(r'G0[4-9]|G[1-9]\d', output)
        allowed_high = {'G18', 'G20', 'G21', 'G40', 'G41', 'G42', 'G43',
                        'G49', 'G80', 'G90', 'G95'}
        for code in motion_codes:
            assert code in allowed_high, (
                f"Unexpected G-code '{code}' found — should be standard G2/G3 only"
            )

    def test_arc_format_matches_regular_arcs(self):
        """Decomposed quadrant arc output format is identical to a regular arc.

        **Validates: Requirement 8.3**
        """
        # Regular arc (as if from a circular profile segment)
        regular_arc = ToolMove(
            move_type=MoveType.ARC_CW,
            x=1.5,
            z=-0.5,
            feed=0.003,
            radius=0.25,
            center_i=0.0,
            center_k=-0.25,
            pass_type=PassType.FINISH,
        )
        # Decomposed quadrant arc (same geometry as sub-arc)
        quadrant_arc = ToolMove(
            move_type=MoveType.ARC_CW,
            x=1.5,
            z=-0.5,
            feed=0.003,
            radius=0.0,  # Decomposed arcs may not have radius set
            center_i=0.0,
            center_k=-0.25,
            pass_type=PassType.FINISH,
        )

        writer = GCodeWriter()

        # Generate output for each
        pr_regular = _make_plan_with_finish_arcs([regular_arc])
        pr_quadrant = _make_plan_with_finish_arcs([quadrant_arc])

        out_regular = writer.write(pr_regular, unit_mode="inch")
        out_quadrant = writer.write(pr_quadrant, unit_mode="inch")

        # Extract the G02 lines from each
        g02_regular = [l for l in out_regular.split('\n') if 'G02' in l]
        g02_quadrant = [l for l in out_quadrant.split('\n') if 'G02' in l]

        assert len(g02_regular) == 1
        assert len(g02_quadrant) == 1

        # Both should have identical G-code content (before the comment)
        def extract_gcode_part(line):
            """Extract just the G-code part (N## G02 X... Z... I... K... F...)."""
            if ';' in line:
                return line.split(';')[0].strip()
            return line.strip()

        regular_gcode = extract_gcode_part(g02_regular[0])
        quadrant_gcode = extract_gcode_part(g02_quadrant[0])

        # Strip N-numbers for comparison (they differ due to line sequencing)
        regular_body = re.sub(r'^N\d+\s+', '', regular_gcode)
        quadrant_body = re.sub(r'^N\d+\s+', '', quadrant_gcode)

        assert regular_body == quadrant_body, (
            f"Regular arc: '{regular_body}'\n"
            f"Quadrant arc: '{quadrant_body}'\n"
            "Format should be identical — no special handling for decomposed arcs."
        )

    def test_feed_emitted_on_first_arc_only(self):
        """Feed rate F is emitted only when it changes (standard modal behavior).

        **Validates: Requirement 8.2**
        """
        arcs = [
            ToolMove(
                move_type=MoveType.ARC_CW,
                x=1.8,
                z=-0.3,
                feed=0.003,
                center_i=0.0,
                center_k=-0.3,
                pass_type=PassType.FINISH,
            ),
            ToolMove(
                move_type=MoveType.ARC_CW,
                x=1.5,
                z=-0.7,
                feed=0.003,
                center_i=-0.1,
                center_k=-0.2,
                pass_type=PassType.FINISH,
            ),
        ]
        pr = _make_plan_with_finish_arcs(arcs)
        writer = GCodeWriter()
        output = writer.write(pr, unit_mode="inch")

        g02_lines = [l for l in output.split('\n') if 'G02' in l]
        assert len(g02_lines) == 2

        # First arc should have F word (feed not yet set)
        assert 'F0.0030' in g02_lines[0]
        # Second arc has same feed — F should be suppressed (modal)
        assert 'F' not in g02_lines[1].split(';')[0].split('K')[1], (
            "Feed should be modal — not repeated on subsequent arcs with same feed"
        )

    def test_metric_mode_scales_quadrant_arc_output(self):
        """Metric mode correctly scales all arc coordinates by 25.4.

        **Validates: Requirement 8.2**
        """
        arc = ToolMove(
            move_type=MoveType.ARC_CW,
            x=2.0,
            z=-0.5,
            feed=0.003,
            center_i=0.1,
            center_k=-0.25,
            pass_type=PassType.FINISH,
        )
        pr = _make_plan_with_finish_arcs([arc])
        writer = GCodeWriter()
        output = writer.write(pr, unit_mode="metric")

        g02_lines = [l for l in output.split('\n') if 'G02' in l]
        assert len(g02_lines) == 1

        line = g02_lines[0]
        # X: 2.0 * 25.4 = 50.800
        assert 'X50.800' in line
        # Z: -0.5 * 25.4 = -12.700
        assert 'Z-12.700' in line
        # I: 0.1 * 25.4 = 2.540
        assert 'I2.540' in line
        # K: -0.25 * 25.4 = -6.350
        assert 'K-6.350' in line
