"""Operation depth is contour geometry, independent of physical stock length."""
import pytest
from shapely.geometry import Point

from geometry.zone_builder import build_zones, contour_z_end
from geometry.zone_query import ZoneQueryAPI
from models.tool import ToolDef, ToolDirection, ToolOrientation, ToolType
from pipeline.model_builder import build_from_fields, profile_from_fields
from pipeline.pipeline import execute
from validation.polygon_builder import ValidationPolygons


def bore_fields(**changes):
    fields = dict(
        segments=[dict(type="line", x=3.117, z=0), dict(type="line", x=3.117, z=-0.568)],
        stock_dia=4, x_start=3.117, z_start=0.05, z_end=-99,
        stock_back_z=-1, mode="id", pilot_hole_dia=2.995,
        doc_dia=0.02, feed=0.003, strategy="staircase", fin_allowance=0.002,
        peck_enabled=False, peck_length=None, spindle_rpm=300,
        finish_passes=1, finish_doc_dia=0.002, finish_feed=0.002,
        tool_def=ToolDef(1, 0.008, 55, 0.25, ToolOrientation.ID_FRONT_RIGHT,
                         ToolDirection.RIGHT, ToolType.BORING),
    )
    fields.update(changes)
    return fields


@pytest.mark.parametrize("mode", ["id", "od"])
@pytest.mark.parametrize("strategy", ["staircase", "offset_contour"])
def test_bore_depth_is_derived_and_stock_behind_it_remains_protected(mode, strategy):
    fields = bore_fields(mode=mode, strategy=strategy)
    profile, stock, roughing, finishing = build_from_fields(**fields)
    assert profile.z_end == pytest.approx(-0.568)
    assert stock.z_end == pytest.approx(-0.568)
    assert stock.physical_z_end == -1
    zones = build_zones(profile, stock, fields["tool_def"], roughing)
    polygons = ValidationPolygons.from_zone_query(ZoneQueryAPI(zones))
    assert polygons.finished_part_poly.contains(Point(3.05 / 2, -0.8))
    if mode == "id":
        assert not polygons.finished_part_poly.contains(Point(2.9 / 2, -0.8))
    result = execute(profile, stock, fields["tool_def"], roughing, finishing)
    assert result.plan_result is not None, result.validations
    assert all(m.z >= -0.568 - 0.0005 for m in result.plan_result.tool_moves)


def test_stock_back_face_cannot_be_in_front_of_cutting_depth():
    with pytest.raises(ValueError, match="Stock back face"):
        build_from_fields(**bore_fields(stock_back_z=-0.4))


def test_stock_back_face_must_be_finite():
    with pytest.raises(ValueError, match="finite"):
        build_from_fields(**bore_fields(stock_back_z=float("nan")))


def test_kernel_depth_includes_arc_extremum_between_endpoints():
    # A semicircle below Z0: endpoints are both at Z0, bottom is Z-0.5.
    profile = profile_from_fields([
        dict(type="line", x=2, z=0),
        dict(type="arc", x=4, z=0, radius=-0.5),
    ], "id")
    assert contour_z_end(profile) == pytest.approx(-0.5)


# --- 2026-11-12 hand-math inquiry: a contour ending exactly at the stock back face ---------
# "Test Program Tab" (reference program, T4) failed in the GUI with "Cannot build face(s):
# wires not planar": its last segment is an R.5 arc ending at Z-1.5 = the stock back face.
# contour_z_end took the kernel's bounding-box minimum, -1.4999999999999865 (1.35e-14 of noise),
# so build_zones saw stock "behind" the part and built a retained-stock rectangle 1.35e-14
# tall, which OCCT cannot make a face from.

_STEPPED_WITH_END_ARC = [dict(type="line", x=0.0, z=0.0), dict(type="line", x=0.5, z=0.0),
                         dict(type="line", x=0.5, z=-0.5), dict(type="line", x=1.0, z=-0.5),
                         dict(type="line", x=1.0, z=-1.0),
                         dict(type="arc", x=1.5, z=-1.5, radius=-0.5)]


def test_contour_end_on_a_vertex_is_exact_not_bounding_box_noise():
    profile = profile_from_fields(_STEPPED_WITH_END_ARC, "od", [])
    assert contour_z_end(profile) == -1.5          # exact: the arc's end point is the lowest Z


@pytest.mark.parametrize("strategy", ["staircase", "offset_contour"])
def test_profile_ending_exactly_at_the_back_face_generates(strategy):
    fields = bore_fields(mode="od", strategy=strategy, segments=_STEPPED_WITH_END_ARC,
                         stock_dia=2.0, x_start=0.0, z_start=0.1, z_end=-1.5, stock_back_z=-1.5,
                         pilot_hole_dia=0.0, fin_allowance=0.005, doc_dia=0.05, feed=0.008,
                         tool_def=ToolDef(4, 0.016, 80, 0.5, ToolOrientation(2),
                                          ToolDirection.RIGHT, ToolType.TURNING))
    profile, stock, roughing, finishing = build_from_fields(**fields)
    result = execute(profile, stock, fields["tool_def"], roughing, finishing)
    assert result.plan_result is not None, [v.message for v in result.validations][:3]


def test_an_arc_dipping_below_its_end_points_still_sets_the_depth():
    # An arc between two points at the SAME Z (-0.4) bulges toward -Z for one of the two
    # radius signs: then its interior, not a vertex, is the contour's lowest point and the
    # kernel's extremum must stand (the vertex snap applies only within 1e-9).
    depths = []
    for r in (0.2, -0.2):
        segs = [dict(type="line", x=0.0, z=0.0), dict(type="line", x=1.0, z=0.0),
                dict(type="line", x=1.0, z=-0.4), dict(type="arc", x=1.6, z=-0.4, radius=r)]
        depths.append(contour_z_end(profile_from_fields(segs, "od", [])))
    assert min(depths) < -0.4 - 0.05            # the dip (about -0.53) is reported
    assert max(depths) == pytest.approx(-0.4)   # the other bulge stays at the vertex depth
