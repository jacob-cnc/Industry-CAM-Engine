"""OD profile ending mid-bar (turned stub with a step face), 2026-11-09.

Bar 1.0 dia, Stock Back Face -1.0. Profile 0.5 dia to Z-0.3, 0.8 dia to Z-0.6,
then (case B) the step face out to the bar OD. Before: the OD face-offset
cleanup route put the cleanup inside the finished part / allowance and the
pipeline was blocked. Now OD uses the shared open-contour kernel offset.
"""
import pytest

from models.tool import ToolDef, ToolOrientation, ToolDirection, ToolType
from outputs.gcode_writer import GCodeWriter
from pipeline.model_builder import build_from_fields
from pipeline.pipeline import execute, PipelineStatus

TOOL = ToolDef(tool_number=2, nose_radius=0.016, tip_angle=80.0, edge_length=0.375,
               orientation=ToolOrientation(2), direction=ToolDirection.RIGHT,
               tool_type=ToolType.TURNING, description="T2")
STUB = [dict(x=0.5, z=0), dict(x=0.5, z=-0.3), dict(x=0.8, z=-0.3), dict(x=0.8, z=-0.6)]
STEP = STUB + [dict(x=1.0, z=-0.6)]


def _run(segments, back=-1.0):
    p, s, r, f = build_from_fields(
        segments=segments, stock_dia=1.0, x_start=0.0, z_start=0.1, z_end=-1.0,
        stock_back_z=back, mode="od", pilot_hole_dia=0.0, strategy="staircase",
        peck_enabled=False, peck_length=None, spindle_rpm=500, finish_passes=1,
        finish_doc_dia=0.002, finish_feed=0.003, doc_dia=0.05, feed=0.006,
        fin_allowance=0.01, tool_def=TOOL, x_park=1.5, z_park=1.0)
    return execute(p, s, TOOL, r, f)


def _pts(moves):
    return [(round(m.x, 4), round(m.z, 4)) for m in moves]


def test_case_b_step_face_drawn_plans_and_offsets_correctly():
    res = _run(STEP)
    assert res.status in (PipelineStatus.SUCCESS, PipelineStatus.SUCCESS_WITH_WARNINGS), \
        [v.message for v in res.validations]
    pr = res.plan_result
    cleanup = _pts(pr.cleanup_passes[0].moves)
    # wall 0.005 off 0.8, stops 0.005 before the step face, step face 0.005 off, out to bar OD
    assert cleanup[-2:] == [(0.81, -0.595), (1.0, -0.595)]
    assert (0.51, -0.295) in cleanup and (0.81, -0.295) in cleanup
    final = _pts(pr.finish_passes[-1].moves)
    assert final[-2:] == [(0.8, -0.6), (1.0, -0.6)]
    # the bar beyond the step is part of the protected finished part
    assert (1.0, -1.0) in [(round(a, 3), round(b, 3)) for a, b in pr.finished_part_boundary]


def test_case_b_no_lead_out_needed_step_face_runs_out_to_air():
    code = GCodeWriter().write(_run(STEP).plan_result)
    assert "Comp lead-out" not in code


def test_case_a_stub_without_step_face_also_plans():
    res = _run(STUB)
    assert res.plan_result is not None, [v.message for v in res.validations]
    assert _pts(res.plan_result.cleanup_passes[0].moves)[-1] == (0.81, -0.595)
    # finish wall ends against the bar: writer adds the comp lead-out
    assert "Comp lead-out" in GCodeWriter().write(res.plan_result)


def test_bar_ending_at_profile_unchanged():
    res = _run(STUB, back=-0.6)
    assert res.plan_result is not None
    assert _pts(res.plan_result.cleanup_passes[0].moves)[-1] == (0.81, -0.595)
