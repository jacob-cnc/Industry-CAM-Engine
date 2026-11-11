"""Arc entry in the segment list (arc strategy Phase 1, Principle C):
the picker shows both arcs for an end point + radius and the click sets the
sign of R; "T" in the radius cell becomes the tangent (smooth) radius."""
import math

import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication

from geometry.arc_entry import arc_candidates, end_direction, tangent_arc
from gui.components.segment_list import COL_RADIUS, SegmentListWidget

_app = QApplication.instance() or QApplication([])


@pytest.fixture
def sl():
    w = SegmentListWidget()
    w.resize(420, 600)
    w.show()
    yield w
    w.close()
    w.deleteLater()


ROWS = [{"type": "line", "x": 1.0, "z": 0.0, "radius": 0.0},
        {"type": "line", "x": 1.0, "z": -0.5, "radius": 0.0},
        {"type": "arc", "x": 1.4, "z": -0.7, "radius": 0.25}]


def test_picker_shows_both_arcs_and_a_click_sets_the_sign(sl):
    sl.set_segments(ROWS)
    sl.select_segment(2)
    picker = sl._arc_picker
    assert picker.isVisible() and picker.candidate_count() == 2
    assert picker.selected_sign() == 1
    picker.grab()                                       # paint: screen points
    other = next(i for i, c in enumerate(picker._cands) if c["radius"] < 0)
    pt = picker._screen[other][len(picker._screen[other]) // 2]
    QTest.mouseClick(picker, Qt.LeftButton, pos=pt.toPoint())
    assert sl.get_segments()[2]["radius"] == pytest.approx(-0.25)
    assert picker.selected_sign() == -1


def test_picker_hidden_for_lines_and_quadrants(sl):
    rows = [dict(r) for r in ROWS]
    rows[2] = {"type": "arc", "x": 1.4, "z": -0.7, "radius": "Q"}
    sl.set_segments(rows)
    sl.select_segment(1)
    assert not sl._arc_picker.isVisible()
    sl.select_segment(2)
    assert not sl._arc_picker.isVisible()


def test_t_becomes_the_tangent_radius(sl):
    sl.set_segments(ROWS)
    sl.select_segment(2)
    sl._table.item(2, COL_RADIUS).setText("T")
    r = sl.get_segments()[2]["radius"]
    # leaving X.5 along -Z, ending .2 out (radius) and .2 further: R .2, curving out
    assert abs(r) == pytest.approx(0.2, abs=1e-4)
    want, _ = tangent_arc((0.5, -0.5), (0.7, -0.7), (0.0, -1.0))
    assert r == pytest.approx(want, abs=1e-4)
    assert sl._arc_picker._tangent_sign == sl._arc_picker.selected_sign()   # "smooth"


def test_t_that_cannot_be_tangent_stays_flagged(sl):
    rows = [dict(r) for r in ROWS]
    rows[2] = {"type": "arc", "x": 1.0, "z": -0.9, "radius": 0.0}  # straight ahead
    sl.set_segments(rows)
    sl._table.item(2, COL_RADIUS).setText("T")
    assert sl._table.item(2, COL_RADIUS).text().upper() == "T"
    ok, why = sl._validate_arc_radius(2)
    assert not ok and "straight ahead" in why


def test_t_after_a_quadrant_uses_its_end_direction(sl):
    rows = [{"type": "line", "x": 1.0, "z": 0.0, "radius": 0.0},
            {"type": "arc", "x": 1.5, "z": -0.25, "radius": "Q"},   # arrives along -Z
            {"type": "arc", "x": 1.7, "z": -0.45, "radius": 0.0}]
    sl.set_segments(rows)
    sl._table.item(2, COL_RADIUS).setText("T")
    # from X1.5 Z-.25 arriving along -Z: centre (r 1.0, Z -.25), R .25
    want, _ = tangent_arc((0.75, -0.25), (0.85, -0.45), (0.0, -1.0))
    assert abs(want) == pytest.approx(0.25)
    assert sl.get_segments()[2]["radius"] == pytest.approx(want, abs=1e-4)


# --- core helpers ---------------------------------------------------------

def test_candidates_are_the_two_sides_of_the_chord():
    c = arc_candidates((0.5, 0.0), (0.6, -0.1), 0.1)
    assert sorted(x["radius"] for x in c) == [-0.1, 0.1]
    assert sorted(round(abs(x["sweep"]), 6) for x in c) == [round(math.pi / 2, 6)] * 2
    assert arc_candidates((0.5, 0.0), (0.6, -0.1), 0.05) == []      # shorter than chord/2


def test_end_directions():
    assert end_direction((0.5, 0.0), (0.6, -0.1), "Q", True) == (0.0, -1.0)
    assert end_direction((0.5, 0.0), (0.6, -0.1), "-Q", True) == (1.0, 0.0)
    assert end_direction((0.5, 0.0), (0.5, -1.0), 0.0, False) == (0.0, -1.0)


def test_tangent_refuses_more_than_half_a_turn():
    r, why = tangent_arc((0.5, 0.0), (0.6, 0.2), (0.0, -1.0))       # end is behind
    assert r is None and "180" in why
