"""Cutter-comp side and boring-bar orientation (bench + sim, 2026-11-08).

Headless LinuxCNC 2.9.6 sim, 0.032 nose dia, straight Z pass:
  ID G41 -> control point exactly on X3.070; ID G42 -> X3.1340 (+2 x TNR dia),
  matching the lathe (X3.1339 at N200 X3.07). OD G42 exact, OD G41 -0.064.
"""
import pytest

from models.tool import ToolDirection
from outputs.gcode_writer import GCodeWriter
from tools.tool_card_data import TYPE_ORIENTATIONS


@pytest.mark.parametrize("direction,is_id,expected", [
    (ToolDirection.RIGHT, False, "G42"),   # OD RH toward chuck (sim-verified)
    (ToolDirection.RIGHT, True, "G41"),    # ID RH boring toward chuck (sim-verified)
    (ToolDirection.LEFT, False, "G41"),    # reversed travel
    (ToolDirection.LEFT, True, "G42"),
    (ToolDirection.NEUTRAL, False, "G40"),
    (ToolDirection.NEUTRAL, True, "G40"),
])
def test_comp_code(direction, is_id, expected):
    assert GCodeWriter._get_comp_code(direction, is_id) == expected


def test_boring_bar_orientations_start_with_conventional_q3():
    # LinuxCNC Fig 2.16 front-tool lathe: Q3 = corner +X/-Z (boring toward chuck)
    assert TYPE_ORIENTATIONS["Boring Bar"][0] == 3
    assert set(TYPE_ORIENTATIONS["Boring Bar"]) == {3, 4, 8}
