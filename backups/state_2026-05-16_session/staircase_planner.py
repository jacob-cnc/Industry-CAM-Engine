"""Staircase roughing planner for Industry CAM Engine.

Constant-X passes with variable Z boundaries. The proven approach.
Each pass feeds along Z at a fixed X level, with boundaries determined
by intersecting the horizontal pass line against the MTR zone boundary wire.

Algorithm:
  1. Compute X levels from stock boundary toward roughing boundary (by DOC)
  2. At each X level, draw a horizontal line from Z_begin to Z_terminate
  3. Intersect that line against the MTR zone boundary wire (OCCT finds crossings)
  4. Classify segments between crossings as inside/outside the zone (face classifier)
  5. Keep segments inside the MTR zone — those are cutting intervals
  6. Each interval becomes one roughing pass at that X level

OD: Passes step from Stock OD inward (decreasing X) toward roughing boundary
ID: Passes step from Pilot Hole outward (increasing X) toward roughing boundary

OD roughing passes: Z_begin = fin_allowance (face already cleared above)
ID roughing passes: Z_begin = Z_start

Imports from: models/, geometry/contour_intersect
"""

from typing import List, TYPE_CHECKING

from models.results import TurningPass, SweptRegion
from models.moves import ToolMove, MoveType, PassType
from models.tool import ToolDef
from models.params import RoughingParams
from models.stock import StockDef
from models.profile import MachiningMode
from models.constants import TOLERANCE

if TYPE_CHECKING:
    from geometry.zone_query import ZoneQueryAPI
    from geometry.contour_intersect import ContourIntersect


class StaircasePlanner:
    """Constant-X roughing passes with variable Z boundaries.

    Uses ContourIntersect to find Z intervals by intersecting a horizontal
    line at each X level against the MTR zone boundary wire, then classifying
    which segments are inside the zone (material to cut).
    """

    def plan(
        self,
        zone_query: 'ZoneQueryAPI',
        tool: ToolDef,
        params: RoughingParams,
        stock: StockDef,
        mode: MachiningMode,
        contour_intersect: 'ContourIntersect' = None,
    ) -> List[TurningPass]:
        """Generate staircase roughing passes.

        Args:
            zone_query: ZoneQueryAPI for boundary queries (dependency injection)
            tool: Tool definition
            params: Roughing parameters (DOC, feed, fin_allowance)
            stock: Stock definition
            mode: OD or ID
            contour_intersect: ContourIntersect instance for wire-based interval finding.
                               If None, falls back to Fiber (legacy behavior).

        Returns:
            Ordered list of TurningPass objects.
        """
        doc_dia = params.doc_dia
        fin_allowance_radius = params.fin_allowance / 2.0

        # Determine Z_begin for roughing passes
        if mode == MachiningMode.OD:
            # OD: face already cleared, Z_begin = fin_allowance
            z_begin = fin_allowance_radius
        else:
            # ID: Z_begin = Z_start
            z_begin = stock.z_start

        # Compute X levels
        x_levels_dia = self._compute_x_levels(stock, params, mode)

        # Generate passes at each X level
        passes = []
        pass_index = 0
        prev_x_dia = self._get_stock_x_dia(stock, mode)

        for x_dia in x_levels_dia:
            # Get material intervals at this X level
            intervals = self._get_intervals(
                x_dia, zone_query, contour_intersect
            )

            # Each interval becomes one pass
            for (interval_z_begin, interval_z_terminate) in intervals:
                # Clip interval Z_begin to our pass Z_begin
                # (don't cut above face-cleared level)
                clipped_z_begin = min(interval_z_begin, z_begin)
                z_terminate = interval_z_terminate

                # Skip if no material to cut at this level
                if clipped_z_begin - z_terminate < TOLERANCE:
                    continue

                # Create the feed move (along Z at constant X)
                move = ToolMove(
                    move_type=MoveType.FEED,
                    x=x_dia,
                    z=z_terminate,
                    feed=params.feed,
                    pass_type=PassType.ROUGH,
                    pass_index=pass_index,
                )

                # Swept region
                swept = SweptRegion(
                    x_min=min(x_dia, prev_x_dia),
                    x_max=max(x_dia, prev_x_dia),
                    z_start=clipped_z_begin,
                    z_end=z_terminate,
                )

                turning_pass = TurningPass(
                    x_level=x_dia,
                    z_start=clipped_z_begin,
                    z_end=z_terminate,
                    pass_index=pass_index,
                    pass_type=PassType.ROUGH,
                    moves=[move],
                    swept_region=swept,
                )
                passes.append(turning_pass)
                pass_index += 1

            prev_x_dia = x_dia

        return passes

    def _get_intervals(
        self,
        x_dia: float,
        zone_query: 'ZoneQueryAPI',
        contour_intersect: 'ContourIntersect',
    ) -> List[tuple]:
        """Get material intervals at an X level.

        Uses ContourIntersect (wire intersection + face classification) when available.
        Falls back to Fiber (legacy BRepAlgoAPI_Section against face) if not provided.

        Returns list of (z_begin, z_terminate) tuples sorted Z descending.
        """
        if contour_intersect is not None:
            return contour_intersect.intervals_at_x(x_dia, "material_to_rough")
        else:
            # Legacy fallback via Fiber
            from intervals.fiber import Fiber
            fiber = Fiber(x_dia, zone_query, "material_to_rough")
            return [(iv.z_start, iv.z_end) for iv in fiber.intervals]

    def _compute_x_levels(self, stock: StockDef, params: RoughingParams, mode: MachiningMode) -> List[float]:
        """Compute X diameter levels for roughing passes.

        OD: Stock OD → decreasing by DOC toward profile
        ID: Pilot hole → increasing by DOC toward profile
        """
        doc_dia = params.doc_dia

        if mode == MachiningMode.OD:
            # Start from stock OD, step inward
            x_start = stock.diameter
            x_levels = []
            x_current = x_start - doc_dia
            # Stop when we've passed the smallest profile X (we don't know exact boundary
            # without querying, so we step until we reach near-zero or a reasonable limit)
            while x_current > TOLERANCE:
                x_levels.append(x_current)
                x_current -= doc_dia
            return x_levels
        else:
            # ID: Start from pilot hole, step outward
            x_start = stock.pilot_hole_dia
            x_levels = []
            x_current = x_start + doc_dia
            # Stop at stock OD (can't bore beyond stock)
            while x_current < stock.diameter - TOLERANCE:
                x_levels.append(x_current)
                x_current += doc_dia
            return x_levels

    def _get_stock_x_dia(self, stock: StockDef, mode: MachiningMode) -> float:
        """Get the starting X diameter (stock boundary)."""
        if mode == MachiningMode.OD:
            return stock.diameter
        else:
            return stock.pilot_hole_dia
