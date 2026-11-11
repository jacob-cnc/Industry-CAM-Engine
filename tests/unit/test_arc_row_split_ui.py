"""Program tab: an arc row that is two pieces is split when the operator leaves
the row (owner decision 2026-11-11; geometry/arc_entry.py), never while typing."""
import pytest
from PyQt5.QtWidgets import QApplication
from gui.program_tab import ProgramTab

_app = QApplication.instance() or QApplication([])


@pytest.fixture
def tab():
    widget = ProgramTab()
    yield widget
    widget.close()
    widget.deleteLater()


def _flush():
    for _ in range(3):
        _app.processEvents()


ROWS = [{"type": "line", "x": 1.0, "z": 0.0, "radius": 0.0},
        {"type": "arc", "x": 1.0, "z": -1.0, "radius": "Q"},
        {"type": "line", "x": 1.0, "z": -1.5, "radius": 0.0}]


def test_leaving_a_same_x_quadrant_row_splits_it(tab):
    sl = tab._segment_list
    sl.set_segments(ROWS)
    sl.select_segment(1)
    _flush()
    assert len(sl.get_segments()) == 3                 # still on the row: untouched
    sl.select_segment(2)                               # leave it
    _flush()
    segs = sl.get_segments()
    assert [(s["x"], s["z"], s["radius"]) for s in segs[1:3]] == [
        (2.0, -0.5, "Q"), (1.0, -1.0, "-Q")]
    assert len(sl.get_corner_breaks()) == 3
    assert "split" in tab._status_label.text().lower()
    assert tab._selected_segment_index == 3             # the row the operator went to


def test_ordinary_rows_are_left_alone(tab):
    sl = tab._segment_list
    rows = [dict(r) for r in ROWS]
    rows[1] = {"type": "arc", "x": 1.5, "z": -0.25, "radius": "Q"}   # a true quarter
    sl.set_segments(rows)
    sl.select_segment(1)
    _flush()
    sl.select_segment(2)
    _flush()
    assert len(sl.get_segments()) == 3
