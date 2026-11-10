"""Software E-STOP must put LinuxCNC in ESTOP, and the ribbon must show it.

Lathe, 2026-11-10: the ribbon E-STOP button called machine_off() (STATE_OFF),
so LinuxCNC never entered ESTOP and the state dot stayed green "IDLE".
"""

from types import SimpleNamespace

from PyQt5.QtWidgets import QApplication

from hal.interface import TaskState
from hal.mock_backend import MockBackend

_app = QApplication.instance() or QApplication([])


def test_mock_estop_enters_estop_and_needs_reset():
    b = MockBackend()
    b.estop_reset()
    b.machine_on()
    assert b.estop() is True
    b.poll()
    assert b.state.estop_active and not b.state.machine_on
    assert b.machine_on() is False            # must reset first
    assert b.estop_reset() and b._task_state == TaskState.ESTOP_RESET


def test_live_backend_sends_state_estop(monkeypatch):
    import importlib
    import sys
    from unittest import mock
    fake = mock.MagicMock(name="linuxcnc")
    fake.STATE_ESTOP, fake.STATE_OFF, fake.error = 1, 3, RuntimeError
    real = sys.modules.get("linuxcnc")
    monkeypatch.setitem(sys.modules, "linuxcnc", real or fake)
    monkeypatch.delitem(sys.modules, "hal.live_backend", raising=False)
    lb = importlib.import_module("hal.live_backend")
    monkeypatch.setattr(lb, "linuxcnc", fake)
    sent = []
    backend = lb.LiveBackend.__new__(lb.LiveBackend)
    backend._cmd = SimpleNamespace(state=lambda s: sent.append(s))
    assert backend.estop() is True
    assert sent == [1]                      # STATE_ESTOP, not STATE_OFF


def test_estop_button_calls_estop_not_machine_off():
    from gui.main_window import MainWindow
    calls = []
    fake = SimpleNamespace(estop=lambda: calls.append("estop") or True,
                           machine_off=lambda: calls.append("off") or True)
    win = SimpleNamespace(_backend=fake, _status_bar=SimpleNamespace(show_error=lambda m: None))
    MainWindow._on_estop_clicked(win)
    assert calls == ["estop"]


def test_ribbon_shows_off_state_not_idle():
    from gui.components.status_bar import StatusBar, _STATE_COLORS
    bar = StatusBar()
    bar.update_state("OFF")
    assert bar._state_label.text() == "OFF"
    assert bar._state_dot.color() == _STATE_COLORS["OFF"].lower()
    assert _STATE_COLORS["OFF"] != _STATE_COLORS["IDLE"]
