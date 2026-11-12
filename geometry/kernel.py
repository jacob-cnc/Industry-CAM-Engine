"""The geometry kernel's public API for planners (owner rule (a), 2026-11-11).

Planners may import from geometry/ ONLY through this module; raw OCP and
build123d stay inside geometry/ (enforced by validation/architecture_check
ALLOWED_SUBMODULE_IMPORTS and tests/architecture). Everything a planner needs
from the kernel - types, arc identity, profile outlines, offsets, and the
face / clip / edge-walk operations - is named here, so the boundary between
"what the CAM decides" (planners) and "what the geometry is" (kernel) is one
readable list.

Coordinates: radius space (r, z) for kernel geometry unless a name says
otherwise; planners convert to diameter for ToolMoves.
"""

from geometry.arc_helpers import is_arc_within_x_bounds
from geometry.arc_math import Arc, arc_from_kernel, r_extent, short_sweep, split_at_quadrants, sweep_piece
from geometry.kernel_offset import KernelOffsetError, offset_face
from geometry.zone_builder import profile_to_radius_coords
from geometry.zone_query import EdgeData
from geometry.face_ops import (clip_to_box, first_ocp_face, line_intersection, translate_face,
                                wire_edges)

__all__ = [
    # arc identity (geometry/arc_math, arc_helpers)
    "Arc", "arc_from_kernel", "short_sweep", "split_at_quadrants", "is_arc_within_x_bounds",
    "sweep_piece", "r_extent",
    # profile outline with corner breaks applied (geometry/zone_builder)
    "profile_to_radius_coords",
    # edge record handed to planners by ZoneQueryAPI (geometry/zone_query)
    "EdgeData",
    # offsets with sharp joins and an explicit, logged rounded-join fallback
    "offset_face", "KernelOffsetError",
    # face operations: first face, move, clip, walk (geometry/face_ops)
    "first_ocp_face", "translate_face", "clip_to_box", "wire_edges",
    # where two lines meet (geometry/face_ops)
    "line_intersection",
]
