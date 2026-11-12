"""Cleanup planner for Industry CAM Engine.

Plans the cleanup pass (semi-finish) that traces the profile contour offset
by fin_allowance. This is the roughing boundary — the same shape as the profile
but shifted outward by the finish allowance amount.

The cleanup contour is computed by offsetting the user's profile segments using
Build123d's offset operation (same kernel used for zone construction). This
guarantees the cleanup pass matches the roughing boundary exactly.

Only used with staircase strategy — offset-contour's last pass IS the cleanup.

Imports from: models/, geometry/ (for offset computation)
"""

from typing import List, TYPE_CHECKING

from models.results import TurningPass
from models.moves import ToolMove, MoveType, PassType
from models.tool import ToolDef
from models.params import RoughingParams
from models.stock import StockDef
from models.profile import ClosedProfile, MachiningMode
from models.constants import TOLERANCE

if TYPE_CHECKING:
    from geometry.zone_query import ZoneQueryAPI, EdgeData


class CleanupPlanner:
    """Plans the cleanup pass following the profile contour offset by fin_allowance.

    The cleanup pass traces the profile shape shifted outward by fin_allowance.
    For OD mode: X increases, arc radii increase (same center, larger radius).
    The offset is computed by Build123d's geometry kernel — no hand math.
    """

    def plan(
        self,
        zone_query: 'ZoneQueryAPI',
        tool: ToolDef,
        params: RoughingParams,
        stock: StockDef,
        mode: MachiningMode,
        profile: ClosedProfile = None,
    ) -> List[TurningPass]:
        """Generate cleanup at the finish-allowance boundary.

        OD and ID both use the kernel's open profile offset
        (ZoneQueryAPI.profile_offset_edges) with wire clipping, preserving
        authored shoulders. (The old OD face-offset route had no callers and was
        removed 2026-11-12.)

        Cleanup pass = Finished Part offset equidistant by fin_allowance,
        clipped at Z0+fin, Z_end, X_start+fin.

        Approach sequence:
          1. [Rapid to X_start+fin, Z0+fin — handled by G-code writer]
          2. Feed along face at Z0+fin from X_start+fin to offset profile X
          3. Continue along clipped offset wire to Z_end

        Args:
            zone_query: ZoneQueryAPI instance
            tool: Tool definition
            params: Roughing parameters (for feed rate, fin_allowance)
            stock: Stock definition
            mode: OD or ID
            profile: The user's ClosedProfile

        Returns:
            List containing one TurningPass (the cleanup contour pass).
        """
        if profile is None:
            return []

        segments = profile.segments
        if len(segments) < 2:
            return []

        fin_allowance_radius = params.fin_allowance / 2.0
        fin_allowance_dia = params.fin_allowance

        # Z start for cleanup pass:
        # OD: Z0 + fin (face passes cleared above this)
        # ID with no TFZ (X_start = first segment X): Z_start (no face passes)
        # ID with TFZ (X_start > first segment X): Z0 + fin
        if mode == MachiningMode.ID and abs(stock.x_start - segments[0].x) < TOLERANCE:
            z0_fin = stock.z_start
        else:
            z0_fin = fin_allowance_radius

        if mode == MachiningMode.OD:
            # OD: X_start + fin (diameter) — approach from centerline outward
            x_start_fin_dia = stock.x_start + fin_allowance_dia
        else:
            # ID: approach from pilot hole outward
            x_start_fin_dia = stock.pilot_hole_dia

        # OD and ID both offset the actual open contour with the shared kernel
        # query and clip it at the operation depth + allowance. (Until
        # 2026-11-09 OD used a face-offset route that put the cleanup inside the
        # finished part at an outward step to the stock OD — an OD profile
        # ending mid-bar, e.g. a turned stub with its step face drawn.)
        # Artificial stock closures must not replace or erase real shoulders.
        edges = zone_query.profile_offset_edges(
            profile, params.fin_allowance, z_min=stock.z_end + fin_allowance_radius)
        if not edges:
            raise RuntimeError(f"{mode.name} cleanup produced no contour for the requested profile.")
        if any(edge.edge_type not in ("LINE", "ARC") for edge in edges):
            raise RuntimeError(f"{mode.name} cleanup currently supports line and circular-arc contours only.")
        offset_edges = [(edge.start, edge.end, edge.edge_type, edge.center, edge.radius,
                         edge.direction) for edge in edges]

        if not offset_edges:
            return []

        # The offset edges from the kernel are the turning portion of the offset wire
        # (clipped at Z0+fin or Z=0, Z_end). They start at the first turning edge.
        # Build the approach sequence to reach the first edge's start point.

        first_edge_start = offset_edges[0][0]
        offset_x_dia = first_edge_start[0]
        offset_start_z = first_edge_start[1]

        moves = []

        # OD contour whose first cut starts below the face-allowance level (the
        # offset of a chamfer or rounded edge at the face): don't step straight
        # down to it - that .0007-.0029 step before the turn is an inside corner
        # LinuxCNC's comp can't make, so the program was refused. Run the first
        # cut back along its own direction up to the face level instead: along
        # the face, then straight down the chamfer in one motion, like the finish
        # (owner 2026-11-11: no burr at the face/chamfer transition).
        ext = self._face_level_extension(offset_edges[0], z0_fin, x_start_fin_dia) \
            if mode == MachiningMode.OD and offset_start_z < z0_fin - TOLERANCE else None
        if ext is not None:
            if ext[0] - x_start_fin_dia > TOLERANCE:
                moves.append(ToolMove(move_type=MoveType.FEED, x=ext[0], z=z0_fin,
                                      feed=params.feed, pass_type=PassType.CLEANUP, pass_index=0))
            moves.append(ToolMove(move_type=MoveType.FEED, x=offset_x_dia, z=offset_start_z,
                                  feed=params.feed, pass_type=PassType.CLEANUP, pass_index=0))
            moves.extend(self._build_moves_from_offset(offset_edges, params))
            return [TurningPass(
                x_level=x_start_fin_dia, z_start=z0_fin, z_end=min(m.z for m in moves),
                pass_index=0, pass_type=PassType.CLEANUP, moves=moves, swept_region=None)]

        # Approach: feed from (X_start+fin, z0_fin) to the first offset edge start.
        # This may be a face-level feed (if first edge starts at Z≈0) or a
        # two-step approach (feed along face, then down to edge start Z).
        if abs(offset_start_z - z0_fin) < TOLERANCE:
            # First edge starts at face level — single feed along face to it
            if offset_x_dia - x_start_fin_dia > TOLERANCE:
                moves.append(ToolMove(
                    move_type=MoveType.FEED,
                    x=offset_x_dia,
                    z=z0_fin,
                    feed=params.feed,
                    pass_type=PassType.CLEANUP,
                    pass_index=0,
                ))
        else:
            # First edge starts below face level — feed along face to X, then down
            if offset_x_dia - x_start_fin_dia > TOLERANCE:
                moves.append(ToolMove(
                    move_type=MoveType.FEED,
                    x=offset_x_dia,
                    z=z0_fin,
                    feed=params.feed,
                    pass_type=PassType.CLEANUP,
                    pass_index=0,
                ))
            if abs(offset_start_z - z0_fin) > TOLERANCE:
                moves.append(ToolMove(
                    move_type=MoveType.FEED,
                    x=offset_x_dia,
                    z=offset_start_z,
                    feed=params.feed,
                    pass_type=PassType.CLEANUP,
                    pass_index=0,
                ))

        # Moves 3+: The offset wire edges
        wire_moves = self._build_moves_from_offset(offset_edges, params)
        moves.extend(wire_moves)

        if not moves:
            return []

        cleanup_pass = TurningPass(
            x_level=x_start_fin_dia,
            z_start=z0_fin,
            z_end=min(m.z for m in moves),
            pass_index=0,
            pass_type=PassType.CLEANUP,
            moves=moves,
            swept_region=None,
        )

        return [cleanup_pass]

        if not moves:
            return []

        cleanup_pass = TurningPass(
            x_level=x_start_fin_dia,
            z_start=stock.z_start,
            z_end=min(m.z for m in moves),
            pass_index=0,
            pass_type=PassType.CLEANUP,
            moves=moves,
            swept_region=None,
        )

        return [cleanup_pass]

    @staticmethod
    def _face_level_extension(edge, z_face, x_min_dia):
        """(X dia, Z) where the first cut, run backward along its start direction,
        reaches the face level z_face - or None if it doesn't rise to it at a
        sensible slope (>= 15 deg) or would pass inside x_min_dia."""
        import math
        start, end, edge_type, center, radius = edge[:5]
        direction = edge[5] if len(edge) > 5 else None
        s0 = (start[0] / 2.0, start[1])
        if edge_type == "LINE":
            t = (end[0] / 2.0 - s0[0], end[1] - s0[1])
        elif edge_type == "ARC" and direction in ("cw", "ccw") and center is not None:
            rv = (s0[0] - center[0] / 2.0, s0[1] - center[1])
            t = (rv[1], -rv[0]) if direction == "cw" else (-rv[1], rv[0])
        else:
            return None
        L = math.hypot(*t)
        if L < 1e-12:
            return None
        u = (t[0] / L, t[1] / L)
        if u[1] > -0.2588:                       # must fall toward the chuck, >= 15 deg
            return None
        s = (z_face - s0[1]) / (-u[1])
        p = (s0[0] - u[0] * s, z_face)
        if 2.0 * p[0] < x_min_dia - 1e-9:
            return None
        return (2.0 * p[0], z_face)

    def _build_moves_from_offset(
        self,
        offset_edges: List[tuple],
        params: RoughingParams,
    ) -> List[ToolMove]:
        """Convert offset edge tuples into ToolMove objects.

        LINE edges -> MoveType.FEED
        ARC edges  -> MoveType.ARC_CW or ARC_CCW (determined by cross product of start→end vs start→center)
        """
        moves = []

        for i, edge in enumerate(offset_edges):
            start, end, edge_type, center, radius = edge[:5]
            direction = edge[5] if len(edge) > 5 else None

            if edge_type == "LINE":
                moves.append(ToolMove(
                    move_type=MoveType.FEED,
                    x=end[0],
                    z=end[1],
                    feed=params.feed,
                    pass_type=PassType.CLEANUP,
                    pass_index=0,
                ))

            elif edge_type == "ARC":
                # Direction from the kernel (EdgeData.direction on a canonical
                # <= 90 deg piece, geometry/arc_math.py). Was: shortest sweep,
                # which reversed the 186 deg offset of a concave 180 deg arc.
                if direction in ("cw", "ccw"):
                    sweep = -1.0 if direction == "cw" else 1.0
                else:                                   # legacy 5-tuple callers
                    from geometry.kernel import short_sweep
                    sweep = short_sweep((start[0] / 2.0, start[1]), (end[0] / 2.0, end[1]),
                                        (center[0] / 2.0, center[1]))

                if sweep < 0:
                    move_type = MoveType.ARC_CW
                    radius_signed = radius
                else:
                    move_type = MoveType.ARC_CCW
                    radius_signed = -radius

                # Incremental offsets from start to center (diameter for X, inches for Z)
                center_i = center[0] - start[0]
                center_k = center[1] - start[1]

                moves.append(ToolMove(
                    move_type=move_type,
                    x=end[0],
                    z=end[1],
                    feed=params.feed,
                    radius=radius_signed,
                    center_i=center_i,
                    center_k=center_k,
                    pass_type=PassType.CLEANUP,
                    pass_index=0,
                ))

        return moves

    def _filter_turning_edges(
        self,
        edges: List['EdgeData'],
        stock: StockDef,
        mode: MachiningMode,
    ) -> List['EdgeData']:
        """Filter out non-cutting boundary segments, keeping only the turning portion.

        For OD: removes edges at stock OD, centerline, and Z_end
        For ID: removes edges at pilot hole, Z=0 (top), and Z_end boundary
        """
        tol = 1e-4
        pilot_hole_dia = stock.pilot_hole_dia
        stock_dia = stock.diameter
        z_end_val = stock.z_end
        fin_r = 0.001  # fin_allowance_radius approximation for boundary matching

        turning = []
        for edge in edges:
            sx, sz = edge.start
            ex, ez = edge.end

            if mode == MachiningMode.ID:
                # ID: skip edges at pilot hole boundary (safe zone side)
                if abs(sx - pilot_hole_dia) < tol and abs(ex - pilot_hole_dia) < tol:
                    continue
                # ID: skip horizontal edges at Z=0 or Z=fin_allowance (top of MTR zone)
                if abs(sz) < tol and abs(ez) < tol:
                    continue
                if abs(sz - fin_r) < tol and abs(ez - fin_r) < tol:
                    continue
                # ID: skip horizontal edges at Z_end boundary (bottom)
                if abs(sz - z_end_val) < tol and abs(ez - z_end_val) < tol:
                    continue
                if abs(sz - (z_end_val + fin_r)) < tol and abs(ez - (z_end_val + fin_r)) < tol:
                    continue
            else:
                # OD: skip edges at stock OD
                if abs(sx - stock_dia) < tol and abs(ex - stock_dia) < tol:
                    continue
                # OD: skip edges at centerline
                if abs(sx) < tol and abs(ex) < tol:
                    continue
                # OD: skip edges at Z_end
                if abs(sz - z_end_val) < tol and abs(ez - z_end_val) < tol:
                    continue

            turning.append(edge)

        return turning

    def _build_moves_from_edge_data(
        self,
        turning_edges: List['EdgeData'],
        params: RoughingParams,
    ) -> List[ToolMove]:
        """Convert EdgeData sequence into ToolMove objects (fallback path)."""
        moves = []

        for edge in turning_edges:
            if edge.edge_type == "LINE":
                moves.append(ToolMove(
                    move_type=MoveType.FEED,
                    x=edge.end[0],
                    z=edge.end[1],
                    feed=params.feed,
                    pass_type=PassType.CLEANUP,
                    pass_index=0,
                ))
            elif edge.edge_type == "ARC":
                if edge.direction == "cw":
                    move_type = MoveType.ARC_CW
                    radius_signed = edge.radius
                else:
                    move_type = MoveType.ARC_CCW
                    radius_signed = -edge.radius

                center_i = edge.center[0] - edge.start[0]
                center_k = edge.center[1] - edge.start[1]

                moves.append(ToolMove(
                    move_type=move_type,
                    x=edge.end[0],
                    z=edge.end[1],
                    feed=params.feed,
                    radius=radius_signed,
                    center_i=center_i,
                    center_k=center_k,
                    pass_type=PassType.CLEANUP,
                    pass_index=0,
                ))

        return moves
