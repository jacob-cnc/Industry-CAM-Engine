"""Tool geometry computation for Industry CAM Engine.

Computes the tool's physical shape as a segment group for reach analysis
and visual preview. Modeled after liblathe's Tool.get_segmentgroup().

TNR compensation is handled by LinuxCNC G41/G42 — this module only provides
reach analysis (can the tool physically fit in concave geometry).

Imports from: models/
"""

import math
from typing import List, Tuple

from models.tool import ToolDef, ToolOrientation, ToolDirection
from models.profile import MachiningMode


class ToolReachError(Exception):
    """Raised when tool nose radius exceeds minimum concave radius in profile."""

    def __init__(self, nose_radius: float, min_concave_radius: float, location: Tuple[float, float]):
        self.nose_radius = nose_radius
        self.min_concave_radius = min_concave_radius
        self.location = location
        super().__init__(
            f"Tool TNR ({nose_radius:.4f}\") exceeds minimum concave radius "
            f"({min_concave_radius:.4f}\") at ({location[0]:.4f}, {location[1]:.4f})"
        )


class ToolShape:
    """Computes the tool's physical geometry as a segment group.

    The tool shape is used for:
    - Reach analysis (can_reach) — determines if the tool fits in concave geometry
    - Visual preview in the Tools Tab (get_outline_points)
    - Reach boundary computation (get_reach_boundary)

    TNR compensation for toolpath generation is NOT done here — LinuxCNC G41/G42
    handles that at runtime using the tool table data.
    """

    def __init__(self, tool_def: ToolDef):
        self._def = tool_def
        self._outline = self._compute_outline()

    @property
    def tool_def(self) -> ToolDef:
        return self._def

    def get_outline_points(self) -> List[Tuple[float, float]]:
        """Get the tool outline as coordinate pairs for visual preview.

        Returns points in (x_offset, z_offset) relative to the tool tip.
        Used by the Tools Tab QPainterPath preview — NOT by the engine.
        Orientation from lathe operator's perspective (looking at cross-slide from front).
        """
        return self._outline

    def get_reach_boundary(self) -> List[Tuple[float, float]]:
        """The envelope of positions the tool tip can reach.

        Returns coordinate pairs (x_radius, z) defining the reach boundary
        based on tip angle, edge length, and orientation.
        """
        td = self._def
        half_angle_rad = math.radians(td.tip_angle / 2.0)

        # The reach is limited by the edge length and tip angle
        # The tool can reach Z positions limited by edge_length * cos(half_angle)
        # and X positions limited by edge_length * sin(half_angle)
        z_reach = td.edge_length * math.cos(half_angle_rad)
        x_reach = td.edge_length * math.sin(half_angle_rad)

        # Return a simplified boundary (rectangle approximation)
        return [
            (0.0, 0.0),           # Tool tip
            (x_reach, 0.0),       # Max X reach at tip Z
            (x_reach, -z_reach),  # Max X at max Z depth
            (0.0, -z_reach),      # Centerline at max Z depth
        ]

    def can_reach(self, x_dia: float, z: float, profile_curvature: float) -> bool:
        """Whether the tool can physically cut at this position given local geometry.

        Args:
            x_dia: X position (diameter)
            z: Z position (inches)
            profile_curvature: Local curvature (1/radius). Positive = concave, negative = convex.
                              For concave regions, if TNR > 1/curvature, tool cannot reach.

        Returns:
            True if tool can reach. False if geometry is too tight.

        Note: This is advisory (produces WARNING, not ERROR). LinuxCNC's cutter comp
        will attempt the geometry regardless — it may gouge or leave material.
        """
        if profile_curvature <= 0:
            # Convex or flat — tool can always reach
            return True

        min_concave_radius = 1.0 / profile_curvature
        return self._def.nose_radius <= min_concave_radius

    def check_reach_or_warn(self, min_concave_radius: float, location: Tuple[float, float]) -> bool:
        """Check if TNR fits in a concave region. Returns False if it doesn't fit.

        Unlike can_reach(), this takes the radius directly (not curvature).
        Used during validation to generate warnings.
        """
        if min_concave_radius <= 0:
            return True  # Not concave
        return self._def.nose_radius <= min_concave_radius

    def _compute_outline(self) -> List[Tuple[float, float]]:
        """Compute tool outline points for visual preview.

        Draws the insert shape based on tip_angle, edge_length, nose_radius,
        and orientation. Points are relative to tool tip (0, 0).

        The outline is from the lathe operator's perspective:
        - X axis = vertical (up = away from centerline)
        - Z axis = horizontal (left = toward chuck)
        """
        td = self._def
        half_angle_rad = math.radians(td.tip_angle / 2.0)
        edge = td.edge_length
        tnr = td.nose_radius

        # Compute the two cutting edges extending from the nose radius center
        # The nose radius center is offset from the tip by TNR
        # Edge directions depend on tip angle

        # Leading edge direction (toward workpiece)
        lead_dx = edge * math.sin(half_angle_rad)
        lead_dz = edge * math.cos(half_angle_rad)

        # Trailing edge direction (away from workpiece)
        trail_dx = edge * math.sin(half_angle_rad)
        trail_dz = -edge * math.cos(half_angle_rad)

        # Build outline points (simplified diamond/rhombic shape)
        points = [
            (0.0, 0.0),                    # Tool tip (nose radius center approximation)
            (lead_dx, -lead_dz),           # Leading edge end
            (lead_dx + trail_dx, 0.0),     # Back of insert (top)
            (trail_dx, trail_dz),          # Trailing edge end
            (0.0, 0.0),                    # Back to tip (closed)
        ]

        # Apply orientation mirroring
        orientation = td.orientation
        if orientation in (ToolOrientation.OD_FRONT_LEFT, ToolOrientation.OD_BACK_LEFT,
                          ToolOrientation.ID_FRONT_LEFT, ToolOrientation.ID_BACK_LEFT):
            # Mirror X for left-hand tools
            points = [(-x, z) for x, z in points]

        if orientation in (ToolOrientation.OD_BACK_RIGHT, ToolOrientation.OD_BACK_LEFT,
                          ToolOrientation.ID_BACK_RIGHT, ToolOrientation.ID_BACK_LEFT):
            # Mirror Z for back-mounted tools
            points = [(x, -z) for x, z in points]

        return points
