"""Finish DOC is derived and spring settings survive block save/load."""
import pytest
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest
from gui.program_tab import ProgramTab

_app = QApplication.instance() or QApplication([])


@pytest.fixture
def tab():
    widget = ProgramTab()
    yield widget
    widget.close()
    widget.deleteLater()


def test_doc_tracks_allowance_count_but_not_spring(tab):
    tab._rough_fin_allowance.set_value(.006)
    tab._finish_passes.set_value(3)
    tab._refresh_finish_doc()
    assert tab._finish_doc.isReadOnly()
    assert tab._finish_doc.value() == pytest.approx(.002)
    tab._finish_spring_pass.setChecked(True)
    assert tab._finish_doc.value() == pytest.approx(.002)
    tab._finish_doc.setFocus()
    QTest.keyClick(tab._finish_doc, Qt.Key_A, Qt.ControlModifier)
    QTest.keyClicks(tab._finish_doc, "0.5")
    assert tab._finish_doc.value() == pytest.approx(.002)


def test_saved_doc_is_rederived_and_spring_is_restored_per_block(tab):
    from models.program import ProgramBlock
    block = ProgramBlock(1, "id_profile", params_data=dict(
        stock=dict(z_end=-1),
        roughing=dict(fin_allowance=.006),
        finishing=dict(passes=3, doc_dia=.5, spring_pass=True),
        segments=[dict(x=3.117, z=0), dict(x=3.117, z=-.568)],
    ))
    tab._restore_block_data(block)
    assert tab._finish_doc.value() == pytest.approx(.002)
    assert tab.get_finishing_values()["spring_pass"] is True
    block.params_data["finishing"] = dict(passes=2, doc_dia=.25)
    tab._restore_block_data(block)
    assert tab._finish_doc.value() == pytest.approx(.003)
    assert tab.get_finishing_values()["spring_pass"] is False


def test_fractional_pass_count_is_not_silently_truncated(tab):
    tab._finish_passes.set_value(1.5)
    tab._refresh_finish_doc()
    assert not tab._finish_doc.is_valid()
    assert tab.get_finishing_values()["passes"] == 1.5
