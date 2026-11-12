"""Run tab: feed / rapid override sliders, single block, optional stop (owner 2026-11-12).

Feed 1-200 %, rapid 1-100 % (LinuxCNC caps rapid override at 100 %). The
sliders set the overrides and follow LinuxCNC's values (the MPGs change them
during a run). Single block: Cycle Start steps (start from idle, next block
when paused); turning it on mid-run stops after the current block; HAL is told
so the green button steps too. Optional stop is applied at every start.
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt5.QtWidgets import QApplication   # noqa: E402

_app = QApplication.instance() or QApplication([])

from hal.interface import InterpState       # noqa: E402
from hal.mock_backend import MockBackend    # noqa: E402


class _Spy(MockBackend):
    def __init__(self):
        super().__init__()
        self.calls = []
        self.busy = False
        self.paused = False

    def _rec(self, *c):
        self.calls.append(c)
        return True

    def set_feed_override(self, v):
        self._rec("feed", round(v, 4)); return super().set_feed_override(v)

    def set_rapid_override(self, v):
        self._rec("rapid", round(v, 4)); return super().set_rapid_override(v)

    def program_step(self):
        return self._rec("step")

    def program_run(self, start_line=0):
        return self._rec("run", start_line)

    def program_resume(self):
        return self._rec("resume")

    def set_single_block(self, on):
        return self._rec("single", on)

    def set_optional_stop(self, on):
        return self._rec("optional", on)

    def program_open(self, path):
        return True

    def poll(self):
        pass

    @property
    def state(self):
        from dataclasses import replace
        s = super().state
        return replace(s, program_busy=self.busy, machine_on=True,
                       interp_state=InterpState.PAUSED if self.paused else s.interp_state,
                       paused=self.paused)


@pytest.fixture
def tab(tmp_path, monkeypatch):
    from PyQt5.QtCore import QSettings
    QSettings.setPath(QSettings.NativeFormat, QSettings.UserScope, str(tmp_path))
    import gui.run_tab as rt
    spy = _Spy()
    monkeypatch.setattr(rt, "get_backend", lambda: spy)
    t = rt.RunTab()
    t._gcode_path = str(tmp_path / "p.ngc")
    t._backend_file = t._gcode_path
    t.tool_table_problems = lambda: []
    spy.calls.clear()
    return t, spy


def test_slider_ranges(tab):
    t, _ = tab
    assert (t._feed_slider.minimum(), t._feed_slider.maximum()) == (1, 200)
    assert (t._rapid_slider.minimum(), t._rapid_slider.maximum()) == (1, 100)


def test_sliders_set_the_overrides(tab):
    t, spy = tab
    t._feed_slider.setValue(150)
    t._rapid_slider.setValue(25)
    assert ("feed", 1.5) in spy.calls and ("rapid", 0.25) in spy.calls
    assert t._feed_value.text() == "150%"


def test_sliders_follow_linuxcnc_without_echoing_it_back(tab):
    t, spy = tab
    from dataclasses import replace
    t._sync_overrides(replace(spy.state, feed_override=0.73, rapid_override=0.4))  # an MPG turned them
    assert t._feed_slider.value() == 73 and t._rapid_slider.value() == 40
    assert not [c for c in spy.calls if c[0] in ("feed", "rapid")]


def test_cycle_start_steps_in_single_block(tab):
    t, spy = tab
    t._btn_single.setChecked(True)
    assert ("single", True) in spy.calls
    spy.calls.clear()
    assert t.cycle_start("screen") == "started"
    assert ("step",) in spy.calls and not [c for c in spy.calls if c[0] == "run"]
    spy.paused = True
    spy.calls.clear()
    assert t.cycle_start("green button") == "stepped"
    assert spy.calls == [("step",)]


def test_cycle_start_runs_and_resumes_normally_without_single_block(tab):
    t, spy = tab
    t._btn_single.setChecked(False)
    spy.calls.clear()
    assert t.cycle_start("screen") == "started"
    assert ("run", 0) in spy.calls
    spy.paused = True
    assert t.cycle_start("screen") == "resumed"


def test_single_block_on_mid_run_stops_after_the_current_block(tab):
    t, spy = tab
    t._btn_single.setChecked(False)
    spy.busy = True
    spy.calls.clear()
    t._btn_single.setChecked(True)
    assert ("step",) in spy.calls


def test_optional_stop_applied_at_every_start(tab):
    t, spy = tab
    t._btn_optional.setChecked(True)
    spy.calls.clear()
    t.cycle_start("screen")
    assert ("optional", True) in spy.calls
