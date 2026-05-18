"""Validation module — Shapely-based runtime safety checking.

The ONLY module that imports Shapely.
Imports from: models/, geometry/
"""

from validation.polygon_builder import ValidationPolygons
from validation.pre_planning_validator import validate_profile
from validation.post_planning_validator import validate_all_moves
from validation.pre_output_validator import validate_gcode_geometry
