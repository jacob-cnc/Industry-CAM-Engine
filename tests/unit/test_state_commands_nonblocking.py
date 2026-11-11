"""Reset / On / Off must not freeze the GUI when LinuxCNC is slow to answer.

Lathe 2026-11-10 17:53: after an E-stop the I/O controller stopped answering;
every Reset/On click blocked the GUI for the full 5 s command timeout and the
clicks queued. They now run on a worker thread, one at a time.
"""

import importlib
import sys
import threading
import time
from types import SimpleNamespace
from unittest import mock


def _backend(monkeypatch, ack_delay):
    calls = []

    class _Cmd:
        def state(self, s):
            calls.append(s)
            time.sleep(ack_delay)

    fake = mock.MagicMock(name="linuxcnc")
    fake.STATE_ESTOP, fake.STATE_ESTOP_RESET, fake.STATE_ON, fake.STATE_OFF = 1, 2, 4, 3
    fake.error = RuntimeError
    fake.command = _Cmd
    monkeypatch.setitem(sys.modules, "linuxcnc", sys.modules.get("linuxcnc") or fake)
    monkeypatch.delitem(sys.modules, "hal.live_backend", raising=False)
    lb = importlib.import_module("hal.live_backend")
    monkeypatch.setattr(lb, "linuxcnc", fake)
    b = lb.LiveBackend.__new__(lb.LiveBackend)
    b._cmd = _Cmd()
    return b, calls


def _wait_idle(b, timeout=3.0):
    lock = b.__dict__.get("_state_lock")
    t0 = time.monotonic()
    while lock is not None and lock.locked() and time.monotonic() - t0 < timeout:
        time.sleep(0.01)


def test_reset_returns_immediately_and_reports_slow_ack(monkeypatch):
    b, calls = _backend(monkeypatch, ack_delay=0.4)
    monkeypatch.setattr(type(b), "STATE_ACK_WARN_S", 0.2)
    t0 = time.monotonic()
    assert b.estop_reset() is True
    assert time.monotonic() - t0 < 0.1           # GUI thread not blocked
    _wait_idle(b)
    assert calls == [2]
    assert "took" in b.take_state_warning()
    assert b.take_state_warning() == ""          # popped once


def test_second_click_while_waiting_is_ignored(monkeypatch):
    b, calls = _backend(monkeypatch, ack_delay=0.3)
    assert b.estop_reset() is True
    assert b.machine_on() is False                # still waiting: ignored
    assert "ignored" in b.take_state_warning()
    _wait_idle(b)
    assert calls == [2]
    assert b.machine_on() is True                 # free again
    _wait_idle(b)
    assert calls == [2, 4]


def test_fast_ack_gives_no_warning(monkeypatch):
    b, calls = _backend(monkeypatch, ack_delay=0.0)
    assert b.machine_off() is True
    _wait_idle(b)
    assert calls == [3] and b.take_state_warning() == ""


def test_estop_stays_synchronous(monkeypatch):
    b, calls = _backend(monkeypatch, ack_delay=0.0)
    sent = []
    b._cmd = SimpleNamespace(state=lambda s: sent.append(s))
    assert b.estop() is True
    assert sent == [1]                            # sent before returning
    assert not any(t.name.startswith("lcnc-") for t in threading.enumerate()
                   if t.is_alive() and "estop" in t.name and "reset" not in t.name)
