"""Tests for CompoundJogEngine (hal/compound_router.py).

Machine facts used here (industry-cam.hal mux8 index 1, 0.001"/click):
    joint.0 (X, radius units) jog-scale = 0.000125 per count
    joint.1 (Z)               jog-scale = 0.00025  per count
Joint limits from industry-cam.ini: X -0.01..4.25, Z -3.0..3.0.
"""

import math

import pytest

from hal.compound_logic import ArcStartType, Quadrant
from hal.compound_router import CompoundJogEngine

X_SCALE = 0.000125
Z_SCALE = 0.00025
LIMITS = (-0.01, 4.25, -3.0, 3.0)


def make(mode="linear", angle=45.0, x=2.0, z=0.0, counts=1000):
    eng = CompoundJogEngine(LIMITS)
    eng.start(x, z, counts, mode=mode, angle_deg=angle)
    return eng


def physical(step_x_total, step_z_total):
    """Physical machine displacement for cumulative output counts."""
    return step_x_total * X_SCALE, step_z_total * Z_SCALE


class TestFirstSampleAndIdle:
    def test_no_motion_without_count_change(self):
        eng = make(counts=12345)
        assert eng.step(12345, Z_SCALE, X_SCALE, Z_SCALE) is None
        assert (eng.x_total, eng.z_total) == (0, 0)

    def test_large_absolute_count_is_not_a_delta(self):
        # Raw encoder value at activation must never be treated as motion.
        eng = make(counts=-987654)
        s = eng.step(-987650, Z_SCALE, X_SCALE, Z_SCALE)
        dx, dz = physical(s.x_total, s.z_total)
        assert math.hypot(dx, dz) == pytest.approx(4 * Z_SCALE, abs=Z_SCALE)

    def test_inactive_engine_emits_nothing(self):
        eng = make()
        eng.stop()
        assert eng.step(2000, Z_SCALE, X_SCALE, Z_SCALE) is None


class TestLinearGeometry:
    @pytest.mark.parametrize("angle", [29.5, 45.0, 60.0, 30.0, 10.0])
    def test_true_angle_in_radius_space(self, angle):
        # 400 counts = one MPG revolution = 0.1" of path at 0.00025"/count
        eng = make(angle=angle)
        for c in range(1001, 1401):
            eng.step(c, Z_SCALE, X_SCALE, Z_SCALE)
        dx, dz = physical(eng.x_total, eng.z_total)
        measured = math.degrees(math.atan2(abs(dx), abs(dz)))
        assert measured == pytest.approx(angle, abs=0.1)
        assert math.hypot(dx, dz) == pytest.approx(0.1, abs=0.0005)

    def test_positive_angle_couples_x_minus_z_plus(self):
        eng = make(angle=45.0)
        eng.step(1400, Z_SCALE, X_SCALE, Z_SCALE)
        assert eng.x_total < 0 < eng.z_total

    def test_negative_angle_couples_x_minus_z_minus(self):
        eng = make(angle=-45.0)
        eng.step(1400, Z_SCALE, X_SCALE, Z_SCALE)
        assert eng.x_total < 0 and eng.z_total < 0

    def test_reverse_rotation_returns_to_start(self):
        eng = make(angle=29.5)
        for c in range(1001, 1301):
            eng.step(c, Z_SCALE, X_SCALE, Z_SCALE)
        for c in range(1299, 999, -1):
            eng.step(c, Z_SCALE, X_SCALE, Z_SCALE)
        assert abs(eng.x_total) <= 1 and abs(eng.z_total) <= 1

    def test_virtual_position_tracks_emitted_counts(self):
        eng = make(angle=45.0, x=2.0, z=0.5)
        for c in range(1001, 1201):
            eng.step(c, Z_SCALE, X_SCALE, Z_SCALE)
        assert eng.x_r == pytest.approx(2.0 + eng.x_total * X_SCALE)
        assert eng.z == pytest.approx(0.5 + eng.z_total * Z_SCALE)

    def test_fractional_counts_are_not_lost(self):
        # 10 deg: X gets sin(10)*0.00025/0.000125 = 0.347 counts per input count.
        eng = make(angle=10.0)
        for c in range(1001, 1101):
            eng.step(c, Z_SCALE, X_SCALE, Z_SCALE)
        expected_x = -100 * Z_SCALE * math.sin(math.radians(10)) / X_SCALE
        assert eng.x_total == pytest.approx(expected_x, abs=1)


class TestLimitsAndSafety:
    def test_uses_machine_limits_not_legacy_constants(self):
        # Legacy constants put Z min at -0.01; real joint 1 min is -3.0.
        eng = make(angle=-45.0, x=2.0, z=-1.0)
        s = eng.step(1100, Z_SCALE, X_SCALE, Z_SCALE)
        assert s is not None and s.z_total < 0

    def test_stops_at_z_limit_without_moving_x_alone(self):
        eng = make(angle=45.0, x=2.0, z=2.9999)
        s = eng.step(1100, Z_SCALE, X_SCALE, Z_SCALE)
        assert s is None
        assert (eng.x_total, eng.z_total) == (0, 0)

    @pytest.mark.parametrize("xs,zs", [(0.0, Z_SCALE), (X_SCALE, 0.0), (0.0, 0.0)])
    def test_unwired_scale_never_emits(self, xs, zs):
        eng = make()
        assert eng.step(1400, zs, xs, zs) is None
        assert (eng.x_total, eng.z_total) == (0, 0)

    def test_bad_mode_rejected(self):
        with pytest.raises(ValueError):
            make(mode="spiral")


class TestArc:
    def test_arc_stays_on_radius(self):
        eng = CompoundJogEngine(LIMITS)
        eng.arc.activate(2.0, 0.0, 0.25, Quadrant.SE, ArcStartType.ARC_TOP)
        cx, cz = eng.arc.arc_center_x, eng.arc.arc_center_z
        eng.start(2.0, 0.0, 0, mode="arc")
        for c in range(1, 600):
            eng.step(c, Z_SCALE, X_SCALE, Z_SCALE)
            r = math.hypot(eng.x_r - cx, eng.z - cz)
            assert r == pytest.approx(0.25, abs=0.0005)
        assert (eng.x_total, eng.z_total) != (0, 0)


class TestJogWindow:
    """Mirror of LinuxCNC refresh_jog_limits (motion/command.c)."""

    def test_homed_uses_position_limits(self):
        from hal.compound_router import jog_window
        assert jog_window(True, 1.0, -0.01, 4.25) == (-0.01, 4.25)

    def test_unhomed_window_follows_position(self):
        from hal.compound_router import jog_window
        lo, hi = jog_window(False, -1.5, -0.01, 4.25)
        assert lo == pytest.approx(-1.5 - 4.26) and hi == pytest.approx(-1.5 + 4.26)

    def test_unhomed_position_outside_ini_limits_still_moves(self):
        # Regression 2026-11-08: unhomed X at -1.5 (outside -0.01..4.25)
        # suppressed every compound pulse.
        from hal.compound_router import jog_window
        x = jog_window(False, -1.5, -0.01, 4.25)
        z = jog_window(False, 0.0, -3.0, 3.0)
        eng = CompoundJogEngine((x[0], x[1], z[0], z[1]))
        eng.start(-1.5, 0.0, 0, angle_deg=45.0)
        assert eng.step(400, Z_SCALE, X_SCALE, Z_SCALE) is not None
        assert eng.suppressed == 0


ALL_ARC_CONFIGS = [(q, st) for q in Quadrant for st in ArcStartType]


class TestArcNoJump:
    """Regression 2026-11-08 bench: one backward MPG click at an arc start
    boundary ran the entire quadrant (machine X +0.5 r, Z -0.5) at jog speed."""

    @pytest.mark.parametrize("q,st", ALL_ARC_CONFIGS)
    @pytest.mark.parametrize("sign", [+1, -1])
    def test_one_click_never_exceeds_commanded_path(self, q, st, sign):
        eng = CompoundJogEngine(LIMITS)
        eng.arc.activate(0.0945, 0.0, 0.5, q, st)
        eng.start(0.0945, 0.0, 756, mode="arc")
        s = eng.step(756 + sign * 4, Z_SCALE, X_SCALE, Z_SCALE)  # one click
        if s is not None:
            dx, dz = physical(s.x_total, s.z_total)
            assert math.hypot(dx, dz) <= 4 * Z_SCALE + 0.0005
        assert eng.rejected == 0

    @pytest.mark.parametrize("q,st", ALL_ARC_CONFIGS)
    def test_forward_traverses_quadrant_then_stops_backward_returns(self, q, st):
        R = 0.25
        eng = CompoundJogEngine(LIMITS)
        eng.arc.activate(1.0, 0.0, R, q, st)
        eng.start(1.0, 0.0, 0, mode="arc")
        # Backward first: must not move at all (already at the start end)
        assert eng.step(-4, Z_SCALE, X_SCALE, Z_SCALE) is None
        eng._last_counts = 0
        arc_len = math.pi / 2 * R
        n = int(arc_len / Z_SCALE) + 400       # beyond the end on purpose
        for c in range(1, n + 1):
            eng.step(c, Z_SCALE, X_SCALE, Z_SCALE)
        dx, dz = physical(eng.x_total, eng.z_total)
        assert abs(dx) == pytest.approx(R, abs=0.001)
        assert abs(dz) == pytest.approx(R, abs=0.001)
        for c in range(n - 1, -1, -1):
            eng.step(c, Z_SCALE, X_SCALE, Z_SCALE)
        dx, dz = physical(eng.x_total, eng.z_total)
        # back within ~1 count of start (the overshoot past the end was dropped)
        assert abs(dx) < 0.002 and abs(dz) < 0.002
        assert eng.rejected == 0


class TestJumpGuard:
    def test_guard_refuses_oversized_step(self):
        eng = make(mode="arc")
        # Corrupt arc state: tool at center -> target is a full radius away
        eng.arc.arc_center_x, eng.arc.arc_center_z = 2.0, 0.0
        eng.arc.radius, eng.arc.angle_start, eng.arc.angle_end = 0.5, 0.0, math.pi / 2
        eng.arc.current_angle = 0.0
        assert eng.step(1004, Z_SCALE, X_SCALE, Z_SCALE) is None
        assert eng.rejected == 1
        assert (eng.x_total, eng.z_total) == (0, 0)


class TestUserArcSelection:
    """resolve_user_arc must equal the inline mapping that was machine-verified
    on 2026-11-08 (manual_tab before refactor)."""

    @staticmethod
    def _old_mapping(user_idx, start_idx):
        q = [Quadrant.SE, Quadrant.SW, Quadrant.NW, Quadrant.NE][user_idx]
        st = ArcStartType.ARC_TOP if start_idx == 0 else ArcStartType.ARC_BOTTOM
        if user_idx in (0, 1):
            st = (ArcStartType.ARC_BOTTOM if st == ArcStartType.ARC_TOP
                  else ArcStartType.ARC_TOP)
        return q, st

    @pytest.mark.parametrize("u", range(4))
    @pytest.mark.parametrize("s", range(2))
    def test_matches_verified_mapping(self, u, s):
        from hal.compound_logic import resolve_user_arc
        assert resolve_user_arc(u, s) == self._old_mapping(u, s)

    @pytest.mark.parametrize("u", range(4))
    @pytest.mark.parametrize("s", range(2))
    def test_endpoint_angles_match_motion(self, u, s):
        """Blue dot = where the tool starts, red dot = where the arc ends."""
        from hal.compound_logic import resolve_user_arc, arc_endpoint_angles
        q, st = resolve_user_arc(u, s)
        a0, a1 = arc_endpoint_angles(q, st)
        eng = CompoundJogEngine(LIMITS)
        eng.arc.activate(1.0, 0.0, 0.25, q, st)
        cx, cz = eng.arc.arc_center_x, eng.arc.arc_center_z
        # start dot == tool position
        assert 1.0 == pytest.approx(cx + 0.25 * math.sin(a0), abs=1e-9)
        assert 0.0 == pytest.approx(cz + 0.25 * math.cos(a0), abs=1e-9)
        # run forward to the end: final position == end dot
        eng.start(1.0, 0.0, 0, mode="arc")
        for c in range(1, 2000):
            eng.step(c, Z_SCALE, X_SCALE, Z_SCALE)
        assert eng.x_r == pytest.approx(cx + 0.25 * math.sin(a1), abs=0.001)
        assert eng.z == pytest.approx(cz + 0.25 * math.cos(a1), abs=0.001)
