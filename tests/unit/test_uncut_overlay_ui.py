"""After Generate the graph shows BOTH the drawn profile and what is cut: the
material the tool can't reach (geometry/tool_reach.py) is shaded between the
drawn contour and the line the tool follows, and hides with the profile."""
import os
import sys

import pytest
from PyQt5.QtWidgets import QApplication

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "integration"))
from test_tool_reach import CNMG  # noqa: E402

_app = QApplication.instance() or QApplication([])

NECK = {
    "version": 1, "block_type": "OD Profile",
    "stock": {"diameter": 1.4, "x_start": 1.4, "z_start": 0.05, "z_end": -1.2, "mode": "od"},
    "roughing": {"tool_number": 4, "doc_dia": 0.05, "feed": 0.008, "fin_allowance": 0.01},
    "finishing": {"tool_number": 4},
    "segments": [{"type": "line", "x": x, "z": z, "radius": 0.0}
                 for x, z in ((1.0, 0.0), (1.0, -0.4), (0.7, -0.4), (0.7, -0.8),
                              (1.2, -0.8), (1.2, -1.2))],
    "corner_breaks": [None] * 5,
}


@pytest.fixture
def tab():
    from gui.program_tab import ProgramTab
    w = ProgramTab()
    w.set_tool_resolver(lambda n: CNMG)
    yield w
    w.close()
    w.deleteLater()


def test_uncut_region_shaded_with_the_drawn_profile(tab):
    tab._load_program_data(NECK)
    tab.show()
    tab._update_preview()
    tab._on_generate_clicked()
    _app.processEvents()
    assert "note" in tab._status_label.text()
    assert any("Left uncut" in n for n in tab._generate_notes)
    assert len(tab._uncut_outlines) == 1
    xs = [p[0] for p in tab._uncut_outlines[0]]
    assert min(xs) == pytest.approx(0.7) and max(xs) == pytest.approx(1.0, abs=1e-3)
    g = tab._sim_viewer._graph
    assert g._profile_overlay_items and g._uncut_overlay_items
    g.set_profile_visible(False)
    assert not any(i.isVisible() for i in g._uncut_overlay_items)
    g.set_profile_visible(True)
    assert all(i.isVisible() for i in g._uncut_overlay_items)


def test_no_shading_when_the_tool_reaches_everything(tab):
    data = dict(NECK, segments=[{"type": "line", "x": x, "z": z, "radius": 0.0}
                                for x, z in ((1.0, 0.0), (1.0, -0.4), (1.2, -0.4), (1.2, -1.2))],
                corner_breaks=[None] * 3)
    tab._load_program_data(data)
    tab.show()
    tab._update_preview()
    tab._on_generate_clicked()
    _app.processEvents()
    assert tab._uncut_outlines == []
    assert not getattr(tab._sim_viewer._graph, "_uncut_overlay_items", [])
