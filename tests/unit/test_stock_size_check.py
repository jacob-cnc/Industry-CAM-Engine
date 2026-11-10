"""Stock-size check: a profile stretch running along the stock surface (with
more profile after it), or a point outside the stock, is a settings error
with a readable message - not a kernel 'clipping' failure. Ending on the
stock surface (a step out to the bar / down to the pilot) stays valid."""

import pytest

from pipeline.model_builder import _check_stock_size, profile_from_fields


def _prof(points, mode="od"):
    return profile_from_fields([{"type": "line", "x": d, "z": z} for d, z in points], mode)


OWNER = [(0.5, 0.0), (0.5, -0.5), (1.0, -0.5), (1.0, -1.0), (0.5, -1.0), (0.5, -1.5)]


def test_owner_profile_with_stock_equal_to_largest_diameter():
    with pytest.raises(ValueError) as exc:
        _check_stock_size(_prof(OWNER), stock_dia=1.0, pilot_hole_dia=0.0, fin_allowance=0.002)
    msg = str(exc.value)
    assert "runs along Ø1.0000 from Z -0.5000 to Z -1.0000" in msg
    assert "larger than Ø1.0020" in msg and "Increase Stock > Diameter" in msg


def test_owner_profile_with_enough_stock_passes():
    _check_stock_size(_prof(OWNER), stock_dia=1.1, pilot_hole_dia=0.0, fin_allowance=0.002)


def test_step_out_to_stock_at_the_end_is_valid():
    _check_stock_size(_prof([(0.5, 0.0), (0.5, -0.6), (1.0, -0.6)]), stock_dia=1.0,
                      pilot_hole_dia=0.0, fin_allowance=0.01)
    _check_stock_size(_prof([(0.5, 0.0), (0.5, -0.6), (1.0, -0.6), (1.0, -1.0)]),
                      stock_dia=1.0, pilot_hole_dia=0.0, fin_allowance=0.01)


def test_point_outside_stock():
    with pytest.raises(ValueError, match="goes outside the stock"):
        _check_stock_size(_prof([(0.5, 0.0), (1.2, -0.5), (1.2, -1.0)]), stock_dia=1.0,
                          pilot_hole_dia=0.0, fin_allowance=0.002)


def test_id_stretch_along_pilot_hole():
    pts = [(2.0, 0.0), (2.0, -0.5), (1.0, -0.5), (1.0, -1.0), (1.5, -1.0), (1.5, -1.5)]
    with pytest.raises(ValueError, match="pilot hole is too large"):
        _check_stock_size(_prof(pts, "id"), stock_dia=3.0, pilot_hole_dia=1.0,
                          fin_allowance=0.002)
    _check_stock_size(_prof(pts, "id"), stock_dia=3.0, pilot_hole_dia=0.9, fin_allowance=0.002)
