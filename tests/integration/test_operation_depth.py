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
