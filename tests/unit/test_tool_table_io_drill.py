"""Unit + property tests for drill .tbl round-trip (spec: drilling-cycles).

A drill's drill diameter rides in the LinuxCNC D column (D = nose_radius*2);
point angle / flute / max peck / tap pitch ride in the comment metadata.

Feature: drilling-cycles
"""

import pytest
from hypothesis import given, settings, strategies as st

from tools.tool_card_data import ToolCardData
from tools.tool_table_io import serialize_tool, deserialize_tool


def make_drill_card(**kw):
    base = dict(
        tool_number=6, tool_type="Twist Drill", insert_code="N/A", orientation=9,
        description="0.25 twist drill", nose_radius=0.125, front_angle=0.0,
        back_angle=0.0, x_offset=0.0, z_offset=-1.0, x_wear=0.0, z_wear=0.0,
        point_angle=118.0, flute_length=2.5, max_peck=0.15, pitch=0.0,
    )
    base.update(kw)
    return ToolCardData(**base)


def test_drill_diameter_in_d_column():
    line = serialize_tool(make_drill_card(nose_radius=0.125))
    assert "D0.250000" in line        # D = drill diameter = 2 * nose_radius
    assert "Q9" in line


def test_drill_metadata_round_trip():
    card = make_drill_card()
    back = deserialize_tool(serialize_tool(card))
    assert back.tool_number == 6
    assert back.tool_type == "Twist Drill"
    assert back.orientation == 9
    assert back.nose_radius == pytest.approx(0.125, abs=1e-6)
    assert back.point_angle == pytest.approx(118.0, abs=0.1)
    assert back.flute_length == pytest.approx(2.5, abs=1e-4)
    assert back.max_peck == pytest.approx(0.15, abs=1e-4)
    assert back.description == "0.25 twist drill"


def test_tap_pitch_round_trip():
    card = make_drill_card(tool_type="Tap", description="1/4-20 tap", pitch=0.05)
    back = deserialize_tool(serialize_tool(card))
    assert back.tool_type == "Tap"
    assert back.pitch == pytest.approx(0.05, abs=1e-5)


def test_non_drill_has_no_drill_metadata():
    card = ToolCardData(
        tool_number=1, tool_type="Turning RH", insert_code="CNMG", orientation=2,
        description="roughing", nose_radius=0.016, front_angle=95.0, back_angle=175.0,
        x_offset=0.0, z_offset=0.0, x_wear=0.0, z_wear=0.0,
    )
    line = serialize_tool(card)
    for key in ("pointangle=", "flute=", "maxpeck=", "pitch="):
        assert key not in line


# Feature: drilling-cycles, Property 4: drill .tbl serialize/deserialize is an
# identity within precision.
@settings(max_examples=150, deadline=None)
@given(
    tool_number=st.integers(1, 99),
    nose_radius=st.floats(0.015, 0.75, allow_nan=False, allow_infinity=False),
    point_angle=st.floats(60.0, 180.0, allow_nan=False, allow_infinity=False),
    flute=st.floats(0.0, 6.0, allow_nan=False, allow_infinity=False),
    peck=st.floats(0.0, 1.0, allow_nan=False, allow_infinity=False),
    z_off=st.floats(-6.0, 0.0, allow_nan=False, allow_infinity=False),
)
def test_property_drill_round_trip(tool_number, nose_radius, point_angle, flute, peck, z_off):
    card = make_drill_card(
        tool_number=tool_number, nose_radius=nose_radius, point_angle=point_angle,
        flute_length=flute, max_peck=peck, z_offset=z_off, description="drill",
    )
    back = deserialize_tool(serialize_tool(card))
    assert back.tool_number == tool_number
    assert back.nose_radius == pytest.approx(nose_radius, abs=1e-6)
    assert back.point_angle == pytest.approx(point_angle, abs=0.1)
    assert back.flute_length == pytest.approx(flute, abs=1e-4)
    assert back.max_peck == pytest.approx(peck, abs=1e-4)
    assert back.orientation == 9
    assert back.tool_type == "Twist Drill"
