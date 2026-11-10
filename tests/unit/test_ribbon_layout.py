"""Ribbon layout invariants: fitted spacing, centring, fit-to-screen, and
errors living in the tab row instead of the ribbon.

Property-style checks (hold at any width / font), not one pixel layout.
"""

import pytest
from PyQt5.QtWidgets import QApplication

from gui.components.status_bar import StatusBar

_app = QApplication.instance() or QApplication([])

LONG_ERROR = ("hm2/hm2_7i96s.0: error finishing read! iter=123456 - joint 0 "
              "following error - " + "x" * 300)


def _geoms(bar):
    return [it.widget().geometry() for it in bar._ribbon_items()]


def _gaps(bar):
    g = _geoms(bar)
    return [g[i + 1].x() - (g[i].x() + g[i].width()) for i in range(len(g) - 1)]


@pytest.fixture
def bar():
    b = StatusBar()
    b.resize(1918, 72)
    b.show()
    _app.processEvents()
    yield b
    b.close()
    b.deleteLater()
    _app.processEvents()


@pytest.mark.parametrize("width", [1700, 1918, 2400])
def test_gaps_uniform_and_maximal(bar, width):
    bar.resize(max(width, bar.minimumSizeHint().width()), 72)
    _app.processEvents()
    gaps = _gaps(bar)
    assert len(set(gaps)) == 1, gaps                  # one gap everywhere
    gap = gaps[0]
    assert gap >= StatusBar.MIN_GAP
    # Maximal: one more px in each of the n-1 gaps + 2 edges would not fit.
    items = bar._ribbon_items()
    need = sum(it.minimumSize().width() for it in items)
    assert need + (gap + 1) * (len(items) + 1) > bar.width() \
        or gap == StatusBar.MIN_GAP


def test_edges_equal_gap_and_centred(bar):
    g = _geoms(bar)
    gap = _gaps(bar)[0]
    n = len(g)
    left = g[0].x()
    right = bar.width() - (g[-1].x() + g[-1].width())
    assert abs(left - right) <= 1                       # centred
    # Edge space = the gap, plus at most half the n+1 px remainder.
    assert gap <= left <= gap + (n + 1) // 2 + 1
    assert gap <= right <= gap + (n + 1) // 2 + 1


def test_min_width_uses_min_gap(bar):
    items = bar._ribbon_items()
    bar.resize(2400, 72)
    _app.processEvents()
    assert bar.layout().spacing() > StatusBar.MIN_GAP
    expected = (sum(it.minimumSize().width() for it in items)
                + StatusBar.MIN_GAP * (len(items) + 1))
    assert bar.minimumSizeHint().width() == expected    # can still shrink


def test_state_box_is_70px(bar):
    assert bar._state_label.width() == 70


def test_error_not_in_ribbon(bar):
    before = _geoms(bar)
    bar.show_error(LONG_ERROR)
    _app.processEvents()
    assert _geoms(bar) == before         # ribbon untouched by an error
    assert bar.error_label.parent() is not bar.layout()
    assert bar.layout().indexOf(bar.error_label) == -1


def test_main_window_error_in_tab_row():
    from gui.main_window import MainWindow
    w = MainWindow()
    w.resize(1918, 1034)
    w.show()
    _app.processEvents()
    try:
        width = w.width()
        ribbon_before = _geoms(w.status_bar)
        w.status_bar.show_error(LONG_ERROR)
        _app.processEvents()
        _app.processEvents()
        lab = w.status_bar.error_label
        tabs = w.tab_widget
        bar = tabs.tabBar()
        last = bar.tabRect(bar.count() - 1)
        last_right = bar.mapTo(tabs, last.topRight()).x()
        g = lab.geometry()
        assert lab.isVisible()
        assert lab.parent() is tabs
        assert g.x() > last_right                        # right of the tabs
        assert g.right() < tabs.width()                  # inside the window
        top = bar.mapTo(tabs, bar.rect().topLeft()).y()
        assert top <= g.y() and g.bottom() <= top + bar.height()
        assert abs((g.y() - top) - (top + bar.height() - 1 - g.bottom())) <= 1
        assert w.width() == width                        # window did not grow
        assert _geoms(w.status_bar) == ribbon_before
        w.status_bar.clear_error()
        _app.processEvents()
        assert not lab.isVisible()
    finally:
        w._status_timer.stop()
        w._cycle_btn_timer.stop()
        w.close()
        w.deleteLater()
        _app.processEvents()


@pytest.mark.parametrize("reading", ["-1.0000", "-12.3456", "-88.8888",
                                     "-127.000", "-888.888", "302.260"])
def test_dro_fits_widest_readings_without_reflow(bar, reading):
    """A DRO box must never cut a digit off nor resize (shifting the
    ribbon) while jogging through realistic readings."""
    before = _geoms(bar)
    for dro in (bar._x_dro, bar._z_dro):
        dro.setText(reading)
    _app.processEvents()
    _app.processEvents()
    for dro in (bar._x_dro, bar._z_dro):
        assert dro.fontMetrics().horizontalAdvance(reading) <= dro.contentsRect().width()
    assert _geoms(bar) == before


@pytest.mark.parametrize("state", ["RUN", "PAUSE", "ESTOP", "IDLE"])
def test_state_dot_and_label_follow_state(bar, state):
    from gui.components.status_bar import _STATE_COLORS
    from PyQt5.QtGui import QColor
    bar.update_state(state)
    _app.processEvents()
    assert bar._state_label.text() == state
    assert bar._state_dot.color() == QColor(_STATE_COLORS[state]).name()


def test_state_dot_is_28px_circle(bar):
    dot = bar._state_dot
    assert dot.diameter == StatusBar.STATE_DOT_DIAMETER == 28
    assert dot.width() >= 28 and dot.height() >= 28


def test_state_label_matches_readout_bubble(bar):
    from PyQt5.QtCore import Qt
    lab = bar._state_label
    assert lab.alignment() & Qt.AlignHCenter
    dro_box = bar._ribbon_items()[3].widget()           # BAR4
    # Same fill / border / radius declarations as the readout bubbles.
    for decl in dro_box.styleSheet().split("{")[1].split("}")[0].split(";"):
        if decl.strip():
            assert decl.strip() in lab.styleSheet()
    # update_state must not wipe the bubble style.
    bar.update_state("PAUSE")
    assert "border-radius" in lab.styleSheet()
