"""Shared test setup.

GUI tests must lay out like the app: on Windows, gui/main_window.main()
pins Qt's font DPI to 96 (the lathe's) before the QApplication exists.
Without the same pin here, whichever test module creates the QApplication
first decides the DPI for the whole run (e.g. 144 on a 150 % desktop), and
pixel-budget layout tests then depend on test order.

Offscreen Qt hygiene (lathe, 2026-11-10): in a full run on Linux two
whole-window test files segfaulted or hung, yet passed alone.
  * Widgets closed with deleteLater() are only destroyed when an event loop
    processes DeferredDelete events; plain processEvents() does not, so dead
    MainWindows piled up and a later app-wide setStyleSheet() walked them.
    After every test the pending deletions are flushed.
  * A modal QMessageBox / QDialog.exec_() offscreen waits for a click that
    never comes. Unpatched modal calls are answered automatically (Ok / No /
    Rejected) and reported as a warning, so the run never hangs. Tests that
    patch these themselves (monkeypatch) still win.
"""

import os
import subprocess
import sys
import warnings

import pytest

# The lathe's display is 1920x1080 at 96 DPI (xdpyinfo, 2026-11-11). Offscreen Qt
# defaults to 100 DPI, so pixel-budget tests measured a layout the lathe never
# shows - and which one depended on test order. Pin 96 on every platform.
os.environ.setdefault("QT_FONT_DPI", "96")

# --- The suite never talks to the machine (lathe, 2026-11-11) -------------------
# Tests run on the lathe's own Python (requirements-lathe.txt), which has
# LinuxCNC's `linuxcnc` and `hal` bindings. Without this, whole-window tests
# reached hal.live_backend and ran real `halcmd net ...` commands, and the Tools
# tab can send controller commands. Make those bindings unimportable - exactly
# the conditions every test was written under - and refuse to run at all while
# LinuxCNC is up (the standing rule: no test suite with the machine running).
sys.modules["linuxcnc"] = None          # import linuxcnc -> ImportError
sys.modules["_hal"] = None              # Debian hal.py (loaded by file path) needs it


def _linuxcnc_running() -> str:
    for name in ("milltask", "rtapi_app", "linuxcncsvr", "linuxcnc"):
        try:
            if subprocess.run(["pgrep", "-x", name], capture_output=True).returncode == 0:
                return name
        except FileNotFoundError:        # no pgrep (Windows dev box)
            return ""
    return ""


def pytest_configure(config):
    running = _linuxcnc_running()
    if running:
        pytest.exit(f"LinuxCNC is running ({running}): the test suite must not run while the "
                    f"machine is up. Shut LinuxCNC down first.", returncode=3)


@pytest.fixture(autouse=True)
def _qt_offscreen_hygiene(monkeypatch, request):
    try:
        from PyQt5.QtCore import QCoreApplication, QEvent
        from PyQt5.QtWidgets import QDialog, QMessageBox
    except Exception:                       # no Qt in this environment
        yield
        return

    seen = []

    def _auto(kind, answer):
        def _box(*args, **kwargs):
            text = next((a for a in args if isinstance(a, str)), "")
            seen.append(f"QMessageBox.{kind}: {text[:120]}")
            return answer
        return staticmethod(_box)

    monkeypatch.setattr(QMessageBox, "warning", _auto("warning", QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, "information", _auto("information", QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, "critical", _auto("critical", QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, "question", _auto("question", QMessageBox.No))

    def _exec(self, *a, **k):
        seen.append(f"{type(self).__name__}.exec_()")
        return QDialog.Rejected
    monkeypatch.setattr(QDialog, "exec_", _exec)
    monkeypatch.setattr(QDialog, "exec", _exec, raising=False)

    yield

    if QCoreApplication.instance() is not None:
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        QCoreApplication.processEvents()
    if seen:
        warnings.warn(f"{request.node.nodeid}: modal dialog(s) auto-answered: "
                      + "; ".join(seen[:3]))
