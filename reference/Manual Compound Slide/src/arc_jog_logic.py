"""Pure computation logic for arc jog motion decomposition.

This module contains the ArcJogLogic class which handles:
- Arc center calculation from tool position and parameters
- Tangent direction computation at angular position
- MPG pulse decomposition along arc tangent
- Re-projection onto ideal arc circle
- Angular clamping to quadrant boundaries
- Soft limit enforcement
- Cumulative distance tracking

No GUI, no HAL, no side effects — fully testable in isolation.
All X coordinates use radius internally.
"""

import math
from enum import Enum
from typing import Tuple


class Quadrant(Enum):
    """The four 90-degree arc segments."""
    TOP_RIGHT = "NE"
    TOP_LEFT = "NW"
    BOTTOM_LEFT = "SW"
    BOTTOM_RIGHT = "SE"


class StartType(Enum):
    """Whether the tool starts at the arc top or arc bottom."""
    POLE = "arc_top"
    MIDPOINT = "arc_bottom"


class ArcJogLogic:
    """Pure logic for arc jog motion decomposition.

    Computes tangent-based motion along a circular arc, with
    re-projection to maintain geometric accuracy and angular
    clamping to enforce quadrant boundaries.

    All X coordinates use radius internally (not diameter).
    """

    def __init__(self, x_min: float, x_max: float, z_min: float, z_max: float):
        """Initialize with soft limits (X in radius).

        Args:
            x_min: Minimum X axis soft limit (radius)
            x_max: Maximum X axis soft limit (radius)
            z_min: Minimum Z axis soft limit
            z_max: Maximum Z axis soft limit
        """
        self.x_min = x_min
        self.x_max = x_max
        self.z_min = z_min
        self.z_max = z_max

        # Arc state (set on activation)
        self.arc_center_x: float = 0.0
        self.arc_center_z: float = 0.0
        self.radius: float = 0.25
        self.quadrant: Quadrant = Quadrant.TOP_RIGHT
        self.current_angle: float = 0.0  # radians, from arc center
        self.angle_start: float = 0.0    # start boundary of quadrant
        self.angle_end: float = 0.0      # end boundary of quadrant
        self.cumulative_distance: float = 0.0

    def reset(self):
        """Reset arc state (called on deactivation)."""
        self.cumulative_distance = 0.0
        self.current_angle = 0.0

    @staticmethod
    def validate_radius(value) -> Tuple[bool, float]:
        """Validate radius input.

        Args:
            value: Input to validate (string or numeric)

        Returns:
            (is_valid, parsed_value) -- parsed_value is 0.0 if invalid
        """
        try:
            r = float(value)
            if r > 0.0:
                return (True, r)
            return (False, 0.0)
        except (ValueError, TypeError):
            return (False, 0.0)

    def compute_arc_center(self, current_x: float, current_z: float,
                           radius: float, quadrant: Quadrant,
                           start_type: StartType) -> Tuple[float, float]:
        """Compute the arc center from tool position and parameters.

        Args:
            current_x: Current X position (radius units)
            current_z: Current Z position
            radius: Arc radius
            quadrant: Selected quadrant
            start_type: Pole or Midpoint

        Returns:
            (center_x, center_z) -- the computed arc center
        """
        if start_type == StartType.POLE:
            # Pole: tool is at top/bottom of arc, offset is in Z
            if quadrant in (Quadrant.TOP_RIGHT, Quadrant.BOTTOM_RIGHT):
                center_x = current_x
                center_z = current_z - radius
            else:  # TOP_LEFT, BOTTOM_LEFT
                center_x = current_x
                center_z = current_z + radius
        else:
            # Midpoint: tool is at left/right of arc, offset is in X
            if quadrant in (Quadrant.TOP_RIGHT, Quadrant.TOP_LEFT):
                center_x = current_x - radius
                center_z = current_z
            else:  # BOTTOM_RIGHT, BOTTOM_LEFT
                center_x = current_x + radius
                center_z = current_z

        return (center_x, center_z)

    def get_quadrant_angle_range(self, quadrant: Quadrant) -> Tuple[float, float]:
        """Get the angular range [start, end] for a quadrant.

        Angles are measured counter-clockwise from the positive Z axis
        (3 o'clock position), matching standard math convention where:
        - 0 rad = positive Z direction from center
        - pi/2 rad = positive X direction from center
        - pi rad = negative Z direction from center
        - 3pi/2 rad = negative X direction from center

        Returns:
            (angle_start, angle_end) in radians
        """
        if quadrant == Quadrant.TOP_RIGHT:
            return (0.0, math.pi / 2)
        elif quadrant == Quadrant.TOP_LEFT:
            return (math.pi / 2, math.pi)
        elif quadrant == Quadrant.BOTTOM_LEFT:
            return (math.pi, 3 * math.pi / 2)
        else:  # BOTTOM_RIGHT
            return (3 * math.pi / 2, 2 * math.pi)

    def activate(self, current_x: float, current_z: float,
                 radius: float, quadrant: Quadrant,
                 start_type: StartType):
        """Activate arc mode -- compute center and set initial angle.

        Args:
            current_x: Current X position (radius units)
            current_z: Current Z position
            radius: Arc radius
            quadrant: Selected quadrant
            start_type: Pole or Midpoint
        """
        self.radius = radius
        self.quadrant = quadrant
        self.arc_center_x, self.arc_center_z = self.compute_arc_center(
            current_x, current_z, radius, quadrant, start_type
        )
        self.angle_start, self.angle_end = self.get_quadrant_angle_range(quadrant)

        # Compute initial angle from the tool position relative to center
        dx = current_x - self.arc_center_x
        dz = current_z - self.arc_center_z
        self.current_angle = math.atan2(dx, dz)  # atan2(x, z) for our convention
        # Normalize to [0, 2pi)
        if self.current_angle < 0:
            self.current_angle += 2 * math.pi

        # Handle the 0/2pi wrap for BOTTOM_RIGHT quadrant:
        # angle 0 and 2pi are the same physical point, but the range is [3pi/2, 2pi]
        if self.current_angle < self.angle_start and abs(self.current_angle) < 1e-10:
            self.current_angle = 2 * math.pi

        self.cumulative_distance = 0.0

    def compute_tangent(self, angle: float) -> Tuple[float, float]:
        """Compute the unit tangent vector at the given angle.

        The tangent is perpendicular to the radius vector, pointing in
        the direction of increasing angle (counter-clockwise).

        For angle theta measured from +Z axis (atan2(x, z) convention):
        - Position on circle: (r*sin(theta), r*cos(theta))
        - Tangent (d/d_theta): (cos(theta), -sin(theta)) -- normalized

        Args:
            angle: Angular position in radians

        Returns:
            (tangent_x, tangent_z) -- unit tangent vector
        """
        tangent_x = math.cos(angle)
        tangent_z = -math.sin(angle)
        return (tangent_x, tangent_z)

    def decompose_arc_pulse(self, count_delta: int, jog_scale: float
                            ) -> Tuple[float, float]:
        """Decompose MPG pulse into X and Z components along arc tangent.

        Args:
            count_delta: Number of encoder counts (signed)
            jog_scale: Distance per pulse (inches)

        Returns:
            (x_delta, z_delta) -- proposed motion in radius units
        """
        tangent_x, tangent_z = self.compute_tangent(self.current_angle)
        x_delta = count_delta * jog_scale * tangent_x
        z_delta = count_delta * jog_scale * tangent_z
        return (x_delta, z_delta)

    def check_soft_limits(self, current_x: float, current_z: float,
                          x_delta: float, z_delta: float) -> Tuple[float, float, bool]:
        """Check if motion would exceed soft limits.

        If either axis would exceed its limits, BOTH axes are suppressed.

        Args:
            current_x: Current X position (radius)
            current_z: Current Z position
            x_delta: Proposed X motion
            z_delta: Proposed Z motion

        Returns:
            (x_delta, z_delta, suppressed)
        """
        new_x = current_x + x_delta
        new_z = current_z + z_delta
        if new_x < self.x_min or new_x > self.x_max:
            return (0.0, 0.0, True)
        if new_z < self.z_min or new_z > self.z_max:
            return (0.0, 0.0, True)
        return (x_delta, z_delta, False)

    def reproject_onto_arc(self, position_x: float, position_z: float
                           ) -> Tuple[float, float]:
        """Re-project a position onto the ideal arc circle.

        Normalizes the vector from arc center to position, then scales
        to exactly the radius distance.

        Args:
            position_x: X position after tangent motion
            position_z: Z position after tangent motion

        Returns:
            (reprojected_x, reprojected_z) -- position on ideal arc
        """
        dx = position_x - self.arc_center_x
        dz = position_z - self.arc_center_z
        dist = math.sqrt(dx * dx + dz * dz)
        if dist < 1e-15:
            # Degenerate case: position is at arc center
            # Return position on arc at current angle
            return (
                self.arc_center_x + self.radius * math.sin(self.current_angle),
                self.arc_center_z + self.radius * math.cos(self.current_angle)
            )
        scale = self.radius / dist
        return (
            self.arc_center_x + dx * scale,
            self.arc_center_z + dz * scale
        )

    def clamp_angle(self, angle: float) -> Tuple[float, bool]:
        """Clamp angle to the quadrant boundaries.

        Args:
            angle: Proposed angle in radians

        Returns:
            (clamped_angle, was_clamped) -- True if clamping occurred
        """
        if angle < self.angle_start:
            return (self.angle_start, True)
        if angle > self.angle_end:
            return (self.angle_end, True)
        return (angle, False)

    def process_pulse(self, count_delta: int, jog_scale: float,
                      current_x: float, current_z: float
                      ) -> Tuple[float, float, bool, bool]:
        """Process a single MPG pulse through the full arc pipeline.

        Pipeline: tangent decomposition -> soft limit check ->
                  re-projection -> angle update -> angular clamping

        Args:
            count_delta: Encoder count delta (signed)
            jog_scale: Distance per pulse (inches)
            current_x: Current X position (radius)
            current_z: Current Z position

        Returns:
            (x_delta, z_delta, suppressed, clamped)
            x_delta/z_delta: Final approved motion (0 if suppressed/clamped)
            suppressed: True if soft limit prevented motion
            clamped: True if angular boundary prevented motion
        """
        # Step 1: Decompose pulse along tangent
        x_delta, z_delta = self.decompose_arc_pulse(count_delta, jog_scale)

        # Step 2: Check soft limits
        x_delta, z_delta, suppressed = self.check_soft_limits(
            current_x, current_z, x_delta, z_delta
        )
        if suppressed:
            return (0.0, 0.0, True, False)

        # Step 3: Apply motion and re-project onto arc
        new_x = current_x + x_delta
        new_z = current_z + z_delta
        reproj_x, reproj_z = self.reproject_onto_arc(new_x, new_z)

        # Step 4: Compute new angle and clamp
        dx = reproj_x - self.arc_center_x
        dz = reproj_z - self.arc_center_z
        new_angle = math.atan2(dx, dz)
        if new_angle < 0:
            new_angle += 2 * math.pi
        # Handle 0/2pi wrap for BOTTOM_RIGHT quadrant
        if new_angle < self.angle_start and abs(new_angle) < 1e-10:
            new_angle = 2 * math.pi
        # Detect wrap-around past 2pi for BOTTOM_RIGHT quadrant:
        # If current angle is in [3pi/2, 2pi] and new angle is small (wrapped past 0),
        # it means we overshot the end boundary at 2pi
        if (self.angle_end >= 2 * math.pi - 1e-10 and
                self.current_angle > self.angle_start and
                new_angle < self.angle_start):
            new_angle = 2 * math.pi
        # If already at end boundary and wrap detection pushed us to end again,
        # treat as clamped at boundary
        if (abs(new_angle - self.angle_end) < 1e-10 and
                abs(self.current_angle - self.angle_end) < 1e-10):
            return (0.0, 0.0, False, True)

        clamped_angle, was_clamped = self.clamp_angle(new_angle)

        if was_clamped:
            # Compute position at clamped angle
            clamped_x = self.arc_center_x + self.radius * math.sin(clamped_angle)
            clamped_z = self.arc_center_z + self.radius * math.cos(clamped_angle)
            # If already at this boundary, suppress entirely
            if abs(clamped_angle - self.current_angle) < 1e-12:
                return (0.0, 0.0, False, True)
            # Otherwise, move to the boundary
            final_x_delta = clamped_x - current_x
            final_z_delta = clamped_z - current_z
            self.current_angle = clamped_angle
            return (final_x_delta, final_z_delta, False, True)

        # Step 5: Compute final deltas from re-projected position
        final_x_delta = reproj_x - current_x
        final_z_delta = reproj_z - current_z
        self.current_angle = clamped_angle

        return (final_x_delta, final_z_delta, False, False)

    def accumulate_distance(self, x_delta: float, z_delta: float) -> float:
        """Add to cumulative arc distance.

        Args:
            x_delta: X component of approved motion
            z_delta: Z component of approved motion

        Returns:
            Updated cumulative distance
        """
        dist = math.sqrt(x_delta ** 2 + z_delta ** 2)
        self.cumulative_distance += dist
        return self.cumulative_distance
