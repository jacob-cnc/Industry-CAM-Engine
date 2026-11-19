"""Run From must never start a program LinuxCNC has not confirmed opening.

Lathe 2026-11-18: Run From, in a session where the program had not first been
run from the top, executed the SOURCE program from line 1 instead of the
resume file - LinuxCNC rejected one of its moves ("Linear move on line 53
would exceed X's negative limit", a line number that only exists in the
107-line source). Cause: run_tab opened the resume file and called
program_run() in the next statement, while live_backend.program_open() neither
waited for the open nor confirmed it, so _ensure_mode(AUTO) aborted the
in-progress open and AUTO_RUN ran whatever file task still had open.

live_backend now wait_complete()s and confirms stat.file before returning
True, which cannot be exercised here (conftest makes the `linuxcnc` binding
unimportable). These tests pin the GUI half: a program_open that returns
False never reaches program_run.
"""
import os
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PyQt5.QtWidgets import QApplication, QMessageBox  # noqa: E402

from hal.factory import get_backend  # noqa: E402
from hal.interface import InterpState, TaskMode  # noqa: E402

_app = QApplication.instance() or QApplication([])

PROGRAM = """\
N10 G20 G7 G18 G40 G49 G80
N20 G90 G95
N30 S900 M3
N40 G00 X0.0000 Z2.0000
N50 T3 M6
N60 G43
N70 G00 X0.1940 Z0.1100
N80 G01 X0.1940 Z-1.0250 F0.0030
N90 G00 X0.1375 Z2.0000
N100 M2
"""


@pytest.fixture
def run_tab(monkeypatch):
    b = get_backend(force_mock=True)
    b.estop_reset()
    b.machine_on()
    b._interp_state = InterpState.IDLE
    b._task_mode = TaskMode.MANUAL

    from gui.main_window import MainWindow
    w = MainWindow()
    w._cycle_btn_timer.stop()
    w._status_timer.stop()

    f = tempfile.NamedTemporaryFile("w", suffix=".ngc", delete=False)
    f.write(PROGRAM)
    f.close()
    w._run_tab._load_gcode_file(f.name)

    # Run From asks the operator to confirm the restored state; always say yes.
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.Yes))
    yield w._run_tab, b
    w.close()
    os.unlink(f.name)


def test_refused_open_never_starts_a_run(run_tab, monkeypatch):
    tab, b = run_tab
    runs = []
    monkeypatch.setattr(b, "program_open", lambda path: False)
    monkeypatch.setattr(b, "program_run",
                        lambda start_line=0: runs.append(start_line) or True)
    monkeypatch.setattr(b, "program_step", lambda: runs.append("step") or True)

    tab._line_spin.setValue(80)      # N80, a move well past the preamble
    tab._on_run_from_line()

    assert runs == [], "a run started although LinuxCNC never confirmed the open"


def test_confirmed_open_runs_the_resume_file(run_tab, monkeypatch):
    tab, b = run_tab
    opened, runs = [], []
    monkeypatch.setattr(b, "program_open", lambda path: opened.append(path) or True)
    monkeypatch.setattr(b, "program_run",
                        lambda start_line=0: runs.append(start_line) or True)

    tab._line_spin.setValue(80)
    tab._on_run_from_line()

    assert runs == [0], "the resume program runs from its own first line"
    assert opened, "nothing was opened"
    assert opened[-1].endswith("- from line 8.ngc"), opened[-1]
