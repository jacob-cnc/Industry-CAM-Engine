"""Pure computation logic for compound slide motion.

Two modes:
  Linear — Decomposes MPG pulses along a user-defined angle (0-90° from Z axis).
  Arc — Traverses a circular arc within a selected quadrant.

No GUI, no HAL, no side effects — fully testable in isolation.
All X coordinates use RADIUS internally.

Usage:
    from hal.compound_logic import CompoundLinearLogic, CompoundArcLogic
"""

import math
from enum import Enum
from typing import Tuple

from hal.constants import X_MIN_LIMIT, X_MAX_LIMIT, Z_MIN_LIMIT, Z_MAX_LIMIT


# Soft limits in radius for X (INI values are diameter)
_X_MIN_R = X_MIN_LIMIT / 2.0
_X_MAX_R = X_MAX_LIMIT / 2.0
_Z_MIN = Z_MIN_LIMIT
_Z_MAX = Z_MAX_LIMIT


# ======================================================================
# Enums
# ======================================================================

class Quadrant(Enum):
    """The four 90° arc segments."""
    NE = "NE"  # Top-right
    NW = "NW"  # Top-left
    SW = "SW"  # Bottom-left
    SE = "SE"  # Bottom-right (default for threading)


class ArcStartType(Enum):
    """Where the tool starts on the arc."""
    ARC_TOP = "arc_top"       # Tool at tangent-horizontal point
    ARC_BOTTOM = "arc_bottom"  # Tool at tangent-vertical point


# ======================================================================
# Linear Compound Logic
# ======================================================================

class CompoundLinearLogic:
    """Pure logic for linear compound slide motion decomposition.

    Decomposes a single-axis MPG input into coordinated X+Z motion
    along a user-defined angle measured from the Z axis.

    Angle convention:
        0° = pure Z motion (along spindle axis)
        29.5° = standard threading infeed
        45° = equal X and Z
        90° = pure X motion (perpendicular to spindle)
    """

    # Common preset angles (degrees from Z axis)
    PRESETS = {
        "29.5° Thread": 29.5,
        "45° Chamfer": 45.0,
        "60° Dovetail": 60.0,
        "30° Taper": 30.0,
    }

    def __init__(self):
        self.cumulative_distance: float = 0.0

    @staticmethod
    def validate_angle(value) -> Tuple[bool, float]:
        """Validate angle input (0.0 to 90.0 degrees).

        Args:
            value: String or numeric input.

        Returns:
            (is_valid, parsed_float) — parsed is 0.0 if invalid.
        """
        try:
            angle = float(value)
            if 0.0 <= angle <= 90.0:
                return (True, angle)
            return (False, 0.0)
        except (ValueError, TypeError):
            return (False, 0.0)

    @staticmethod
    def decompose_pulse(count_delta: int, jog_scale: float,
                        angle_deg: float) -> Tuple[float, float]:
        """Decompose MPG pulse into X and Z distance components.

        Args:
            count_delta: Encoder count change (signed).
            jog_scale: Distance per count (inches).
            angle_deg: Compound angle in degrees from Z axis.

        Returns:
            (x_distance, z_distance) — X in radius units.
        """
        angle_rad = math.radians(angle_deg)
        x_dist = count_delta * jog_scale * math.sin(angle_rad)
        z_dist = count_delta * jog_scale * math.cos(angle_rad)
        return (x_dist, z_dist)

    @staticmethod
    def check_soft_limits(current_x: float, current_z: float,
                          x_delta: float, z_delta: float) -> Tuple[float, float, bool]:
        """Check if motion would exceed soft limits.

        If EITHER axis would exceed, BOTH are suppressed (no partial motion).

        Args:
            current_x: Current X position (radius).
            current_z: Current Z position.
            x_delta: Proposed X motion (radius).
            z_delta: Proposed Z motion.

        Returns:
            (x_delta, z_delta, suppressed).
        """
        if (current_x + x_delta) < _X_MIN_R or (current_x + x_delta) > _X_MAX_R:
            return (0.0, 0.0, True)
        if (current_z + z_delta) < _Z_MIN or (current_z + z_delta) > _Z_MAX:
            return (0.0, 0.0, True)
        return (x_delta, z_delta, False)

    def accumulate_distance(self, x_delta: float, z_delta: float) -> float:
        """Add to cumulative distance along compound path.

        Returns updated cumulative distance.
        """
        self.cumulative_distance += math.sqrt(x_delta**2 + z_delta**2)
        return self.cumulative_distance

    def reset_distance(self):
        """Reset cumulative distance only."""
        self.cumulative_distance = 0.0

    def reset(self):
        """Reset cumulative distance (called on deactivation)."""
        self.cumulative_distance = 0.0


# ======================================================================
# Arc Compound Logic
# ======================================================================

class CompoundArcLogic:
    """Pure logic for arc jog motion decomposition.

    Traverses a circular arc within a selected 90° quadrant.
    Each MPG pulse moves the tool along the arc tangent, then
    re-projects onto the ideal circle to prevent drift.

    All X coordinates use radius internally.
    """

    def __init__(self):
        self.arc_center_x: float = 0.0
        self.arc_center_z: float = 0.0
        self.radius: float = 0.25
        self.quadrant: Quadrant = Quadrant.SE
        self.current_angle: float = 0.0
        self.angle_start: float = 0.0
        self.angle_end: float = 0.0
        self.cumulative_distance: float = 0.0

    @staticmethod
    def validate_radius(value) -> Tuple[bool, float]:
        """Validate radius input (must be > 0).

        Returns:
            (is_valid, parsed_float).
        """
        try:
            r = float(value)
            return (True, r) if r > 0.0 else (False, 0.0)
        except (ValueError, TypeError):
            return (False, 0.0)

    def get_quadrant_angle_range(self, quadrant: Quadrant) -> Tuple[float, float]:
        """Get angular range [start, end] for a quadrant.

        Angles measured counter-clockwise from +Z axis (atan2(x, z) convention):
            0 = +Z direction, π/2 = +X direction, π = -Z, 3π/2 = -X
        """
        ranges = {
            Quadrant.NE: (0.0, math.pi / 2),
            Quadrant.NW: (math.pi / 2, math.pi),
            Quadrant.SW: (math.pi, 3 * math.pi / 2),
            Quadrant.SE: (3 * math.pi / 2, 2 * math.pi),
        }
        return ranges[quadrant]

    def compute_arc_center(self, current_x: float, current_z: float,
                           radius: float, quadrant: Quadrant,
                           start_type: ArcStartType) -> Tuple[float, float]:
        """Compute arc center from tool position and parameters.

        Args:
            current_x: Current X (radius).
            current_z: Current Z.
            radius: Arc radius.
            quadrant: Selected quadrant.
            start_type: ARC_TOP or ARC_BOTTOM.

        Returns:
            (center_x, center_z).
        """
        if start_type == ArcStartType.ARC_TOP:
            if quadrant in (Quadrant.NE, Quadrant.SE):
                return (current_x, current_z - radius)
            else:
                return (current_x, current_z + radius)
        else:
            if quadrant in (Quadrant.NE, Quadrant.NW):
                return (current_x - radius, current_z)
            else:
                return (current_x + radius, current_z)

    def activate(self, current_x: float, current_z: float,
                 radius: float, quadrant: Quadrant,
                 start_type: ArcStartType):
        """Activate arc mode — compute center and initial angle.

        Must be called with the tool's current position at activation time.
        """
        self.radius = radius
        self.quadrant = quadrant
        self.arc_center_x, self.arc_center_z = self.compute_arc_center(
            current_x, current_z, radius, quadrant, start_type
        )
        self.angle_start, self.angle_end = self.get_quadrant_angle_range(quadrant)

        # Initial angle from tool position relative to center
        dx = current_x - self.arc_center_x
        dz = current_z - self.arc_center_z
        self.current_angle = math.atan2(dx, dz)
        if self.current_angle < 0:
            self.current_angle += 2 * math.pi
        # Handle 0/2π wrap for SE quadrant
        if self.current_angle < self.angle_start and abs(self.current_angle) < 1e-10:
            self.current_angle = 2 * math.pi

        self.cumulative_distance = 0.0

    def process_pulse(self, count_delta: int, jog_scale: float,
                      current_x: float, current_z: float
                      ) -> Tuple[float, float, bool, bool]:
        """Process a single MPG pulse through the full arc pipeline.

        Pipeline:
            1. Tangent decomposition
            2. Soft limit check
            3. Apply motion + re-project onto arc
            4. Angle update + angular clamping

        Args:
            count_delta: Encoder count delta (signed).
            jog_scale: Distance per count (inches).
            current_x: Current X (radius).
            current_z: Current Z.

        Returns:
            (x_delta, z_delta, suppressed, clamped).
        """
        # 1. Decompose along tangent
        tangent_x = math.cos(self.current_angle)
        tangent_z = -math.sin(self.current_angle)
        x_delta = count_delta * jog_scale * tangent_x
        z_delta = count_delta * jog_scale * tangent_z

        # 2. Soft limits
        new_x = current_x + x_delta
        new_z = current_z + z_delta
        if new_x < _X_MIN_R or new_x > _X_MAX_R or new_z < _Z_MIN or new_z > _Z_MAX:
            return (0.0, 0.0, True, False)

        # 3. Re-project onto arc
        dx = new_x - self.arc_center_x
        dz = new_z - self.arc_center_z
        dist = math.sqrt(dx * dx + dz * dz)
        if dist < 1e-15:
            return (0.0, 0.0, False, False)
        scale = self.radius / dist
        reproj_x = self.arc_center_x + dx * scale
        reproj_z = self.arc_center_z + dz * scale

        # 4. Compute new angle and clamp
        dx2 = reproj_x - self.arc_center_x
        dz2 = reproj_z - self.arc_center_z
        new_angle = math.atan2(dx2, dz2)
        if new_angle < 0:
            new_angle += 2 * math.pi
        if new_angle < self.angle_start and abs(new_angle) < 1e-10:
            new_angle = 2 * math.pi
        # Wrap detection for SE quadrant
        if (self.angle_end >= 2 * math.pi - 1e-10 and
                self.current_angle > self.angle_start and
                new_angle < self.angle_start):
            new_angle = 2 * math.pi

        # Clamp to quadrant boundaries
        clamped = False
        if new_angle < self.angle_start:
            new_angle = self.angle_start
            clamped = True
        elif new_angle > self.angle_end:
            new_angle = self.angle_end
            clamped = True

        if clamped:
            # Move to boundary position
            clamped_x = self.arc_center_x + self.radius * math.sin(new_angle)
            clamped_z = self.arc_center_z + self.radius * math.cos(new_angle)
            if abs(new_angle - self.current_angle) < 1e-12:
                return (0.0, 0.0, False, True)
            final_x = clamped_x - current_x
            final_z = clamped_z - current_z
            self.current_angle = new_angle
            return (final_x, final_z, False, True)

        # Normal motion
        final_x = reproj_x - current_x
        final_z = reproj_z - current_z
        self.current_angle = new_angle
        return (final_x, final_z, False, False)

    def accumulate_distance(self, x_delta: float, z_delta: float) -> float:
        """Add to cumulative arc distance."""
        self.cumulative_distance += math.sqrt(x_delta**2 + z_delta**2)
        return self.cumulative_distance

    def reset_distance(self):
        """Reset cumulative distance only."""
        self.cumulative_distance = 0.0

    def reset(self):
        """Reset arc state."""
        self.cumulative_distance = 0.0
        self.current_angle = 0.0

    def get_arc_points(self, n_points: int = 40) -> list:
        """Generate points along the active arc for graph overlay.

        Returns list of (x_radius, z) tuples forming the arc path.
        Empty list if not activated.
        """
        if self.radius <= 0 or self.angle_start == self.angle_end:
            return []
        points = []
        for i in range(n_points + 1):
            t = i / n_points
            angle = self.angle_start + t * (self.angle_end - self.angle_start)
            x = self.arc_center_x + self.radius * math.sin(angle)
            z = self.arc_center_z + self.radius * math.cos(angle)
            points.append((x, z))
        return points
