"""Cleanup/finish entries feed the last .020 dia of X (owner 2026-11-11).

Bench 2026-11-11: X has .0156 dia backlash, ~.0005 dia of start-of-move windup and
an acceleration-dependent outward slip. Owner approved: every cleanup, finish and
spring pass rapids to CONTOUR_FEED_IN_DIA short of its entry X on the approach side
(outside for OD, inside for ID) and FEEDS the rest, the same way every time.
"""
import os
import re
import shutil
import subprocess

import pytest

from models.constants import CONTOUR_FEED_IN_DIA
from models.moves import MoveType
from outputs.gcode_writer import GCodeWriter
from pipeline.model_builder import build_from_fields
from pipeline.pipeline import execute
from tests.integration.test_diagonal_contour_retracts import fields_for

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RS274 = shutil.which("rs274")
_MOVE = re.compile(r"\bG0?([01])\s+X(-?[\d.]+)\s+Z(-?[\d.]+)")
CASES = [(mode, passes, spring) for mode in ("od", "id") for passes, spring in ((1, False), (2, True))]


def _plan(mode, passes, spring):
    f = fields_for(mode, strategy="staircase", finish_passes=passes, finish_spring_pass=spring)
    p, s, r, fin = build_from_fields(**f)
    result = execute(p, s, f["tool_def"], r, fin)
    assert result.plan_result is not None, result.validations
    return result.plan_result


def _entries(code):
    """For each cutter-comp-on line: the last two motions that changed X before it."""
    x, changes, entries = None, [], []
    for line in code.splitlines():
        body = line.split(";")[0]
        m = _MOVE.search(body)
        if m:
            g, nx = m.group(1), float(m.group(2))
            if x is not None and abs(nx - x) > 1e-9:
                changes.append((g, x, nx))
            x = nx
        if re.search(r"\bG4[12]\b", body):
            entries.append(changes[-2:])
    return entries


@pytest.mark.parametrize("mode,passes,spring", CASES)
def test_every_contour_entry_feeds_the_last_020_from_the_approach_side(mode, passes, spring):
    plan = _plan(mode, passes, spring)
    entries = _entries(GCodeWriter().write(plan))
    assert len(entries) == len(plan.cleanup_passes) + len(plan.finish_passes)
    inward = mode == "od"
    for before, last in entries:
        g, x0, x1 = last
        assert g == "1", f"final X approach must be a feed, got G0{g} {x0}->{x1}"
        assert abs(x1 - x0) == pytest.approx(CONTOUR_FEED_IN_DIA, abs=1e-4)
        assert (x1 < x0) == inward, f"{mode}: feed-in {x0}->{x1} is from the wrong side"
        assert before[0] == "0" and before[2] == pytest.approx(x0, abs=1e-4), \
            f"feed must start where the approach rapid ended: {before} then {last}"


@pytest.mark.parametrize("mode", ["od", "id"])
def test_planned_finish_links_end_with_the_feed_in(mode):
    plan = _plan(mode, 2, True)
    side = 1.0 if mode == "od" else -1.0
    later = plan.finish_passes[1:]
    assert later, "need finish pass 2 / spring pass"
    for contour in later:
        rapid, feed = contour.approach_moves[-2], contour.approach_moves[-1]
        assert feed.move_type == MoveType.FEED and feed.feed > 0
        assert rapid.move_type == MoveType.RAPID
        assert rapid.x - feed.x == pytest.approx(side * CONTOUR_FEED_IN_DIA)
        assert rapid.z == pytest.approx(feed.z)


def test_feed_in_is_longer_than_the_measured_x_backlash():
    assert CONTOUR_FEED_IN_DIA > 0.0156          # bench 2026-11-11, total, diameter


@pytest.mark.skipif(RS274 is None, reason="LinuxCNC rs274 not installed")
@pytest.mark.parametrize("mode", ["od", "id"])
def test_linuxcnc_interpreter_runs_the_feed_in_program(tmp_path, mode):
    code = GCodeWriter().write(_plan(mode, 2, True))
    for name in ("industry-cam.ini", "tool.tbl"):
        shutil.copy(os.path.join(REPO, name), tmp_path / name)
    var = os.path.join(REPO, "industry-cam.var")
    if os.path.exists(var):
        shutil.copy(var, tmp_path / "industry-cam.var")
    else:
        (tmp_path / "industry-cam.var").write_text("5220\t1.000000\n")
    (tmp_path / "p.ngc").write_text(code)
    run = subprocess.run([RS274, "-i", "industry-cam.ini", "-t", "tool.tbl", "-v",
                          "industry-cam.var", "p.ngc", "c.txt"], cwd=tmp_path,
                         stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)
    canon = (tmp_path / "c.txt").read_text()
    assert "PROGRAM_END" in canon, run.stdout[-2000:] + run.stderr[-2000:]
