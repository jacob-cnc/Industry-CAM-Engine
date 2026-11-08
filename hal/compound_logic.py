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


# Default soft limits (legacy constants). Live compound jogging passes the
# machine's real joint limits via the ``limits`` argument instead, because
# these constants do not match the INI (see CompoundJogEngine).
_X_MIN_R = X_MIN_LIMIT / 2.0
_X_MAX_R = X_MAX_LIMIT / 2.0
_Z_MIN = Z_MIN_LIMIT
_Z_MAX = Z_MAX_LIMIT

# (x_min_radius, x_max_radius, z_min, z_max)
Limits = Tuple[float, float, float, float]
_DEFAULT_LIMITS: Limits = (_X_MIN_R, _X_MAX_R, _Z_MIN, _Z_MAX)


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
                          x_delta: float, z_delta: float,
                          limits: Limits = None) -> Tuple[float, float, bool]:
        """Check if motion would exceed soft limits.

        If EITHER axis would exceed, BOTH are suppressed (no partial motion).

        Args:
            current_x: Current X position (radius).
            current_z: Current Z position.
            x_delta: Proposed X motion (radius).
            z_delta: Proposed Z motion.
            limits: (x_min_r, x_max_r, z_min, z_max); defaults to legacy constants.

        Returns:
            (x_delta, z_delta, suppressed).
        """
        x_min, x_max, z_min, z_max = limits or _DEFAULT_LIMITS
        if (current_x + x_delta) < x_min or (current_x + x_delta) > x_max:
            return (0.0, 0.0, True)
        if (current_z + z_delta) < z_min or (current_z + z_delta) > z_max:
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
        self._direction: float = 1.0   # +1: positive counts increase angle
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
        By construction the tool sits exactly on one END of the quadrant's
        arc (ARC_TOP / ARC_BOTTOM are the two tangent points), so the angle is
        snapped to that boundary and the travel direction is chosen so that a
        POSITIVE MPG count always moves INTO the quadrant.
        """
        self.radius = radius
        self.quadrant = quadrant
        self.arc_center_x, self.arc_center_z = self.compute_arc_center(
            current_x, current_z, radius, quadrant, start_type
        )
        self.angle_start, self.angle_end = self.get_quadrant_angle_range(quadrant)

        dx = current_x - self.arc_center_x
        dz = current_z - self.arc_center_z
        raw = math.atan2(dx, dz)

        def ang_dist(a, b):
            d = (a - b) % (2 * math.pi)
            return min(d, 2 * math.pi - d)

        if ang_dist(raw, self.angle_start) <= ang_dist(raw, self.angle_end):
            self.current_angle = self.angle_start
            self._direction = 1.0
        else:
            self.current_angle = self.angle_end
            self._direction = -1.0

        self.cumulative_distance = 0.0

    def process_pulse(self, count_delta: int, jog_scale: float,
                      current_x: float, current_z: float,
                      limits: Limits = None
                      ) -> Tuple[float, float, bool, bool]:
        """Advance along the arc by ``count_delta * jog_scale`` of path length.

        The angle is tracked directly (no atan2 re-derivation, so no 0/2pi
        wrap) and clamped to the quadrant, so one pulse can never move the
        tool more than the arc length it commanded. (2026-11-08: the previous
        tangent + re-projection + atan2 version wrapped at the start boundary
        and clamped to the FAR end — one MPG click ran the whole quadrant.)

        Args:
            count_delta: Encoder count delta (signed). Positive = into the arc.
            jog_scale: Path length per count (inches).
            current_x: Current X (radius) — the commanded/virtual position.
            current_z: Current Z.
            limits: (x_min_r, x_max_r, z_min, z_max); defaults to legacy constants.

        Returns:
            (x_delta, z_delta, suppressed, clamped) — deltas move the tool from
            (current_x, current_z) to the new point on the arc.
        """
        if count_delta == 0 or self.radius <= 0.0:
            return (0.0, 0.0, False, False)

        direction = getattr(self, "_direction", 1.0)
        target = self.current_angle + direction * count_delta * jog_scale / self.radius
        new_angle = min(max(target, self.angle_start), self.angle_end)
        clamped = new_angle != target
        if abs(new_angle - self.current_angle) < 1e-15:
            return (0.0, 0.0, False, clamped)

        new_x = self.arc_center_x + self.radius * math.sin(new_angle)
        new_z = self.arc_center_z + self.radius * math.cos(new_angle)

        x_min, x_max, z_min, z_max = limits or _DEFAULT_LIMITS
        if new_x < x_min or new_x > x_max or new_z < z_min or new_z > z_max:
            return (0.0, 0.0, True, False)

        self.current_angle = new_angle
        return (new_x - current_x, new_z - current_z, False, clamped)

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


# ======================================================================
# Operator selection -> logic arc (shared by activation and the UI graphic)
# ======================================================================

_USER_QUADRANTS = ["NE", "NW", "SW", "SE"]   # Manual-tab combo order


def resolve_user_arc(user_quadrant_idx: int, start_idx: int
                     ) -> Tuple[Quadrant, ArcStartType]:
    """Map the Manual-tab combos to the logic quadrant and start type.

    The combo labels use the operator's view of the graph (invertY: X+ is
    down), while the logic uses atan2(dx, dz) with +X at pi/2, so N/S swap:
        user NE -> logic SE, NW -> SW, SW -> NW, SE -> NE.
    The swap also inverts top/bottom for the user's north quadrants, so the
    start type is flipped there. (Machine-verified mapping, 2026-11-08.)

    Args:
        user_quadrant_idx: combo index, 0..3 = NE, NW, SW, SE.
        start_idx: combo index, 0 = "Arc Top", 1 = "Arc Bottom".
    """
    quadrant = [Quadrant.SE, Quadrant.SW, Quadrant.NW, Quadrant.NE][user_quadrant_idx]
    start = ArcStartType.ARC_TOP if start_idx == 0 else ArcStartType.ARC_BOTTOM
    if user_quadrant_idx in (0, 1):   # user NE / NW
        start = (ArcStartType.ARC_BOTTOM if start == ArcStartType.ARC_TOP
                 else ArcStartType.ARC_TOP)
    return quadrant, start


def arc_endpoint_angles(quadrant: Quadrant, start_type: ArcStartType
                        ) -> Tuple[float, float]:
    """(start_angle, end_angle) the arc logic will use for this selection.

    Angles are atan2(dx, dz) convention: point = center + R*(sin a, cos a)
    with dx = X (radius), dz = Z. Derived by activating the real logic, so
    the UI can never disagree with the motion.
    """
    logic = CompoundArcLogic()
    logic.activate(0.0, 0.0, 1.0, quadrant, start_type)
    start = logic.current_angle
    end = logic.angle_end if start == logic.angle_start else logic.angle_start
    return start, end
