"""Corner-break tool: vertex picking rules, vertex model in the builder,
apply/remove with trim pop-ups, and the preview drawing engine geometry."""

import math

import pytest
from PyQt5.QtWidgets import QApplication

from gui.components.vertex_picking import pick_vertex

_app = QApplication.instance() or QApplication([])

S = 0.1     # the NX reference part (mm) scaled to inch size
NX_PTS = [(6, 0), (6, -6), (12, -6), (12, -12), (6, -12), (6, -18), (15, -18),
          (15, -21), (12, -21), (12, -27), (18, -27), (18, -33)]


# ----------------------------------------------------------------------
# Picking rules (pure, screen pixels)
# ----------------------------------------------------------------------

def test_nearest_within_tolerance():
    pts = [(0, 0), (100, 0)]
    assert pick_vertex((5, 3), pts, [None] * 2, [None] * 2) == [0]
    assert pick_vertex((96, 0), pts, [None] * 2, [None] * 2) == [1]
    assert pick_vertex((50, 0), pts, [None] * 2, [None] * 2) == []      # out of range


def test_tie_broken_by_side_of_corner():
    """Two vertices on the same pixel (a segment used up by its breaks):
    the one whose segments point toward the cursor wins."""
    pts = [(50, 50), (50, 50)]
    prev = [(0, 50), (50, 50)]        # V_a: segment comes from the left
    nxt = [(50, 50), (50, 100)]       # V_b: segment goes down
    assert pick_vertex((40, 51), pts, prev, nxt) == [0]       # cursor left -> V_a
    assert pick_vertex((51, 60), pts, prev, nxt) == [1]       # cursor below -> V_b


def test_tie_then_selected_then_chooser():
    pts = [(50, 50), (50, 50)]
    none = [None, None]
    assert pick_vertex((52, 52), pts, none, none, selected=[1]) == [1]
    assert pick_vertex((52, 52), pts, none, none) == [0, 1]   # caller asks


# ----------------------------------------------------------------------
# Program tab integration
# ----------------------------------------------------------------------

def _program_window(monkeypatch, smooth_answer=None):
    """smooth_answer: QMessageBox.Yes / .No for the 'smooth?' prompt
    (default No = keep NX style). Prompt texts are recorded too."""
    from PyQt5.QtWidgets import QMessageBox
    from gui.main_window import MainWindow
    popups = []
    answer = QMessageBox.No if smooth_answer is None else smooth_answer

    def question(parent, title, text, *args, **kwargs):
        popups.append(text)
        return answer

    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda parent, title, text: popups.append(text)))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(question))
    w = MainWindow()
    w.resize(1918, 1034)
    w.show()
    w.tab_widget.setCurrentWidget(w.program_tab)
    pt = w.program_tab
    pt._segment_list.set_segments(
        [{"type": "line", "x": d * S, "z": z * S, "radius": 0.0} for d, z in NX_PTS], None)
    for _ in range(3):
        _app.processEvents()
    return w, pt, popups


def _close(w):
    w._status_timer.stop()
    w._cycle_btn_timer.stop()
    w.close()
    w.deleteLater()
    _app.processEvents()


def _apply(pt, vertices, kind, size):
    pt._cb_panel.set_selected([v - 1 for v in vertices])
    pt._cb_panel._kind.setCurrentIndex(0 if kind == "chamfer" else 1)
    pt._cb_panel._size.set_value(size)
    pt._cb_panel._btn_apply.click()
    _app.processEvents()


def test_tool_toggles_builder_and_lists_every_vertex(monkeypatch):
    w, pt, _ = _program_window(monkeypatch)
    try:
        pt._btn_cb_tool.click()
        _app.processEvents()
        assert pt._cb_panel.isVisible() and not pt._segment_list.isVisible()
        t = pt._cb_panel._table
        assert t.rowCount() == len(NX_PTS) - 1                 # V1..V11
        assert [t.item(r, 0).text() for r in (0, 10)] == ["V1", "V11"]
        assert t.item(0, 3).text() == "convex" and t.item(1, 3).text() == "concave"
        pt._btn_cb_tool.click()
        _app.processEvents()
        assert pt._segment_list.isVisible() and not pt._cb_panel.isVisible()
    finally:
        _close(w)


def test_apply_one_size_to_many_and_conflict_popup(monkeypatch):
    w, pt, popups = _program_window(monkeypatch)
    try:
        pt._btn_cb_tool.click()
        _apply(pt, [1, 2, 7, 8], "chamfer", 0.1)
        assert popups == []                                    # all fit
        _apply(pt, [3, 4, 5, 6, 9], "fillet", 0.1)
        assert len(popups) == 1 and popups[0].startswith("V9:")
        breaks = pt._segment_list.get_corner_breaks()
        assert [b["type"] if b else None for b in breaks] == [
            "chamfer", "chamfer", "fillet", "fillet", "fillet", "fillet",
            "chamfer", "chamfer", "fillet", None, None]
        assert all(abs((b.get("size") or b.get("radius")) - 0.1) < 1e-12
                   for b in breaks if b)
        t = pt._cb_panel._table
        assert t.item(8, 5).text() == "trimmed"
        assert "cut short" in t.item(8, 5).toolTip()
        pt._btn_cb_tool.click()                                 # badges in builder
        hdr = pt._segment_list._table.verticalHeaderItem
        assert hdr(8).text().endswith("R.1!") and hdr(7).text().endswith("C.1")
    finally:
        _close(w)


def test_remove_and_status_change_on_neighbour(monkeypatch):
    """Removing V8's chamfer frees the Z-2.1 face: V9 goes back to ok."""
    w, pt, popups = _program_window(monkeypatch)
    try:
        pt._btn_cb_tool.click()
        _apply(pt, [8], "chamfer", 0.1)
        _apply(pt, [9], "fillet", 0.1)
        assert len(popups) == 1
        pt._cb_panel.set_selected([7])
        pt._cb_panel._btn_remove.click()
        _app.processEvents()
        breaks = pt._segment_list.get_corner_breaks()
        assert breaks[7] is None and breaks[8]["type"] == "fillet"
        assert pt._cb_panel._table.item(8, 5).text() == "ok"
    finally:
        _close(w)


def test_preview_draws_engine_geometry(monkeypatch):
    """Every engine trim point lies on the drawn outline; V1 at the face too."""
    w, pt, _ = _program_window(monkeypatch)
    try:
        pt._btn_cb_tool.click()
        _apply(pt, [1, 2, 7, 8], "chamfer", 0.1)
        _apply(pt, [3, 4, 5, 6, 9], "fillet", 0.1)
        _apply(pt, [10], "fillet", 0.3)
        pt._update_preview()
        drawn = [p for zs, xs in pt._profile_contour_segments for p in zip(xs, zs)]
        geo = pt._od_corner_result().geometry
        assert sorted(geo) == list(range(10))
        worst = max(min(math.dist(p, q) for q in drawn)
                    for g in geo.values() for p in (g.t_in, g.t_out))
        assert worst < 1e-9
        assert math.dist(drawn[0], geo[0].t_in) < 1e-9       # starts at V1's chamfer
    finally:
        _close(w)


def test_tool_button_says_how_to_leave_and_esc_leaves(monkeypatch):
    w, pt, _ = _program_window(monkeypatch)
    try:
        pt._btn_cb_tool.click()
        _app.processEvents()
        assert "Back to Segment Builder" in pt._btn_cb_tool.text()
        pt._cb_esc.activated.emit()                        # Esc
        _app.processEvents()
        assert not pt._btn_cb_tool.isChecked()
        assert pt._btn_cb_tool.text() == "Corner Breaks"
        assert pt._segment_list.isVisible() and not pt._cb_panel.isVisible()
    finally:
        _close(w)


def test_trim_prompt_no_keeps_nx_style(monkeypatch):
    w, pt, popups = _program_window(monkeypatch)            # answers No
    try:
        pt._btn_cb_tool.click()
        _apply(pt, [8], "chamfer", 0.1)
        _apply(pt, [9], "fillet", 0.1)
        assert len(popups) == 1 and "Smooth the trimmed fillet (V9)?" in popups[0]
        breaks = pt._segment_list.get_corner_breaks()
        assert breaks[8].get("trim", "nx") == "nx"
        assert pt._cb_panel._table.item(8, 5).text() == "trimmed"
    finally:
        _close(w)


def test_trim_prompt_yes_smooths(monkeypatch):
    from PyQt5.QtWidgets import QMessageBox
    w, pt, popups = _program_window(monkeypatch, smooth_answer=QMessageBox.Yes)
    try:
        pt._btn_cb_tool.click()
        _apply(pt, [8], "chamfer", 0.1)
        _apply(pt, [9], "fillet", 0.1)
        assert len(popups) == 2                             # question + result
        assert "rolls onto the V8 chamfer" in popups[1]
        breaks = pt._segment_list.get_corner_breaks()
        assert breaks[8]["trim"] == "smooth"
        t = pt._cb_panel._table
        assert t.item(7, 5).text() == "smoothed" and t.item(8, 5).text() == "smoothed"
        pt._btn_cb_tool.click()
        hdr = pt._segment_list._table.verticalHeaderItem
        assert hdr(8).text().endswith("R.1~") and hdr(7).text().endswith("C.1~")
    finally:
        _close(w)


# ----------------------------------------------------------------------
# Vertex dots stay live over a generated toolpath (not while playing)
# ----------------------------------------------------------------------

def _fail_instead_of_error_dialog(monkeypatch):
    """The generation error dialog is modal and hangs an offscreen run."""
    from gui.components import error_dialog

    def _raise(self, exc, tb_str, stage=None):
        raise AssertionError(f"generate failed at {stage}: {exc}\n{tb_str}")

    monkeypatch.setattr(error_dialog.GenerationErrorDialog, "show_exception", _raise)


def _generated_window(monkeypatch):
    """Small two-step part with stock big enough to plan, then Generate."""
    from gui.program_tab import ProgramState
    _fail_instead_of_error_dialog(monkeypatch)
    w, pt, popups = _program_window(monkeypatch)
    pts = [(0.5, 0.0), (0.5, -0.5), (1.0, -0.5), (1.0, -1.0), (1.2, -1.0), (1.2, -1.5)]
    pt._segment_list.set_segments(
        [{"type": "line", "x": d, "z": z, "radius": 0.0} for d, z in pts], None)
    pt._stock_diameter.set_value(1.25)
    pt._stock_back_z.set_value(-1.5)
    pt._rough_tool_num.setValue(4)                     # T4 CNMG (T1 is a boring bar)
    pt._finish_tool_num.setValue(4)
    _app.processEvents()
    pt._generate_btn.click()
    _app.processEvents()
    assert pt.state == ProgramState.DISPLAYING, popups
    return w, pt, len(pts)


def _overlay_on_graph(pt) -> bool:
    items = pt._graph_widget.getPlotItem().items
    return len(pt._cb_overlay_items) == 3 and all(i in items for i in pt._cb_overlay_items)


def test_dots_appear_when_tool_opened_after_generate(monkeypatch):
    w, pt, n = _generated_window(monkeypatch)
    try:
        pt._btn_cb_tool.click()
        _app.processEvents()
        assert _overlay_on_graph(pt)
        dots = pt._cb_overlay_items[1]
        assert len(dots.data) == n - 1                       # every vertex, no edit needed
        pt._cb_panel.set_selected([1])                       # selection highlight works too
        _app.processEvents()
        assert len(pt._cb_overlay_items[2].data) == 1
        pt._btn_cb_tool.click()                              # closing the tool removes them
        _app.processEvents()
        assert pt._cb_overlay_items == []
    finally:
        _close(w)


def test_dots_survive_regenerate_with_tool_open(monkeypatch):
    """Tool open in BUILDING, then Generate: the new plot keeps the dots."""
    _fail_instead_of_error_dialog(monkeypatch)
    w, pt, _ = _program_window(monkeypatch)
    try:
        pts = [(0.5, 0.0), (0.5, -0.5), (1.0, -0.5), (1.0, -1.0), (1.2, -1.0), (1.2, -1.5)]
        pt._segment_list.set_segments(
            [{"type": "line", "x": d, "z": z, "radius": 0.0} for d, z in pts], None)
        pt._stock_diameter.set_value(1.25)
        pt._stock_back_z.set_value(-1.5)
        pt._rough_tool_num.setValue(4)                 # T4 CNMG (T1 is a boring bar)
        pt._finish_tool_num.setValue(4)
        pt._btn_cb_tool.click()
        _app.processEvents()
        pt._generate_btn.click()
        _app.processEvents()
        assert _overlay_on_graph(pt)
    finally:
        _close(w)


def test_dots_hidden_and_clicks_ignored_while_playing(monkeypatch):
    w, pt, _ = _generated_window(monkeypatch)
    try:
        pt._btn_cb_tool.click()
        _app.processEvents()
        sv = pt._sim_viewer
        sv._toggle_play()                                    # play
        assert sv.is_playing()
        assert pt._cb_overlay_items == []

        class _Ev:                                           # a click right on V1
            def __init__(self, pos):
                self._pos = pos
            def button(self):
                return Qt.LeftButton
            def double(self):
                return False
            def modifiers(self):
                return Qt.NoModifier
            def scenePos(self):
                return self._pos
            def accept(self):
                pass

        from PyQt5.QtCore import QPointF, Qt
        verts, _p, _n = pt._sharp_vertex_points()
        on_v1 = pt._graph_widget.getViewBox().mapViewToScene(QPointF(*verts[0]))
        pt._on_graph_clicked_cb(_Ev(on_v1))
        assert pt._cb_selected == []                         # ignored while playing

        sv._toggle_play()                                    # pause -> dots back
        assert not sv.is_playing() and _overlay_on_graph(pt)
        pt._on_graph_clicked_cb(_Ev(on_v1))
        _app.processEvents()
        assert pt._cb_selected == [0]
    finally:
        _close(w)
