"""Shapely validation polygon construction for Industry CAM Engine.

Constructs Shapely Polygon objects from Build123d zone boundaries for
fast runtime safety checking. Uses adaptive arc densification.

The ONLY place where Shapely is used for polygon construction.
Imports from: models/, geometry/
"""

from typing import List, Tuple, TYPE_CHECKING

from shapely.geometry import Polygon

from models.constants import SHAPELY_COS_LIMIT, MAX_DENSIFICATION_DEPTH
from geometry.adaptive_sampling import adaptive_densify_arc

if TYPE_CHECKING:
    from geometry.zone_query import ZoneQueryAPI, EdgeData
    from geometry.zone_builder import ZoneSet


class ValidationPolygons:
    """Shapely polygons constructed from Build123d zone boundaries.

    Cached — constructed once after build_zones(), never reconstructed per-query.
    Used by post_planning_validator to check every move against zone boundaries.

    Properties:
    - Inscribed-chord guarantee: polygon chords are INSIDE the true arc
    - Max chord error < 0.000025" (50× tighter than TOLERANCE)
    - Construction time < 10ms for profiles with up to 20 arc segments
    """

    def __init__(self, finished_part_poly: Polygon, finish_allowance_poly: Polygon,
                 material_to_rough_poly: Polygon):
        self.finished_part_poly = finished_part_poly
        self.finish_allowance_poly = finish_allowance_poly
        self.material_to_rough_poly = material_to_rough_poly

    @classmethod
    def from_zone_query(cls, zone_query: 'ZoneQueryAPI') -> 'ValidationPolygons':
        """Construct Shapely polygons from zone boundary wires.

        For LINE edges: exact start/end coordinates (no densification)
        For ARC edges: adaptive densification with cos_limit=0.9999

        All coordinates converted to RADIUS for Shapely (matching Build123d convention).
        """
        finished_part_poly = cls._build_polygon(
            zone_query.boundary_wire_extraction("finished_part")
        )
        finish_allowance_poly = cls._build_polygon(
            zone_query.boundary_wire_extraction("finish_allowance")
        )
        material_to_rough_poly = cls._build_polygon(
            zone_query.boundary_wire_extraction("material_to_rough")
        )

        return cls(finished_part_poly, finish_allowance_poly, material_to_rough_poly)

    @classmethod
    def _build_polygon(cls, edges: List['EdgeData']) -> Polygon:
        """Convert boundary edges to a Shapely Polygon.

        Coordinates are converted from DIAMETER (as returned by boundary_wire_extraction)
        to RADIUS (as used by Shapely/Build123d internally).
        """
        if not edges:
            return Polygon()  # Empty polygon

        coords = []
        for edge in edges:
            # Convert from diameter to radius
            start_x_r = edge.start[0] / 2.0
            start_z = edge.start[1]
            end_x_r = edge.end[0] / 2.0
            end_z = edge.end[1]

            if not coords:
                coords.append((start_x_r, start_z))

            if edge.edge_type == "LINE":
                coords.append((end_x_r, end_z))
            elif edge.edge_type == "ARC":
                # Adaptive densification for arc segments
                center_x_r = edge.center[0] / 2.0 if edge.center else 0.0
                center_z = edge.center[1] if edge.center else 0.0

                arc_points = adaptive_densify_arc(
                    start=(start_x_r, start_z),
                    end=(end_x_r, end_z),
                    center=(center_x_r, center_z),
                    radius=edge.radius,
                    cos_limit=SHAPELY_COS_LIMIT,
                    max_depth=MAX_DENSIFICATION_DEPTH,
                )
                # Skip the first point (it's the start, already in coords)
                coords.extend(arc_points[1:])

        # Close the polygon if not already closed
        if coords and coords[0] != coords[-1]:
            coords.append(coords[0])

        if len(coords) < 4:
            return Polygon()  # Need at least 3 unique points + closure

        poly = Polygon(coords)
        if not poly.is_valid:
            from shapely.validation import make_valid
            poly = make_valid(poly)

        return poly
