"""Cycle-time estimate from the G-code as LinuxCNC runs it (validation/cycle_time.py)."""
import math
import os
import shutil

import pytest

from validation.cycle_time import _cap, _trapezoid, estimate_for_machine, fmt_duration, prepare

needs_rs274 = pytest.mark.skipif(shutil.which("rs274") is None, reason="LinuxCNC rs274 not installed")


def test_trapezoid_and_triangle_profiles():
    assert _trapezoid(1.0, 0.5, 2.0) == pytest.approx(1.0 / 0.5 + 0.5 / 2.0)   # reaches v
    assert _trapezoid(0.01, 0.5, 2.0) == pytest.approx(2 * math.sqrt(0.01 / 2.0))


def test_axis_caps_limit_the_vector_speed():
    # pure Z move: Z axis 0.75 but TRAJ 0.5 -> 0.5; pure X: 1.8 vs 0.5 -> 0.5
    assert _cap(0.0, 1.0, 0.5, 1.8, 0.75) == pytest.approx(0.5)
    # 45 deg: Z component may not exceed 0.3 -> vector 0.3*sqrt2
    assert _cap(1.0, 1.0, 1.0, 1.8, 0.3) == pytest.approx(0.3 * math.sqrt(2))


def test_prepare_strips_tool_checks_and_counts_stops():
    src = ("N10 T4 M6\no9001 if [#5400 NE 4]\n  (DEBUG, x)\n  M0\no9001 endif\n"
           "N20 M1 ; optional\nN30 M0\nN40 G0 X1 Z1\n")
    prog, tc, m0, m1 = prepare(src)
    lines = prog.splitlines()
    assert len(lines) == len(src.splitlines())                  # line numbers kept
    assert "o9001" not in prog and "M1" not in lines[5] and "M0" not in lines[6]
    assert (tc, m0, m1) == (1, 1, 1)                            # the M0 inside the check is not counted


def test_fmt_duration():
    assert fmt_duration(65) == "1:05" and fmt_duration(3725) == "1:02:05"


@needs_rs274
def test_a_feed_move_is_timed_at_feed_per_rev_times_rpm():
    """G95 F.005 at S600 = 3 in/min = .05 in/s: a 1.2 in cut takes 24 s."""
    gcode = ("%\nN10 G20 G7 G18 G40 G49 G80\nN20 G90 G95\nN30 S600 M3\nN40 T4 M6\nN50 G43\n"
             "N60 G0 X1.0 Z0.1\nN70 G1 X1.0 Z-1.1 F0.005\nN80 M5\nN90 M2\n%\n")
    est = estimate_for_machine(gcode)
    assert est.complete, est.problem
    assert est.cutting_s == pytest.approx(24.0, rel=1e-6)
    assert est.tool_changes == 1
    # time left: after the cut only nothing remains
    lines = gcode.splitlines()
    cut = next(i for i, l in enumerate(lines) if l.startswith("N70"))
    assert est.remaining_after_line[cut] == pytest.approx(0.0, abs=1e-9)
    assert est.remaining_after_line[cut - 1] == pytest.approx(24.0, rel=1e-6)


@needs_rs274
def test_interpreter_errors_make_an_incomplete_estimate():
    gcode = "%\nN10 G20 G7 G18\nN20 G95 S400 M3\nN30 G0 X0.3 Z0.1\nN40 G76 P0.05 Z-0.5 I0 J0.01 K0.03\nN50 M2\n%\n"
    est = estimate_for_machine(gcode)
    assert not est.complete and "G76" in est.problem
