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
from geometry.kernel import circumcenter, curve_arc_spans

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
        CURVE edges → decomposed into G02/G03 arc sequences via chord-error subdivision

        The first move feeds to the first edge's start point.
        """
        from models.constants import QUADRANT_CHORD_ERROR

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

            if edge.edge_type == "CURVE" and edge.ocp_edge is not None:
                # Decompose non-circular edge into circular arc segments
                arc_moves = self._decompose_curve_edge(
                    edge, prev_x_dia, prev_z, finishing_params, QUADRANT_CHORD_ERROR
                )
                moves.extend(arc_moves)
                # Update prev position to the edge endpoint (guaranteed by decomposition)
                prev_x_dia = end_x_dia
                prev_z = end_z

            elif edge.edge_type == "ARC" and edge.center is not None:
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

    def _decompose_curve_edge(
        self, edge: 'EdgeData', prev_x_dia: float, prev_z: float,
        finishing_params: FinishingParams, chord_error: float
    ) -> List[ToolMove]:
        """Decompose a non-circular OCCT edge into circular arc segments.

        Uses adaptive parametric sampling with chord-error-based subdivision.
        For each sub-span, fits a circular arc through three points (start, mid, end)
        and checks that the maximum deviation from the true curve is within tolerance.
        If not, the span is subdivided recursively.

        Guarantees:
        - Endpoint continuity: each sub-arc starts exactly where the previous ended
        - Final endpoint matches edge.end exactly (no drift)
        - All sub-arcs respect chord_error tolerance

        Args:
            edge: EdgeData with ocp_edge set (non-circular curve)
            prev_x_dia: Current X position (diameter)
            prev_z: Current Z position
            finishing_params: Feed rate and pass info
            chord_error: Maximum allowable deviation (inches)

        Returns:
            List of ToolMove objects (G2/G3 arcs) approximating the curve.
        """
        import math

        moves = []
        # Arc pieces on the curve in cutting order, first/last snapped to the
        # edge's ends (kernel: geometry/curve_fit.curve_arc_spans).
        spans = curve_arc_spans(edge.ocp_edge, edge.start, edge.end, chord_error)

        # Convert each span into a circular arc ToolMove
        # Track the running start point for incremental I/K calculation
        running_x_dia = prev_x_dia
        running_z = prev_z

        for i, ((ax_dia, az), (mx_dia, mz), (bx_dia, bz)) in enumerate(spans):
            # Fit circular arc through three points (circumcenter in radius space)
            ax_r = ax_dia / 2.0
            mx_r = mx_dia / 2.0
            bx_r = bx_dia / 2.0

            center = circumcenter(ax_r, az, mx_r, mz, bx_r, bz)

            if center is None:
                # Degenerate (collinear) — emit as line move
                moves.append(ToolMove(
                    move_type=MoveType.FEED,
                    x=bx_dia,
                    z=bz,
                    feed=finishing_params.feed,
                    pass_type=PassType.FINISH,
                    pass_index=0,
                ))
            else:
                cx_r, cz = center
                cx_dia = cx_r * 2.0
                radius = math.sqrt((ax_r - cx_r) ** 2 + (az - cz) ** 2)

                # I/K incremental from the arc start point (in diameter for I)
                center_i = cx_dia - running_x_dia
                center_k = cz - running_z

                # Determine arc direction (CW/CCW) using cross product
                # Cross product of (start→mid) × (start→end)
                dx1 = mx_r - ax_r
                dz1 = mz - az
                dx2 = bx_r - ax_r
                dz2 = bz - az
                cross = dx1 * dz2 - dz1 * dx2

                # Negative cross = CW (G02), Positive cross = CCW (G03)
                is_cw = cross < 0
                move_type = MoveType.ARC_CW if is_cw else MoveType.ARC_CCW
                signed_r = radius if is_cw else -radius

                moves.append(ToolMove(
                    move_type=move_type,
                    x=bx_dia,
                    z=bz,
                    feed=finishing_params.feed,
                    radius=signed_r,
                    center_i=center_i,
                    center_k=center_k,
                    pass_type=PassType.FINISH,
                    pass_index=0,
                ))

            running_x_dia = bx_dia
            running_z = bz

        return moves

