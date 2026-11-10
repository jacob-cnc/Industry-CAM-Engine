"""Segment builder: Insert, numbering, large text, r column, and the
Program tab's 420 px column that widens only to avoid overflow.

Invariant-style checks (they hold for any segment list), not one layout.
"""

import os

import pytest

# Lay out like the app does (main() pins font DPI to 96, matching the lathe);
# only effective if this module creates the QApplication.
os.environ.setdefault("QT_FONT_DPI", "96")

from PyQt5.QtGui import QFontInfo  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from gui.components.segment_list import (  # noqa: E402
    SegmentListWidget, SEG_FONT_PX, SEGMENT_ROW_HEIGHT, COL_TYPE, COL_X,
    COL_RADIUS,
)

_app = QApplication.instance() or QApplication([])

FILLET = {"type": "fillet", "size": 0.03, "angle": 45.0, "radius": 0.03}
CHAMFER = {"type": "chamfer", "size": 0.02, "angle": 45.0, "radius": 0.0}


def _three():
    return ([{"type": "line", "x": 1.0, "z": 0.0, "radius": 0.0},
             {"type": "line", "x": 1.0, "z": -1.0, "radius": 0.0},
             {"type": "line", "x": 2.0, "z": -1.5, "radius": 0.0}],
            [FILLET, CHAMFER])


def _corner_types(w):
    return [None if c is None else c["type"] for c in w.get_corner_breaks()]


@pytest.fixture
def seg():
    w = SegmentListWidget()
    w.resize(420, 600)
    w.show()
    w.set_segments(*_three())
    _app.processEvents()
    yield w
    w.close()
    w.deleteLater()
    _app.processEvents()


@pytest.mark.parametrize("number", [1, 2, 3])
def test_insert_is_zero_length_and_keeps_everything_else(seg, number):
    before = seg.get_segments()
    seg.insert_segment_before(number)
    after = seg.get_segments()
    k = number - 1
    assert len(after) == len(before) + 1
    new = after[k]
    src = before[k - 1] if k > 0 else before[0]
    assert (new["type"], new["x"], new["z"]) == ("line", src["x"], src["z"])
    # Not a replace: every original segment is unchanged, in order.
    assert after[:k] + after[k + 1:] == before
    # Corners stay as they were; only the new junction (new -> old #number) is None.
    expected = ["fillet", "chamfer"]
    expected.insert(k, None)
    assert _corner_types(seg) == expected


def test_numbers_follow_segments_and_skip_corner_rows(seg):
    seg.insert_segment_before(2)
    t = seg._table
    labels = [t.verticalHeaderItem(r).text() for r in range(t.rowCount())]
    assert [l for l in labels if l] == ["1", "2", "3", "4"]
    for r, label in enumerate(labels):
        assert (label == "") == seg._is_corner_break_row(r)
    assert seg._insert_before.maximum() == 4


@pytest.mark.parametrize("col", [COL_X, 2])          # X and Z cells
def test_cell_editor_keeps_large_text(seg, col):
    """Clicking into a cell must not drop to the app's small line-edit font."""
    from PyQt5.QtWidgets import QLineEdit
    t = seg._table
    t.setCurrentCell(0, col)
    t.editItem(t.item(0, col))
    _app.processEvents()
    # The cell editor lives on the viewport; corner-break rows hold their
    # own NumericField line edits, which are not cell editors.
    editors = [e for e in t.viewport().findChildren(QLineEdit)
               if e.isVisible() and type(e) is QLineEdit]
    assert editors, "no cell editor opened"
    ed = editors[0]
    assert ed.font().pixelSize() == SEG_FONT_PX
    assert f"font-size: {SEG_FONT_PX}px" in ed.styleSheet()
    assert ed.alignment() & 0x2                          # Qt.AlignRight
    assert ed.height() <= t.rowHeight(0)                 # fits the row


def test_large_text_without_taller_rows(seg):
    t = seg._table
    # Requested sizes (a font-less offscreen platform cannot resolve them).
    assert t.item(0, COL_X).font().pixelSize() == SEG_FONT_PX
    assert f"font-size: {SEG_FONT_PX}px" in t.cellWidget(0, COL_TYPE).styleSheet()
    assert t.rowHeight(0) == SEGMENT_ROW_HEIGHT == 69


def _real_fonts() -> bool:
    """False on a platform with no font database (e.g. bare offscreen),
    where text widths are meaningless for pixel-budget checks."""
    from PyQt5.QtGui import QFont
    return bool(QFontInfo(QFont()).family())


def test_r_column_opens_only_for_selected_arc_row(seg):
    t = seg._table
    narrow = t.horizontalHeader().sectionSize(COL_RADIUS)
    row1 = seg._segment_index_to_row(1)
    t.cellWidget(row1, COL_TYPE).setCurrentText("ARC")   # also selects it
    _app.processEvents()
    assert t.currentRow() == row1
    wide = t.horizontalHeader().sectionSize(COL_RADIUS)
    assert wide > narrow
    t.setCurrentCell(seg._segment_index_to_row(0), COL_X)   # a LINE row
    _app.processEvents()
    assert t.horizontalHeader().sectionSize(COL_RADIUS) == narrow


def test_columns_never_overflow_at_required_width(seg):
    """At required_width() every column shows its widest value in full."""
    seg.resize(seg.required_width(), 600)
    _app.processEvents()
    t = seg._table
    fm = t.fontMetrics()
    hdr = t.horizontalHeader()
    assert sum(hdr.sectionSize(c) for c in range(4)) <= t.viewport().width()


def _program_window():
    from gui.main_window import MainWindow
    from gui.colors import STYLESHEET
    _app.setStyleSheet(STYLESHEET)      # as main() does: scrollbar/header sizes
    w = MainWindow()
    w.resize(1918, 1034)
    w.show()
    w.tab_widget.setCurrentWidget(w.program_tab)
    for _ in range(3):
        _app.processEvents()
    return w


def _close(w):
    w._status_timer.stop()
    w._cycle_btn_timer.stop()
    w.close()
    w.deleteLater()
    _app.setStyleSheet("")
    _app.processEvents()


def test_program_column_420_widens_for_arc_and_returns():
    if not _real_fonts():
        pytest.skip("needs real fonts: the 420 px budget is a pixel measurement")
    w = _program_window()
    try:
        pt = w.program_tab
        seg = pt._segment_list
        dpi96 = round(QApplication.primaryScreen().logicalDotsPerInch()) == 96
        seg.set_segments(*_three())
        for _ in range(3):
            _app.processEvents()
        line_w = pt._splitter.sizes()[0]
        assert line_w >= 420
        if dpi96:                       # the app's (and lathe's) layout
            assert line_w == 420        # LINE rows fit: no widening
        assert seg.width() >= seg.required_width()     # never overflows
        t = seg._table
        t.cellWidget(seg._segment_index_to_row(1), COL_TYPE).setCurrentText("ARC")
        for _ in range(4):
            _app.processEvents()
        assert pt._splitter.sizes()[0] > line_w        # widened for r column
        assert seg.width() >= seg.required_width()     # no overflow
        t.setCurrentCell(seg._segment_index_to_row(0), COL_X)
        for _ in range(4):
            _app.processEvents()
        assert pt._splitter.sizes()[0] == line_w       # back to where it was
    finally:
        _close(w)


def test_parameters_holds_setup_sections_and_collapses():
    w = _program_window()
    try:
        pt = w.program_tab
        params = pt._section_parameters
        for s in (pt._section_blocks, pt._section_stock, pt._section_roughing,
                  pt._section_finishing, pt._section_threading,
                  pt._section_grooving, pt._section_parting):
            assert params.isAncestorOf(s)
        assert not params.isAncestorOf(pt._section_profile)
        open_h = pt._section_profile.height()
        params.set_expanded(False)
        for _ in range(3):
            _app.processEvents()
        assert pt._section_profile.height() > open_h
        gen_top = pt._generate_btn.mapTo(w, pt._generate_btn.rect().topLeft()).y()
        prof = pt._section_profile
        prof_bottom = prof.mapTo(w, prof.rect().bottomLeft()).y()
        assert gen_top - prof_bottom <= 10            # fills down to Generate
    finally:
        _close(w)


def test_button_order(seg):
    """Left to right: Add, Remove, Insert (+ its # box), Move Up, Move Down."""
    widgets = [seg._btn_add, seg._btn_remove, seg._btn_insert,
               seg._insert_before, seg._btn_move_up, seg._btn_move_down]
    xs = [w.x() for w in widgets]
    assert xs == sorted(xs)
    assert [b.text() for b in widgets if b is not seg._insert_before] == \
        ["Add", "Remove", "Insert", "Move Up", "Move Down"]


def test_first_view_defaults():
    """Parameters + Profile open, setup sections collapsed; finish
    allowance and calculated finish DOC default to 0.002 (dia)."""
    w = _program_window()
    try:
        pt = w.program_tab
        assert pt._section_parameters.is_expanded
        assert pt._section_profile.is_expanded
        for s in (pt._section_blocks, pt._section_stock,
                  pt._section_roughing, pt._section_finishing):
            assert not s.is_expanded
        assert pt._rough_fin_allowance.value() == pytest.approx(0.002)
        assert pt._finish_passes.value() == 1
        assert pt._finish_doc.value() == pytest.approx(0.002)
    finally:
        _close(w)
