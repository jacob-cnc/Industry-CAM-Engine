"""Finish planner for Industry CAM Engine.

Plans the finish pass that traces the exact profile boundary.
The finish pass removes the fin_allowance left by roughing/cleanup.

The finish tool approaches from (X_start, Z_start) and traces the entire
profile contour — including face segments if defined.

IMPORTANT: Only traces the USER'S profile segments — NOT the closure segments.
Closure segments go through the finished part and must never be cut.

Architecture: The finish pass geometry is derived from the Build123d/OCCT
zone boundary (single source of truth). The zone_query extracts exact edge
geometry including arc centers computed by the CAD kernel. This guarantees
the finish pass matches the validator's polygon exactly — no dual computation.

Imports from: models/, geometry/
"""

from typing import List, Optional, TYPE_CHECKING

from models.results import TurningPass
from models.moves import ToolMove, MoveType, PassType
from models.tool import ToolDef
from models.params import FinishingParams
from models.stock import StockDef
from models.profile import ClosedProfile, ProfileMove, SegmentType, MachiningMode

if TYPE_CHECKING:
    from geometry.zone_query import ZoneQueryAPI, EdgeData


class FinishPlanner:
    """Plans the finish pass following the profile boundary exactly.

    The finish pass traces the user's profile segments ONLY (not closure).
    G41/G42 cutter compensation is active — coordinates are programmed to the
    exact profile, LinuxCNC offsets by TNR at runtime.

    Geometry is extracted from the OCCT zone boundary (Build123d is truth).
    """

    def plan(
        self,
        zone_query: 'ZoneQueryAPI',
        tool: ToolDef,
        finishing_params: FinishingParams,
        stock: StockDef,
        mode: MachiningMode,
        profile: ClosedProfile = None,
    ) -> List[TurningPass]:
        """Generate finish pass following the profile segments.

        Extracts the profile boundary edges from the finished part zone
        (OCCT geometry) and emits moves directly from those edges. This
        guarantees the finish pass matches the zone/validator exactly.

        Falls back to coordinate math if zone_query is unavailable.
        """
        if profile is None:
            return []

        segments = profile.segments
        if len(segments) < 2:
            return []

        from models.constants import TOLERANCE
        import math

        if mode == MachiningMode.ID and abs(stock.x_start - segments[0].x) < TOLERANCE:
            approach_z = stock.z_start
        else:
            approach_z = 0.001  # fin_clearance (Z0+fin)

        # Primary path: extract profile edges from OCCT zone boundary
        profile_edges = None
        if zone_query is not None:
            profile_edges = self._extract_profile_edges(zone_query, profile)

        if profile_edges and len(profile_edges) > 0:
            moves = self._moves_from_edges(profile_edges, finishing_params)
        else:
            # Fallback: trace raw segments (no corner breaks in output)
            moves = self._moves_from_segments(segments, finishing_params)

        if not moves:
            return []

        finish_pass = TurningPass(
            x_level=stock.x_start,
            z_start=approach_z,
            z_end=min(m.z for m in moves),
            pass_index=0,
            pass_type=PassType.FINISH,
            moves=moves,
            swept_region=None,
        )

        return [finish_pass]

    def _extract_profile_edges(
        self, zone_query: 'ZoneQueryAPI', profile: ClosedProfile
    ) -> Optional[List['EdgeData']]:
        """Extract the profile portion of the finished part boundary wire.

        The boundary wire contains profile edges + closure edges. OCCT may
        merge adjacent collinear edges, so we can't rely on edge count.
        Instead, we identify the profile portion by finding the path from
        the profile's first point to its last point (excluding closure).

        Strategy: find the edge sequence that connects the first profile
        coord to the last profile coord WITHOUT going through the closure
        region (centerline for OD, stock OD for ID).

        Returns:
            List of EdgeData for the profile portion in cutting order, or None.
        """
        from geometry.zone_builder import _profile_to_radius_coords

        try:
            all_edges = zone_query.boundary_wire_extraction("finished_part")
            if not all_edges:
                return None

            profile_coords = _profile_to_radius_coords(profile)
            if not profile_coords:
                return None

            # Profile start and end in diameter
            first_x_dia = profile_coords[0]["x_radius"] * 2.0
            first_z = profile_coords[0]["z"]
            last_x_dia = profile_coords[-1]["x_radius"] * 2.0
            last_z = profile_coords[-1]["z"]

            n_total = len(all_edges)

            # Find edge whose start matches the last profile coord
            # (the wire goes: ...closure... → last_profile → ...profile... → first_profile → ...closure...)
            # We want the sequence from last_profile_start to first_profile_end
            # then reverse it to get cutting direction (first → last).

            # Find edge starting at last profile coord
            last_start_idx = None
            for i, edge in enumerate(all_edges):
                sx, sz = edge.start
                if abs(sx - last_x_dia) < 0.001 and abs(sz - last_z) < 0.001:
                    last_start_idx = i
                    break

            if last_start_idx is None:
                return None

            # Walk forward from last_start_idx until we reach first_coord
            # These are the profile edges in REVERSE cutting order
            reversed_edges = []
            idx = last_start_idx
            for _ in range(n_total):
                edge = all_edges[idx]
                ex, ez = edge.end
                reversed_edges.append(edge)
                # Check if we've reached the first profile coord
                if abs(ex - first_x_dia) < 0.001 and abs(ez - first_z) < 0.001:
                    break
                idx = (idx + 1) % n_total
            else:
                # Didn't find first coord — extraction failed
                return None

            # Reverse the edges and flip each one to get cutting direction.
            # Mark them as flipped so arc direction can be inverted.
            from geometry.zone_query import EdgeData
            profile_edges = []
            for edge in reversed(reversed_edges):
                flipped = EdgeData(
                    edge_type=edge.edge_type,
                    start=edge.end,
                    end=edge.start,
                    center=edge.center,
                    radius=edge.radius,
                    direction="flipped",  # Signal that arc direction must be inverted
                )
                profile_edges.append(flipped)

            return profile_edges if profile_edges else None
        except Exception:
            return None

    def _moves_from_edges(
        self, edges: List['EdgeData'], finishing_params: FinishingParams
    ) -> List[ToolMove]:
        """Convert OCCT boundary edges to ToolMove objects.

        LINE edges → G01 feed moves
        ARC edges → G02/G03 with exact center from OCCT

        The first move feeds to the first edge's start point.
        """
        import math

        moves = []
        if not edges:
            return moves

        # First move: feed to the start of the first edge
        first_start = edges[0].start
        moves.append(ToolMove(
            move_type=MoveType.FEED,
            x=first_start[0],
            z=first_start[1],
            feed=finishing_params.feed,
            pass_type=PassType.FINISH,
            pass_index=0,
        ))

        prev_x_dia = first_start[0]
        prev_z = first_start[1]

        for edge in edges:
            end_x_dia, end_z = edge.end

            if edge.edge_type == "ARC" and edge.center is not None:
                # Arc move with exact OCCT center
                center_x_dia, center_z = edge.center
                # I/K are incremental from start point (in diameter for I)
                center_i = center_x_dia - prev_x_dia
                center_k = center_z - prev_z

                # Determine G02/G03 from the actual sweep direction.
                # The center is extracted from OCCT (guaranteed correct).
                # Compute sweep from start to end around center:
                #   Negative sweep (CW in math) = G02 (CW in G18)
                #   Positive sweep (CCW in math) = G03 (CCW in G18)
                import math as _math
                sx_r = prev_x_dia / 2.0
                ex_r = end_x_dia / 2.0
                cx_r = center_x_dia / 2.0
                angle_start = _math.atan2(prev_z - center_z, sx_r - cx_r)
                angle_end = _math.atan2(end_z - center_z, ex_r - cx_r)

                # Compute sweep, taking the shorter path (minor arc for fillets)
                sweep = angle_end - angle_start
                if sweep > _math.pi:
                    sweep -= 2 * _math.pi
                elif sweep < -_math.pi:
                    sweep += 2 * _math.pi

                # Negative sweep = CW = G02, Positive sweep = CCW = G03
                is_cw = sweep < 0
                move_type = MoveType.ARC_CW if is_cw else MoveType.ARC_CCW
                signed_r = edge.radius if is_cw else -edge.radius

                moves.append(ToolMove(
                    move_type=move_type,
                    x=end_x_dia,
                    z=end_z,
                    feed=finishing_params.feed,
                    radius=signed_r,
                    center_i=center_i,
                    center_k=center_k,
                    pass_type=PassType.FINISH,
                    pass_index=0,
                ))
            else:
                # Line move
                moves.append(ToolMove(
                    move_type=MoveType.FEED,
                    x=end_x_dia,
                    z=end_z,
                    feed=finishing_params.feed,
                    pass_type=PassType.FINISH,
                    pass_index=0,
                ))

            prev_x_dia = end_x_dia
            prev_z = end_z

        return moves

    def _moves_from_segments(
        self, segments: List[ProfileMove], finishing_params: FinishingParams
    ) -> List[ToolMove]:
        """Fallback: trace raw segments without corner breaks.

        Used when zone_query is unavailable (e.g., testing without Build123d).
        """
        moves = []

        first_seg = segments[0]
        moves.append(ToolMove(
            move_type=MoveType.FEED,
            x=first_seg.x,
            z=first_seg.z,
            feed=finishing_params.feed,
            pass_type=PassType.FINISH,
            pass_index=0,
        ))

        prev_x_dia = segments[0].x
        prev_z = segments[0].z

        for i in range(1, len(segments)):
            seg = segments[i]

            if seg.segment_type == SegmentType.ARC and seg.radius != 0.0:
                is_cw = seg.radius > 0
                center = self._find_arc_center(
                    prev_x_dia / 2.0, prev_z,
                    seg.x / 2.0, seg.z,
                    abs(seg.radius), is_cw,
                )
                if center is not None:
                    center_x_r, center_z = center
                    center_i = (center_x_r - prev_x_dia / 2.0) * 2.0
                    center_k = center_z - prev_z
                else:
                    center_i = 0.0
                    center_k = 0.0

                move_type = MoveType.ARC_CW if is_cw else MoveType.ARC_CCW
                moves.append(ToolMove(
                    move_type=move_type,
                    x=seg.x,
                    z=seg.z,
                    feed=finishing_params.feed,
                    radius=seg.radius,
                    center_i=center_i,
                    center_k=center_k,
                    pass_type=PassType.FINISH,
                    pass_index=0,
                ))
            else:
                moves.append(ToolMove(
                    move_type=MoveType.FEED,
                    x=seg.x,
                    z=seg.z,
                    feed=finishing_params.feed,
                    pass_type=PassType.FINISH,
                    pass_index=0,
                ))

            prev_x_dia = seg.x
            prev_z = seg.z

        return moves

    def _find_arc_center(
        self, x1_r: float, z1: float, x2_r: float, z2: float,
        radius: float, is_cw: bool
    ) -> Optional[tuple]:
        """Find arc center given two endpoints and radius (fallback math)."""
        import math
        from geometry.arc_helpers import is_arc_within_x_bounds

        mx = (x1_r + x2_r) / 2.0
        mz = (z1 + z2) / 2.0
        dx = x2_r - x1_r
        dz = z2 - z1
        d = math.sqrt(dx**2 + dz**2)

        if d < 1e-10:
            return None

        h_sq = radius**2 - (d / 2.0)**2
        if h_sq < 0:
            h_sq = 0
        h = math.sqrt(h_sq)

        px = -dz / d
        pz = dx / d

        c1_x = mx + h * px
        c1_z = mz + h * pz
        c2_x = mx - h * px
        c2_z = mz - h * pz

        ax = x1_r - c1_x
        az = z1 - c1_z
        bx = x2_r - c1_x
        bz = z2 - c1_z
        cr1 = ax * bz - az * bx

        if is_cw:
            cx, cz = (c1_x, c1_z) if cr1 < 0 else (c2_x, c2_z)
            other_cx, other_cz = (c2_x, c2_z) if cr1 < 0 else (c1_x, c1_z)
        else:
            cx, cz = (c1_x, c1_z) if cr1 > 0 else (c2_x, c2_z)
            other_cx, other_cz = (c2_x, c2_z) if cr1 > 0 else (c1_x, c1_z)

        if not is_arc_within_x_bounds(cx, cz, radius, x1_r, z1, x2_r, z2, is_cw):
            if is_arc_within_x_bounds(other_cx, other_cz, radius, x1_r, z1, x2_r, z2, is_cw):
                cx, cz = other_cx, other_cz

        return (cx, cz)
