"""True-scale insert outline (tool-graphic plan 2026-11-13, phase T1).

The controlled point (LinuxCNC's imaginary tip, Q9 = nose centre) is at (0, 0);
the nose centre sits where LinuxCNC puts it; the cutting edges leave at the
tool table's I / J angles; the body has the ISO inscribed circle.
"""
import math

import pytest
import shapely
from shapely.geometry import Polygon

from geometry.tool_outline import tool_outline
from models.tool import InsertSpec, Q_TIP_DIRECTION
from tools.insert_geometry_lookup import parse_iso_code
from tools.tool_card_data import ToolCardData, insert_spec, iso_radius_mismatch
from tools.tool_table_io import deserialize_tool, serialize_tool

R = 1 / 64


def _dir(seg):
    """Unit direction of a straight edge, pointing AWAY from the nose."""
    (r0, z0), (r1, z1) = seg[0], seg[-1]
    return (r1 - r0, z1 - z0)


def _angle_rz(v):
    return math.degrees(math.atan2(v[0], v[1])) % 360.0


@pytest.mark.parametrize("q", range(1, 10))
def test_nose_centre_is_where_linuxcnc_puts_it(q):
    o = tool_outline(InsertSpec(q, R, 95.0, 175.0, "C", 0.5))
    dr, dz = Q_TIP_DIRECTION[q]
    assert o.nose_centre == pytest.approx((-dr * R, -dz * R), abs=1e-12)
    # every point of the nose arc is on the nose circle
    nose = o.cutting_edges[1]
    for p in nose:
        assert math.hypot(p[0] - o.nose_centre[0], p[1] - o.nose_centre[1]) == pytest.approx(R, abs=1e-9)


@pytest.mark.parametrize("q", [1, 2, 3, 4])
def test_95_deg_holder_stays_behind_both_touch_off_lines(q):
    """A CNMG in a 95 deg holder touches X and Z at the imaginary tip and lies
    entirely on the tool side of both lines (it is what a touch-off measures)."""
    o = tool_outline(InsertSpec(q, R, 95.0, 175.0, "C", 0.5))
    dr, dz = Q_TIP_DIRECTION[q]
    rs = [dr * p[0] for p in o.outline]
    zs = [dz * p[1] for p in o.outline]
    assert max(rs) == pytest.approx(0.0, abs=1e-9)     # touches the X line
    assert max(zs) == pytest.approx(0.0, abs=1e-9)     # touches the Z line


@pytest.mark.parametrize("q, feed, air", [
    (2, (0, -1), (1, 0)),    # RH OD: feeds toward the chuck, air above
    (1, (0, 1), (1, 0)),     # LH OD
    (3, (0, -1), (-1, 0)),   # boring bar
    (4, (0, 1), (-1, 0)),    # back boring
])
@pytest.mark.parametrize("front, back", [(95.0, 175.0), (62.5, 117.5), (72.5, 107.5), (60.0, 120.0)])
def test_edges_leave_at_the_tool_table_angles(q, feed, air, front, back):
    """Edge direction = feed rotated by I (front) / J (back) toward the air side,
    the convention of geometry/tool_reach.py."""
    o = tool_outline(InsertSpec(q, R, front, back, "custom", 0.5))
    got = sorted(_angle_rz(_dir(e)) for e in (o.cutting_edges[0], o.cutting_edges[2][::-1]))
    want = []
    for a in (front, back):
        c, s = math.cos(math.radians(a)), math.sin(math.radians(a))
        want.append(_angle_rz((c * feed[0] + s * air[0], c * feed[1] + s * air[1])))
    # the straight edges run from the nose outward in either stored order
    got_any = sorted([_angle_rz(_dir(o.cutting_edges[0])), _angle_rz(_dir(o.cutting_edges[0][::-1])),
                      _angle_rz(_dir(o.cutting_edges[2])), _angle_rz(_dir(o.cutting_edges[2][::-1]))])
    for w in want:
        assert any(abs((w - g + 180) % 360 - 180) < 1e-6 for g in got_any), (w, got_any, got)


@pytest.mark.parametrize("shape, included", [("C", 80.0), ("D", 55.0), ("V", 35.0), ("S", 90.0),
                                             ("T", 60.0), ("W", 80.0)])
def test_body_has_the_iso_inscribed_circle(shape, included):
    ic = 0.5
    front = 95.0 if included == 80.0 else 90.0 - included / 2.0
    o = tool_outline(InsertSpec(2, R, front, front + included, shape, ic))
    poly = Polygon(o.outline)
    assert poly.is_valid
    mic = shapely.maximum_inscribed_circle(poly, tolerance=1e-6)
    assert mic.length == pytest.approx(ic / 2.0, abs=2e-4)


def test_round_insert_q9_is_centred_on_the_controlled_point():
    o = tool_outline(InsertSpec(9, 0.1875, 0.0, 0.0, "R", 0.375))
    assert o.nose_centre == (0.0, 0.0)
    assert all(math.hypot(*p) == pytest.approx(0.1875, abs=1e-9) for p in o.outline)


def test_groove_blade_width_and_corner():
    o = tool_outline(InsertSpec(2, 0.008, 0.0, 0.0, "groove", 0.4, blade_width=0.118))
    zs = [p[1] for p in o.outline]
    rs = [p[0] for p in o.outline]
    assert (min(zs), max(zs)) == pytest.approx((0.0, 0.118), abs=1e-9)   # Q2: width toward +Z
    assert (min(rs), max(rs)) == pytest.approx((0.0, 0.4), abs=1e-9)     # away from the work


def test_unknown_size_is_drawn_nominal_and_says_so():
    o = tool_outline(InsertSpec(2, R, 95.0, 175.0, "C", 0.0))
    assert not o.size_known and any("unknown" in n for n in o.notes)


def test_unknown_angles_are_refused_not_guessed():
    with pytest.raises(ValueError, match="angles unknown"):
        tool_outline(InsertSpec(1, R, 0.0, 0.0, "custom", 0.5))


def test_translated_moves_the_controlled_point():
    o = tool_outline(InsertSpec(2, R, 95.0, 175.0, "C", 0.5)).translated(0.75, -1.25)
    assert o.nose_centre == pytest.approx((0.75 + R, -1.25 + R))


# --------------------------------------------------------------- ISO codes

@pytest.mark.parametrize("code, want", [
    ("CNMG432", ("C", 0.5, 2 / 64)), ("CNMG 431", ("C", 0.5, 1 / 64)),
    ("CNMG432MF", ("C", 0.5, 2 / 64)), ("CCMT32.51", ("C", 0.375, 1 / 64)),
    ("DCMT21.51", ("D", 0.25, 1 / 64)), ("TNMG332", ("T", 0.375, 2 / 64)),
    ("CNMG120408", ("C", 12.7 / 25.4, 0.8 / 25.4)), ("CNMG120408-PM", ("C", 12.7 / 25.4, 0.8 / 25.4)),
    ("DCMT11T304", ("D", 9.525 / 25.4, 0.4 / 25.4)), ("VNMG160404", ("V", 9.525 / 25.4, 0.4 / 25.4)),
    ("WNMG080408", ("W", 12.7 / 25.4, 0.8 / 25.4)),
    ("RCMT32", ("R", 0.375, 0.1875)), ("RCMT1204", ("R", 12 / 25.4, 6 / 25.4)),
])
def test_iso_codes(code, want):
    got = parse_iso_code(code)
    assert got[0] == want[0] and got[1:] == pytest.approx(want[1:])


@pytest.mark.parametrize("code", ["CNMG", "foo", "", "CNMG990408"])
def test_iso_codes_without_a_readable_size(code):
    assert parse_iso_code(code) is None


def _card(**kw):
    c = dict(tool_number=4, tool_type="Turning RH", insert_code="CNMG", orientation=2,
             description="", nose_radius=1 / 64, front_angle=95.0, back_angle=175.0,
             x_offset=0.0, z_offset=0.0, x_wear=0.0, z_wear=0.0)
    c.update(kw)
    return ToolCardData(**c)


def test_ic_field_wins_then_iso_then_unknown():
    assert insert_spec(_card(ic=0.375, iso_code="CNMG432")).ic == 0.375
    assert insert_spec(_card(iso_code="CNMG432")).ic == 0.5
    assert insert_spec(_card()).ic == 0.0
    assert insert_spec(_card(insert_code="Custom", iso_code="DNMG432")).shape == "D"


def test_iso_radius_mismatch_note():
    assert "nose radius" in iso_radius_mismatch(_card(iso_code="CNMG432"))
    assert iso_radius_mismatch(_card(iso_code="CNMG431")) == ""


def test_tool_table_round_trip_with_and_without_the_new_fields():
    c = _card(iso_code="CNMG431", ic=0.5)
    line = serialize_tool(c)
    assert "iso=CNMG431" in line and "ic=0.5000" in line
    back = deserialize_tool(line)
    assert (back.iso_code, back.ic) == ("CNMG431", 0.5)
    plain = serialize_tool(_card())
    assert "iso=" not in plain and "ic=" not in plain         # unchanged lines for old tools
