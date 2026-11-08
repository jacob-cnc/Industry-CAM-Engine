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
