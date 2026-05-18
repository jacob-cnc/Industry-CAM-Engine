"""Offset-contour roughing planner for Industry CAM Engine.

Profile-following passes at increasing offsets from the roughing boundary.
An alternative to the staircase planner that preserves part geometry in
each pass — arcs remain arcs, lines remain lines.

Algorithm:
1. Start from roughing boundary (profile + fin_allowance + nose_radius offset)
2. Offset outward by DOC increments using zone_query.offset_boundary(distance)
3. Clip each offset contour to stock boundary
4. Each offset contour becomes one TurningPass
5. Passes ordered: outermost first (largest offset), working inward

Status: P1.5 — structurally correct but not yet fully tested through the pipeline.
The offset_boundary() method on ZoneQueryAPI may not yet be implemented.

Imports from: models/, intervals/
"""

from __future__ import annotations

import logging
from typing import List, Tuple, TYPE_CHECKING

from models.results import TurningPass, SweptRegion
from models.moves import ToolMove, MoveType, PassType
from models.tool import ToolDef
from models.params import RoughingParams
from models.stock import StockDef
from models.profile import MachiningMode
from models.constants import TOLERANCE

if TYPE_CHECKING:
    from geometry.zone_query import ZoneQueryAPI, EdgeData

logger = logging.getLogger(__name__)


class OffsetContourPlanner:
    """Profile-following roughing passes at increasing offsets from the roughing boundary.

    Algorithm:
    1. Compute the base roughing boundary (profile + fin_allowance + nose_radius)
    2. Generate offset contours at DOC increments outward from that boundary
    3. Clip each contour to stock limits
    4. Order passes outermost-first (largest offset), working inward toward profile
    5. Preserve geometry type — arcs remain arcs, lines remain lines

    If zone_query.offset_boundary() is unavailable or returns empty, falls back
    to an empty pass list with a logged warning.
    """

    def plan(
        self,
        zone_query: 'ZoneQueryAPI',
        tool: ToolDef,
        params: RoughingParams,
        stock: StockDef,
        mode: MachiningMode,
    ) -> List[TurningPass]:
        """Generate offset-contour roughing passes.

        Args:
            zone_query: ZoneQueryAPI for boundary queries (dependency injection)
            tool: Tool definition (nose_radius used for base offset)
            params: Roughing parameters (DOC, feed, fin_allowance, peck settings)
            stock: Stock definition
            mode: OD or ID

        Returns:
            Ordered list of TurningPass objects (outermost first).
        """
        doc_radius = params.doc_dia / 2.0
        fin_allowance_radius = params.fin_allowance / 2.0
        nose_radius = tool.nose_radius

        # Base offset: fin_allowance (radius) + nose_radius gives the roughing boundary
        base_offset = fin_allowance_radius + nose_radius

        # Determine maximum offset distance from base to stock boundary
        stock_radius = stock.diameter / 2.0
        if mode == MachiningMode.OD:
            max_offset = stock_radius - base_offset
        else:
            # ID: offset inward from pilot hole toward profile
            pilot_radius = stock.pilot_hole_dia / 2.0
            max_offset = base_offset - pilot_radius

        if max_offset <= TOLERANCE:
            logger.warning(
                "OffsetContourPlanner: max_offset (%.6f) <= TOLERANCE, no passes generated.",
                max_offset,
            )
            return []

        # Generate offset distances from DOC up to max_offset
        offset_distances: List[float] = []
        current_offset = doc_radius
        while current_offset < max_offset + TOLERANCE:
            offset_distances.append(min(current_offset, max_offset))
            current_offset += doc_radius

        # Ensure we reach the stock boundary
        if offset_distances and abs(offset_distances[-1] - max_offset) > TOLERANCE:
            offset_distances.append(max_offset)

        # Generate contour passes at each offset distance
        contour_passes: List[Tuple[float, List['EdgeData']]] = []

        for distance in offset_distances:
            edges = self._get_offset_contour(zone_query, distance)
            if edges:
                contour_passes.append((distance, edges))

        if not contour_passes:
            logger.warning(
                "OffsetContourPlanner: No valid offset contours generated. "
                "offset_boundary() may not be implemented yet (P1.5)."
            )
            return []

        # Order: outermost first (largest offset), working inward
        contour_passes.sort(key=lambda x: x[0], reverse=True)

        # Convert contour edges to TurningPass objects
        passes: List[TurningPass] = []
        pass_index = 0

        for i, (distance, edges) in enumerate(contour_passes):
            # Compute inner boundary (next smaller offset, or base boundary)
            if i + 1 < len(contour_passes):
                inner_distance = contour_passes[i + 1][0]
            else:
                inner_distance = 0.0  # Base roughing boundary

            # Build moves from edge data
            moves = self._edges_to_moves(edges, params, pass_index)

            # Handle peck roughing if enabled
            if params.peck_enabled and params.peck_length is not None:
                moves = self._insert_peck_dwells(moves, params.peck_length)

            # Compute swept region with boundary coordinate arrays
            outer_boundary = [(e.start[0], e.start[1]) for e in edges]
            if edges:
                outer_boundary.append((edges[-1].end[0], edges[-1].end[1]))

            # Inner boundary from next-smaller contour (or base)
            inner_edges = self._get_offset_contour(zone_query, inner_distance) if inner_distance > TOLERANCE else []
            if inner_edges:
                inner_boundary = [(e.start[0], e.start[1]) for e in inner_edges]
                inner_boundary.append((inner_edges[-1].end[0], inner_edges[-1].end[1]))
            else:
                inner_boundary = []

            # Bounding box for SweptRegion
            all_x = [pt[0] for pt in outer_boundary] if outer_boundary else [0.0]
            all_z = [pt[1] for pt in outer_boundary] if outer_boundary else [0.0]

            swept = SweptRegion(
                x_min=min(all_x),
                x_max=max(all_x),
                z_start=max(all_z),
                z_end=min(all_z),
                inner_boundary=inner_boundary if inner_boundary else None,
                outer_boundary=outer_boundary if outer_boundary else None,
            )

            # Use midpoint X as the nominal x_level for the pass
            x_level = (swept.x_min + swept.x_max) / 2.0

            turning_pass = TurningPass(
                x_level=x_level,
                z_start=swept.z_start,
                z_end=swept.z_end,
                pass_index=pass_index,
                pass_type=PassType.ROUGH,
                moves=moves,
                swept_region=swept,
            )
            passes.append(turning_pass)
            pass_index += 1

        return passes

    def _get_offset_contour(
        self, zone_query: 'ZoneQueryAPI', distance: float
    ) -> List['EdgeData']:
        """Get offset boundary edges at the given distance from roughing boundary.

        Falls back to empty list if offset_boundary() is not available or raises.

        Args:
            zone_query: ZoneQueryAPI instance
            distance: Offset distance from roughing boundary (radius, inches)

        Returns:
            List of EdgeData describing the offset contour, or empty list on failure.
        """
        try:
            edges = zone_query.offset_boundary(distance)
            if edges:
                return edges
        except AttributeError:
            # offset_boundary() not yet implemented on ZoneQueryAPI
            logger.debug(
                "OffsetContourPlanner: zone_query.offset_boundary() not available."
            )
        except Exception as exc:
            logger.warning(
                "OffsetContourPlanner: offset_boundary(%.4f) raised %s: %s",
                distance, type(exc).__name__, exc,
            )
        return []

    def _edges_to_moves(
        self, edges: List['EdgeData'], params: RoughingParams, pass_index: int
    ) -> List[ToolMove]:
        """Convert EdgeData list to ToolMove list, preserving geometry type.

        Lines become G01 feed moves, arcs become G02/G03 arc moves.

        Args:
            edges: Ordered list of EdgeData from offset_boundary
            params: Roughing parameters (feed rate)
            pass_index: Current pass index for move tagging

        Returns:
            List of ToolMove objects.
        """
        moves: List[ToolMove] = []

        for edge in edges:
            if edge.edge_type == "ARC":
                # Determine arc direction
                if edge.direction == "cw":
                    move_type = MoveType.ARC_CW
                else:
                    move_type = MoveType.ARC_CCW

                # Compute IJK incremental offsets from start to center
                # EdgeData coordinates are in DIAMETER for X
                center_i = edge.center[0] - edge.start[0] if edge.center else 0.0
                center_k = edge.center[1] - edge.start[1] if edge.center else 0.0

                move = ToolMove(
                    move_type=move_type,
                    x=edge.end[0],
                    z=edge.end[1],
                    feed=params.feed,
                    radius=edge.radius,
                    center_i=center_i,
                    center_k=center_k,
                    pass_type=PassType.ROUGH,
                    pass_index=pass_index,
                )
            else:
                # LINE — G01 feed move
                move = ToolMove(
                    move_type=MoveType.FEED,
                    x=edge.end[0],
                    z=edge.end[1],
                    feed=params.feed,
                    pass_type=PassType.ROUGH,
                    pass_index=pass_index,
                )

            moves.append(move)

        return moves

    def _insert_peck_dwells(
        self, moves: List[ToolMove], peck_length: float
    ) -> List[ToolMove]:
        """Insert dwell moves at peck_length intervals along the contour.

        For peck roughing, the tool retracts slightly and re-engages at
        regular intervals to break chips. This inserts a zero-feed dwell
        move (same position) at each peck interval.

        Args:
            moves: Original move list
            peck_length: Distance between peck dwells (inches)

        Returns:
            New move list with dwell moves inserted.
        """
        if not moves or peck_length <= TOLERANCE:
            return moves

        result: List[ToolMove] = []
        accumulated_length = 0.0

        for i, move in enumerate(moves):
            # Estimate segment length from previous endpoint
            if i > 0:
                prev = moves[i - 1]
                dx = (move.x - prev.x) / 2.0  # Convert diameter to radius for distance
                dz = move.z - prev.z
                seg_length = (dx**2 + dz**2) ** 0.5
            else:
                seg_length = 0.0

            accumulated_length += seg_length

            # Insert dwell if we've exceeded peck_length
            if accumulated_length >= peck_length and i > 0:
                # Dwell at current position (zero-feed rapid to same spot)
                dwell = ToolMove(
                    move_type=MoveType.FEED,
                    x=move.x,
                    z=move.z,
                    feed=0.0,  # Dwell — zero feed signals pause
                    pass_type=PassType.ROUGH,
                    pass_index=move.pass_index,
                )
                result.append(dwell)
                accumulated_length = 0.0

            result.append(move)

        return result
