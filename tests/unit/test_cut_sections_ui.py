"""The shaded sections on screen (docs/handoffs/2026-11-11-zone-shading-plan.md).

Renders the real Program tab offscreen and reads pixel colours: at high zoom,
.0005" either side of the finished edge must be the finished-part colour on one
side and the cleanup/finish colour on the other, for OD and ID. That is the
check the earlier shading never had (it drew the right data the wrong way)."""
import os
import shutil
import sys

import pytest
from PyQt5.QtCore import QPointF
from PyQt5.QtWidgets import QApplication

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "integration"))
from test_tool_reach import BAR, CNMG  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("rs274") is None, reason="LinuxCNC rs274 not installed")
_app = QApplication.instance() or QApplication([])


def _program(mode, pts, stock_dia, pilot=0.0):
    return {"version": 1, "block_type": "ID Profile" if mode == "id" else "OD Profile",
            "stock": {"diameter": stock_dia, "x_start": pilot if mode == "id" else 0.0,
                      "z_start": 0.05, "z_end": min(z for _, z in pts), "mode": mode,
                      "pilot_hole_dia": pilot, "x_park": 0.5 if mode == "id" else 3.0},
            "roughing": {"tool_number": 4, "doc_dia": 0.06, "feed": 0.008, "fin_allowance": 0.02},
            "finishing": {"tool_number": 4},
            "segments": [{"type": "line", "x": x, "z": z, "radius": 0.0} for x, z in pts],
            "corner_breaks": [None] * (len(pts) - 1)}


OD = ("od", [(1.0, 0.0), (1.0, -0.4), (1.2, -0.4), (1.2, -1.0)], 1.4, 0.0, CNMG)
ID = ("id", [(1.0, 0.0), (1.0, -0.4), (0.9, -0.4), (0.9, -1.0)], 1.6, 0.7, BAR)


@pytest.fixture
def tab():
    from gui.program_tab import ProgramTab
    w = ProgramTab()
    w.resize(1500, 850)
    yield w
    w.close()
    w.deleteLater()


def _generate(tab, case):
    mode, pts, dia, pilot, tool = case
    tab.set_tool_resolver(lambda n: tool)
    tab._load_program_data(_program(mode, pts, dia, pilot))
    tab.show()
    _app.processEvents()
    tab._update_preview()
    _app.processEvents()
    preview_has_finished = bool(tab._sim_viewer._graph._section_items.get("finished"))
    tab._on_generate_clicked()
    _app.processEvents()
    return preview_has_finished


def _pixel(g, img, z, r):
    vb = g.getPlotItem().getViewBox()
    p = g.mapFromScene(vb.mapViewToScene(QPointF(z, r)))
    return img.pixelColor(p.x(), p.y())


def _close(c1, c2, tol=10):
    return all(abs(a - b) <= tol for a, b in zip(c1.getRgb()[:3], c2.getRgb()[:3]))


@pytest.mark.parametrize("case", [OD, ID], ids=["OD", "ID"])
def test_finished_edge_is_exact_on_screen(tab, case):
    assert _generate(tab, case)                                     # preview: finished part only
    rings = tab._last_cut_rings
    assert rings["finished"] and rings["band"] and rings["rough"]
    assert not rings["gouge"] and not rings["not_removed"]
    g = tab._sim_viewer._graph
    g.resize(900, 700)
    z = -0.2137                                                      # along the X1.0 diameter
    g.setXRange(z - 0.03, z + 0.03, padding=0)
    g.setYRange(0.47, 0.53, padding=0)                               # ~.0001"/px
    tab._sim_viewer._graph.set_rapids_visible(False)
    for item in g._profile_overlay_items:                            # the white line sits on the edge
        item.setVisible(False)
    _app.processEvents()
    img = g.grab().toImage()
    inside = -1 if case[0] == "od" else 1                            # finished side of r = .5
    fin_ref = _pixel(g, img, z + 0.011, 0.5 + inside * 0.012)
    band_ref = _pixel(g, img, z + 0.011, 0.5 - inside * 0.004)
    assert not _close(fin_ref, band_ref, 6)                          # two different colours
    for dz in (-0.017, 0.0, 0.019):
        assert _close(_pixel(g, img, z + dz, 0.5 + inside * 0.0005), fin_ref)
        assert _close(_pixel(g, img, z + dz, 0.5 - inside * 0.0005), band_ref)


def test_legend_toggles_sections(tab):
    _generate(tab, OD)
    sv = tab._sim_viewer
    assert sv._legend.isVisibleTo(sv)
    box = sv._section_boxes["finished"]
    box.setChecked(False)
    assert not any(i.isVisible() for i in sv._graph._section_items["finished"])
    box.setChecked(True)
    assert all(i.isVisible() for i in sv._graph._section_items["finished"])
