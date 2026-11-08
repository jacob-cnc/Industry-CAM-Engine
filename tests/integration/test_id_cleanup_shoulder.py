"""GCH counterbore cleanup retains the authored terminal shoulder."""
import pytest

from geometry.zone_query import ZoneQueryAPI
from models.moves import MoveType
from outputs.gcode_parser import parse
from outputs.gcode_writer import GCodeWriter
from pipeline.model_builder import build_from_fields
from pipeline.pipeline import execute
from tests.integration.test_operation_depth import bore_fields


@pytest.mark.parametrize("strategy", ["staircase", "offset_contour"])
@pytest.mark.parametrize("passes,spring", [(1, False), (3, True)])
def test_gch_cleanup_cuts_wall_then_shoulder_before_retract(strategy, passes, spring):
    fields = bore_fields(strategy=strategy, finish_passes=passes, finish_spring_pass=spring,
        segments=[dict(x=3.117, z=0), dict(x=3.117, z=-.568), dict(x=2.995, z=-.568)])
    p, s, r, f = build_from_fields(**fields)
    result = execute(p, s, fields["tool_def"], r, f)
    assert result.plan_result is not None, result.validations
    plan = result.plan_result
    assert len(plan.cleanup_passes) == 1
    cleanup = plan.cleanup_passes[0]
    assert [m.x for m in cleanup.moves[-2:]] == pytest.approx([3.115, 2.995])
    assert [m.z for m in cleanup.moves[-2:]] == pytest.approx([-.567, -.567])
    assert all(m.move_type == MoveType.FEED for m in cleanup.moves)
    final = [p for p in plan.finish_passes if not p.is_spring_pass][-1]
    assert [m.x for m in final.moves] == pytest.approx([3.117, 3.117, 2.995])
    assert [m.z for m in final.moves] == pytest.approx([0, -.568, -.568])
    code = GCodeWriter().write(plan)
    section = code.split("; === CLEANUP PASS")[1].split("; === FINISH PASS")[0]
    parsed = parse(section)
    feeds = [m for m in parsed if m.move_type == MoveType.FEED]
    assert [m.x for m in feeds[-2:]] == pytest.approx([3.115, 2.995])
    assert [m.z for m in feeds[-2:]] == pytest.approx([-.567, -.567])
    shoulder_index = parsed.index(feeds[-1])
    assert parsed[shoulder_index + 1].move_type == MoveType.RAPID
    assert parsed[shoulder_index + 1].x == pytest.approx(2.985)
    assert parsed[shoulder_index + 1].z == pytest.approx(.05)


def test_wall_only_cleanup_keeps_existing_bottom_allowance():
    fields = bore_fields()
    p, s, r, f = build_from_fields(**fields)
    plan = execute(p, s, fields["tool_def"], r, f).plan_result
    assert plan is not None
    assert plan.cleanup_passes[0].moves[-1].x == pytest.approx(3.115)
    assert plan.cleanup_passes[0].moves[-1].z == pytest.approx(-.567)


def test_zero_allowance_cleanup_retains_terminal_shoulder():
    fields = bore_fields(fin_allowance=0,
        segments=[dict(x=3.117, z=0), dict(x=3.117, z=-.568), dict(x=2.995, z=-.568)])
    p, s, r, f = build_from_fields(**fields)
    plan = execute(p, s, fields["tool_def"], r, f).plan_result
    assert plan is not None
    assert plan.cleanup_passes[0].moves[-1].x == pytest.approx(2.995)
    assert plan.cleanup_passes[0].moves[-1].z == pytest.approx(-.568)


def test_cleanup_kernel_failure_is_not_silently_omitted(monkeypatch):
    def failed(*args, **kwargs):
        raise RuntimeError("Cleanup kernel failure")
    monkeypatch.setattr(ZoneQueryAPI, "profile_offset_edges", failed)
    fields = bore_fields()
    p, s, r, f = build_from_fields(**fields)
    with pytest.raises(RuntimeError, match="Cleanup kernel failure"):
        execute(p, s, fields["tool_def"], r, f)


@pytest.mark.parametrize("strategy", ["staircase", "offset_contour"])
@pytest.mark.parametrize("segments", [
    [dict(x=1.2, z=0), dict(x=1.2, z=-1), dict(x=.8, z=-1), dict(x=.8, z=-1.5)],
    [dict(x=3, z=0), dict(type="arc", x=3.5, z=-.25, radius=-.25), dict(x=3.5, z=-1)],
    [dict(x=4, z=0), dict(x=3.117, z=0), dict(x=3.117, z=-.568), dict(x=2.995, z=-.568)],
])
def test_id_steps_arcs_and_authored_face_keep_connected_cleanup(strategy, segments):
    fields = bore_fields(strategy=strategy, segments=segments, stock_back_z=-2,
                         x_start=segments[0]["x"], pilot_hole_dia=.5)
    p, s, r, f = build_from_fields(**fields)
    result = execute(p, s, fields["tool_def"], r, f)
    assert result.plan_result is not None, result.validations
    assert len(result.plan_result.cleanup_passes) == 1
    GCodeWriter().write(result.plan_result)


def test_empty_requested_cleanup_is_an_error(monkeypatch):
    monkeypatch.setattr(ZoneQueryAPI, "profile_offset_edges", lambda *args, **kwargs: [])
    fields = bore_fields()
    p, s, r, f = build_from_fields(**fields)
    with pytest.raises(RuntimeError, match="no contour"):
        execute(p, s, fields["tool_def"], r, f)
