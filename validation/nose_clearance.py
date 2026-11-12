"""Where the roughing tool's TIP may feed without its NOSE entering the keep zone.

Moved from planners/staircase_planner.py on 2026-11-12 (structure cleanup):
Shapely may only be used in validation/, and planners may not import
validation/. The pipeline builds a NoseClearance and hands it to the
staircase planner, which only asks it `free_spans(...)`.

Why it exists (2026-11-11, found by the G-code section check): roughing is
uncompensated - LinuxCNC drives the imaginary tip and the nose circle sits
nose_centre_offset away from it - so beside a contour that falls toward the
chuck the nose overhangs the flank (.0125 into a 60 deg flank with a VNMG
against a .005 allowance). The forbidden region is the keep zone (finished
part + finish allowance) grown by the nose radius and shifted from nose
centre to tip. On faces and diameters it coincides with the zone, so ordinary
turning is unchanged.

Coordinates: (r, z), radius space.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from models.constants import TOLERANCE


class NoseClearance:
    """Forbidden tip region for one roughing tool against one keep zone."""

    def __init__(self, forbidden):
        self._forbidden = forbidden          # Shapely geometry, (r, z)

    @classmethod
    def build(cls, zone_query, tool) -> Optional["NoseClearance"]:
        """The tool's NoseClearance, or None when there is nothing to keep clear
        of (zone polygons unavailable, empty keep zone, or a sharp tool)."""
        from shapely.affinity import translate
        from models.tool import nose_centre_offset
        try:
            from validation.polygon_builder import ValidationPolygons
            vp = ValidationPolygons.from_zone_query(zone_query)
            keep = vp.finished_part_poly.union(vp.finish_allowance_poly)
        except Exception:
            return None
        if keep.is_empty or tool.nose_radius <= 0:
            return None
        off = nose_centre_offset(tool)
        # nose centre must stay >= R from keep: centre not in keep (+) R; tip = centre - off
        # buffer's 2nd argument positionally: resolution (Shapely 1.8) = quad_segs (2.x)
        return cls(translate(keep.buffer(tool.nose_radius, 32), -off[0], -off[1]))

    def free_spans(self, r: float, z_top: float, z_bottom: float) -> List[Tuple[float, float]]:
        """Pieces (z_hi, z_lo) of the feed line at radius r from z_top down to
        z_bottom where the tip may go, highest first. Pieces shorter than
        TOLERANCE are dropped."""
        from shapely.geometry import LineString
        free = LineString([(r, z_top), (r, z_bottom)]).difference(self._forbidden)
        parts = [free] if free.geom_type == "LineString" else list(getattr(free, "geoms", []))
        pieces = []
        for g in parts:
            if g.is_empty or g.length < TOLERANCE:
                continue
            zs = [c[1] for c in g.coords]
            pieces.append((max(zs), min(zs)))
        return sorted(pieces, key=lambda p: -p[0])
