"""Tool-type orientation lists and saved-Q preservation (2026-11-08 review).

LinuxCNC 2.9.6 manual Fig 2.16, front-tool lathe: cutting corner relative to the
nose centre 1 -X+Z, 2 -X-Z, 3 +X-Z, 4 +X+Z, 5 +Z, 6 -X, 7 -Z, 8 +X, 9 centre.
"""
import dataclasses

import pytest
from PyQt5.QtWidgets import QApplication

from tools.tool_card_data import TYPE_ORIENTATIONS, ToolCardData

_app = QApplication.instance() or QApplication([])

EXPECTED = {
    "Turning RH": [2, 6],
    "Turning LH": [1, 6],
    "Boring Bar": [3, 4, 8],
    "Threading External": [6],
    "Threading Internal": [8],
    "Grooving/Parting": [2, 1, 6],
    "Knurling": [9],
}


@pytest.mark.parametrize("tool_type,expected", EXPECTED.items())
def test_type_orientations(tool_type, expected):
    assert TYPE_ORIENTATIONS[tool_type] == expected


def test_od_types_never_offer_inside_corners_or_plus_x():
    for t in ("Turning RH", "Turning LH", "Threading External", "Grooving/Parting"):
        assert not set(TYPE_ORIENTATIONS[t]) & {3, 4, 8}, t


def _card(**kw):
    base = dict(tool_number=4, tool_type="Turning RH", insert_code="CNMG", orientation=1,
                description="", x_offset=0.0, z_offset=0.0, x_wear=0.0, z_wear=0.0,
                nose_radius=0.016, front_angle=95.0, back_angle=175.0, blade_width=0.0)
    names = {f.name for f in dataclasses.fields(ToolCardData)}
    return ToolCardData(**{k: v for k, v in {**base, **kw}.items() if k in names})


@pytest.mark.parametrize("tool_type,insert,saved_q", [
    ("Turning RH", "CNMG", 1),               # lathe T4 today
    ("Threading External", "60° UN/Metric", 2),  # lathe T2 today
    ("Boring Bar", "CCMT", 8),               # still listed
])
def test_saved_orientation_is_never_silently_changed(tool_type, insert, saved_q):
    from gui.components.tool_geometry_row import ToolGeometryRow
    row = ToolGeometryRow(_card(tool_type=tool_type, insert_code=insert, orientation=saved_q))
    row.set_data(_card(tool_type=tool_type, insert_code=insert, orientation=saved_q))
    assert row.get_data().orientation == saved_q
    text = row._orient_combo.currentText()
    if saved_q in TYPE_ORIENTATIONS[tool_type]:
        assert text == f"Q{saved_q}"
    else:
        assert text == f"Q{saved_q} (non-standard)"
