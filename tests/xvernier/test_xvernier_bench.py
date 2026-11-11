"""X vernier: offline bench + calibration fit (no realtime, no HAL, no machine).

Builds tests/xvernier/bench.c against the estimator core extracted verbatim
from rtcomp/xvernier.comp, then checks, in DIAMETER inches:
  * the bench reproduces today's loop (~.0009 parking error) and Step 1 (~.0002-.0004)
  * scripts/xvernier/fit_calibration.py recovers the simulated machine
  * sweep -> fit -> calibrated vernier holds the finish-pass scenarios to ~.0001
  * a sudden slip (lost steps) latches the fault and the estimate recovers
docs/handoffs/2026-11-10-x-vernier-commissioning.md
"""
import json
import os
import re
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
FIT = os.path.join(REPO, "scripts", "xvernier", "fit_calibration.py")

pytestmark = pytest.mark.skipif(shutil.which("gcc") is None, reason="needs gcc")


@pytest.fixture(scope="module")
def bench(tmp_path_factory):
    out = tmp_path_factory.mktemp("xvbench")
    subprocess.run([os.path.join(HERE, "build_bench.sh"), str(out)], check=True,
                   capture_output=True, text=True)
    return out


def _run(bench, plants, env=None, loop=None, scen=None):
    e = dict(os.environ)
    e.update(env or {})
    if loop:
        e["XV_LOOP"] = loop
    if scen:
        e["XV_SCEN"] = scen
    out = subprocess.run([str(bench / "xv_bench")] + plants, check=True, capture_output=True,
                         text=True, env=e).stdout
    res = {}
    for line in out.splitlines():
        f = line.split()
        if f and f[0] == "RESULT":
            kv = dict(x.split("=") for x in f[4:])
            res[(f[1], f[2], f[3])] = {k: float(v) for k, v in kv.items()}
    return res


def _fit(bench, plant):
    cap = bench / f"sweep_{plant}.txt"
    subprocess.run([str(bench / "xv_bench"), "--sweep", plant, str(cap)], check=True)
    out = subprocess.run([sys.executable, FIT, str(cap), "--json"], check=True,
                         capture_output=True, text=True).stdout
    return json.loads(out)


def test_bench_reproduces_todays_loop_and_step1(bench):
    r = _run(bench, ["nominal"])
    assert 0.0007 < r[("scale-db5", "face-up", "nominal")]["max"] < 0.0011
    assert r[("scale-db11", "rapid-in", "nominal")]["max"] > 0.0003        # the .0004 grid


@pytest.mark.parametrize("plant,h,lead,amp,slope", [
    ("nominal", 0.0001, 0.059, 0.00008, 2e-4),
    ("loose", 0.0004, 0.059, 0.00015, 5e-4),
])
def test_fit_recovers_the_machine(bench, plant, h, lead, amp, slope):
    d = _fit(bench, plant)
    # "loose" also has .05 count of scale edge hysteresis, which is indistinguishable
    # from backlash and lands in H_INIT (+.000005 r, ~.00001 dia: harmless)
    assert d["H_INIT"] == pytest.approx(h, abs=1e-5)
    assert d["LEAD"] == pytest.approx(lead, rel=0.002)
    assert d["harm_amp"] == pytest.approx(amp, rel=0.05)
    assert d["SLOPE"] == pytest.approx(slope, rel=0.05)
    assert d["resid_rms"] < 3e-5


def test_fit_finds_no_harmonic_when_there_is_none(bench):
    d = _fit(bench, "only-backlash")
    assert d["LEAD"] == 0.0


@pytest.mark.parametrize("plant", ["nominal", "loose", "laggy", "warming"])
def test_calibrated_vernier_holds_a_tenth(bench, plant):
    d = _fit(bench, plant)
    cal = " ".join(str(d[k]) for k in ("H_INIT", "LEAD", "HARM_COS", "HARM_SIN", "SLOPE", "LAG_TIME"))
    r = _run(bench, [plant], env={"XV_CAL": cal}, loop="vern-cal")
    for scen in ("face-up", "face-down", "wear-steps"):
        st = r[("vern-cal", scen, plant)]
        assert st["max"] <= 0.00012, (scen, st)
        assert st["fault"] == 0, (scen, st)
    assert r[("vern-cal", "rapid-in", plant)]["max"] <= 0.00016


def test_lost_steps_fault_and_recover(bench):
    d = _fit(bench, "nominal")
    cal = " ".join(str(d[k]) for k in ("H_INIT", "LEAD", "HARM_COS", "HARM_SIN", "SLOPE", "LAG_TIME"))
    r = _run(bench, ["nominal"], env={"XV_CAL": cal}, loop="vern-cal", scen="lost-steps")
    st = r[("vern-cal", "lost-steps", "nominal")]
    assert st["fault"] == 1
    assert st["max"] <= 0.00012          # every other hold, before and after the slip


def test_core_in_bench_is_the_shipped_core(bench):
    comp = open(os.path.join(REPO, "rtcomp", "xvernier.comp")).read()
    core = re.search(r"/\* CORE-BEGIN.*?/\* CORE-END \*/", comp, re.S).group(0)
    assert core in open(bench / "xv_core.h").read()


def _holds(bench, plant, loop, env=None):
    cap = bench / f"pos_{plant}_{loop}.txt"
    e = dict(os.environ)
    e.update(env or {})
    subprocess.run([str(bench / "xv_bench"), "--positioning", plant, loop, str(cap)], check=True, env=e)
    out = subprocess.run([sys.executable, os.path.join(REPO, "scripts", "xvernier", "analyze_holds.py"),
                          str(cap), "--json"], check=True, capture_output=True, text=True).stdout
    return json.loads(out)


def test_analyzer_measures_todays_parking_error_in_shadow(bench):
    holds = _holds(bench, "nominal", "scale-db5")
    assert len(holds) == 36
    assert max(abs(h["est_err"]) for h in holds) > 0.0007        # today's loop, seen by the vernier
    assert max(h["resid_max"] for h in holds) <= 0.6


def test_analyzer_on_calibrated_closed_loop(bench):
    d = _fit(bench, "nominal")
    cal = " ".join(str(d[k]) for k in ("H_INIT", "LEAD", "HARM_COS", "HARM_SIN", "SLOPE", "LAG_TIME"))
    holds = _holds(bench, "nominal", "vern-cal", env={"XV_CAL": cal})
    assert len(holds) == 36
    assert max(abs(h["est_err"]) for h in holds) < 0.0001
    assert max(h["resid_max"] for h in holds) <= 0.6
