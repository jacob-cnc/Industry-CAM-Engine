"""Unit tests for drill support in the tool card data layer (spec: drilling-cycles).

Covers the drill tool types, the Q9/no-insert cascade, the ToolCardData <-> ToolDef
mapping for drills, and the drill InsertSpec.
"""

import pytest

from models.tool import ToolType, ToolOrientation, ToolDirection, InsertSpec
from tools.tool_card_data import (
    ToolCardData, TOOL_TYPES, DRILL_TYPES, TYPE_ORIENTATIONS, TYPE_INSERTS,
    tool_card_to_tool_def, tool_def_to_tool_card, insert_spec,
)


def make_drill_card(**kw):
    base = dict(
        tool_number=6, tool_type="Twist Drill", insert_code="N/A", orientation=9,
        description="0.25 twist drill", nose_radius=0.125, front_angle=0.0,
        back_angle=0.0, x_offset=0.0, z_offset=-1.0, x_wear=0.0, z_wear=0.0,
        point_angle=118.0, flute_length=2.5, max_peck=0.15, pitch=0.0,
    )
    base.update(kw)
    return ToolCardData(**base)


def test_drill_types_registered():
    for t in DRILL_TYPES:
        assert t in TOOL_TYPES
        assert TYPE_ORIENTATIONS[t] == [9]          # all drills are Q9 CENTER
        assert TYPE_INSERTS[t] == ["N/A"]           # no insert


def test_card_to_tool_def_drill():
    card = make_drill_card()
    td = tool_card_to_tool_def(card)
    assert td.tool_type == ToolType.DRILLING
    assert td.direction == ToolDirection.NEUTRAL
    assert td.orientation == ToolOrientation.CENTER
    assert td.tip_angle == pytest.approx(118.0)      # point angle, not back-front
    assert td.nose_radius == pytest.approx(0.125)    # drill radius (D/2)
    assert 2.0 * td.nose_radius == pytest.approx(0.25)   # planner reads dia = 2*nose_radius


def test_tool_def_to_card_drill():
    td = tool_card_to_tool_def(make_drill_card(point_angle=135.0))
    card = tool_def_to_tool_card(td)
    assert card.tool_type == "Twist Drill"
    assert card.orientation == 9
    assert card.point_angle == pytest.approx(135.0)
    assert card.nose_radius == pytest.approx(0.125)


def test_insert_spec_is_drill_shape():
    spec = insert_spec(make_drill_card())
    assert isinstance(spec, InsertSpec)
    assert spec.shape == "drill"
    assert spec.point_angle == pytest.approx(118.0)
    assert spec.ic == pytest.approx(0.25)            # drill diameter
    assert spec.nose_radius == pytest.approx(0.125)


def test_non_drill_has_no_point_angle():
    card = ToolCardData(
        tool_number=1, tool_type="Turning RH", insert_code="CNMG", orientation=2,
        description="roughing", nose_radius=0.016, front_angle=95.0, back_angle=175.0,
        x_offset=0.0, z_offset=0.0, x_wear=0.0, z_wear=0.0,
    )
    assert card.point_angle == 0.0
    td = tool_card_to_tool_def(card)
    assert td.tool_type == ToolType.TURNING
    assert td.tip_angle == pytest.approx(80.0)        # back - front, not a point angle


def test_drill_outline_is_drawable():
    # tool_outline imports build123d; skip where the kernel is not installed.
    pytest.importorskip("build123d")
    from geometry.tool_outline import tool_outline
    outline = tool_outline(insert_spec(make_drill_card()))
    rs = [p[0] for p in outline.outline]
    assert max(rs) == pytest.approx(0.125, abs=1e-6)   # body reaches the drill radius
    assert min(rs) == pytest.approx(-0.125, abs=1e-6)
    assert (0.0, 0.0) in outline.outline                # the tip is on center
