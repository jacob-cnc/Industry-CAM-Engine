"""Unit tests for DrillingPlanner (spec: drilling-cycles, phase 1).

On-center axial drilling: a hole at X0 fed along Z, emitted as explicit peck
moves. Z is negative toward the tailstock.
"""

import math

import pytest

from models.program import DrillingParams
from models.stock import StockDef
from models.tool import ToolDef, ToolOrientation, ToolDirection, ToolType
from models.moves import MoveType, PassType
from planners.drilling_planner import DrillingPlanner, tip_length, RAPID_CLEARANCE


def make_tool(dia=0.25, point=118.0):
    return ToolDef(
        tool_number=6, nose_radius=dia / 2.0, tip_angle=point, edge_length=0.0,
        orientation=ToolOrientation.CENTER, direction=ToolDirection.NEUTRAL,
        tool_type=ToolType.DRILLING, description="drill",
    )


def make_stock(diameter=1.0, z_start=0.0, z_end=-5.0):
    return StockDef(diameter=diameter, x_start=0.0, z_start=z_start, z_end=z_end)


def make_params(**kw):
    base = dict(
        operation="drill", z_start=0.0, depth=0.5, depth_to_tip=True,
        through_hole=False, r_plane=0.1, peck_enabled=False, peck_increment=0.1,
        full_retract=True, dwell=0.0, feed=0.004, spindle_rpm=1200, tool_number=6,
    )
    base.update(kw)
    return DrillingParams(**base)


# --- tip_length -------------------------------------------------------------

def test_tip_length_118_quarter_inch():
    # 118 deg, 0.25 dia -> (0.125)/tan(59 deg) ~= 0.0751"
    assert tip_length(0.25, 118.0) == pytest.approx(0.125 / math.tan(math.radians(59.0)))
    assert tip_length(0.25, 118.0) == pytest.approx(0.07506, abs=1e-4)


def test_tip_length_flat_and_unknown_are_zero():
    assert tip_length(0.25, 180.0) == 0.0
    assert tip_length(0.25, 0.0) == 0.0
    assert tip_length(0.0, 118.0) == 0.0


# --- single feed (no peck) --------------------------------------------------

def test_single_feed_sequence():
    p = make_params(peck_enabled=False, depth=0.5, r_plane=0.1)
    moves = DrillingPlanner().plan(p, make_tool(), make_stock())
    assert [m.move_type for m in moves] == [MoveType.RAPID, MoveType.FEED, MoveType.RAPID]
    assert all(m.x == 0.0 for m in moves)             # on center
    assert all(m.pass_type == PassType.DRILLING for m in moves)
    assert moves[0].z == pytest.approx(0.1)           # to clearance plane
    assert moves[1].z == pytest.approx(-0.5)          # tip depth (depth_to_tip)
    assert moves[1].feed == pytest.approx(0.004)
    assert moves[2].z == pytest.approx(0.1)           # retract


# --- peck: full retract -----------------------------------------------------

def test_peck_full_retract_structure():
    # depth 0.30 from r_plane 0.10 -> descent 0.40, peck 0.10 -> 4 feeds
    p = make_params(peck_enabled=True, full_retract=True, depth=0.30,
                    depth_to_tip=True, r_plane=0.10, peck_increment=0.10)
    moves = DrillingPlanner().plan(p, make_tool(), make_stock())
    feeds = [m for m in moves if m.move_type == MoveType.FEED]
    # pecks count from the clearance plane (G83 semantics): 0.0, -0.10, -0.20, -0.30
    assert len(feeds) == 4
    assert feeds[-1].z == pytest.approx(-0.30)
    # between pecks: a rapid to the clearance plane then a rapid back into the hole
    plane_rapids = [m for m in moves
                    if m.move_type == MoveType.RAPID and abs(m.z - 0.10) < 1e-9]
    # first approach + 3 between-peck retracts + final retract = 5 rapids to plane
    assert len(plane_rapids) == 5
    back_rapids = [m for m in moves
                   if m.move_type == MoveType.RAPID and m.z < 0.10 - 1e-9]
    assert len(back_rapids) == 3
    # each rapid back re-enters just above the matching peck depth
    assert back_rapids[0].z == pytest.approx(feeds[0].z + RAPID_CLEARANCE)
    assert back_rapids[1].z == pytest.approx(feeds[1].z + RAPID_CLEARANCE)


def test_peck_feeds_never_exceed_increment_and_reach_bottom():
    p = make_params(peck_enabled=True, full_retract=True, depth=0.55,
                    depth_to_tip=True, r_plane=0.10, peck_increment=0.125)
    moves = DrillingPlanner().plan(p, make_tool(), make_stock())
    feed_z = [m.z for m in moves if m.move_type == MoveType.FEED]
    prev = p.r_plane
    for z in feed_z:
        assert prev - z <= p.peck_increment + 1e-9      # no peck deeper than increment
        prev = z
    assert feed_z[-1] == pytest.approx(-0.55)


# --- peck: chip break -------------------------------------------------------

def test_peck_chip_break_stays_in_hole():
    p = make_params(peck_enabled=True, full_retract=False, depth=0.30,
                    depth_to_tip=True, r_plane=0.10, peck_increment=0.10)
    moves = DrillingPlanner().plan(p, make_tool(), make_stock())
    feeds = [m for m in moves if m.move_type == MoveType.FEED]
    assert len(feeds) == 4                                # 0.0, -0.10, -0.20, -0.30
    # No intermediate rapid returns to the clearance plane except the final retract
    plane_rapids = [m for m in moves
                    if m.move_type == MoveType.RAPID and abs(m.z - 0.10) < 1e-9]
    assert len(plane_rapids) == 2                        # initial approach + final retract
    chip_retracts = [m for m in moves
                     if m.move_type == MoveType.RAPID and m.z < 0.10 - 1e-9]
    assert len(chip_retracts) == 3                        # between 4 feeds
    assert chip_retracts[0].z == pytest.approx(feeds[0].z + RAPID_CLEARANCE)


# --- dwell ------------------------------------------------------------------

def test_bottom_dwell_emitted():
    p = make_params(peck_enabled=False, dwell=0.75, depth=0.4)
    moves = DrillingPlanner().plan(p, make_tool(), make_stock())
    dwells = [m for m in moves if m.move_type == MoveType.DWELL]
    assert len(dwells) == 1
    assert dwells[0].feed == pytest.approx(0.75)         # seconds carried in feed
    assert dwells[0].z == pytest.approx(-0.4)


def test_no_dwell_when_zero():
    p = make_params(dwell=0.0)
    moves = DrillingPlanner().plan(p, make_tool(), make_stock())
    assert not any(m.move_type == MoveType.DWELL for m in moves)


# --- depth reference and through-hole --------------------------------------

def test_through_hole_extends_by_tip_length():
    tl = tip_length(0.25, 118.0)
    p = make_params(through_hole=True, depth=1.0, depth_to_tip=True)
    moves = DrillingPlanner().plan(p, make_tool(0.25, 118.0), make_stock(z_end=-2.0))
    z_final = min(m.z for m in moves)
    assert z_final == pytest.approx(0.0 - 1.0 - tl)


def test_shoulder_reference_is_tip_length_deeper_than_tip():
    tool = make_tool(0.25, 118.0)
    stock = make_stock()
    tip = DrillingPlanner().plan(make_params(depth_to_tip=True, depth=0.5), tool, stock)
    shoulder = DrillingPlanner().plan(make_params(depth_to_tip=False, depth=0.5), tool, stock)
    z_tip = min(m.z for m in tip)
    z_shoulder = min(m.z for m in shoulder)
    assert (z_tip - z_shoulder) == pytest.approx(tip_length(0.25, 118.0))


# --- validation -------------------------------------------------------------

@pytest.mark.parametrize("kw", [
    dict(feed=0.0),
    dict(feed=-0.004),
    dict(depth=0.0),
    dict(depth=-0.5),
    dict(peck_enabled=True, peck_increment=0.0),
    dict(r_plane=-1.0, depth=0.5),              # clearance below the hole bottom
])
def test_validation_rejects_bad_params(kw):
    with pytest.raises(ValueError):
        DrillingPlanner().plan(make_params(**kw), make_tool(), make_stock())


def test_validation_zero_diameter_tool():
    with pytest.raises(ValueError):
        DrillingPlanner().plan(make_params(), make_tool(dia=0.0), make_stock())


def test_validation_drill_bigger_than_stock():
    with pytest.raises(ValueError):
        DrillingPlanner().plan(make_params(), make_tool(dia=1.5), make_stock(diameter=1.0))


def test_validation_blind_hole_past_back_face():
    # depth 3.0 from face 0.0 -> bottom -3.0, stock back face -2.0, not through
    with pytest.raises(ValueError):
        DrillingPlanner().plan(
            make_params(depth=3.0, through_hole=False),
            make_tool(), make_stock(z_end=-2.0),
        )


def test_through_hole_allows_depth_past_back_face():
    # same depth, but through-hole is allowed to pass the back face
    moves = DrillingPlanner().plan(
        make_params(depth=3.0, through_hole=True),
        make_tool(), make_stock(z_end=-2.0),
    )
    assert any(m.move_type == MoveType.FEED for m in moves)
