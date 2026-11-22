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
import tempfile
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


# --- QSettings isolation -------------------------------------------------------
# The GUI persists toggles with QSettings("IndustryCAM", ...), whose native store
# is the Windows registry (HKCU\Software\IndustryCAM) or ~/.config on Linux. Left
# alone the suite writes the developer's real settings and leaks state between
# tests: one test toggling Single Block left single_block=true, so a later RunTab
# read it back checked and the run-from tests saw program_step() in place of
# program_run(). Redirect every QSettings to a temp INI instead.
#
# Wired here at conftest import - before any test module (and the widgets some
# build at import time) loads - so not even a construction-time read reaches the
# real store. The (organization, application) constructor ignores
# setDefaultFormat (it stays NativeFormat), so the class itself is swapped for a
# factory that writes an INI file. The path is indirected through _QSETTINGS_INI
# so _qsettings_per_test can hand each test a fresh, empty store. The swap is
# never undone: widgets a fixture leaves alive are destroyed at interpreter
# shutdown and their close/destructor QSettings writes would reach the real store
# if the class were put back; the process is exiting, so this is harmless.
_QSETTINGS_INI = {"path": os.path.join(
    tempfile.mkdtemp(prefix="ic-qsettings-"), "session.ini")}

try:
    from PyQt5 import QtCore as _qtcore
except Exception:                           # no Qt in this environment
    _qtcore = None
else:
    _real_qsettings = _qtcore.QSettings

    def _qsettings_factory(*args, **kwargs):
        return _real_qsettings(_QSETTINGS_INI["path"], _real_qsettings.IniFormat)

    # Callers also reach class-level members through the symbol (e.g.
    # test_run_controls.py does QSettings.setPath(QSettings.NativeFormat, ...)),
    # so carry the scope/format enums and static methods onto the factory.
    for _attr in ("setPath", "setDefaultFormat", "defaultFormat",
                  "NativeFormat", "IniFormat", "InvalidFormat", "Format",
                  "UserScope", "SystemScope", "Scope"):
        try:
            setattr(_qsettings_factory, _attr, getattr(_real_qsettings, _attr))
        except AttributeError:
            pass

    # conftest imports before the test modules and gui packages, so patching the
    # canonical attribute covers their later `from PyQt5.QtCore import QSettings`;
    # also patch anything that happened to bind the name before this ran.
    _qtcore.QSettings = _qsettings_factory
    for _mod in list(sys.modules.values()):
        try:
            if getattr(_mod, "QSettings", None) is _real_qsettings:
                _mod.QSettings = _qsettings_factory
        except Exception:
            pass


@pytest.fixture(autouse=True)
def _qsettings_per_test(tmp_path):
    """Hand each test a fresh, empty QSettings store (see the module-level note),
    so GUI-toggle state never leaks between tests."""
    if _qtcore is None:
        yield
        return
    previous = _QSETTINGS_INI["path"]
    _QSETTINGS_INI["path"] = str(tmp_path / "qsettings.ini")
    yield
    _QSETTINGS_INI["path"] = previous
