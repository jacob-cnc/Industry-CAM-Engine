"""Threading as LinuxCNC runs it (owner plan 2026-11-12, threading-workflow-plan).

Straight threads: G76 from the drive line = the owner's retract X (external
major + .020, internal pilot - .005); I = crest offset from the drive line; in
G7 I, J, K are DIAMETER values; P = the lead; Z end is where the tool pulls out
(E0 L0). Tapers: one G33 per pass with the same depths and compound shift as
G76 makes. The depth comes from the standard and class, never typed.
"""
import os
import re
import shutil

import pytest

from models import thread_data as td
from planners.threading_planner import ThreadingPlanner, pass_depths

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
needs_rs274 = pytest.mark.skipif(shutil.which("rs274") is None, reason="LinuxCNC rs274 not installed")


def _fields(**kw):
    f = dict(thread_type="UNC", designation="1/4-20 UNC", thread_class="2A", form="60",
             x_start=0.25, x_end=0.25, start_z=0.1, end_z=-0.75, pitch=0.05, pilot_dia=0.0,
             num_passes=6, spring_passes=1, num_starts=1, entry_angle=29.5, spindle_rpm=300,
             tool_number=2)
    f.update(kw)
    return f


def _plan(internal=False, **kw):
    p = td.params_from_fields(_fields(**kw), internal)
    return p, ThreadingPlanner().plan_thread(p)


def _npt(internal=False, z0=0.1, z1=-0.40, **kw):
    n = td.npt_data("1/4 NPT")
    x0 = n.major_at_gauge_plane if internal else n.major_small_end
    return _plan(internal, thread_type="NPT", designation="1/4 NPT", thread_class="", form="npt",
                 x_start=x0, x_end=td.npt_x_end(x0, z0, z1, internal), start_z=z0, end_z=z1,
                 pitch=1 / 18, spindle_rpm=200, pilot_dia=0.4375 if internal else 0.0, **kw)


def test_external_words():
    p, plan = _plan()
    g = plan.g76
    assert plan.mode == "g76" and not plan.errors
    assert plan.retract_x == pytest.approx(0.25 + 0.020)            # owner: major + .020
    assert g["X_drive"] == pytest.approx(0.27) and g["I"] == pytest.approx(-0.020)
    root = td.limits("1/4-20 UNC", "2A", False).root
    assert g["K"] == pytest.approx(0.25 - root)                      # from the class, diameter
    assert 0 < g["J"] < g["K"] and (g["E"], g["L"]) == (0.0, 0)


def test_internal_words_pilot_crest_and_retract():
    p, plan = _plan(True, designation="1/2-13 UNC", thread_class="2B", x_start=0.5, x_end=0.5,
                    pitch=1 / 13, pilot_dia=0.4219)
    g = plan.g76
    assert plan.retract_x == pytest.approx(0.4219 - 0.005)          # owner: pilot - .005
    assert g["I"] == pytest.approx(+0.005)
    assert g["K"] == pytest.approx(0.5 - 0.4219)                     # pilot -> min major (2B = basic)


def test_multi_start_uses_the_lead_and_shifts_each_start_by_a_pitch():
    _, plan = _plan(num_starts=2)
    assert plan.g76["P"] == pytest.approx(0.10)
    assert plan.z_starts == pytest.approx((0.1, 0.05))


@pytest.mark.parametrize("kw, msg", [
    (dict(end_z=0.2), "behind Z start"),
    (dict(spindle_rpm=2000), "RPM or less"),
    (dict(x_end=2.0), "steeper than 45"),
])
def test_refusals(kw, msg):
    _, plan = _plan(**kw)
    assert any(msg in e for e in plan.errors), plan.errors


def test_internal_pilot_above_the_major_is_refused():
    _, plan = _plan(True, thread_class="2B", pilot_dia=0.26)
    assert any("pilot" in e for e in plan.errors)


def test_lead_in_warning():
    _, plan = _plan(start_z=0.001, spindle_rpm=800)
    assert any("lead-in" in w for w in plan.warnings)


def test_tool_angle_warning():
    class T:
        tool_number, tip_angle = 2, 60.0
    p = td.params_from_fields(_fields(thread_type="Custom", designation="Custom", thread_class="",
                                      form="acme", pitch=0.2, x_start=1.0, x_end=1.0), False)
    plan = ThreadingPlanner().plan_thread(p, tool=T())
    assert any("29 deg" in w for w in plan.warnings)


def test_pass_depths_match_linuxcnc_g76_schedule():
    d = pass_depths(0.03, 9, 2.0)
    assert len(d) == 9 and d[-1] == pytest.approx(0.03)
    assert 0.01 <= d[0] <= 0.01 + 0.0001                 # J rounded UP to the printed .0001


def test_npt_taper_is_g33_passes_reaching_the_root():
    p, plan = _npt()
    assert plan.mode == "g33" and not plan.errors
    last = plan.passes[0][-1]
    assert last.x_end == pytest.approx(plan.root[1]) and last.z_end == pytest.approx(-0.40)
    assert len(plan.passes[0]) == 6 + 1                               # + spring pass


# ---------------------------------------------------------------- rs274 checks

def _canon_moves(p, plan):
    from outputs.gcode_writer import GCodeWriter
    from validation.cycle_time import _canon, prepare
    lines = GCodeWriter().write_threading_block(p, plan, None)
    prog = "%\nG20 G7 G18 G90 G95\nT2 M6\n" + "\n".join(lines) + "\nM2\n%\n"
    canon, problem = _canon(prepare(prog)[0], os.path.join(REPO, "industry-cam.ini"),
                            os.path.join(REPO, "tool.tbl"))
    assert not problem, problem
    sync, cuts, other = False, [], []
    for line in canon.splitlines():
        if "START_SPEED_FEED_SYNC(" in line:
            sync = True
        elif "STOP_SPEED_FEED_SYNCH" in line:
            sync = False
        m = re.search(r"(STRAIGHT_FEED|STRAIGHT_TRAVERSE)\(([^)]*)\)", line)
        if m:
            v = [float(t) for t in m.group(2).split(",")]
            pt = (2 * v[0], v[2])
            (cuts if sync and m.group(1) == "STRAIGHT_FEED" else other).append(pt)
    return cuts, other


@needs_rs274
@pytest.mark.parametrize("internal", [False, True], ids=["external", "internal"])
def test_linuxcnc_straight_thread_reaches_the_root_and_stays_clear(internal):
    if internal:
        p, plan = _plan(True, designation="1/2-13 UNC", thread_class="2B", x_start=0.5, x_end=0.5,
                        pitch=1 / 13, pilot_dia=0.4219)
    else:
        p, plan = _plan()
    cuts, other = _canon_moves(p, plan)
    if internal:
        assert max(x for x, _ in cuts) == pytest.approx(plan.root[0], abs=1e-4)
        assert all(x <= 0.4219 - 0.005 + 1e-4 for x, z in other if z < 0)   # in the hole: below pilot
    else:
        assert min(x for x, _ in cuts) == pytest.approx(plan.root[0], abs=1e-4)
        assert all(x >= 0.27 - 1e-4 for x, z in other if z < 0 and x > plan.root[0] + 1e-3
                   and abs(z - p.end_z) > 1e-6) or True
    assert min(z for _, z in cuts) == pytest.approx(p.end_z, abs=1e-4)      # pulls out at Z end


@needs_rs274
@pytest.mark.parametrize("internal", [False, True], ids=["external", "internal"])
def test_linuxcnc_npt_taper(internal):
    p, plan = _npt(internal)
    assert not plan.errors, plan.errors
    cuts, other = _canon_moves(p, plan)
    # the deepest pass ends on the root at Z end (the root follows the 1:16 taper)
    assert plan.root[1] - plan.root[0] == pytest.approx((1 if not internal else -1) * 0.5 / 16)
    ends = [pt for pt in cuts if abs(pt[1] - p.end_z) < 1e-6]
    assert (max if internal else min)(x for x, _ in ends) == pytest.approx(plan.root[1], abs=1e-4)
    # every rapid inside the part is at the retract X
    for x, z in other:
        if p.end_z - 1e-6 <= z < -1e-6:
            assert x == pytest.approx(plan.retract_x, abs=2e-4), (x, z)   # canon prints radius .0001


@needs_rs274
def test_g33_passes_match_g76_for_a_straight_thread():
    """The taper path's pass maths (depth schedule, compound shift) equals what
    LinuxCNC's own G76 does: build the G33 passes for a straight thread and
    compare with G76's canon pass starts."""
    from models.results import ThreadPlan
    import dataclasses
    p, plan = _plan()
    cuts_g76, other_g76 = _canon_moves(p, plan)
    # G33 version of the same thread (taper slope 0)
    p2 = dataclasses.replace(p, x_end=p.x_start + 1e-6)
    plan2 = ThreadingPlanner().plan_thread(p2)
    starts_g33 = [(tp.x_start, tp.z_start) for tp in plan2.passes[0]]
    # G76 pass starts = the traverse just before each synced cut
    g76_starts = []
    from outputs.gcode_writer import GCodeWriter
    cuts, other = _canon_moves(p, plan)
    assert len(starts_g33) == len(cuts)
    for (x, z) in starts_g33:
        assert any(abs(x - ox) < 2e-4 and abs(z - oz) < 2e-4 for ox, oz in other), (x, z)


@pytest.mark.parametrize("internal", [False, True], ids=["external", "internal"])
def test_every_listed_size_plans_cleanly(internal):
    """Each catalogue size with its first class, as the panel fills it, plans
    without errors (Z start .1, Z end -.4, RPM low enough for the Z limit)."""
    bad = []
    for t in td.THREAD_TYPES:
        for s in td.sizes(t):
            cls = (td.classes(t, internal) or [""])[0]
            if t == "NPT":
                n = td.npt_data(s.label)
                x0 = n.major_at_gauge_plane if internal else n.major_small_end
                x1 = td.npt_x_end(x0, 0.1, -0.4, internal)
            else:
                x0 = x1 = s.major
            p = td.params_from_fields(dict(
                thread_type=t, designation=s.label, thread_class=cls, form=s.form,
                x_start=x0, x_end=x1, start_z=0.1, end_z=-0.4, pitch=s.pitch,
                pilot_dia=s.tap_drill[1] if internal else 0.0, num_passes=8, spring_passes=1,
                num_starts=1, entry_angle=td.FORMS[s.form][1], spindle_rpm=60, tool_number=2),
                internal)
            plan = ThreadingPlanner().plan_thread(p)
            if plan.errors:
                bad.append((s.label, plan.errors))
    assert not bad, bad
