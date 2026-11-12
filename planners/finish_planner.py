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

from typing import List, TYPE_CHECKING

from models.results import TurningPass
from models.moves import ToolMove, MoveType, PassType
from models.tool import ToolDef
from models.params import FinishingParams
from models.stock import StockDef
from models.profile import ClosedProfile, MachiningMode

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
        finish_allowance_dia: float | None = None,
    ) -> List[TurningPass]:
        """Generate finish pass following the profile segments.

        Extracts the profile boundary edges from the finished part zone
        (OCCT geometry) and emits moves directly from those edges. This
        guarantees the finish pass matches the zone/validator exactly.

        Requires zone_query (no coordinate-math fallback since 2026-11-12).
        """
        if profile is None:
            return []

        segments = profile.segments
        if len(segments) < 2:
            return []

        from models.constants import TOLERANCE

        if mode == MachiningMode.ID and abs(stock.x_start - segments[0].x) < TOLERANCE:
            approach_z = stock.z_start
        elif mode == MachiningMode.OD and (stock.x_start < segments[0].x - TOLERANCE
                                           or segments[0].x <= TOLERANCE):
            # The face is being faced (X start inside the first point) or the
            # profile starts at the centre: the lead from X start to the first
            # point IS the face cut - run it exactly at Z0 so the face comes out
            # flat and flows straight into the profile in one motion (owner
            # 2026-11-11). At Z0+.001 it left the face .001 conical and kept the
            # writer's centre entry from engaging, leaving a nib.
            approach_z = 0.0
        else:
            approach_z = 0.001  # fin_clearance (Z0+fin)

        # The finish contour is the kernel's open wire of the profile (corner breaks
        # applied), the same query the intermediate finish cuts use with an allowance.
        # Until 2026-11-12 it was found by walking the CLOSED finished-part outline for
        # the profile's end points, and fell back to hand-math arcs when the walk failed
        # (a profile running along the engine's closure line, e.g. a back shoulder at
        # the operation end). Kernel-only now; a profile the kernel can't build raises.
        if zone_query is None:
            raise ValueError("The finish pass needs the kernel zone query (the pipeline provides it).")
        profile_edges = self._extract_profile_edges(zone_query, profile)
        moves = self._moves_from_edges(profile_edges, finishing_params)

        if not moves:
            return []

        from dataclasses import replace
        if finishing_params.passes > 1 and (zone_query is None or finish_allowance_dia is None):
            raise ValueError("Multiple finish cuts require a kernel query and explicit finish allowance.")
        if finish_allowance_dia is not None:
            FinishingParams.doc_from_allowance(finish_allowance_dia, finishing_params.passes)
        passes = []
        for index in range(finishing_params.passes):
            if index == finishing_params.passes - 1:
                pass_moves = moves
            else:
                remaining = finish_allowance_dia * (finishing_params.passes - index - 1) / finishing_params.passes
                edges = zone_query.profile_offset_edges(profile, remaining)
                pass_moves = self._moves_from_edges(edges, finishing_params)
            pass_moves = [replace(move, pass_index=index) for move in pass_moves]
            if not pass_moves:
                raise RuntimeError("Finish contour has no cutting moves.")
            passes.append(TurningPass(
                x_level=stock.x_start if finishing_params.passes == 1 and not finishing_params.spring_pass else pass_moves[0].x,
                z_start=approach_z if finishing_params.passes == 1 and not finishing_params.spring_pass else max(stock.z_start, pass_moves[0].z),
                z_end=min(move.z for move in pass_moves),
                pass_index=index, pass_type=PassType.FINISH, moves=pass_moves,
            ))
        if finishing_params.spring_pass:
            final = passes[-1]
            passes.append(replace(final, pass_index=finishing_params.passes, is_spring_pass=True,
                moves=[replace(move, pass_index=finishing_params.passes) for move in final.moves]))
        return passes

    def _extract_profile_edges(
        self, zone_query: 'ZoneQueryAPI', profile: ClosedProfile
    ) -> List['EdgeData']:
        """The profile's own edges in cutting order: the kernel's open wire of the
        corner-break-aware profile (ZoneQueryAPI.profile_offset_edges with zero
        allowance). Raises if the kernel can't build it."""
        return zone_query.profile_offset_edges(profile, 0.0)

    def _moves_from_edges(
        self, edges: List['EdgeData'], finishing_params: FinishingParams
    ) -> List[ToolMove]:
        """Convert OCCT boundary edges to ToolMove objects.

        LINE edges → G01 feed moves
        ARC edges → G02/G03 with exact center from OCCT
        anything else → refused (ValueError): profiles are lines and circular arcs

        The first move feeds to the first edge's start point.
        """
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

            if edge.edge_type not in ("LINE", "ARC") or \
                    (edge.edge_type == "ARC" and edge.center is None):
                # Profiles are lines and circular arcs (ellipses retired
                # 2026-11-11), so their outlines and offsets are too. Anything
                # else is an engine fault: refuse rather than cut it as a line
                # or approximate it (the curve-fitting path, unreachable since,
                # was removed 2026-11-12).
                raise ValueError(
                    f"Finish contour: a {edge.edge_type} edge from X{edge.start[0]:.4f} "
                    f"Z{edge.start[1]:.4f} to X{edge.end[0]:.4f} Z{edge.end[1]:.4f} is not a line "
                    "or a circular arc with a centre; it can't be cut. Please report this.")

            if edge.edge_type == "ARC":
                # Arc move with exact OCCT center
                center_x_dia, center_z = edge.center
                # I/K are incremental from start point (in diameter for I)
                center_i = center_x_dia - prev_x_dia
                center_k = center_z - prev_z

                # Direction comes from the kernel (EdgeData.direction, a
                # canonical <= 90 deg piece; geometry/arc_math.py) - never
                # re-guessed from start/end/centre.
                is_cw = edge.direction == "cw"
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
