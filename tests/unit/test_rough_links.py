"""Roughing retract / approach rule (owner 2026-11-12, planners/rough_links.py).

OD: pass 1 retracts to stock OD + .005; pass n to the previous pass's highest
X + .005. ID: pass 1 to pilot - .001; pass n to the previous pass's lowest X
- .005. A pass ending at a wall pulls off at 45 deg. A Z traverse that would
leave the corridor already cleared first exits the pocket (to just beyond an
earlier pass covering the range, else the pass-1 target).
"""
import pytest

from models.moves import MoveType, PassType, ToolMove
from models.results import TurningPass
from planners.rough_links import pass_x_extent, plan_rough_links


class _Stock:
    def __init__(self, diameter=2.0, pilot=0.0, z_start=0.1):
        self.diameter, self.pilot_hole_dia, self.z_start = diameter, pilot, z_start


def _pass(level, z0, z1, moves=None, i=0):
    return TurningPass(x_level=level, z_start=z0, z_end=z1, pass_index=i, pass_type=PassType.ROUGH,
                       moves=moves or [ToolMove(MoveType.FEED, level, z1, feed=0.01)])


NO_WALL = lambda pt: False       # noqa: E731
WALL = lambda pt: True           # noqa: E731


def _retract(p):
    assert len(p.retract_moves) == 1
    m = p.retract_moves[0]
    return m.x, m.z


def test_od_targets_stock_then_previous_pass_plus_005_at_a_wall():
    ps = plan_rough_links([_pass(1.9, 0.0, -1.0), _pass(1.8, 0.0, -1.0), _pass(1.7, 0.0, -1.0),
                           _pass(1.6, 0.0, -1.0)],
                          _Stock(2.0), False, 0.01, WALL)
    # last pass: full exit (see test_last_pass_exits_fully...)
    assert [_retract(p)[0] for p in ps] == pytest.approx([2.005, 1.905, 1.805, 2.005])


def test_od_free_end_uses_010_and_retracts_straight_in_x():
    ps = plan_rough_links([_pass(1.9, 0.0, -1.0), _pass(1.8, 0.0, -1.0), _pass(1.7, 0.0, -1.0),
                           _pass(1.6, 0.0, -1.0)],
                          _Stock(2.0), False, 0.01, NO_WALL)
    assert [_retract(p)[0] for p in ps] == pytest.approx([2.005, 1.91, 1.81, 2.005])   # pass 1: stock + .005
    assert all(_retract(p)[1] == pytest.approx(-1.0) for p in ps)          # straight X, no wall


def test_id_targets_pilot_minus_001_then_previous_pass_minus_005():
    ps = plan_rough_links([_pass(1.05, 0.0, -1.0), _pass(1.10, 0.0, -1.0), _pass(1.15, 0.0, -1.0)],
                          _Stock(3.0, pilot=1.0), True, 0.01, WALL)
    assert [_retract(p)[0] for p in ps] == pytest.approx([0.999, 1.045, 0.999])
    ps = plan_rough_links([_pass(1.05, 0.0, -1.0), _pass(1.10, 0.0, -1.0), _pass(1.15, 0.0, -1.0)],
                          _Stock(3.0, pilot=1.0), True, 0.01, NO_WALL)
    assert [_retract(p)[0] for p in ps] == pytest.approx([0.999, 1.04, 0.999])      # free end: .010


def test_45_degree_pull_off_at_a_wall_capped_by_the_pass_length():
    ps = plan_rough_links([_pass(1.9, 0.0, -1.0), _pass(1.8, 0.0, -0.01), _pass(1.7, 0.0, -0.01)],
                          _Stock(2.0), False, 0.01, WALL)
    x, z = _retract(ps[0])                    # 2.005 from 1.9: .0525 radial -> +Z .0525
    assert (x, z) == pytest.approx((2.005, -1.0 + 0.0525))
    x, z = _retract(ps[1])                    # wants +.0525 but the pass is only .01 long
    assert (x, z) == pytest.approx((1.905, 0.0))


def test_id_pull_off_moves_away_from_the_wall_toward_the_mouth():
    ps = plan_rough_links([_pass(1.05, 0.0, -1.0)], _Stock(3.0, pilot=1.0), True, 0.01, WALL)
    x, z = _retract(ps[0])
    assert (x, z) == pytest.approx((0.999, -1.0 + 0.0255))


def test_highest_x_includes_an_arc_peak():
    # a convex arc from (1.8, 0) bulging to X2.0 and back to (1.8, -0.2): its
    # highest X is the peak, not an end point
    arc = ToolMove(MoveType.ARC_CW, 1.8, -0.2, feed=0.01, center_i=-0.0, center_k=-0.1)
    p = _pass(1.8, 0.0, -0.2, moves=[arc])
    lo, hi = pass_x_extent(p)
    assert hi == pytest.approx(2.0, abs=1e-9) and lo == pytest.approx(1.8)


def test_first_approach_arrives_in_front_of_the_face_then_straight_in_z():
    ps = plan_rough_links([_pass(0.95, 0.0, -1.0)], _Stock(3.0, pilot=0.9, z_start=0.05), True,
                          0.01, NO_WALL)
    a = ps[0].approach_moves
    assert (a[0].x, a[0].z) == pytest.approx((0.899, 0.10))
    assert (a[1].x, a[1].z) == pytest.approx((0.899, 0.0))
    assert a[-1].move_type == MoveType.FEED and (a[-1].x, a[-1].z) == pytest.approx((0.95, 0.0))


def test_traverse_out_of_a_pocket_goes_to_the_pocket_mouth():
    """Pass 0 covers the whole length at X1.0; then front (Z0..-.2) and back
    (Z-.5..-1) regions alternate at X0.9 and X0.8 with the part between them.
    Pass 3 (front, X0.8) retracts to X0.91 (pass 2 + .010, free end); travelling to the
    back from there would cross the part, so pass 4's approach first rises to
    X1.005 - just beyond pass 0, the pocket's mouth - not to the stock."""
    ps = plan_rough_links([_pass(1.0, 0.0, -1.0), _pass(0.9, 0.0, -0.2), _pass(0.9, -0.5, -1.0),
                           _pass(0.8, 0.0, -0.2), _pass(0.8, -0.5, -1.0)],
                          _Stock(2.0), False, 0.01, NO_WALL)
    assert _retract(ps[3]) == pytest.approx((0.91, -0.2))        # free end: pass 2 + .010
    a = ps[4].approach_moves
    assert (a[0].x, a[0].z) == pytest.approx((1.005, -0.2))      # out of the pocket first
    assert (a[1].x, a[1].z) == pytest.approx((1.005, -0.5))      # then along Z
    assert max(m.x for m in a) < 2.0


def test_traverse_with_no_covering_pass_exits_to_the_stock():
    ps = plan_rough_links([_pass(1.0, 0.0, -0.2), _pass(1.0, -0.5, -1.0)],
                          _Stock(2.0), False, 0.01, NO_WALL)
    a = ps[1].approach_moves
    assert a[0].x == pytest.approx(2.005)


def test_last_pass_exits_fully_so_the_next_section_starts_clear():
    """A neck: the last roughing pass is in the recess. Its retract goes to the
    stock (pass-1 target), not just beyond the previous pass - the cleanup
    approach rises along Z from there (2026-11-12: from X1.005 it ran .0225
    into the cleanup band on the Ø1.0 section)."""
    ps = plan_rough_links([_pass(1.3, 0.0, -1.2), _pass(1.05, 0.0, -0.4),
                           _pass(0.95, -0.4, -0.8), _pass(0.75, -0.4, -0.8)],
                          _Stock(1.4), False, 0.01, WALL)
    assert _retract(ps[-1])[0] == pytest.approx(1.405)
    assert _retract(ps[-2])[0] < 1.4                     # earlier passes keep the rule
