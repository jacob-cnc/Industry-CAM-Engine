"""Applied tool offsets survive LinuxCNC rewrites and guarded live saves."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PyQt5.QtWidgets import QApplication

from gui import tools_tab
from gui.components.tool_geometry_row import ToolGeometryRow
from pipeline.tool_card_data import ToolCardData, tool_card_to_tool_def
from pipeline.tool_table_io import (
    LegacyToolTableError, create_backup, deserialize_tool, load_tool_table, save_tool_table, serialize_tool,
)

_app = QApplication.instance() or QApplication([])


def tool():
    return ToolCardData(2, "Boring Bar", "DCMT", 5, "boring", .016, 62.5, 117.5,
                        .5, -.25, .001, -.002)


def test_radius_file_and_diameter_gui_round_trip():
    original = tool()
    line = serialize_tool(original)
    assert "X+0.501000" in line
    assert "Z-0.252000" in line
    row = ToolGeometryRow(deserialize_tool(line))
    assert row._x_offset_field.value() == pytest.approx(1.0)
    assert row._wear_x_field.value() == pytest.approx(.002)
    assert row.get_data().x_offset == pytest.approx(.5)
    assert row.get_data().x_wear == pytest.approx(.001)
    row.deleteLater()


def test_linuxcnc_reordered_zero_omitting_rewrite_preserves_split():
    metadata = serialize_tool(tool()).split(";", 1)[1]
    # v2.9.6 tooldata_format_toolline uses T P D X Y Z ... I J Q order.
    rewritten = "T2 P2 D0.032 X0.501 Z-0.252 I62.5 J117.5 Q5 ;" + metadata
    loaded = deserialize_tool(rewritten)
    assert loaded == tool()
    zero = deserialize_tool("T2 P2 Q5 ;ice=2|xwear=0|zwear=0")
    assert zero.x_offset == zero.z_offset == 0
    # The controller's rewritten totals win if changed with G10, while wear remains.
    changed = deserialize_tool(rewritten.replace("X0.501", "X0.601"))
    assert changed.x_offset == pytest.approx(.6)
    assert changed.x_wear == .001


def test_entry_fits_linuxcnc_full_line_and_rewrite_buffer(tmp_path):
    path = tmp_path / "tool.tbl"
    save_tool_table([tool()], str(path))
    before = path.read_bytes()
    oversized = tool()
    oversized.description = "x" * 95
    with pytest.raises(ValueError, match="256-byte"):
        save_tool_table([oversized], str(path))
    assert path.read_bytes() == before


def test_legacy_application_nonzero_x_is_not_guessed_or_silently_skipped(tmp_path):
    path = tmp_path / "old.tbl"
    path.write_text("T2 P2 X1 Z0 Q5 ;type=boring_bar|insert=DCMT\n")
    with pytest.raises(LegacyToolTableError, match="ambiguous"):
        load_tool_table(str(path))
    assert deserialize_tool("T2 P2 X1 Q5 ;native table", unversioned_x_units="radius").x_offset == 1
    assert deserialize_tool("T2 P2 X0 Q5 ;type=boring_bar").x_offset == 0


def test_explicit_legacy_migration_preserves_original_and_versions_new_file(tmp_path):
    original = tmp_path / "legacy.tbl"
    original.write_text("T2 P2 X1 Z-0.25 Q5 ;old API description\n")
    with pytest.raises(LegacyToolTableError):
        load_tool_table(str(original))
    backup = create_backup(str(original))
    cards = load_tool_table(str(original), unversioned_x_units="diameter")
    save_tool_table(cards, str(original))
    assert load_tool_table(str(original))[0].x_offset == .5
    assert "X1" in open(backup).read()
    second_backup = create_backup(str(original))
    assert second_backup != backup
    assert "X1" in open(backup).read()


@pytest.fixture
def tab(monkeypatch):
    monkeypatch.setattr(tools_tab, "HAS_LINUXCNC", False)
    monkeypatch.setattr(tools_tab.Tools_Tab, "_load_settings_and_auto_load", lambda self: None)
    monkeypatch.setattr(tools_tab.QMessageBox, "warning", Mock())
    widget = tools_tab.Tools_Tab()
    yield widget
    widget.close()
    widget.deleteLater()


@pytest.fixture
def live(tab, tmp_path, monkeypatch):
    ini_path = tmp_path / "machine.ini"
    ini_path.write_text("[EMCIO]\nTOOL_TABLE = offsets.tbl\n")
    path = tmp_path / "offsets.tbl"
    save_tool_table([tool()], str(path))
    stat = SimpleNamespace(interp_state=1, task_mode=1, paused=False, gcodes=(),
                           tool_in_spindle=2, tool_table=[], poll=Mock(), tool_offset=(.501, 0, -.252))
    command = Mock()
    command.wait_complete.return_value = 1
    def reload_table():
        stat.tool_table = [SimpleNamespace(
            id=t.tool_number, xoffset=t.x_offset + t.x_wear, zoffset=t.z_offset + t.z_wear,
            diameter=t.nose_radius * 2, frontangle=t.front_angle,
            backangle=t.back_angle, orientation=t.orientation,
        ) for t in load_tool_table(str(path))]
    command.load_tool_table.side_effect = reload_table
    command.mode.side_effect = lambda mode: setattr(stat, "task_mode", mode)
    command.mdi.side_effect = lambda text: setattr(stat, "tool_offset", (
        stat.tool_table[0].xoffset, 0, stat.tool_table[0].zoffset))
    api = SimpleNamespace(INTERP_IDLE=1, MODE_MANUAL=1, MODE_MDI=3, RCS_DONE=1, RCS_ERROR=3,
                          ini=lambda name: SimpleNamespace(find=lambda sec, key: "offsets.tbl"))
    monkeypatch.setattr(tools_tab, "linuxcnc", api, raising=False)
    monkeypatch.setenv("INI_FILE_NAME", str(ini_path))
    tab._linuxcnc_stat, tab._linuxcnc_command = stat, command
    tab._accept_table(str(path), [tool()])
    reload_table()
    return tab, path, stat, command


def edit_wear(tab):
    updated = deepcopy(tool())
    updated.x_wear = .002
    tab.set_cards([updated])


def test_live_save_reloads_verifies_and_reapplies_active_g43(live):
    tab, path, stat, command = live
    stat.gcodes = (430,)
    edit_wear(tab)
    assert tab._autosave()
    assert "X+0.502000" in path.read_text()
    command.load_tool_table.assert_called_once()
    command.mdi.assert_called_once_with("G43 H2")
    assert stat.task_mode == 1
    assert stat.tool_offset[0] == pytest.approx(.502)


@pytest.mark.parametrize("state", ["running", "auto", "paused"])
def test_live_busy_blocks_disk_and_controller_changes(live, state):
    tab, path, stat, command = live
    before = path.read_bytes()
    if state == "running": stat.interp_state = 2
    if state == "auto": stat.task_mode = 2
    if state == "paused": stat.paused = True
    edit_wear(tab)
    assert not tab._autosave()
    assert path.read_bytes() == before
    command.load_tool_table.assert_not_called()
    assert tab.get_tool(2).x_wear == .001


def test_failed_live_reload_restores_file_and_blocks_unverified_edits(live):
    tab, path, stat, command = live
    before = path.read_bytes()
    command.load_tool_table.side_effect = RuntimeError("controller unavailable")
    edit_wear(tab)
    assert not tab._autosave()
    assert path.read_bytes() == before
    assert tab._table_sync_failed
    assert tab.get_tool(2).x_wear == .001


def test_external_g10_rewrite_is_not_overwritten(live):
    tab, path, stat, command = live
    path.write_text(path.read_text().replace("X+0.501000", "X+0.601000"))
    before = path.read_bytes()
    edit_wear(tab)
    assert not tab._autosave()
    assert path.read_bytes() == before
    command.load_tool_table.assert_not_called()


def test_subsequent_geometry_autosave_does_not_drop_applied_wear(live):
    tab, path, stat, command = live
    edit_wear(tab)
    assert tab._autosave()
    tab._cards[0]._desc_edit.setText("new description")
    tab._cards[0]._desc_edit.editingFinished.emit()
    recovered = load_tool_table(str(path))[0]
    assert recovered.description == "new description"
    assert recovered.x_wear == .002
    assert recovered.x_offset == .5
    assert stat.tool_table[0].xoffset == pytest.approx(.502)


def test_active_g43_for_different_offset_cannot_be_silently_replaced(live):
    tab, path, stat, command = live
    before = path.read_bytes()
    stat.gcodes = (430,)
    stat.tool_offset = (.9, 0, -.252)
    edit_wear(tab)
    assert not tab._autosave()
    assert path.read_bytes() == before
    command.load_tool_table.assert_not_called()


def test_live_path_comes_from_ini_not_settings(live):
    tab, path, stat, command = live
    assert tab._live_table_path() == str(path)


def test_stale_windows_settings_falls_back_to_local_table(tab, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "tool.tbl"
    save_tool_table([tool()], str(path))
    monkeypatch.setattr(tab, "_load_settings", lambda: "C:/old/Windows/tool.tbl")
    # Call the real implementation despite the fixture's startup suppression.
    _AUTOLOAD(tab)
    assert tab._active_file_path == str(path)


_AUTOLOAD = tools_tab.Tools_Tab._load_settings_and_auto_load


def test_wear_edit_on_spindle_tool_applies_g43_even_when_inactive(live):
    # Owner 2026-11-09: T1 already in the spindle, wear edited, offset only
    # took effect after a redundant tool change (G43 was not active).
    tab, path, stat, command = live
    stat.gcodes = ()                       # G49 in effect, tool 2 in spindle
    edit_wear(tab)
    assert tab._autosave(edited_tool=2)
    command.mdi.assert_called_once_with("G43 H2")
    assert stat.tool_offset[0] == pytest.approx(.502)
    assert stat.task_mode == 1


def test_edit_of_other_tool_does_not_turn_on_g43(live):
    tab, path, stat, command = live
    stat.gcodes = ()
    edit_wear(tab)
    assert tab._autosave(edited_tool=7)    # not the spindle tool
    command.mdi.assert_not_called()
