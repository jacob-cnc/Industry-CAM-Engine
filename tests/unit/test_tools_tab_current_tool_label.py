"""The Tools tab's spindle-tool label (owner, 2026-11-16).

The label is constructed as "Offline" and refresh_current_tool_display() had
no caller anywhere in the repo, so it read "Offline" for a whole session even
with a live controller. These tests pin the wiring, not the formatting.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PyQt5.QtGui import QShowEvent  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

_app = QApplication.instance() or QApplication([])

import gui.tools_tab as tools_tab_module  # noqa: E402
from gui.tools_tab import ToolsTab  # noqa: E402
from tools.tool_card_data import ToolCardData  # noqa: E402


class _FakeStat:
    """Just the two members refresh_current_tool_display touches."""

    def __init__(self, tool_in_spindle=0, raises=False):
        self.tool_in_spindle = tool_in_spindle
        self._raises = raises
        self.polls = 0

    def poll(self):
        self.polls += 1
        if self._raises:
            raise RuntimeError("stat channel is gone")


def _card(number, desc):
    return ToolCardData(tool_number=number, tool_type="Boring Bar", insert_code="CCMT",
                        orientation=3, description=desc, nose_radius=0.0,
                        front_angle=95.0, back_angle=175.0, x_offset=0.0, z_offset=0.0,
                        x_wear=0.0, z_wear=0.0)


@pytest.fixture
def tab(monkeypatch):
    """A Tools tab built in offline mode, so no test ever touches a live controller."""
    monkeypatch.setattr(tools_tab_module, "HAS_LINUXCNC", False)
    t = ToolsTab()
    t.set_cards([_card(1, "CCMT boring bar"), _card(3, "Solid carbide .1875 min bore")])
    return t


def _label(t):
    return t._button_bar._current_tool_label.text()


def test_offline_tab_says_offline(tab):
    """No stat channel: the label is the honest 'Offline'."""
    tab.showEvent(QShowEvent())
    assert _label(tab) == "Offline"


def test_showing_the_tab_reads_the_spindle_tool(tab):
    """The regression: showing the tab must refresh the label, not leave
    the constructor's 'Offline' text in place."""
    tab._linuxcnc_stat = _FakeStat(tool_in_spindle=3)
    tab.showEvent(QShowEvent())
    assert _label(tab) == "T3 - Solid carbide .1875 min bore"
    assert tab._linuxcnc_stat.polls == 1


def test_an_empty_spindle_is_not_reported_as_a_tool(tab):
    tab._linuxcnc_stat = _FakeStat(tool_in_spindle=0)
    tab.showEvent(QShowEvent())
    assert _label(tab) == "T0 - No tool"


def test_a_dead_stat_channel_falls_back_to_offline(tab):
    """A real connection failure is the one case that should read 'Offline'."""
    tab._linuxcnc_stat = _FakeStat(tool_in_spindle=3, raises=True)
    tab.showEvent(QShowEvent())
    assert _label(tab) == "Offline"


def test_a_tool_not_in_the_table_shows_the_number_with_no_description(tab):
    tab._linuxcnc_stat = _FakeStat(tool_in_spindle=7)
    tab.showEvent(QShowEvent())
    assert _label(tab) == "T7 - "


def test_reloading_the_table_refreshes_the_description(tab, tmp_path):
    """_accept_table replaces the cards the label's description comes from."""
    tab._linuxcnc_stat = _FakeStat(tool_in_spindle=3)
    tab.showEvent(QShowEvent())
    assert _label(tab) == "T3 - Solid carbide .1875 min bore"
    table = tmp_path / "tool.tbl"
    table.write_text("")
    tab._accept_table(str(table), [_card(3, "renamed in the file")])
    assert _label(tab) == "T3 - renamed in the file"
