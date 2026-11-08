"""Saved conversation restores the selected job, independent of cached G-code."""
import copy
import json
import pytest
from PyQt5.QtWidgets import QApplication
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


def program():
    return dict(version=2, stock_back_face_z=-1, blocks=[
        dict(block_id=1, block_type="od_profile", enabled=False, visible=False, params={}),
        dict(block_id=2, block_type="id_profile", tool_number=3, params=dict(
            stock=dict(diameter=4, pilot_hole_dia=2.995, x_start=2.98, z_start=.05,
                       x_park=3.5, z_park=2),
            roughing=dict(strategy="offset_contour", peck_enabled=True, peck_length=.125,
                          doc_dia=.02, feed=.004, fin_allowance=.006, spindle_rpm=500, tool_number=3),
            finishing=dict(passes=3, feed=.002, spindle_rpm=600, tool_number=4, spring_pass=True),
            segments=[dict(type="line", x=3.117, z=0),
                      dict(type="line", x=3.117, z=-.568),
                      dict(type="line", x=2.995, z=-.568)]))])


def test_program_open_restores_job_and_clears_unrelated_output(tab, tmp_path, monkeypatch):
    from gui import program_tab
    path = tmp_path / "GCH Boring Test Ring Bore.json"
    data = program()
    path.write_text(json.dumps(data))
    monkeypatch.setattr(program_tab.QFileDialog, "getOpenFileName", lambda *a, **k: (str(path), ""))
    warnings = []
    monkeypatch.setattr(program_tab.QMessageBox, "warning", lambda *a: warnings.append(a))
    tab._last_gcode_text = "OLD PROGRAM"
    tab._on_file_open()
    assert not warnings
    assert tab._active_block_id == 2
    assert tab._stock_diameter.value() == 4
    assert tab._stock_pilot_hole.value() == 2.995
    assert tab._stock_z_end.value() == pytest.approx(-.568)
    assert tab._rough_strategy.currentText() == "Offset Contour"
    assert tab._rough_peck_check.isChecked()
    assert tab._rough_peck_length.value() == .125
    assert tab._rough_rpm.value() == 500
    assert tab._finish_rpm.value() == 600
    assert tab._finish_passes.value() == 3
    assert tab._finish_spring_pass.isChecked()
    assert tab._finish_doc.value() == pytest.approx(.002)
    assert tab._finish_tool_num.value() == 4
    assert [(s["x"], s["z"]) for s in tab._segment_list.get_segments()] == [(3.117, 0), (3.117, -.568), (2.995, -.568)]
    assert tab._last_gcode_text == ""
    assert tab._sim_viewer._gcode_panel.toPlainText() == ""
    tab._write_program_file(str(path))
    assert not path.with_suffix(".ngc").exists()
    saved = json.loads(path.read_text())
    assert saved["active_block_id"] == 2
    tab._load_program_data(saved)
    assert tab._active_block_id == 2
    assert tab._finish_rpm.value() == 600


def test_explicit_active_block_and_input_models_survive_id_collision(tab):
    data = program()
    data["active_block_id"] = 1
    original = copy.deepcopy(data)
    tab._stock_diameter.set_value(9)
    tab._load_program_data(data)
    assert tab._active_block_id == 1
    assert data == original
    assert tab._block_list.get_blocks()[1].params_data == original["blocks"][1]["params"]


def test_invalid_schema_does_not_replace_existing_program(tab):
    tab._load_program_data(program())
    with pytest.raises(ValueError, match="block list"):
        tab._load_program_data(dict(version=2, blocks={}))
    assert tab._active_block_id == 2
    assert tab._stock_diameter.value() == 4


def test_empty_and_optional_fields_do_not_inherit_previous_job(tab):
    tab._load_program_data(program())
    tab._load_program_data(dict(version=2, blocks=[dict(block_id=2, block_type="id_profile",
        params=dict(segments=[dict(type="line", x=2, z=0), dict(type="line", x=2, z=-.2)]))]))
    assert tab._stock_diameter.value() == tab._stock_diameter._config.default_value
    assert tab._finish_rpm.value() == tab._finish_rpm._config.default_value
    assert not tab._rough_peck_check.isChecked()
    assert tab._rough_strategy.currentText() == "Staircase"
    tab._load_program_data(dict(version=2, blocks=[]))
    assert tab._block_list.get_blocks() == []
    assert tab._segment_list.get_segments() == []
    assert tab._active_block_id == -1
