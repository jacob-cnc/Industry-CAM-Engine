"""Integration test: Full pipeline with Q arc segments.

Exercises the complete pipeline from profile definition through to G-code output
for quadrant arc ("Q" and "-Q") segments. Verifies:
- No gouge errors from Shapely validator (post-planning validation passes)
- Finish pass traces the correct contour with arc moves
- G-code contains G2/G3 moves approximating the quadrant arc
- Both axis-aligned and off-axis cases work end-to-end

Q / -Q is a TRUE CIRCULAR quarter since 2026-11-11 (ellipses retired by the
owner; geometry/arc_entry.py):
a. Same-X +Q / -Q → two quadrants through the apex (bead / groove)
b. Off-axis Q with equal legs → one circular arc about the bounding-box corner
c. Unequal legs or same-Z → refused, with valid end points offered

Validates Requirements: 1.1-1.3, 2.1-2.4, 3.1-3.4, 4.1-4.4, 5.1-5.3,
                        6.1-6.4, 7.1-7.4, 8.1-8.3
"""

import re
import pytest

from models.profile import ClosedProfile, ProfileMove, SegmentType, MachiningMode
from models.stock import StockDef
from models.tool import ToolDef, ToolOrientation, ToolDirection
from models.params import RoughingParams, FinishingParams, RoughingStrategy
from models.moves import MoveType, PassType
from models.validation import PipelineStatus, Severity
from pipeline.pipeline import execute
from outputs.gcode_writer import GCodeWriter


# --- Fixtures / Helpers ---

def _od_tool() -> ToolDef:
    """Standard OD turning tool for integration tests."""
    return ToolDef(
        tool_number=1,
        nose_radius=0.016,
        tip_angle=55.0,
        edge_length=0.5,
        orientation=ToolOrientation.OD_FRONT_RIGHT,
        direction=ToolDirection.RIGHT,
        description="DNMG 55deg test",
    )


def _standard_roughing() -> RoughingParams:
    """Standard roughing parameters for integration tests."""
    return RoughingParams(
        doc_dia=0.050,
        feed=0.008,
        strategy=RoughingStrategy.STAIRCASE,
        fin_allowance=0.010,
        spindle_rpm=1200.0,
    )


def _standard_finishing() -> FinishingParams:
    """Standard finishing parameters for integration tests."""
    return FinishingParams(passes=1, doc_dia=0.002, feed=0.003)


def _run_pipeline(profile: ClosedProfile, stock: StockDef):
    """Execute the full pipeline and return PipelineResult."""
    tool = _od_tool()
    roughing = _standard_roughing()
    finishing = _standard_finishing()
    return execute(profile, stock, tool, roughing, finishing)


def _generate_gcode(pipeline_result) -> str:
    """Generate G-code from a successful pipeline result."""
    assert pipeline_result.plan_result is not None, (
        f"Pipeline failed: {pipeline_result.status}, "
        f"errors: {[v.message for v in pipeline_result.validations if v.severity == Severity.ERROR]}"
    )
    writer = GCodeWriter()
    return writer.write(pipeline_result.plan_result, unit_mode="inch")


def _count_arc_moves(gcode: str) -> int:
    """Count number of G02/G03 moves in G-code output."""
    return len(re.findall(r'\bG0[23]\b', gcode))


def _get_finish_pass_arc_moves(pipeline_result):
    """Extract arc moves from the finish pass(es)."""
    arcs = []
    for fp in pipeline_result.plan_result.finish_passes:
        for move in fp.moves:
            if move.move_type in (MoveType.ARC_CW, MoveType.ARC_CCW):
                arcs.append(move)
    return arcs


# --- Test: Axis-Aligned +Q (same X, vertical chord) ---

class TestAxisAlignedConvexQ:
    """Axis-aligned +Q arc: start and end share same X coordinate.

    Profile: straight OD at X=1.5" dia, then a convex quadrant arc dropping
    from Z=-0.5 to Z=-1.0 (same X=1.5 dia → vertical chord → circular arc).
    """

    def _make_profile_and_stock(self):
        """Create a profile with an axis-aligned +Q segment (same X)."""
        profile = ClosedProfile(
            segments=[
                ProfileMove(SegmentType.LINE, x=1.5, z=0.0),
                ProfileMove(SegmentType.LINE, x=1.5, z=-0.5),
                ProfileMove(SegmentType.ARC, x=1.5, z=-1.0,
                            quadrant=True, quadrant_sign=1),
                ProfileMove(SegmentType.LINE, x=2.0, z=-1.0),
                ProfileMove(SegmentType.LINE, x=2.0, z=-1.5),
            ],
            corner_breaks=[None, None, None, None],
            mode=MachiningMode.OD,
            z_start=0.0,
            z_end=-1.5,
        )
        stock = StockDef(
            diameter=2.5,
            x_start=1.5,
            z_start=0.100,
            z_end=-1.5,
            mode=MachiningMode.OD,
            x_park=3.0,
            z_park=3.0,
        )
        return profile, stock

    def test_pipeline_succeeds_no_errors(self):
        """Pipeline completes without ERROR-level validation results."""
        profile, stock = self._make_profile_and_stock()
        result = _run_pipeline(profile, stock)

        errors = [v for v in result.validations if v.severity == Severity.ERROR]
        assert result.status in (PipelineStatus.SUCCESS, PipelineStatus.SUCCESS_WITH_WARNINGS), (
            f"Pipeline failed with status {result.status}. "
            f"Errors: {[e.message for e in errors]}"
        )

    def test_finish_pass_contains_arc_moves(self):
        """The finish pass should contain at least one arc move for the quadrant arc segment."""
        profile, stock = self._make_profile_and_stock()
        result = _run_pipeline(profile, stock)

        assert result.plan_result is not None
        arcs = _get_finish_pass_arc_moves(result)
        assert len(arcs) >= 1, (
            "Expected at least one arc move in finish pass for axis-aligned Q segment"
        )

    def test_gcode_contains_g2_or_g3(self):
        """G-code output contains G02 or G03 arc moves."""
        profile, stock = self._make_profile_and_stock()
        result = _run_pipeline(profile, stock)
        gcode = _generate_gcode(result)

        arc_count = _count_arc_moves(gcode)
        assert arc_count >= 1, (
            f"Expected G02/G03 in G-code for axis-aligned Q arc, got {arc_count} arc moves"
        )

    def test_gcode_arcs_have_ik_offsets(self):
        """Each G02/G03 line includes I and K center offsets."""
        profile, stock = self._make_profile_and_stock()
        result = _run_pipeline(profile, stock)
        gcode = _generate_gcode(result)

        arc_lines = [l for l in gcode.split('\n') if re.search(r'\bG0[23]\b', l)]
        for line in arc_lines:
            assert re.search(r'I-?\d+\.\d+', line), f"Missing I offset in: {line}"
            assert re.search(r'K-?\d+\.\d+', line), f"Missing K offset in: {line}"


# --- Test: Axis-Aligned -Q (same X, vertical chord, concave) ---

class TestAxisAlignedConcaveQ:
    """Axis-aligned -Q arc: same X coordinate (vertical chord), concave.

    Profile: straight OD at X=2.0" dia, with a concave (-Q) arc scooping inward
    from Z=-0.5 to Z=-1.0 (same X=2.0 dia). No shoulder transition after the arc
    to avoid cleanup gouge issues.
    """

    def _make_profile_and_stock(self):
        """Create a profile with an axis-aligned -Q segment (same X, concave)."""
        profile = ClosedProfile(
            segments=[
                ProfileMove(SegmentType.LINE, x=2.0, z=0.0),
                ProfileMove(SegmentType.LINE, x=2.0, z=-0.5),
                ProfileMove(SegmentType.ARC, x=2.0, z=-1.0,
                            quadrant=True, quadrant_sign=-1),
                ProfileMove(SegmentType.LINE, x=2.0, z=-1.5),
            ],
            corner_breaks=[None, None, None],
            mode=MachiningMode.OD,
            z_start=0.0,
            z_end=-1.5,
        )
        stock = StockDef(
            diameter=2.5,
            x_start=2.0,
            z_start=0.100,
            z_end=-1.5,
            mode=MachiningMode.OD,
            x_park=3.0,
            z_park=3.0,
        )
        return profile, stock

    def test_pipeline_succeeds_no_errors(self):
        """Pipeline completes without ERROR-level validation results for -Q axis-aligned."""
        profile, stock = self._make_profile_and_stock()
        result = _run_pipeline(profile, stock)

        errors = [v for v in result.validations if v.severity == Severity.ERROR]
        assert result.status in (PipelineStatus.SUCCESS, PipelineStatus.SUCCESS_WITH_WARNINGS), (
            f"Pipeline failed with status {result.status}. "
            f"Errors: {[e.message for e in errors]}"
        )

    def test_finish_pass_contains_arc_moves(self):
        """The finish pass should contain at least one arc move for the -Q segment."""
        profile, stock = self._make_profile_and_stock()
        result = _run_pipeline(profile, stock)

        assert result.plan_result is not None
        arcs = _get_finish_pass_arc_moves(result)
        assert len(arcs) >= 1, (
            "Expected at least one arc move in finish pass for axis-aligned -Q segment"
        )

    def test_gcode_contains_g2_or_g3(self):
        """G-code output contains G02 or G03 arc moves for -Q."""
        profile, stock = self._make_profile_and_stock()
        result = _run_pipeline(profile, stock)
        gcode = _generate_gcode(result)

        arc_count = _count_arc_moves(gcode)
        assert arc_count >= 1, (
            f"Expected G02/G03 in G-code for axis-aligned -Q arc, got {arc_count} arc moves"
        )


# --- Off-axis Q: a TRUE quarter circle (equal legs), owner decision 2026-11-11 ---

def _q_profile(x0, z0, x1, z1, sign, tail_x=None):
    tail_x = x1 if tail_x is None else tail_x
    return ClosedProfile(
        segments=[
            ProfileMove(SegmentType.LINE, x=x0, z=0.0),
            ProfileMove(SegmentType.LINE, x=x0, z=z0),
            ProfileMove(SegmentType.ARC, x=x1, z=z1, quadrant=True, quadrant_sign=sign),
            ProfileMove(SegmentType.LINE, x=tail_x, z=-1.5),
        ],
        corner_breaks=[None, None, None],
        mode=MachiningMode.OD, z_start=0.0, z_end=-1.5,
    )


def _stock(x_start):
    return StockDef(diameter=2.5, x_start=x_start, z_start=0.100, z_end=-1.5,
                    mode=MachiningMode.OD, x_park=3.0, z_park=3.0)


def _finish_arc_centres(result):
    """(centre r, centre z, radius) of each finish-pass arc, radius space."""
    out = []
    for fp in result.plan_result.finish_passes:
        pos = None
        for m in fp.moves:
            if m.move_type in (MoveType.ARC_CW, MoveType.ARC_CCW) and pos is not None:
                c = (pos[0] / 2 + m.center_i / 2, pos[1] + m.center_k)
                out.append((c[0], c[1], ((pos[0] / 2 - c[0]) ** 2 + (pos[1] - c[1]) ** 2) ** 0.5))
            pos = (m.x, m.z)
    return out


class TestOffAxisConvexQ:
    """+Q from X1.5 Z-0.5 to X2.0 Z-0.75: a rounded shoulder, R .25, centre at
    (r .75, Z -.75) - the bounding-box corner under the start."""

    def _run(self):
        return _run_pipeline(_q_profile(1.5, -0.5, 2.0, -0.75, 1), _stock(1.5))

    def test_pipeline_succeeds(self):
        r = self._run()
        assert r.status in (PipelineStatus.SUCCESS, PipelineStatus.SUCCESS_WITH_WARNINGS), (
            [v.message for v in r.validations if v.severity == Severity.ERROR])

    def test_finish_arc_is_the_true_circle(self):
        """The finish pass (tool path, TNR comp in G42) runs on the part circle:
        one arc of the profile's radius about the bounding-box corner."""
        arcs = _finish_arc_centres(self._run())
        assert arcs, "no finish arcs"
        assert any(abs(cr - 0.75) < 2e-4 and abs(cz + 0.75) < 2e-4 and abs(rad - 0.25) < 3e-4
                   for cr, cz, rad in arcs), arcs

    def test_gcode_has_arc_and_no_spline_words(self):
        gcode = _generate_gcode(self._run())
        assert _count_arc_moves(gcode) >= 1
        for word in ("G05", "G06", "G6.1"):
            assert word not in gcode


class TestOffAxisConcaveQ:
    """-Q from X2.0 Z-0.5 to X2.2 Z-0.6: leaves along Z, arrives radially;
    R .1, centre (r 1.1, Z -.5)."""

    def _run(self):
        return _run_pipeline(_q_profile(2.0, -0.5, 2.2, -0.6, -1), _stock(2.0))

    def test_pipeline_succeeds(self):
        r = self._run()
        assert r.status in (PipelineStatus.SUCCESS, PipelineStatus.SUCCESS_WITH_WARNINGS), (
            [v.message for v in r.validations if v.severity == Severity.ERROR])

    def test_finish_arc_is_the_true_circle(self):
        arcs = _finish_arc_centres(self._run())
        assert any(abs(cr - 1.1) < 2e-4 and abs(cz + 0.5) < 2e-4 for cr, cz, rad in arcs), arcs


class TestQuadrantEntryRules:
    """Ellipses are retired: unequal legs and same-Z quadrants are refused with
    a usable message; same-X quadrants become two quadrants."""

    def test_unequal_legs_refused_with_valid_end_points_offered(self):
        r = _run_pipeline(_q_profile(1.5, -0.5, 2.0, -1.0, 1), _stock(1.5))
        assert r.status == PipelineStatus.BLOCKED_BY_ERROR
        msg = " ".join(v.message for v in r.validations if v.severity == Severity.ERROR)
        assert "true quarter circle" in msg
        assert "X2.0000 Z-0.7500" in msg          # keep X: R .25
        assert "X2.5000 Z-1.0000" in msg          # keep Z: R .5

    def test_same_z_quadrant_refused(self):
        prof = ClosedProfile(
            segments=[ProfileMove(SegmentType.LINE, x=1.0, z=0.0),
                      ProfileMove(SegmentType.LINE, x=1.0, z=-0.5),
                      ProfileMove(SegmentType.ARC, x=1.5, z=-0.5, quadrant=True),
                      ProfileMove(SegmentType.LINE, x=1.5, z=-1.5)],
            corner_breaks=[None, None, None], mode=MachiningMode.OD, z_start=0.0, z_end=-1.5)
        r = _run_pipeline(prof, _stock(1.0))
        assert r.status == PipelineStatus.BLOCKED_BY_ERROR
        assert any("same Z" in v.message for v in r.validations)

    def test_same_x_quadrant_is_two_quadrants_through_the_apex(self):
        """Owner's example: X1 Z0 -> X1 Z-1 as one arc is cut as +Q to the apex
        then -Q back. X is diameter, so the R .5 bead peaks at X2.0."""
        from geometry.arc_entry import normalize_profile
        prof = ClosedProfile(
            segments=[ProfileMove(SegmentType.LINE, x=1.0, z=0.0),
                      ProfileMove(SegmentType.ARC, x=1.0, z=-1.0, quadrant=True, quadrant_sign=1),
                      ProfileMove(SegmentType.LINE, x=1.0, z=-1.5)],
            corner_breaks=[None, None], mode=MachiningMode.OD, z_start=0.0, z_end=-1.5)
        n = normalize_profile(prof)
        assert [(m.x, m.z, m.quadrant, m.quadrant_sign) for m in n.segments[1:3]] == [
            (2.0, -0.5, True, 1), (1.0, -1.0, True, -1)]
        assert n.corner_breaks == [None, None, None]
        assert normalize_profile(n) is n                  # idempotent

    def test_same_x_quadrant_id_bulges_into_the_bore(self):
        from geometry.arc_entry import split_rows
        rows = [{"type": "line", "x": 1.0, "z": 0.0, "radius": 0.0},
                {"type": "arc", "x": 1.0, "z": -0.2, "radius": "Q"}]
        segs, _, _ = split_rows(rows, [None], "id")
        assert (segs[1]["x"], segs[1]["z"]) == pytest.approx((0.8, -0.1))
        segs, _, _ = split_rows(rows, [None], "od")
        assert (segs[1]["x"], segs[1]["z"]) == pytest.approx((1.2, -0.1))
        rows[1]["radius"] = "-Q"
        segs, _, _ = split_rows(rows, [None], "id")
        assert segs[1]["x"] == pytest.approx(1.2)          # ID groove: into the wall


# --- Test: Pipeline via model_builder (string "Q"/"-Q" parsing) ---

class TestModelBuilderQParsing:
    """Verify that "Q" and "-Q" strings in segment dicts flow through model_builder
    to produce correct ProfileMove objects that the pipeline can process.
    """

    def test_q_string_produces_pipeline_success(self):
        """A segment with radius="Q" successfully runs through the full pipeline.

        Uses axis-aligned geometry (same X) to avoid offset_2d failure on splines.
        """
        from pipeline.model_builder import build_from_fields

        segments = [
            {"type": "line", "x": 1.5, "z": 0.0},
            {"type": "line", "x": 1.5, "z": -0.5},
            {"type": "arc", "x": 1.5, "z": -1.0, "radius": "Q"},
            {"type": "line", "x": 2.0, "z": -1.0},
            {"type": "line", "x": 2.0, "z": -1.5},
        ]

        profile, stock, roughing, finishing = build_from_fields(
            segments=segments,
            stock_dia=2.5,
            x_start=1.5,
            z_start=0.100,
            z_end=-1.5,
            mode="od",
            pilot_hole_dia=0.0,
            doc_dia=0.050,
            feed=0.008,
            strategy="staircase",
            fin_allowance=0.010,
            peck_enabled=False,
            peck_length=None,
            spindle_rpm=1200.0,
            finish_passes=1,
            finish_doc_dia=0.002,
            finish_feed=0.003,
            tool_def=_od_tool(),
        )

        result = execute(profile, stock, _od_tool(), roughing, finishing)
        errors = [v for v in result.validations if v.severity == Severity.ERROR]
        assert result.status in (PipelineStatus.SUCCESS, PipelineStatus.SUCCESS_WITH_WARNINGS), (
            f"Pipeline with 'Q' string failed: {[e.message for e in errors]}"
        )

    def test_neg_q_string_produces_pipeline_success(self):
        """A segment with radius="-Q" successfully runs through the full pipeline.

        Uses axis-aligned geometry (same X) to avoid offset_2d failure on splines.
        No shoulder transition after the arc to avoid cleanup gouge issues.
        """
        from pipeline.model_builder import build_from_fields

        segments = [
            {"type": "line", "x": 2.0, "z": 0.0},
            {"type": "line", "x": 2.0, "z": -0.5},
            {"type": "arc", "x": 2.0, "z": -1.0, "radius": "-Q"},
            {"type": "line", "x": 2.0, "z": -1.5},
        ]

        profile, stock, roughing, finishing = build_from_fields(
            segments=segments,
            stock_dia=2.5,
            x_start=2.0,
            z_start=0.100,
            z_end=-1.5,
            mode="od",
            pilot_hole_dia=0.0,
            doc_dia=0.050,
            feed=0.008,
            strategy="staircase",
            fin_allowance=0.010,
            peck_enabled=False,
            peck_length=None,
            spindle_rpm=1200.0,
            finish_passes=1,
            finish_doc_dia=0.002,
            finish_feed=0.003,
            tool_def=_od_tool(),
        )

        result = execute(profile, stock, _od_tool(), roughing, finishing)
        errors = [v for v in result.validations if v.severity == Severity.ERROR]
        assert result.status in (PipelineStatus.SUCCESS, PipelineStatus.SUCCESS_WITH_WARNINGS), (
            f"Pipeline with '-Q' string failed: {[e.message for e in errors]}"
        )
