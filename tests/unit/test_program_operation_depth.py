"""Read-only operation depth survives editing, block switches, and saved files."""
import json
import pytest
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest
from gui.program_tab import ProgramTab
from gui.unit_state import unit_state, UnitMode

_app = QApplication.instance() or QApplication([])


@pytest.fixture
def tab():
    unit_state._mode = UnitMode.INCH
    widget = ProgramTab()
    yield widget
    widget.close()
    widget.deleteLater()


def segments(depth):
    return [dict(type="line", x=3.117, z=0), dict(type="line", x=3.117, z=depth)]


def test_depth_is_read_only_and_updates_when_contour_shrinks_or_clears(tab):
    tab._segment_list.set_segments(segments(-0.568))
    assert tab._stock_z_end.isReadOnly()
    assert tab._stock_z_end.value() == pytest.approx(-0.568)
    tab._stock_z_end.setFocus()
    QTest.keyClick(tab._stock_z_end, Qt.Key_A, Qt.ControlModifier)
    QTest.keyClicks(tab._stock_z_end, "-9")
    assert tab._stock_z_end.value() == pytest.approx(-0.568)
    tab._segment_list.set_segments(segments(-0.25))
    assert tab._stock_z_end.value() == pytest.approx(-0.25)
    tab._segment_list.clear()
    assert tab._stock_z_end.value() == 0
    assert not tab._stock_z_end.is_valid()


def test_loading_blocks_rederives_depth_and_preserves_shared_stock(tab, tmp_path):
    data = dict(version=2, stock_back_face_z=-1.0, blocks=[
        dict(block_id=1, block_type="id_profile", tool_number=1, enabled=True,
             params=dict(stock=dict(z_end=-99), segments=segments(-0.568))),
        dict(block_id=2, block_type="id_profile", tool_number=1, enabled=True,
             params=dict(stock=dict(z_end=-99), segments=segments(-0.25))),
    ])
    tab._load_program_data(data)
    blocks = tab._block_list.get_blocks()
    for block, depth in zip(blocks, [-0.568, -0.25]):
        tab._restore_block_data(block)
        assert tab._stock_z_end.value() == pytest.approx(depth)
        assert tab._stock_back_z.value() == -1
    path = tmp_path / "bore.json"
    tab._write_program_file(str(path))
    assert json.loads(path.read_text())["stock_back_face_z"] == -1


def test_legacy_file_keeps_stock_depth_and_recalculates_operation(tab):
    tab._load_program_data(dict(
        version=1, block_type="ID Profile", stock=dict(z_end=-1),
        segments=segments(-0.568),
    ))
    assert tab._stock_back_z.value() == -1
    assert tab._stock_z_end.value() == pytest.approx(-0.568)
