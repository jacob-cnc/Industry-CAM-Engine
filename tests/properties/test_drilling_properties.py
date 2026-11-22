"""Property-based tests for DrillingPlanner (spec: drilling-cycles).

Feature: drilling-cycles
"""

from dataclasses import replace

import pytest
from hypothesis import given, settings, strategies as st

from models.program import DrillingParams
from models.stock import StockDef
from models.tool import ToolDef, ToolOrientation, ToolDirection, ToolType
from models.moves import MoveType
from planners.drilling_planner import DrillingPlanner, tip_length

POINT_ANGLES = [90.0, 118.0, 135.0, 150.0, 180.0]


def _tool(dia, point):
    return ToolDef(
        tool_number=6, nose_radius=dia / 2.0, tip_angle=point, edge_length=0.0,
        orientation=ToolOrientation.CENTER, direction=ToolDirection.NEUTRAL,
        tool_type=ToolType.DRILLING, description="drill",
    )


def _stock(dia, z_start, z_end):
    return StockDef(diameter=dia, x_start=0.0, z_start=z_start, z_end=z_end)


@st.composite
def drilling_case(draw, through=None, depth_to_tip=None):
    z_start = draw(st.floats(-1.0, 1.0, allow_nan=False, allow_infinity=False))
    depth = draw(st.floats(0.05, 2.0, allow_nan=False, allow_infinity=False))
    point = draw(st.sampled_from(POINT_ANGLES))
    dia = draw(st.floats(0.0625, 1.0, allow_nan=False, allow_infinity=False))
    peck_inc = draw(st.floats(0.02, 0.5, allow_nan=False, allow_infinity=False))
    full = draw(st.booleans())
    thru = draw(st.booleans()) if through is None else through
    d2t = draw(st.booleans()) if depth_to_tip is None else depth_to_tip
    r_gap = draw(st.floats(0.02, 0.25, allow_nan=False, allow_infinity=False))
    stock_dia = dia + draw(st.floats(0.1, 2.0, allow_nan=False, allow_infinity=False))

    params = DrillingParams(
        operation="drill", z_start=z_start, depth=depth, depth_to_tip=d2t,
        through_hole=thru, r_plane=z_start + r_gap, peck_enabled=True,
        peck_increment=peck_inc, full_retract=full, dwell=0.0, feed=0.004,
        spindle_rpm=1000, tool_number=6,
    )
    # Back face deep enough that blind holes always validate; geometry is the focus.
    stock = _stock(stock_dia, z_start, z_start - depth - 3.0)
    return params, _tool(dia, point), stock


# Feature: drilling-cycles, Property 1: feeds advance monotonically toward the
# part and never pass the final planned depth.
@settings(max_examples=200, deadline=None)
@given(drilling_case())
def test_property_1_feeds_monotone_bounded(case):
    params, tool, stock = case
    moves = DrillingPlanner().plan(params, tool, stock)
    feed_z = [m.z for m in moves if m.move_type == MoveType.FEED]
    assert feed_z, "a hole must have at least one feed"
    z_final = min(feed_z)
    for a, b in zip(feed_z, feed_z[1:]):
        assert a - b > 1e-12, "each peck must go strictly deeper"
    assert all(z >= z_final - 1e-9 for z in feed_z)
    assert feed_z[-1] == z_final


# Feature: drilling-cycles, Property 2: no single peck feed exceeds the peck
# increment, and the feeds reach exactly the final depth.
@settings(max_examples=200, deadline=None)
@given(drilling_case())
def test_property_2_peck_increments_bounded(case):
    params, tool, stock = case
    moves = DrillingPlanner().plan(params, tool, stock)
    feed_z = [m.z for m in moves if m.move_type == MoveType.FEED]
    prev = params.r_plane
    for z in feed_z:
        step = prev - z
        assert 0.0 < step <= params.peck_increment + 1e-9
        prev = z
    z_final = _expected_final(params, tool)
    assert feed_z[-1] == pytest.approx(z_final, abs=1e-9)


# Feature: drilling-cycles, Property 3: a through hole's deepest Z equals the
# commanded (full-diameter) depth minus the drill-point tip length.
@settings(max_examples=200, deadline=None)
@given(drilling_case(through=True))
def test_property_3_through_hole_tip_extension(case):
    params, tool, stock = case
    moves = DrillingPlanner().plan(params, tool, stock)
    z_final = min(m.z for m in moves if m.move_type == MoveType.FEED)
    tl = tip_length(2.0 * tool.nose_radius, tool.tip_angle)
    expected = params.z_start - params.depth - tl
    assert z_final == pytest.approx(expected, abs=1e-9)


# Feature: drilling-cycles, Property 5: for the same commanded depth, a shoulder
# reference bottoms out exactly one tip length deeper than a tip reference.
@settings(max_examples=200, deadline=None)
@given(drilling_case(through=False))
def test_property_5_depth_reference_consistency(case):
    params, tool, stock = case
    tip_params = replace(params, depth_to_tip=True)
    shoulder_params = replace(params, depth_to_tip=False)
    z_tip = min(m.z for m in DrillingPlanner().plan(tip_params, tool, stock)
                if m.move_type == MoveType.FEED)
    z_shoulder = min(m.z for m in DrillingPlanner().plan(shoulder_params, tool, stock)
                     if m.move_type == MoveType.FEED)
    tl = tip_length(2.0 * tool.nose_radius, tool.tip_angle)
    assert (z_tip - z_shoulder) == pytest.approx(tl, abs=1e-9)


def _expected_final(params, tool):
    tl = tip_length(2.0 * tool.nose_radius, tool.tip_angle)
    base = params.z_start - params.depth
    if params.depth_to_tip and not params.through_hole:
        return base
    return base - tl
