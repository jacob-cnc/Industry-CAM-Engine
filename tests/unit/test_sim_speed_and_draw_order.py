"""Sim playback speeds (halved, labels unchanged) and toolpath draw order."""

import pytest
from PyQt5.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])

# Steps per 16 ms frame before the 2026-11-10 change.
OLD_STEPS = {"0.25x": 1, "0.5x": 2, "1x": 4, "2x": 8, "5x": 16, "10x": 32}


def _viewer_with_path(n=10000):
    from gui.components.sim_viewer import SimViewerWidget
    from outputs.graph_adapter import GraphData
    sv = SimViewerWidget()
    sv._graph.set_graph_data(GraphData())     # empty plot, toolpath lists exist
    sv._path = [(0.0, -i * 0.001, 0) for i in range(n)]
    sv._path_len = n
    sv._sim_step = 0
    sv._update_display = lambda: None         # graph not needed here
    sv._emit_line = lambda: None
    return sv


def test_labels_unchanged():
    from gui.components.sim_viewer import SimViewerWidget
    sv = SimViewerWidget()
    labels = [sv._speed_combo.itemText(i) for i in range(sv._speed_combo.count())]
    assert labels == ["0.25x", "0.5x", "1x", "2x", "5x", "10x"]
    assert sv._speed_combo.currentText() == "1x"
    assert list(SimViewerWidget.SPEED_STEPS) == labels


@pytest.mark.parametrize("label", list(OLD_STEPS))
def test_every_speed_is_half_the_old_rate(label):
    sv = _viewer_with_path()
    sv._on_speed(label)
    frames = 200
    for _ in range(frames):
        sv._sim_advance()
    assert sv._sim_step == pytest.approx(OLD_STEPS[label] * frames / 2, abs=1)


def test_new_1x_equals_old_half_x():
    from gui.components.sim_viewer import SimViewerWidget
    assert SimViewerWidget.SPEED_STEPS["1x"] == OLD_STEPS["0.5x"]


def test_default_speed_is_1x():
    from gui.components.sim_viewer import SimViewerWidget
    sv = _viewer_with_path()
    assert sv._steps_per_tick == SimViewerWidget.SPEED_STEPS["1x"]


def test_playing_changed_signal():
    sv = _viewer_with_path(10)
    seen = []
    sv.playing_changed.connect(seen.append)
    sv._toggle_play()
    sv._toggle_play()
    sv._toggle_play()
    sv._sim_stop()
    assert seen == [True, False, True, False]
    sv._sim_stop()                            # not playing: no extra signal
    assert seen == [True, False, True, False]


def test_cutting_moves_draw_above_rapids():
    """Rapid returns run along the previous pass's cut line. Feeds and arcs
    must always draw on top so the overlap reads consistently."""
    from gui.components.graph_widget import MachiningGraphWidget
    from outputs.graph_adapter import convert_from_moves
    from outputs.gcode_parser import parse as parse_gcode
    gcode = "\n".join([
        "G20 G18 G90", "G00 X1.0 Z0.1",
        "G01 X0.9 Z0.0 F0.01", "G01 Z-1.0",           # pass 1 at X0.9
        "G00 X1.0 Z-0.999", "G00 Z0.1",
        "G01 X0.8 Z0.0", "G01 Z-1.0",                 # pass 2 at X0.8
        "G00 X0.9 Z-0.999", "G00 Z0.1",               # return on pass 1's line
        "G02 X1.0 Z-1.1 I0.0 K-0.1",
    ])
    data = convert_from_moves(parse_gcode(gcode))
    g = MachiningGraphWidget()
    g.set_graph_data(data)
    rapid_z = {i.zValue() for i in g._rapid_items}
    cut_z = {i.zValue() for i in g._toolpath_items if i not in g._rapid_items}
    assert rapid_z and cut_z
    assert max(rapid_z) < min(cut_z)
