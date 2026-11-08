"""Cycle start/pause pushbuttons (2026-11-08).

Green = gpio.009, red = gpio.010 (measured on the lathe). HAL: red ->
halui.program.pause, green AND paused -> halui.program.resume (verified in the
headless 2.9.6 sim: no motion while paused, resume continues the same line).
GUI: green rising edge starts the loaded program only when nothing is queued.
"""
import os
import tempfile

import pytest
from PyQt5.QtWidgets import QApplication

from hal.factory import get_backend
from hal.interface import InterpState, TaskMode

_app = QApplication.instance() or QApplication([])


@pytest.fixture
def win(monkeypatch):
    b = get_backend(force_mock=True)
    b.estop_reset(); b.machine_on(); b._interp_state = InterpState.IDLE; b._task_mode = TaskMode.MANUAL
    from gui.main_window import MainWindow
    w = MainWindow()
    w._cycle_btn_timer.stop(); w._status_timer.stop()
    calls = []
    monkeypatch.setattr(b, "program_run", lambda start_line=0: calls.append(("run", start_line)) or True)
    monkeypatch.setattr(b, "program_resume", lambda: calls.append(("resume",)) or True)
    w._calls = calls
    yield w, b
    w.close()


def _press(w, b):
    b._cycle_start = True; w._poll_cycle_button()
    b._cycle_start = False; w._poll_cycle_button()


def _load(w):
    f = tempfile.NamedTemporaryFile("w", suffix=".ngc", delete=False)
    f.write("G20\nG0 X1 Z1\nM2\n"); f.close()
    w._run_tab._load_gcode_file(f.name)
    return f.name


def test_green_idle_with_program_starts_at_line_1(win):
    w, b = win
    path = _load(w)
    _press(w, b)
    assert w._calls == [("run", 0)]
    assert w._tab_widget.currentWidget() is w._run_tab
    os.unlink(path)


def test_green_held_is_one_press(win):
    w, b = win
    path = _load(w)
    b._cycle_start = True
    for _ in range(10):
        w._poll_cycle_button()
    assert w._calls == [("run", 0)]
    os.unlink(path)


def test_green_while_paused_leaves_resume_to_hal(win):
    w, b = win
    _load(w)
    b._task_mode = TaskMode.AUTO; b._interp_state = InterpState.PAUSED
    _press(w, b)
    assert w._calls == []


def test_green_while_running_is_ignored(win):
    w, b = win
    _load(w)
    b._task_mode = TaskMode.AUTO; b._interp_state = InterpState.READING
    _press(w, b)
    assert w._calls == []


def test_green_without_program_shows_message(win):
    w, b = win
    w._run_tab._gcode_path = None
    _press(w, b)
    assert w._calls == []
    assert "No program loaded" in w._run_tab._status_error.text()


def test_green_machine_off_shows_message(win):
    w, b = win
    _load(w)
    b.machine_off()
    _press(w, b)
    assert w._calls == []
    assert "Machine is off" in w._run_tab._status_error.text()


def test_screen_cycle_start_resumes_when_paused(win):
    w, b = win
    _load(w)
    b._task_mode = TaskMode.AUTO; b._interp_state = InterpState.PAUSED
    w._run_tab._on_start()
    assert w._calls == [("resume",)]
