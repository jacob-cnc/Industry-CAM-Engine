"""Interval class for Industry CAM Engine.

A contiguous region of material along a Fiber, with merge/containment/gap operations.
Modeled after OpenCamLib's Interval class.

Imports from: models/ (constants only)
"""

from dataclasses import dataclass

from models.constants import TOLERANCE


@dataclass
class Interval:
    """A contiguous material region along a Fiber.

    z_start > z_end (z_start is higher/closer to face, z_end is deeper into workpiece).
    """
    z_start: float  # Higher Z (toward face)
    z_end: float    # Lower Z (into workpiece)

    def __post_init__(self):
        if self.z_start < self.z_end:
            # Auto-correct if passed in wrong order
            self.z_start, self.z_end = self.z_end, self.z_start

    @property
    def length(self) -> float:
        """Length of the interval (always positive)."""
        return self.z_start - self.z_end

    def contains(self, other: 'Interval') -> bool:
        """True if other is fully inside self (within TOLERANCE)."""
        return (self.z_start + TOLERANCE >= other.z_start and
                self.z_end - TOLERANCE <= other.z_end)

    def overlaps(self, other: 'Interval') -> bool:
        """True if any overlap exists (within TOLERANCE).

        Two intervals overlap if they share any Z range, or if they're
        separated by less than TOLERANCE (treated as touching).
        """
        return (self.z_start + TOLERANCE >= other.z_end and
                other.z_start + TOLERANCE >= self.z_end)

    def merge(self, other: 'Interval') -> 'Interval':
        """Union of two overlapping intervals.

        Raises ValueError if intervals don't overlap.
        """
        if not self.overlaps(other):
            raise ValueError(
                f"Cannot merge non-overlapping intervals: "
                f"({self.z_start:.5f}, {self.z_end:.5f}) and "
                f"({other.z_start:.5f}, {other.z_end:.5f})"
            )
        return Interval(
            z_start=max(self.z_start, other.z_start),
            z_end=min(self.z_end, other.z_end),
        )

    def gap(self, other: 'Interval') -> float:
        """Distance between non-overlapping intervals.

        Returns 0 if intervals overlap.
        """
        if self.overlaps(other):
            return 0.0
        # Determine which is higher
        if self.z_end > other.z_start:
            return self.z_end - other.z_start
        else:
            return other.z_end - self.z_start

    def __repr__(self) -> str:
        return f"Interval(z_start={self.z_start:.5f}, z_end={self.z_end:.5f})"
