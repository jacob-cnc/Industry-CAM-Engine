"""Geometry module — Build123d zone construction and query API.

The ONLY module that imports Build123d or OCCT.
Imports from: models/, tools/
"""

from geometry.adaptive_sampling import adaptive_densify_arc, flatness_predicate, arc_midpoint
from geometry.zone_builder import ZoneSet, build_zones
from geometry.zone_query import ZoneQueryAPI, EdgeData
from geometry.contour_intersect import ContourIntersect
