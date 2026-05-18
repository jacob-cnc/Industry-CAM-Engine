"""Fiber class for Industry CAM Engine.

A query line at a fixed X level (diameter) that collects Intervals.
Modeled after OpenCamLib's Fiber class.

Imports from: models/, geometry/ (ZoneQueryAPI received as parameter)
"""

from typing import List, TYPE_CHECKING

from models.constants import TOLERANCE
from intervals.interval import Interval

if TYPE_CHECKING:
    from geometry.zone_query import ZoneQueryAPI


class Fiber:
    """A query line at a fixed X level (diameter) that collects Intervals.

    The Fiber queries ZoneQueryAPI.boundary_at_x() to obtain its intervals.
    It never computes intervals manually — all material boundaries come from
    the geometry kernel.

    Usage:
        fiber = Fiber(x_dia=1.0, zone_query=query_api)
        for interval in fiber.intervals:
            print(f"Material from Z={interval.z_start} to Z={interval.z_end}")
    """

    def __init__(self, x_dia: float, zone_query: 'ZoneQueryAPI', zone_name: str = "material_to_rough"):
        """Create a Fiber at the given X diameter level.

        Args:
            x_dia: X position in DIAMETER
            zone_query: ZoneQueryAPI instance (dependency injection — not imported)
            zone_name: Which zone to query for material boundaries
        """
        self._x_dia = x_dia
        self._intervals: List[Interval] = []
        self._query(zone_query, zone_name)

    @property
    def x_dia(self) -> float:
        """The X diameter level of this fiber."""
        return self._x_dia

    @property
    def intervals(self) -> List[Interval]:
        """Sorted list of non-overlapping Intervals (z_start descending)."""
        return sorted(self._intervals, key=lambda i: -i.z_start)

    def add_interval(self, interval: Interval) -> None:
        """Add interval with automatic merge of overlapping intervals.

        Uses TOLERANCE = 0.0005" for merge decisions. If the new interval
        overlaps with any existing interval(s), they are all merged into one.
        """
        merged = interval
        remaining = []
        for existing in self._intervals:
            if merged.overlaps(existing):
                merged = merged.merge(existing)
            else:
                remaining.append(existing)
        remaining.append(merged)
        self._intervals = remaining

    def material_at(self, z: float) -> bool:
        """Point-in-material test at this fiber's X level.

        Returns True if Z position is within any interval (within TOLERANCE).
        """
        for interval in self._intervals:
            if interval.z_start + TOLERANCE >= z >= interval.z_end - TOLERANCE:
                return True
        return False

    @property
    def total_material_length(self) -> float:
        """Sum of all interval lengths."""
        return sum(i.length for i in self._intervals)

    @property
    def interval_count(self) -> int:
        """Number of distinct material intervals at this X level."""
        return len(self._intervals)

    def _query(self, zone_query: 'ZoneQueryAPI', zone_name: str) -> None:
        """Obtain intervals from ZoneQueryAPI.boundary_at_x() — never manual computation."""
        boundaries = zone_query.boundary_at_x(self._x_dia, zone_name)
        for z_start, z_end in boundaries:
            self.add_interval(Interval(z_start, z_end))

    def __repr__(self) -> str:
        return f"Fiber(x_dia={self._x_dia:.4f}, intervals={len(self._intervals)})"
