"""A finish pass must cut the bore contour, never the stock closure."""

import pytest

from models.tool import ToolDef, ToolDirection, ToolOrientation, ToolType
from models.validation import PipelineStatus
from outputs.gcode_writer import GCodeWriter
from outputs.gcode_parser import parse
from models.moves import MoveType
from pipeline.model_builder import build_from_fields
from pipeline.pipeline import execute

def _without_comp_entries(gcode: str) -> str:
    """Drop the in-air cutter-comp entry/lead-out moves (added 2026-11-08)
    so tests compare only the planned contour moves."""
    return "\n".join(l for l in gcode.splitlines()
                     if "Comp entry" not in l and "Comp lead-out" not in l
                     and "Contour approach" not in l)



@pytest.mark.parametrize("strategy", ["staircase", "offset_contour"])
@pytest.mark.parametrize("x_start", [2.995, 3.117])
def test_counterbore_finish_stays_on_requested_wall(strategy, x_start):
    tool = ToolDef(
        1, 0.008, 55.0, 0.25, ToolOrientation.ID_FRONT_RIGHT,
        ToolDirection.RIGHT, ToolType.BORING,
    )
    profile, stock, roughing, finishing = build_from_fields(
        segments=[{"type": "line", "x": 3.117, "z": 0.0},
                  {"type": "line", "x": 3.117, "z": -0.568}],
        stock_dia=4.0, x_start=x_start, z_start=0.05, z_end=-0.568,
        mode="id", pilot_hole_dia=2.995, doc_dia=0.02, feed=0.003,
        strategy=strategy, fin_allowance=0.002, peck_enabled=False,
        peck_length=None, spindle_rpm=300, finish_passes=1,
        finish_doc_dia=0.002, finish_feed=0.002, tool_def=tool,
    )
    result = execute(profile, stock, tool, roughing, finishing)
    assert result.status in (PipelineStatus.SUCCESS, PipelineStatus.SUCCESS_WITH_WARNINGS)
    plan = result.plan_result
    moves = plan.finish_passes[0].moves
    assert len(moves) == 2
    assert [m.x for m in moves] == pytest.approx([3.117, 3.117])
    assert [m.z for m in moves] == pytest.approx([0.0, -0.568])
    # Inspect the emitted finish section too: the writer reconstructs pass moves.
    code = GCodeWriter().write(plan)
    finish_section = code.split("; === FINISH PASS")[1].split("; === PROGRAM END")[0]
    assert "X4.0000" not in finish_section
    assert "Z-0.5680" in finish_section
    emitted_finish = [m for m in parse(_without_comp_entries(finish_section)) if m.move_type == MoveType.FEED]
    assert len(emitted_finish) == 2
    assert [m.x for m in emitted_finish] == pytest.approx([3.117, 3.117])
    assert [m.z for m in emitted_finish] == pytest.approx([0.0, -0.568])


def test_stepped_id_finish_follows_ground_truth_profile():
    import json
    from pathlib import Path
    from geometry.zone_builder import build_zones
    from geometry.zone_query import ZoneQueryAPI
    from planners.finish_planner import FinishPlanner

    fixture = json.loads(
        (Path(__file__).parents[1] / "ground_truth" / "stepped_id.json").read_text()
    )
    tool = ToolDef(1, 0.008, 55.0, 0.25, ToolOrientation.ID_FRONT_RIGHT,
                   ToolDirection.RIGHT, ToolType.BORING)
    profile, stock, roughing, finishing = build_from_fields(
        segments=fixture["segments"], stock_dia=2.0, x_start=1.2,
        z_start=0.05, z_end=-1.5, mode="id", pilot_hole_dia=0.5,
        doc_dia=0.05, feed=0.003, strategy="staircase", fin_allowance=0.002,
        peck_enabled=False, peck_length=None, spindle_rpm=300,
        finish_passes=1, finish_doc_dia=0.002, finish_feed=0.002, tool_def=tool,
    )
    query = ZoneQueryAPI(build_zones(profile, stock, tool, roughing))
    finish = FinishPlanner().plan(query, tool, finishing, stock, profile.mode, profile)[0]
    assert len(finish.moves) == len(fixture["segments"])
    assert [m.x for m in finish.moves] == pytest.approx(
        [s["x_dia"] for s in fixture["segments"]]
    )
    assert [m.z for m in finish.moves] == pytest.approx(
        [s["z"] for s in fixture["segments"]]
    )
