"""Threading panel (owner plan 2026-11-12, phase T2), offscreen."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

_app = QApplication.instance() or QApplication([])

from gui.components.threading_panel import ThreadingPanel  # noqa: E402
from models import thread_data as td  # noqa: E402


def _panel(thread_type="UNC", size="1/4-20 UNC", internal=False):
    p = ThreadingPanel()
    p._side.setCurrentIndex(1 if internal else 0)
    p._type.setCurrentText(thread_type)
    if size:
        p._size.setCurrentText(size)
    return p


def test_size_fills_x_pitch_and_the_od_hint():
    p = _panel()
    v = p.get_values()
    assert (v["x_start"], v["x_end"], v["pitch"]) == pytest.approx((0.25, 0.25, 0.05))
    assert "0.2164 - 0.2127" in p._hint.text()                   # 2A pitch-diameter window
    assert "(UN 2A)" in p._depth_label.text()


def test_internal_shows_the_tap_drill_and_fills_the_pilot():
    p = _panel(internal=True)
    assert p._class.currentText() == "2B"
    assert p.get_values()["pilot_dia"] == pytest.approx(0.2010)
    assert "Tap drill: #7" in p._hint.text()


def test_classes_per_type():
    p = _panel("Metric Coarse", "M6x1")
    assert [p._class.itemText(i) for i in range(p._class.count())] == ["6g", "4h"]
    p._side.setCurrentIndex(1)
    assert [p._class.itemText(i) for i in range(p._class.count())] == ["6H", "5H"]


def test_npt_x_end_follows_the_taper():
    p = _panel("NPT", "1/4 NPT")
    v = p.get_values()
    n = td.npt_data("1/4 NPT")
    assert v["x_start"] == pytest.approx(n.major_small_end)
    assert v["x_end"] - v["x_start"] == pytest.approx((v["start_z"] - v["end_z"]) / 16)
    assert "ring gauge" in p._hint.text()


def test_editing_x_turns_the_thread_custom():
    p = _panel()
    p._x_start.set_value(0.3)
    p._on_geometry_edit()
    assert p.get_values()["thread_type"] == "Custom"
    assert "Custom (no tolerance data)" in p._hint.text()


def test_metric_pitch_survives_the_switch_to_custom():
    p = _panel("Metric Coarse", "M6x1")
    p._pitch.set_value(1.25)
    p._on_geometry_edit()
    assert p.get_values()["pitch"] * 25.4 == pytest.approx(1.25)


@pytest.mark.parametrize("args", [("UNC", "1/2-13 UNC", False), ("Acme", "1-5 ACME", True),
                                  ("Metric Trapezoidal", "Tr20x4", False), ("NPT", "1/2 NPT", True)])
def test_round_trip(args):
    p = _panel(*args)
    v = p.get_values()
    q = ThreadingPanel()
    q.set_values(v, args[2])
    assert q.get_values() == v


def test_legacy_block_loads():
    q = ThreadingPanel()
    q.set_values({"thread_standard": "UN", "designation": "1/4-20 UNC", "major_diameter": 0.2448,
                  "pitch": 0.05, "thread_depth": 0.02706, "start_z": 0.05, "end_z": -0.77,
                  "infeed_method": "modified_flank", "num_passes": 6, "spring_passes": 2,
                  "chamfer_threads": 1.0, "spindle_rpm": 400.0, "tool_number": 2,
                  "is_internal": False, "fit": "mid", "thread_class": "2A"}, False)
    v = q.get_values()
    assert v["designation"] == "1/4-20 UNC" and v["x_start"] == pytest.approx(0.25)
    assert v["end_z"] == pytest.approx(-0.77) and v["thread_class"] == "2A"


def test_side_change_signal():
    p = _panel()
    got = []
    p.side_changed.connect(got.append)
    p._side.setCurrentIndex(1)
    assert got == [True]


def test_every_size_and_class_displays_on_both_sides():
    """No listed thread may break the panel (a slot exception aborts the GUI)."""
    import sys
    errors = []
    old = sys.excepthook
    sys.excepthook = lambda *exc: errors.append(exc)
    try:
        p = ThreadingPanel()
        for internal in (False, True):
            p._side.setCurrentIndex(1 if internal else 0)
            for t in td.THREAD_TYPES:
                p._type.setCurrentText(t)
                for s in td.sizes(t):
                    p._size.setCurrentText(s.label)
                    for i in range(p._class.count()):
                        p._class.setCurrentIndex(i)
                        assert "per side" in p._depth_label.text(), (s.label, internal)
    finally:
        sys.excepthook = old
    assert not errors, errors[0]


def test_npt_internal_hint_is_the_asme_k0():
    p = _panel("NPT", "1/2 NPT", internal=True)
    assert "K0 0.7013" in p._hint.text() and "plug gauge" in p._hint.text()
    assert p.get_values()["pilot_dia"] == pytest.approx(0.7013, abs=5e-5)
