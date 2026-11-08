"""Contour exits are diagonal in both the validated plan and emitted program."""
from dataclasses import replace
import pytest
from shapely.geometry import Polygon

from models.moves import MoveType, PassType, ToolMove
from models.validation import PipelineStatus
from outputs.gcode_parser import parse
from outputs.gcode_writer import GCodeWriter
from pipeline.model_builder import build_from_fields
from pipeline.pipeline import execute
from tests.integration.test_operation_depth import bore_fields
from validation.polygon_builder import ValidationPolygons
from validation.post_planning_validator import validate_all_moves
from models.profile import MachiningMode


def fields_for(mode, **kwargs):
    segments = [dict(x=3.117, z=0), dict(x=3.117, z=-.568)]
    if mode == "id":
        segments.append(dict(x=2.995, z=-.568))
    return bore_fields(mode=mode, segments=segments, **kwargs)


@pytest.mark.parametrize("mode", ["id", "od"])
@pytest.mark.parametrize("strategy", ["staircase", "offset_contour"])
@pytest.mark.parametrize("passes,spring", [(1, False), (3, True)])
def test_cleanup_and_each_finish_exit_move_both_axes(mode, strategy, passes, spring):
    fields = fields_for(mode, strategy=strategy, finish_passes=passes, finish_spring_pass=spring)
    p, s, r, f = build_from_fields(**fields)
    result = execute(p, s, fields["tool_def"], r, f)
    assert result.plan_result is not None, result.validations
    plan = result.plan_result
    safe_x = 2.985 if mode == "id" else 4.01
    for contour in plan.cleanup_passes + plan.finish_passes:
        assert len(contour.retract_moves) == 1
        exit_move = contour.retract_moves[0]
        assert exit_move.move_type == MoveType.RAPID
        assert exit_move.x == pytest.approx(safe_x)
        assert exit_move.z == pytest.approx(contour.z_start)
        assert exit_move.x != contour.moves[-1].x
        assert exit_move.z != contour.moves[-1].z
        assert exit_move in plan.tool_moves
    assert plan.tool_moves[-1] == plan.finish_passes[-1].retract_moves[-1]
    code = GCodeWriter().write(plan)
    cleanup_exit = next(line for line in code.splitlines() if "Diagonal retract after cleanup" in line)
    final_exit = next(line for line in code.splitlines() if "Diagonal retract after final finish/spring" in line)
    for line, contour in [(cleanup_exit, plan.cleanup_passes[-1]), (final_exit, plan.finish_passes[-1])]:
        move = parse(line)[0]
        assert move.x == pytest.approx(contour.retract_moves[0].x)
        assert move.z == pytest.approx(contour.retract_moves[0].z)


def test_diagonal_is_checked_from_cut_endpoint_across_phase_boundary():
    polygons = ValidationPolygons(Polygon([(.25, -.8), (.4, -.8), (.4, -.2), (.25, -.2)]),
                                  Polygon(), Polygon())
    moves = [ToolMove(MoveType.FEED, 1.0, -1, feed=.002, pass_type=PassType.FINISH),
             ToolMove(MoveType.RAPID, .4, .1, pass_type=PassType.TRANSITION)]
    results = validate_all_moves(moves, polygons, MachiningMode.ID)
    assert any("GOUGE" in result.message for result in results)


def test_diagonal_that_crosses_od_shoulder_is_blocked():
    fields = bore_fields(mode="od", segments=[dict(x=3.117, z=0),
        dict(x=3.117, z=-.568), dict(x=2.995, z=-.568)])
    p, s, r, f = build_from_fields(**fields)
    result = execute(p, s, fields["tool_def"], r, f)
    assert result.status == PipelineStatus.BLOCKED_BY_ERROR
    assert result.plan_result is None
    assert any("TRANSITION" in v.message and "GOUGE" in v.message for v in result.validations)


def test_cleanup_diagonal_precedes_tool_change_travel():
    fields = fields_for("id")
    p, s, r, f = build_from_fields(**fields)
    plan = execute(p, s, fields["tool_def"], r, f,
                   finish_tool=replace(fields["tool_def"], tool_number=2)).plan_result
    assert plan is not None
    code = GCodeWriter().write(plan)
    assert code.index("Diagonal retract after cleanup") < code.index("Cutter comp off for tool change")


def test_writer_refuses_missing_terminal_retract():
    fields = fields_for("id")
    p, s, r, f = build_from_fields(**fields)
    plan = execute(p, s, fields["tool_def"], r, f).plan_result
    broken = replace(plan, finish_passes=[replace(plan.finish_passes[0], retract_moves=None)])
    with pytest.raises(ValueError, match="planned diagonal retract"):
        GCodeWriter().write(broken)
