"""Unit tests for GCodeWriter.write_drilling_block (spec: drilling-cycles, phase 1).

Drilling is emitted as explicit G0/G1/G4 — never a G8x canned cycle (a canned
cycle in G18 would drill along Y, not Z). Feed is per-rev under the inherited G95.
"""

import pytest

from models.program import DrillingParams
from models.stock import StockDef
from models.tool import ToolDef, ToolOrientation, ToolDirection, ToolType
from planners.drilling_planner import DrillingPlanner
from outputs.gcode_writer import GCodeWriter


def make_tool(dia=0.25, point=118.0):
    return ToolDef(
        tool_number=6, nose_radius=dia / 2.0, tip_angle=point, edge_length=0.0,
        orientation=ToolOrientation.CENTER, direction=ToolDirection.NEUTRAL,
        tool_type=ToolType.DRILLING, description="0.25 drill",
    )


def make_stock():
    return StockDef(diameter=1.0, x_start=0.0, z_start=0.0, z_end=-5.0)


def make_params(**kw):
    base = dict(
        operation="drill", z_start=0.0, depth=0.5, depth_to_tip=True,
        through_hole=False, r_plane=0.1, peck_enabled=True, peck_increment=0.15,
        full_retract=True, dwell=0.5, feed=0.004, spindle_rpm=1200, tool_number=6,
    )
    base.update(kw)
    return DrillingParams(**base)


def emit(params=None, unit_mode="inch"):
    params = params or make_params()
    tool, stock = make_tool(), make_stock()
    moves = DrillingPlanner().plan(params, tool, stock)
    return GCodeWriter().write_drilling_block(params, moves, tool, unit_mode)


def test_no_canned_cycle_codes():
    text = "\n".join(emit())
    for code in ("G80", "G81", "G82", "G83", "G73", "G74", "G33"):
        assert code not in text, f"{code} must not appear in explicit-move drilling"


def test_does_not_touch_feed_mode():
    # The block inherits G95 from the program preamble and never re-asserts feed mode.
    text = "\n".join(emit())
    assert "G94" not in text
    assert "G95" not in text


def test_emits_core_motion_and_spindle():
    text = "\n".join(emit())
    assert "G7" in text                 # diameter mode re-asserted locally
    assert "M3" in text                 # spindle on
    assert "G00" in text                # rapids
    assert "G01" in text                # feeds


def test_on_center_every_motion_line():
    lines = emit()
    motion = [ln for ln in lines if ("G00" in ln or "G01" in ln)]
    assert motion
    for ln in motion:
        assert "X0.0000" in ln, f"motion not on center: {ln}"


def test_dwell_line_present():
    text = "\n".join(emit(make_params(dwell=0.5)))
    assert "G04 P0.500" in text


def test_no_dwell_line_when_zero():
    text = "\n".join(emit(make_params(dwell=0.0)))
    assert "G04" not in text


def test_single_feed_has_one_g01():
    lines = emit(make_params(peck_enabled=False, dwell=0.0))
    assert sum("G01" in ln for ln in lines) == 1


def test_metric_scaling():
    # depth 0.5" -> tip at Z-0.5" -> -12.700 mm; 3-decimal metric format
    text = "\n".join(emit(make_params(peck_enabled=False), unit_mode="metric"))
    assert "Z-12.700" in text


def test_invalid_unit_mode_raises():
    params = make_params()
    tool, stock = make_tool(), make_stock()
    moves = DrillingPlanner().plan(params, tool, stock)
    with pytest.raises(ValueError):
        GCodeWriter().write_drilling_block(params, moves, tool, unit_mode="imperial")
