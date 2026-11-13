"""The sim path from LinuxCNC's interpreter (tool-graphic plan 2026-11-13, T4)."""
import math
import os
import shutil

import pytest
from shapely.geometry import LineString, Point

from models.tool import Q_TIP_DIRECTION
from validation.sim_path import number_lines, parse_sim_canon, sim_path

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INI = os.path.join(REPO, "industry-cam.ini")
needs_rs274 = pytest.mark.skipif(shutil.which("rs274") is None, reason="LinuxCNC rs274 not installed")

R = 0.015625                                   # nose radius in the test table
TABLE = (f"T4 P4 X+0.100000 Z-0.250000 D{2 * R:f} I95.0 J175.0 Q2 ;\n"
         f"T1 P1 X+0.050000 Z+0.300000 D{2 * R:f} I95.0 J175.0 Q3 ;\n"
         f"T2 P2 X+0.000000 Z+0.000000 D0.016000 I60.0 J120.0 Q2 ;\n")


@pytest.fixture
def table(tmp_path):
    p = tmp_path / "tool.tbl"
    p.write_text(TABLE)
    return str(p)


def test_number_lines_keeps_the_line_count_and_replaces_n_words():
    src = "G20\n\nN10 G0 X1\no100 if [1]\n%\n(comment)\n"
    got = number_lines(src).splitlines()
    assert got == ["N1 G20", "", "N3 G0 X1", "o100 if [1]", "%", "N6 (comment)"]


def test_parse_canon_tools_offsets_kinds_and_mm():
    canon = """\
    1 N..... USE_LENGTH_UNITS(CANON_UNITS_INCHES)
    2 N00002 SELECT_TOOL(4)
    3 N00002 CHANGE_TOOL(1)
    4 N00002 USE_TOOL_LENGTH_OFFSET(0.1000 0.0000 -0.2500, 0.0000 0.0000 0.0000, 0.0000 0.0000 0.0000)
    5 N00003 STRAIGHT_TRAVERSE(0.5000, 0.0000, 0.1000, 0.0000, 0.0000, 0.0000)
    6 N00004 STRAIGHT_FEED(0.5000, 0.0000, -0.5000, 0.0000, 0.0000, 0.0000)
    7 N00005 START_SPEED_FEED_SYNCH(0.0500, 0)
    8 N00005 STRAIGHT_FEED(0.4800, 0.0000, -1.0000, 0.0000, 0.0000, 0.0000)
    9 N00005 STOP_SPEED_FEED_SYNCH()
   10 N00006 USE_LENGTH_UNITS(CANON_UNITS_MM)
   11 N00006 STRAIGHT_TRAVERSE(25.4000, 0.0000, 25.4000, 0.0000, 0.0000, 0.0000)
"""
    segs = parse_sim_canon(canon)
    assert [s.kind for s in segs] == ["feed", "thread", "rapid"]
    assert [s.line_idx for s in segs] == [3, 4, 5]
    assert all(s.tool == 4 and s.tool_offset == pytest.approx((0.1, -0.25)) for s in segs)
    assert segs[-1].pts[-1] == pytest.approx((1.0, 1.0))


@needs_rs274
def test_tool_change_per_t_word_with_its_offset(table):
    prog = "G18 G20 G7 G90\nT4 M6 G43\nG0 X1.0 Z0.1\nG1 Z-0.5 F5\nT1 M6 G43\nG0 X0.5 Z0.1\nG0 X0.4\nM2\n"
    p = sim_path(prog, INI, table)
    assert p.problem == ""
    assert [(s.tool, s.line_idx) for s in p.segments] == [(4, 3), (1, 5), (1, 6)]
    assert p.segments[0].tool_offset == pytest.approx((0.1, -0.25))
    assert p.segments[-1].tool_offset == pytest.approx((0.05, 0.3))


@needs_rs274
def test_tool_change_without_g43_has_no_offset(table):
    p = sim_path("G18 G20 G7 G90\nT4 M6\nG0 X1.0 Z0.1\nG0 X0.9\nM2\n", INI, table)
    assert p.segments[0].tool == 4 and p.segments[0].tool_offset is None


def _profile():
    """Programmed (uncompensated) OD contour, (r, z): a 45 deg chamfer, a
    straight, a G2 R.1 radius into a shoulder."""
    pts = [(0.4, 0.0), (0.5, -0.1), (0.5, -0.4)]
    c = (0.6, -0.4)                                       # centre of the R.1 arc
    arc = [(c[0] - 0.1 * math.cos(a), c[1] - 0.1 * math.sin(a))
           for a in [k * (math.pi / 2) / 200 for k in range(201)]]
    return LineString(pts + arc[1:] + [(0.8, -0.5)])


@needs_rs274
def test_g42_nose_touches_the_programmed_profile(table):
    """Plan check 4.2: under LinuxCNC's G42 the nose circle (centre = canon
    tip - R x Q direction) is tangent to the programmed profile everywhere
    along the cut: centre distance = R within .0001 (rs274 prints 4 decimals)."""
    prog = ("G18 G20 G7 G90 G95\nT4 M6 G43\nS500 M3\nG0 X0.7 Z0.2\nG0 X0.7 Z0.05\n"
            "G42 G1 X0.8 Z0.0 F.004\nG1 X1.0 Z-0.1\nG1 Z-0.4\nG2 X1.2 Z-0.5 I0.1\n"
            "G1 X1.6\nG40 G0 X2.0 Z0.2\nM2\n")
    p = sim_path(prog, INI, table)
    assert p.problem == ""
    dr, dz = Q_TIP_DIRECTION[2]
    prof = _profile()
    lines = [s.line_idx for s in p.segments]
    # comp-delayed moves are given back to their own block (rs274 prints each
    # one under the NEXT motion block): entry, chamfer, straight, R.1, shoulder
    assert lines == [4, 5, 6, 6, 7, 8, 9, 10]       # (the corner arc goes with the chamfer)
    cut = [s for s in p.segments if s.line_idx in (6, 7, 8, 9)]
    assert cut and {s.kind for s in cut} >= {"feed", "arc"}
    worst = 0.0
    for s in cut:
        for r, z in s.resampled(400):
            centre = Point(r - dr * R, z - dz * R)
            worst = max(worst, abs(prof.distance(centre) - R))
    assert worst < 1e-4, worst


@needs_rs274
def test_g76_is_linuxcnc_s_own_passes(table):
    prog = ("G18 G20 G7 G90\nT2 M6 G43\nG0 X1.1 Z0.1\nS300 M3\n"
            "G76 P0.0625 Z-0.75 I-0.04 J0.02 K0.08 Q29.5 R2 E0.02 L2 H1\nG0 X1.2\nM2\n")
    p = sim_path(prog, INI, table)
    assert p.problem == ""
    threads = [s for s in p.segments if s.kind == "thread"]
    assert len(threads) >= 4 and all(s.line_idx == 4 for s in threads)
    # the last pass reaches I + K below the drive line - DIAMETER values in G7
    # (LinuxCNC halves them; the threading planner writes them as diameters)
    assert min(min(pt[0] for pt in s.pts) for s in threads) == pytest.approx(0.55 - 0.02 - 0.04, abs=1e-4)


@needs_rs274
def test_interpreter_error_is_reported_with_the_path_so_far(table):
    p = sim_path("G18 G20 G7 G90\nT4 M6 G43\nG0 X1 Z0.1\nG1 Z-0.5 F5\nG2 X1.2 Z-0.6\nM2\n", INI, table)
    assert "G2" in p.problem and len(p.segments) == 1


@needs_rs274
def test_comp_line_attribution_with_g42_alone_and_a_feed_only_line(table):
    prog = ("G18 G20 G7 G90 G95\nT4 M6 G43\nS500 M3\nG0 X0.7 Z0.05\nG42\n"
            "G1 X0.8 Z0.0 F.004\nG1 X1.0 Z-0.1\nF.002\n(note)\nG1 Z-0.4\nG40 G0 X2.0\nM2\n")
    p = sim_path(prog, INI, table)
    assert p.problem == ""
    assert sorted({s.line_idx for s in p.segments if not s.kind == "rapid"}) == [5, 6, 9]
    assert [s.line_idx for s in p.segments if s.kind == "rapid"] == [10]
