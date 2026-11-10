"""Unit tests for gui/debug_overlay.py - UI debug overlay.

Checks invariants of the ID tree (reading order, visibility, clipping,
wrapper collapse) rather than one hard-coded layout.
"""

import json
import os

import pytest
from PyQt5.QtCore import QEvent, QPoint, Qt
from PyQt5.QtGui import QKeyEvent, QMouseEvent
from PyQt5.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QMainWindow, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from gui.debug_overlay import (
    DebugOverlay, build_tree, debug_ui_enabled, iter_nodes, snapshot_dir,
)

_app = QApplication.instance() or QApplication([])


@pytest.fixture
def demo():
    """Window: title label, a row of two buttons, a hidden button, a
    wrapper around one button, and a short scroll area with 10 buttons."""
    win = QMainWindow()
    central = QWidget()
    win.setCentralWidget(central)
    col = QVBoxLayout(central)

    win.title = QLabel("Title")
    col.addWidget(win.title)

    row = QWidget()
    rl = QHBoxLayout(row)
    win.left, win.right = QPushButton("Left"), QPushButton("Right")
    rl.addWidget(win.left)
    rl.addWidget(win.right)
    col.addWidget(row)

    win.hidden = QPushButton("Hidden")
    col.addWidget(win.hidden)

    wrapper = QWidget()
    wl = QVBoxLayout(wrapper)
    wl.setContentsMargins(0, 0, 0, 0)
    win.wrapped = QPushButton("Wrapped")
    # Fill the wrapper exactly, so it is a pure pass-through container.
    from PyQt5.QtWidgets import QSizePolicy
    win.wrapped.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    wl.addWidget(win.wrapped)
    col.addWidget(wrapper)

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFixedHeight(80)
    inner = QWidget()
    il = QVBoxLayout(inner)
    win.scroll_buttons = [QPushButton(f"S{i}") for i in range(10)]
    for b in win.scroll_buttons:
        b.setFixedHeight(30)
        il.addWidget(b)
    scroll.setWidget(inner)
    col.addWidget(scroll)

    win.resize(400, 400)
    win.show()
    win.hidden.hide()
    _app.processEvents()
    overlay = DebugOverlay(win)
    _app.processEvents()
    yield win, overlay
    win.close()
    win.deleteLater()
    _app.processEvents()


def _ids(overlay):
    return {id(n.widget): n.id for n in iter_nodes(overlay.tree())}


def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("INDUSTRY_CAM_DEBUG_UI", raising=False)
    assert not debug_ui_enabled()
    monkeypatch.setenv("INDUSTRY_CAM_DEBUG_UI", "1")
    assert debug_ui_enabled()


def test_ids_unique_and_hierarchical(demo):
    _, overlay = demo
    nodes = list(iter_nodes(overlay.tree()))
    ids = [n.id for n in nodes]
    assert len(ids) == len(set(ids))
    for n in nodes:
        for c in n.children:
            assert c.depth == n.depth + 1
            sep = "" if n.depth == 0 else "."
            assert c.id.startswith(n.id + sep)


def test_reading_order(demo):
    win, overlay = demo
    ids = _ids(overlay)
    # Same row: left before right. Title above the row: title first.
    assert ids[id(win.left)] < ids[id(win.right)]
    assert ids[id(win.title)].split(".")[0] < ids[id(win.left)].split(".")[0]


def test_hidden_and_overlay_excluded(demo):
    win, overlay = demo
    ids = _ids(overlay)
    assert id(win.hidden) not in ids
    assert id(overlay) not in ids


def test_scrolled_away_widgets_excluded(demo):
    win, overlay = demo
    ids = _ids(overlay)
    tagged = [b for b in win.scroll_buttons if id(b) in ids]
    assert 0 < len(tagged) < len(win.scroll_buttons)
    # Every tagged node lies inside the window.
    for n in iter_nodes(overlay.tree()):
        assert win.rect().contains(n.visible)


def test_wrapper_collapses_onto_child(demo):
    win, overlay = demo
    nodes = {id(n.widget): n for n in iter_nodes(overlay.tree())}
    wrapped = nodes[id(win.wrapped)]
    # The zero-margin wrapper does not take an ID level of its own.
    assert wrapped.depth == 1


def test_f12_cycles_tag_depth(demo):
    win, overlay = demo
    seen = []
    for _ in range(6):
        QApplication.sendEvent(win.left, QKeyEvent(QEvent.KeyPress, Qt.Key_F12, Qt.NoModifier))
        seen.append(overlay.tag_depth)
    assert seen == [1, 2, 3, 4, 99, None]


def test_other_keys_pass_through(demo):
    win, overlay = demo
    ev = QKeyEvent(QEvent.KeyPress, Qt.Key_Up, Qt.NoModifier)
    assert overlay.eventFilter(win.left, ev) is False


def _drag(win, overlay, start, delta):
    """Ctrl+Shift+drag on win.left from global start by delta."""
    mods = Qt.ControlModifier | Qt.ShiftModifier
    end = start + delta

    def send(kind, gpos, buttons):
        local = win.left.mapFromGlobal(gpos)
        QApplication.sendEvent(win.left, QMouseEvent(
            kind, local, gpos, Qt.LeftButton, buttons, mods))

    send(QEvent.MouseButtonPress, start, Qt.LeftButton)
    send(QEvent.MouseMove, end, Qt.LeftButton)
    send(QEvent.MouseButtonRelease, end, Qt.NoButton)


def _key(win, key, mods=Qt.NoModifier):
    QApplication.sendEvent(win.left, QKeyEvent(QEvent.KeyPress, key, mods))


def test_rulers_add_undo_and_clear(demo):
    win, overlay = demo
    start = win.left.mapToGlobal(QPoint(2, 2))
    _drag(win, overlay, start, QPoint(50, 20))
    _drag(win, overlay, start, QPoint(0, 30))
    _drag(win, overlay, start, QPoint(15, 0))
    deltas = [(b.x() - a.x(), b.y() - a.y()) for a, b in overlay.rulers]
    assert deltas == [(50, 20), (0, 30), (15, 0)]

    _key(win, Qt.Key_F8)                       # undo removes the newest
    assert [(b.x() - a.x(), b.y() - a.y()) for a, b in overlay.rulers] \
        == [(50, 20), (0, 30)]
    _key(win, Qt.Key_F8, Qt.ShiftModifier)     # clear all
    assert overlay.rulers == []
    _key(win, Qt.Key_F8)                       # undo on empty is harmless
    assert overlay.rulers == []


def test_click_or_jitter_adds_no_ruler(demo):
    win, overlay = demo
    start = win.left.mapToGlobal(QPoint(2, 2))
    _drag(win, overlay, start, QPoint(0, 0))
    _drag(win, overlay, start, QPoint(2, 1))
    assert overlay.rulers == []


def test_snapshot_lists_rulers(demo, tmp_path, monkeypatch):
    win, overlay = demo
    monkeypatch.setenv("INDUSTRY_CAM_SNAPSHOT_DIR", str(tmp_path))
    start = win.left.mapToGlobal(QPoint(2, 2))
    _drag(win, overlay, start, QPoint(40, 0))
    _drag(win, overlay, start, QPoint(0, 25))
    paths = overlay.take_snapshot()
    meta = json.load(open(paths["json"], encoding="utf-8"))["meta"]
    assert [r["id"] for r in meta["rulers"]] == ["R1", "R2"]
    text = open(paths["txt"], encoding="utf-8").read()
    assert "Ruler R1:" in text and "dx 40  dy 0" in text
    assert "Ruler R2:" in text and "dx 0  dy 25" in text


def test_snapshot_writes_files(demo, tmp_path, monkeypatch):
    win, overlay = demo
    monkeypatch.setenv("INDUSTRY_CAM_SNAPSHOT_DIR", str(tmp_path))
    assert snapshot_dir() == str(tmp_path)
    p1 = overlay.take_snapshot()
    p2 = overlay.take_snapshot()
    for path in p1.values():
        assert os.path.getsize(path) > 0
    assert "snap_001_" in p1["txt"] and "snap_002_" in p2["txt"]
    data = json.load(open(p1["json"], encoding="utf-8"))
    ids = [n["id"] for n in data["nodes"]]
    assert ids == [n.id for n in iter_nodes(overlay.tree())]
    text = open(p1["txt"], encoding="utf-8").read()
    left = next(n for n in data["nodes"] if n["text"] == "Left")
    assert left["id"] in text and left["w"] == win.left.width()
    # Tag state is restored after the forced-tags tagged image.
    assert overlay.tag_depth is None


def test_main_window_roots():
    from gui.main_window import MainWindow
    win = MainWindow()
    win.resize(1920, 1050)
    win.show()
    _app.processEvents()
    overlay = DebugOverlay(win)
    try:
        prefixes = [p for p, _ in overlay.roots()]
        assert prefixes[:2] == ["BAR", "TABS"]
        win.tab_widget.setCurrentWidget(win.program_tab)
        _app.processEvents()
        trees = overlay.tree()
        assert [t.id for t in trees] == ["BAR", "TABS", "P"]
        assert trees[2].widget is win.program_tab
        assert len(trees[2].children) >= 2      # splitter panes at least
    finally:
        win._status_timer.stop()
        win._cycle_btn_timer.stop()
        win.close()
        win.deleteLater()
        _app.processEvents()


def test_row_with_mixed_heights_reads_left_to_right():
    """A taller, lower-starting widget in a row still sorts by x (the INCH
    toggle beside the ribbon chips); a stacked column still sorts by y."""
    win = QWidget()
    win.resize(600, 300)
    a = QLabel("a", win); a.setGeometry(10, 8, 100, 56)      # row band 8-64
    tall = QPushButton("tall", win); tall.setGeometry(300, 18, 90, 62)
    b = QLabel("b", win); b.setGeometry(450, 8, 100, 56)
    below = QLabel("below", win); below.setGeometry(10, 120, 100, 30)
    win.show()
    _app.processEvents()
    tree = build_tree(win, [("W", win)])[0]
    order = [n.widget for n in tree.children]
    assert order == [a, tall, b, below]
    win.close()
    win.deleteLater()
