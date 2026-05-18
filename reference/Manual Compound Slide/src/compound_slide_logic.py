"""Pure computation logic for compound slide motion decomposition.

This module contains the CompoundSlideLogic class which handles:
- Angle validation
- MPG pulse decomposition into X/Z components
- Soft limit enforcement
- Cumulative distance tracking

No GUI, no HAL, no side effects — fully testable in isolation.
All X coordinates use radius internally.
"""

import math


class CompoundSlideLogic:
    """Pure logic for compound slide motion decomposition."""

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
        self.cumulative_distance = 0.0

    @staticmethod
    def validate_angle(value) -> tuple:
        """Validate angle input.

        Args:
            value: Input to validate (string or numeric)

        Returns:
            (is_valid, parsed_value) — parsed_value is 0.0 if invalid
        """
        try:
            angle = float(value)
            if 0.0 <= angle <= 90.0:
                return (True, angle)
            return (False, 0.0)
        except (ValueError, TypeError):
            return (False, 0.0)

    def decompose_pulse(self, count_delta: int, jog_scale: float,
                        angle_deg: float) -> tuple:
        """Decompose MPG pulse into X and Z components.

        X_distance = count_delta × jog_scale × sin(angle_rad)
        Z_distance = count_delta × jog_scale × cos(angle_rad)

        Args:
            count_delta: Number of encoder counts (signed)
            jog_scale: Distance per pulse (inches)
            angle_deg: Compound angle in degrees from Z axis

        Returns:
            (x_distance, z_distance) — X in radius units
        """
        angle_rad = math.radians(angle_deg)
        x_dist = count_delta * jog_scale * math.sin(angle_rad)
        z_dist = count_delta * jog_scale * math.cos(angle_rad)
        return (x_dist, z_dist)

    def check_soft_limits(self, current_x: float, current_z: float,
                          x_delta: float, z_delta: float) -> tuple:
        """Check if motion would exceed soft limits.

        If either axis would exceed its limits, BOTH axes are suppressed
        (no partial motion allowed).

        Args:
            current_x: Current X position (radius)
            current_z: Current Z position
            x_delta: Proposed X motion (radius)
            z_delta: Proposed Z motion

        Returns:
            (x_delta, z_delta, suppressed) — if suppressed, both deltas are 0.0
        """
        new_x = current_x + x_delta
        new_z = current_z + z_delta
        if new_x < self.x_min or new_x > self.x_max:
            return (0.0, 0.0, True)
        if new_z < self.z_min or new_z > self.z_max:
            return (0.0, 0.0, True)
        return (x_delta, z_delta, False)

    def accumulate_distance(self, x_delta: float, z_delta: float) -> float:
        """Add to cumulative distance along compound angle.

        Distance = sqrt(x_delta² + z_delta²) for each pulse.

        Args:
            x_delta: X component of motion
            z_delta: Z component of motion

        Returns:
            Updated cumulative distance
        """
        dist = math.sqrt(x_delta**2 + z_delta**2)
        self.cumulative_distance += dist
        return self.cumulative_distance

    def reset(self):
        """Reset cumulative distance to zero (called on deactivation)."""
        self.cumulative_distance = 0.0
