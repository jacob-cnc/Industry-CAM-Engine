"""Red cycle-pause button reaches the GUI, not only halui (owner 2026-11-22).

industry-cam.hal wires the debounced red button (TB3 P11) to
halui.program.pause, and that is kept. But halui is not a dependable sole
path: halui.cc's emcCommandSend() blocks until task echoes the command,
polling every 0.1 s for up to 10 s, and takes no HAL snapshot while blocked.
check_hal_changes() samples the pins once per loop pass, so a press that
begins AND ends inside a stall is silently dropped — and the MPG feed/rapid
override wiring drives halui commands all through a run, which is exactly when
an operator reaches for pause. halui also exits on SIGTERM/SIGINT, after which
its pins freeze at their last values and it reads nothing at all.

So the GUI reads the same signal itself (compound-slide.cycle-pause) and
pauses through the task channel. These tests cover that GUI-side path only.
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt5.QtWidgets import QApplication   # noqa: E402

_app = QApplication.instance() or QApplication([])

from hal.mock_backend import MockBackend    # noqa: E402


class _Spy(MockBackend):
    """Mock whose button, busy and paused state the test drives directly."""

    def __init__(self):
        super().__init__()
        self.pauses = 0
        self.busy = False
        self.paused = False
        self._cycle_pause = False

    def program_pause(self):
        self.pauses += 1
        return True

    def poll(self):
        pass

    @property
    def state(self):
        from dataclasses import replace
        return replace(super().state, program_busy=self.busy,
                       machine_on=True, paused=self.paused)


class _Win:
    """Just the red-button poller, bound to a spy backend.

    MainWindow builds the whole app (graphs, tabs, OCCT); this exercises the
    handler itself, which is where the edge detection and the guards live.
    """

    def __init__(self, backend):
        from gui.main_window import MainWindow
        self._backend = backend
        self._pause_btn_prev = False
        self._poll = MainWindow._poll_pause_button.__get__(self)

    def press(self):
        self._backend._cycle_pause = True
        self._poll()

    def release(self):
        self._backend._cycle_pause = False
        self._poll()


@pytest.fixture
def win():
    spy = _Spy()
    return _Win(spy), spy


def test_press_pauses_a_running_program(win):
    w, spy = win
    spy.busy = True
    w.press()
    assert spy.pauses == 1


def test_holding_the_button_pauses_once_not_repeatedly(win):
    """Edge-triggered: a held button must not re-issue pause every 20 ms."""
    w, spy = win
    spy.busy = True
    w.press()
    for _ in range(50):
        w._poll()
    assert spy.pauses == 1


def test_second_press_after_release_pauses_again(win):
    w, spy = win
    spy.busy = True
    w.press()
    w.release()
    spy.paused = False
    w.press()
    assert spy.pauses == 2


def test_no_pause_when_nothing_is_running(win):
    w, spy = win
    spy.busy = False
    w.press()
    assert spy.pauses == 0


def test_no_pause_when_already_paused(win):
    """Red only pauses. Green resumes, and that is handled in HAL."""
    w, spy = win
    spy.busy = True
    spy.paused = True
    w.press()
    assert spy.pauses == 0


def test_backend_without_the_pin_is_ignored(win):
    """An older backend with no read_cycle_pause must not raise."""
    w, _ = win

    class _Old:
        pass

    w._backend = _Old()
    w._poll()          # must simply return


def test_backend_errors_do_not_escape(win):
    """A HAL hiccup must not kill the 20 ms timer that also polls green."""
    w, spy = win
    spy.busy = True

    def boom():
        raise RuntimeError("HAL gone")

    spy.poll = boom
    w.press()          # logged, not raised
    assert spy.pauses == 0
