"""Zone boundary polylines lie ON the kernel's outline (hand-math inquiry F5, 2026-11-12).

pipeline._extract_zone_boundary densified arcs from DIAMETER-space start/end/centre
with the RADIUS-space radius: an arc of R.25 came out up to .118 off the true arc
(squashed in X), and the G-code writer's comp lead-out uses finished_part_boundary
to decide whether material lies beyond a contour end. The polyline now samples
each arc on the kernel's own arc (radius space, the edge's signed sweep).
"""
import math

import pytest

from models.tool import ToolDef, ToolDirection, ToolOrientation, ToolType
from pipeline.model_builder import build_from_fields

CNMG = ToolDef(4, 0.016, 80, 0.5, ToolOrientation(2), ToolDirection.RIGHT, ToolType.TURNING,
               front_angle=95.0, back_angle=175.0)
PROFILES = {
    "quadrants": [dict(type="line", x=0.0, z=0.0), dict(type="line", x=0.5, z=0.0),
                  dict(type="arc", x=1.0, z=-0.25, radius="Q"), dict(type="line", x=1.0, z=-0.75),
                  dict(type="arc", x=1.5, z=-1.0, radius="-Q"), dict(type="line", x=1.5, z=-1.25)],
    "radius_arcs": [dict(type="line", x=0.0, z=0.0), dict(type="line", x=0.5, z=0.0),
                    dict(type="line", x=0.5, z=-0.5), dict(type="line", x=1.0, z=-0.5),
                    dict(type="arc", x=1.25, z=-1.0, radius=-1.0)],
}


def _zones(segments, z_end):
    from geometry.zone_builder import build_zones
    from geometry.zone_query import ZoneQueryAPI
    p, s, r, f = build_from_fields(
        segments=segments, stock_dia=2.0, x_start=0.0, z_start=0.1, z_end=z_end, stock_back_z=None,
        mode="od", pilot_hole_dia=0.0, doc_dia=0.05, feed=0.008, strategy="staircase",
        fin_allowance=0.01, peck_enabled=False, peck_length=None, spindle_rpm=1000, finish_passes=1,
        finish_doc_dia=0.002, finish_feed=0.003, finish_spring_pass=False, tool_def=CNMG,
        x_park=3, z_park=1, corner_breaks=[])
    zones = build_zones(p, s, CNMG, r)
    return zones, ZoneQueryAPI(zones)


@pytest.mark.parametrize("name,z_end", [("quadrants", -1.25), ("radius_arcs", -1.0)])
@pytest.mark.parametrize("zone", ["finished_part", "material_to_rough"])
def test_every_boundary_point_lies_on_the_kernel_outline(name, z_end, zone):
    from build123d import Vertex
    from pipeline.pipeline import _extract_zone_boundary
    zones, zq = _zones(PROFILES[name], z_end)
    face = getattr(zones, zone)
    outline = face.faces()[0].outer_wire() if hasattr(face, "faces") else face.outer_wire()
    pts = _extract_zone_boundary(zq, zone)
    assert len(pts) > 8
    worst = max(Vertex(x / 2.0, z, 0).distance_to(outline) for x, z in pts)
    assert worst < 1e-7, f"{name}/{zone}: a boundary point is {worst:.3g} in off the kernel outline"


def test_arc_samples_follow_the_edges_own_sweep():
    from geometry.zone_query import EdgeData, boundary_polyline
    # quarter arc in radius space, centre (0.5, -1.0), r .25, clockwise (negative sweep)
    e = EdgeData("ARC", start=(1.5, -1.0), end=(1.0, -0.75), center=(1.0, -1.0), radius=0.25,
                 direction="ccw", sweep=math.pi / 2)
    pts = boundary_polyline([e])
    assert pts[0] == (1.5, -1.0) and pts[-1] == (1.0, -0.75)
    worst = max(abs(math.hypot(x / 2 - 0.5, z + 1.0) - 0.25) for x, z in pts)
    assert worst < 1e-12
