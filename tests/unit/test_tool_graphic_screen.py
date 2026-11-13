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
    """Live positions draw the spindle tool; a sim position with no tool
    graphic (plain G-code path, no interpreter) is the dot."""
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


# ------------------------------------------------------- T4: sim from canon

_SIM_PROG = ("G18 G20 G7 G90 G95\nT4 M6 G43\nS500 M3\nG0 X1.0 Z0.1\nG1 Z-0.5 F.004\n"
             "G0 X1.2\nT1 M6 G43\nG0 X0.5 Z0.1\nG1 Z-0.3\nG0 X0.4\nM2\n")


def _sim_table(tmp_path):
    from tools.tool_table_io import save_tool_table
    t4 = _card()
    t1 = _card(tool_number=1, tool_type="Boring Bar", insert_code="CCMT", orientation=3,
               iso_code="CCMT32.51", x_offset=0.05, z_offset=0.3, x_wear=0.0)
    path = str(tmp_path / "tool.tbl")
    save_tool_table([t1, t4], path)
    return path


@pytest.mark.skipif(__import__("shutil").which("rs274") is None, reason="rs274 not installed")
def test_sim_draws_each_move_with_its_own_tool(tmp_path):
    from gui.components.sim_viewer import SimViewerWidget, build_sim_moves
    from outputs.gcode_parser import parse as parse_gcode
    from outputs.graph_adapter import convert_from_moves
    moves, note = build_sim_moves(_SIM_PROG, _sim_table(tmp_path))
    assert note == ""
    tools = [(m.line_idx, m.graphic[0].ic if m.graphic[0] else None) for m in moves]
    assert tools[0] == (4, 0.5) and tools[-1] == (9, 0.375)          # CNMG431, then CCMT32.51
    v = SimViewerWidget()
    v.load(convert_from_moves(parse_gcode(_SIM_PROG)), _SIM_PROG, moves, note)
    # every interpreter move maps to the drawn segment of its own line
    assert len(v._sim_to_toolmoves) == len(moves)
    gt = v._graph._tool_graphic
    for step in (5, v._path_len - 2):
        v._sim_step = step
        v._update_display()
        r, z, i = v._path[step]
        assert gt.outline is moves[i].graphic[0] and gt.position() == pytest.approx((r, z))


@pytest.mark.skipif(__import__("shutil").which("rs274") is None, reason="rs274 not installed")
def test_sim_without_g43_shows_the_dot_with_the_reason(tmp_path):
    from gui.components.sim_viewer import build_sim_moves
    prog = _SIM_PROG.replace("T4 M6 G43", "T4 M6")
    moves, _ = build_sim_moves(prog, _sim_table(tmp_path))
    assert moves[0].graphic[0] is None and "G43" in moves[0].graphic[1]


@pytest.mark.skipif(__import__("shutil").which("rs274") is None, reason="rs274 not installed")
def test_sim_interpreter_error_is_shown(tmp_path):
    from gui.components.sim_viewer import build_sim_moves
    moves, note = build_sim_moves(_SIM_PROG.replace("G1 Z-0.3", "G2 Z-0.3"), _sim_table(tmp_path))
    assert "stops here" in note and moves


def test_nominal_size_is_marked_on_the_screen():
    c = _card(iso_code="")
    out, note = graphic_for(c, 4, _offset(c))
    assert out is not None and not out.size_known and "size not set" in note
