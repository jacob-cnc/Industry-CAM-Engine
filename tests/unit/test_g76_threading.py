"""G76 threading as LinuxCNC means it (2.9 manual; owner 2026-11-12).

Drive line = the tool's X before G76; I = crest offset FROM the drive line
(negative external, positive internal); J / K = depths beyond the crest; in G7
I, J, K are DIAMETER values; P = distance per spindle rev = the LEAD. The drive
line sits .020 (diameter) outside the crest. Until 2026-11-12: I0 (LinuxCNC
error), radial J/K read as diameters (half-depth threads), internal threads
approached at the MAJOR diameter (into the bore wall), P = pitch on multi-start.
"""
import os
import re
import shutil

import pytest

from models.program import ThreadingParams
from planners.threading_planner import ThreadingPlanner


def _params(internal=False, starts=1, chamfer=0.0, taper=0.0, major=0.2448, depth=0.0271,
            z0=0.05, z1=-0.77):
    return ThreadingParams(
        thread_standard="UNC", designation="1/4-20 UNC", major_diameter=major, pitch=0.05,
        thread_depth=depth, start_z=z0, end_z=z1, infeed_method="modified_flank", num_passes=6,
        spring_passes=2, chamfer_threads=chamfer, is_internal=internal, spindle_rpm=400, tool_number=2,
        num_starts=starts, taper_amount=taper)


def test_external_words():
    g = ThreadingPlanner().compute_g76_params(_params())
    assert g["I"] == pytest.approx(-0.020)
    assert g["X_drive"] == pytest.approx(0.2448 + 0.020)
    assert g["K"] == pytest.approx(2 * 0.0271)                 # diameter, G7
    assert 0 < g["J"] < g["K"]
    assert g["X_safe"] > g["X_drive"]
    assert (g["E"], g["L"]) == (0.0, 0)


def test_internal_words_approach_from_inside_the_bore():
    g = ThreadingPlanner().compute_g76_params(_params(internal=True, major=1.0, depth=0.0271))
    crest = 1.0 - 2 * 0.0271                                   # minor = bore
    assert g["crest"] == pytest.approx(crest)
    assert g["X_drive"] == pytest.approx(crest - 0.020)
    assert g["I"] == pytest.approx(+0.020)
    assert g["X_safe"] < g["X_drive"] < crest


def test_multi_start_uses_the_lead_and_shifts_each_start_by_a_pitch():
    g = ThreadingPlanner().compute_g76_params(_params(starts=2))
    assert g["P"] == pytest.approx(0.10)
    assert g["Z_start"] == pytest.approx([0.05, 0.0])


def test_pull_out_chamfer_is_an_exit_taper():
    g = ThreadingPlanner().compute_g76_params(_params(chamfer=1.0))
    assert (g["E"], g["L"]) == (pytest.approx(0.05), 2)


def test_tapered_threads_are_refused():
    with pytest.raises(ValueError, match="Tapered threads"):
        ThreadingPlanner().compute_g76_params(_params(taper=0.0625))


@pytest.mark.skipif(shutil.which("rs274") is None, reason="LinuxCNC rs274 not installed")
@pytest.mark.parametrize("internal", [False, True], ids=["external", "internal"])
def test_linuxcnc_cuts_the_full_depth_and_stays_clear(internal):
    from outputs.gcode_writer import GCodeWriter
    from validation.cycle_time import _canon, prepare
    from models.tool import ToolDef, ToolDirection, ToolOrientation, ToolType
    params = _params(internal=internal, major=1.0 if internal else 0.2448)
    g = ThreadingPlanner().compute_g76_params(params)
    tool = ToolDef(2, 0.016, 60, 0.5, ToolOrientation(2), ToolDirection.RIGHT,
                   ToolType.THREADING, front_angle=60.0, back_angle=120.0)
    lines = GCodeWriter().write_threading_block(params, g, tool, 1.5)
    prog = "%\nG20 G7 G18 G90 G95\nT2 M6\n" + "\n".join(lines) + "\nM2\n%\n"
    repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    canon, problem = _canon(prepare(prog)[0], os.path.join(repo, "industry-cam.ini"),
                            os.path.join(repo, "tool.tbl"))
    assert not problem, problem
    sync, xs, before = False, [], []
    for line in canon.splitlines():
        if "START_SPEED_FEED_SYNC(" in line:
            sync = True
        elif "STOP_SPEED_FEED_SYNCH" in line:
            sync = False
        m = re.search(r"(STRAIGHT_FEED|STRAIGHT_TRAVERSE)\(([^)]*)\)", line)
        if m:
            x = 2 * float(m.group(2).split(",")[0])
            (xs if sync else before).append(x)
    crest, depth = g["crest"], g["K"]
    if internal:
        assert max(xs) == pytest.approx(crest + depth, abs=1e-4)        # out to the major
        assert all(x <= crest + 1e-9 for x in before[:3])                # approach stays in the bore
    else:
        assert min(xs) == pytest.approx(crest - depth, abs=1e-4)        # down to the minor
