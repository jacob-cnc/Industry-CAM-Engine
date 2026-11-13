"""The tool on the Manual graph (tool-graphic plan 2026-11-13, phase T2), offscreen."""
import dataclasses
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PyQt5.QtCore import QPointF  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

_app = QApplication.instance() or QApplication([])

from gui.components.position_graph import PositionGraphWidget  # noqa: E402
from gui.components.tool_graphic_item import graphic_for  # noqa: E402
from tools.tool_card_data import ToolCardData  # noqa: E402


def _card(**kw):
    c = dict(tool_number=4, tool_type="Turning RH", insert_code="CNMG", orientation=2,
             description="", nose_radius=1 / 64, front_angle=95.0, back_angle=175.0,
             x_offset=0.0123, z_offset=-0.25, x_wear=0.0005, z_wear=0.0, iso_code="CNMG431")
    c.update(kw)
    return ToolCardData(**c)


def _offset(c):
    return (c.x_offset + c.x_wear, c.z_offset + c.z_wear)


def _graph():
    g = PositionGraphWidget()
    g.resize(900, 600)
    g.show()
    return g


def test_the_controlled_point_lands_on_the_dro_position():
    """The outline's (0, 0) is drawn exactly where the work position maps on
    screen, and +X (diameter) is DOWN as on the rest of the graph."""
    g = _graph()
    c = _card()
    out, note = graphic_for(c, 4, _offset(c))
    assert out is not None and note == ""
    g.set_tool_outline(out)
    g.update_position(1.0, -0.5)
    vb = g.getViewBox()
    vb.setRange(xRange=(-0.9, -0.1), yRange=(0.3, 0.9), padding=0)
    _app.processEvents()
    body = g.tool_graphic._body
    got = body.mapToScene(QPointF(0.0, 0.0))
    want = vb.mapViewToScene(QPointF(-0.5, 0.5))
    assert (got.x(), got.y()) == pytest.approx((want.x(), want.y()), abs=1e-6)
    # the nose centre (r + R, z + R for Q2) is right of and BELOW the tip on screen
    nc = body.mapToScene(QPointF(out.nose_centre[1], out.nose_centre[0]))
    assert nc.x() > got.x() and nc.y() > got.y()


def test_fast_move_only_moves_the_tool():
    g = _graph()
    c = _card()
    g.set_tool_outline(graphic_for(c, 4, _offset(c))[0])
    g.update_position(1.0, -0.5)
    g.move_tool(1.2, -0.3)
    assert g.tool_graphic.position() == pytest.approx((0.6, -0.3))
    assert g.tool_graphic._body.pos().x() == pytest.approx(-0.3)


def test_dot_without_a_drawable_tool():
    g = _graph()
    g.set_tool_outline(None, "T3: edge angles unknown")
    gt = g.tool_graphic
    assert gt._dot.isVisible() and not gt._body.isVisible() and gt._note.isVisible()


@pytest.mark.parametrize("card, tool, offset, note", [
    (None, 0, None, ""),                                          # no tool: plain dot
    (None, 7, None, "T7 is not in the tool table"),
    (_card(front_angle=0.0, back_angle=0.0, insert_code="Custom", iso_code=""), 4, None,
     "angles unknown"),
])
def test_dot_reasons(card, tool, offset, note):
    out, got = graphic_for(card, tool, offset)
    assert out is None and note in got


def test_g43_not_applied_shows_the_dot_not_a_misplaced_insert():
    c = _card()
    out, note = graphic_for(c, 4, (0.0, 0.0))
    assert out is None and "G43" in note


def test_interface_work_position_has_no_side_effects():
    from hal.mock_backend import MockBackend
    b = MockBackend()
    b.poll()
    assert b.work_position() == (b.state.x.position, b.state.z.position)


# ------------------------------------------------------------ T3: Run graph

def test_run_graph_live_shows_the_spindle_tool_sim_shows_the_dot():
    """Live positions draw the spindle tool; sim playback keeps the dot until
    the sim knows each move's tool (plan phase T4)."""
    from gui.components.graph_widget import MachiningGraphWidget as GraphWidget
    g = GraphWidget()
    c = _card()
    g.set_live_tool_outline(graphic_for(c, 4, _offset(c))[0])
    g.set_tool_position(0.5, -0.5, live=True)
    gt = g._tool_graphic
    assert gt.outline is not None and gt._body.isVisible() and not gt._dot.isVisible()
    g.set_tool_position(0.4, -0.2)                               # sim playback
    assert gt.outline is None and gt._dot.isVisible()
    g.set_tool_position(0.5, -0.5, live=True)
    assert gt.outline is not None


def test_run_graph_survives_a_program_reload():
    from gui.components.graph_widget import MachiningGraphWidget as GraphWidget
    g = GraphWidget()
    c = _card()
    g.set_live_tool_outline(graphic_for(c, 4, _offset(c))[0])
    g.set_tool_position(0.5, -0.5, live=True)
    g.clear_toolpath()                                           # clears every plot item
    g.set_tool_position(0.5, -0.5, live=True)
    assert g._tool_graphic.outline is not None and g._tool_graphic._body.scene() is not None
