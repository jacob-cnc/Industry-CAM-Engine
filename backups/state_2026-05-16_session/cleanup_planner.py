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

from typing import List, Tuple, TYPE_CHECKING

from models.results import TurningPass
from models.moves import ToolMove, MoveType, PassType
from models.tool import ToolDef
from models.params import RoughingParams
from models.stock import StockDef
from models.profile import ClosedProfile, ProfileMove, SegmentType, MachiningMode
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
        """Generate cleanup pass: offset finished part by fin_allowance, clip to turning region.

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

        # X_start + fin (diameter)
        x_start_fin_dia = stock.x_start + fin_allowance_dia
        # Z0 + fin
        z0_fin = fin_allowance_radius

        # Compute the offset profile using the geometry kernel
        offset_edges = self._compute_offset_profile(segments, fin_allowance_radius, mode)
        if not offset_edges:
            # Fallback: use zone boundary wire extraction
            return self._plan_from_zone_boundary(zone_query, params, stock, mode)

        # The offset edges from the kernel are the turning portion of the offset wire
        # (clipped at Z0+fin, Z_end). They start at the first turning edge after the clip.
        # We need to build the full move sequence:
        #   1. Feed along face at Z0+fin from X_start+fin to the offset profile X
        #   2. Feed straight down from Z0+fin to the first offset edge start Z (if gap exists)
        #   3. Then the offset edges (arc + straight segments)

        # Determine the offset profile X (the X value of the turning edges)
        # All turning edges should be at the same X for this profile type
        first_edge_start = offset_edges[0][0]
        offset_x_dia = first_edge_start[0]
        offset_start_z = first_edge_start[1]

        moves = []

        # Move 1: Feed along face at Z0+fin from X_start+fin to offset X
        if offset_x_dia - x_start_fin_dia > TOLERANCE:
            moves.append(ToolMove(
                move_type=MoveType.FEED,
                x=offset_x_dia,
                z=z0_fin,
                feed=params.feed,
                pass_type=PassType.CLEANUP,
                pass_index=0,
            ))

        # Move 2: If the first offset edge doesn't start at Z0+fin, feed down to it
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

    def _compute_offset_profile(
        self,
        segments: List[ProfileMove],
        fin_allowance_radius: float,
        mode: MachiningMode,
    ) -> List[tuple]:
        """Compute the cleanup contour by offsetting the finished part face.

        Process:
          1. Build the finished part face from profile segments (same as zone_builder)
          2. Offset it outward by fin_allowance using Build123d (kernel operation)
          3. Extract the boundary wire of the offset result
          4. Filter to turning edges only (clip at Z0+fin, Z_end, X_start+fin)

        Returns list of edge tuples:
          LINE: ((start_x_dia, start_z), (end_x_dia, end_z), "LINE", None, 0.0)
          ARC:  ((start_x_dia, start_z), (end_x_dia, end_z), "ARC", (center_x_dia, center_z), radius)

        Returns empty list if offset fails (triggers fallback to zone boundary).
        """
        from build123d import (
            BuildSketch, BuildLine, Line, RadiusArc, make_face,
            offset as b3d_offset, Kind,
        )
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopAbs import TopAbs_EDGE, TopAbs_WIRE, TopAbs_FACE
        from OCP.TopoDS import TopoDS
        from OCP.BRepAdaptor import BRepAdaptor_Curve
        from OCP.GeomAbs import GeomAbs_Line, GeomAbs_Circle
        from OCP.BRepTools import BRepTools

        if len(segments) < 2:
            return []

        # Step 1: Build the finished part face (same logic as zone_builder)
        try:
            from geometry.zone_builder import _profile_to_radius_coords, _build_face_from_coords
            from models.stock import StockDef
            from models.profile import ClosedProfile

            # We need the full closed profile to build the face
            # Reconstruct it from segments + closure
            # Actually, we can use zone_query to get the finished part wire directly
            # But we need the offset of it. Let's build the face from scratch.
            pass
        except Exception:
            pass

        # Build closed profile contour (profile + closure to centerline)
        try:
            coords = []
            for seg in segments:
                coords.append({
                    "type": seg.segment_type,
                    "x_radius": seg.x / 2.0,
                    "z": seg.z,
                    "radius": seg.radius,
                })

            # Add closure segments (to centerline for OD, to stock OD for ID)
            last_seg = segments[-1]
            first_seg = segments[0]

            if mode == MachiningMode.OD:
                closure_x = 0.0
            else:
                # ID closure would go to stock OD — but we don't have stock here
                # Fall back to zone boundary method for ID mode
                return []

            # Closure: last point → (closure_x, last_z) → (closure_x, 0) → first point
            last_x_r = last_seg.x / 2.0
            last_z = last_seg.z
            first_x_r = first_seg.x / 2.0
            first_z = first_seg.z

            if abs(last_x_r - closure_x) > 1e-10:
                coords.append({"type": SegmentType.LINE, "x_radius": closure_x, "z": last_z, "radius": 0.0})
            coords.append({"type": SegmentType.LINE, "x_radius": closure_x, "z": 0.0, "radius": 0.0})
            if abs(closure_x - first_x_r) > 1e-10 or abs(0.0 - first_z) > 1e-10:
                coords.append({"type": SegmentType.LINE, "x_radius": first_x_r, "z": first_z, "radius": 0.0})

            # Build face
            with BuildSketch() as sketch:
                with BuildLine():
                    for i in range(len(coords)):
                        next_i = (i + 1) % len(coords)
                        current = coords[i]
                        target = coords[next_i]

                        cx, cz = current["x_radius"], current["z"]
                        tx, tz = target["x_radius"], target["z"]

                        if abs(cx - tx) < 1e-10 and abs(cz - tz) < 1e-10:
                            continue

                        if target["type"] == SegmentType.ARC and target["radius"] != 0.0:
                            b3d_radius = -target["radius"]
                            RadiusArc((cx, cz), (tx, tz), b3d_radius)
                        else:
                            Line((cx, cz), (tx, tz))
                make_face()

            finished_part_face = sketch.sketch
        except Exception:
            return []

        # Step 2: Offset the finished part face outward by fin_allowance
        try:
            if mode == MachiningMode.OD:
                offset_amount = fin_allowance_radius
            else:
                offset_amount = -fin_allowance_radius

            offset_face = b3d_offset(finished_part_face, amount=offset_amount, kind=Kind.INTERSECTION)
        except Exception:
            return []

        # Step 3: Extract boundary wire from the offset face
        try:
            # Get the OCP face from the offset result
            offset_faces = offset_face.faces() if hasattr(offset_face, 'faces') else []
            if not offset_faces:
                return []

            ocp_face = offset_faces[0].wrapped
            outer_wire = BRepTools.OuterWire_s(ocp_face)
        except Exception:
            return []

        # Step 4: Clip the offset wire to the turning region
        # Clip bounds: X > x_start+fin, Z from Z0+fin to Z_end
        # Build a clipping face and intersect with the offset face to get only the turning portion
        try:
            from build123d import BuildSketch, BuildLine, Line, make_face
            from OCP.BRepAlgoAPI import BRepAlgoAPI_Common

            # Clip region: rectangle from (x_start_r + fin, z0+fin) to (large_x, z_end)
            # x_start is the profile start X (in radius). For OD, x_start = first segment X / 2
            # Since x_start+fin > 0 always, and we want X > 0, use a small positive X min
            x_min_r = fin_allowance_radius  # x_start(0) + fin_allowance in radius
            x_max_r = 10.0  # Well beyond any stock
            z_top = fin_allowance_radius  # Z0 + fin (in radius = fin_allowance_radius)
            z_bot = segments[-1].z  # Z_end (most negative Z from profile)

            with BuildSketch() as clip_sketch:
                with BuildLine():
                    Line((x_min_r, z_top), (x_max_r, z_top))
                    Line((x_max_r, z_top), (x_max_r, z_bot))
                    Line((x_max_r, z_bot), (x_min_r, z_bot))
                    Line((x_min_r, z_bot), (x_min_r, z_top))
                make_face()

            clip_faces = clip_sketch.sketch.faces()
            if not clip_faces:
                return []

            # Intersect offset face with clip face
            common_op = BRepAlgoAPI_Common(ocp_face, clip_faces[0].wrapped)
            common_op.Build()
            if not common_op.IsDone():
                return []

            # Extract the outer wire of the clipped result
            clipped_shape = common_op.Shape()

            # Get the face from the clipped result
            face_explorer = TopExp_Explorer(clipped_shape, TopAbs_FACE)
            if not face_explorer.More():
                return []
            clipped_face = TopoDS.Face_s(face_explorer.Current())
            clipped_wire = BRepTools.OuterWire_s(clipped_face)
        except Exception:
            return []

        # Step 5: Extract edges from the clipped wire in order
        try:
            from OCP.BRepTools import BRepTools_WireExplorer
            from OCP.BRep import BRep_Tool

            wire_explorer = BRepTools_WireExplorer(clipped_wire)
            all_edges = []

            while wire_explorer.More():
                edge = wire_explorer.Current()
                curve = BRepAdaptor_Curve(edge)

                p_first = curve.Value(curve.FirstParameter())
                p_last = curve.Value(curve.LastParameter())

                # Determine edge direction from wire traversal
                vertex = wire_explorer.CurrentVertex()
                v_pnt = BRep_Tool.Pnt_s(vertex)
                dist_to_first = ((v_pnt.X() - p_first.X())**2 + (v_pnt.Y() - p_first.Y())**2)**0.5
                dist_to_last = ((v_pnt.X() - p_last.X())**2 + (v_pnt.Y() - p_last.Y())**2)**0.5

                if dist_to_first <= dist_to_last:
                    p_start, p_end = p_first, p_last
                else:
                    p_start, p_end = p_last, p_first

                start_x_dia = p_start.X() * 2.0
                start_z = p_start.Y()
                end_x_dia = p_end.X() * 2.0
                end_z = p_end.Y()

                curve_type = curve.GetType()

                if curve_type == GeomAbs_Line:
                    all_edges.append((
                        (start_x_dia, start_z),
                        (end_x_dia, end_z),
                        "LINE",
                        None,
                        0.0,
                    ))
                elif curve_type == GeomAbs_Circle:
                    circle = curve.Circle()
                    center = circle.Location()
                    center_x_dia = center.X() * 2.0
                    center_z = center.Y()
                    radius = circle.Radius()
                    all_edges.append((
                        (start_x_dia, start_z),
                        (end_x_dia, end_z),
                        "ARC",
                        (center_x_dia, center_z),
                        radius,
                    ))

                wire_explorer.Next()

            # The clipped wire is a closed polygon. We need to extract just the
            # turning portion (the profile-following edges), not the clip boundary edges.
            # Clip boundary edges run along X=x_min, Z=z_top, or Z=z_bot.
            # Turning edges are everything else.
            tol = 1e-4
            x_min_dia = x_min_r * 2.0
            turning_edges = []
            for edge in all_edges:
                start, end = edge[0], edge[1]
                sx, sz = start
                ex, ez = end

                # Skip edges along the clip boundary (X = x_min_dia)
                if abs(sx - x_min_dia) < tol and abs(ex - x_min_dia) < tol:
                    continue
                # Skip edges along Z = z_top (face level — handled by face passes)
                if abs(sz - z_top) < tol and abs(ez - z_top) < tol:
                    continue
                # Skip edges along Z = z_bot
                if abs(sz - z_bot) < tol and abs(ez - z_bot) < tol:
                    continue

                turning_edges.append(edge)

            # Order edges so they go from Z0+fin toward Z_end (top to bottom)
            # The cutting direction is always from highest Z to lowest Z.
            # Chain edges: find the edge starting at the highest Z, then follow
            # end→start connections.
            if not turning_edges:
                return []

            # Find the edge whose start point has the highest Z (closest to face)
            # This is where cutting begins
            ordered = []
            remaining = list(turning_edges)

            # Start with the edge that begins at the highest Z
            remaining.sort(key=lambda e: -e[0][1])  # Sort by start Z descending
            # But we might need to reverse some edges if they're going the wrong way
            # Check: does the first edge go downward (start_z > end_z)?
            first = remaining[0]
            if first[0][1] < first[1][1]:
                # Edge goes upward — reverse it
                start, end, etype, center, radius = first
                remaining[0] = (end, start, etype, center, radius)

            # Chain: pick first, then find next edge whose start matches current end
            current = remaining.pop(0)
            ordered.append(current)

            while remaining:
                current_end = ordered[-1][1]
                found = False
                for i, edge in enumerate(remaining):
                    # Check if edge start matches current end
                    if (abs(edge[0][0] - current_end[0]) < 0.001 and
                            abs(edge[0][1] - current_end[1]) < 0.001):
                        ordered.append(remaining.pop(i))
                        found = True
                        break
                    # Check if edge end matches current end (need to reverse)
                    if (abs(edge[1][0] - current_end[0]) < 0.001 and
                            abs(edge[1][1] - current_end[1]) < 0.001):
                        start, end, etype, center, radius = remaining.pop(i)
                        ordered.append((end, start, etype, center, radius))
                        found = True
                        break
                if not found:
                    break

            return ordered
        except Exception:
            return []

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
            start, end, edge_type, center, radius = edge

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
                # Determine CW vs CCW from the cross product of vectors:
                # start→center and start→end
                # For a 2D plane (X=radius, Y=Z):
                #   cross > 0 → CCW, cross < 0 → CW
                dx_center = center[0] - start[0]
                dz_center = center[1] - start[1]
                dx_end = end[0] - start[0]
                dz_end = end[1] - start[1]
                cross = dx_center * dz_end - dz_center * dx_end

                if cross < 0:
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

    def _find_arc_center(
        self, x1_r: float, z1: float, x2_r: float, z2: float,
        radius: float, is_ccw: bool
    ) -> tuple:
        """Find arc center given two endpoints and radius using OCCT.

        Returns (center_x_radius, center_z) or None if no solution.
        """
        import math

        # Midpoint
        mx = (x1_r + x2_r) / 2.0
        mz = (z1 + z2) / 2.0

        # Distance between points
        dx = x2_r - x1_r
        dz = z2 - z1
        d = math.sqrt(dx**2 + dz**2)

        if d < 1e-10:
            return None

        # Distance from midpoint to center
        h_sq = radius**2 - (d / 2.0)**2
        if h_sq < 0:
            h_sq = 0
        h = math.sqrt(h_sq)

        # Perpendicular direction
        px = -dz / d
        pz = dx / d

        # Two possible centers — choose based on CW/CCW
        if is_ccw:
            center_x = mx - h * px
            center_z = mz - h * pz
        else:
            center_x = mx + h * px
            center_z = mz + h * pz

        return (center_x, center_z)

    def _plan_from_zone_boundary(
        self,
        zone_query: 'ZoneQueryAPI',
        params: RoughingParams,
        stock: StockDef,
        mode: MachiningMode,
    ) -> List[TurningPass]:
        """Fallback: plan cleanup from MTR zone boundary wire extraction.

        Used when the offset computation fails. Extracts the turning portion
        of the MTR zone boundary wire.
        """
        all_edges = zone_query.boundary_wire_extraction("material_to_rough")
        if not all_edges:
            return []

        turning_edges = self._filter_turning_edges(all_edges, stock, mode)
        if not turning_edges:
            return []

        moves = self._build_moves_from_edge_data(turning_edges, params)
        if not moves:
            return []

        z_start = turning_edges[0].start[1]
        z_values = [m.z for m in moves]
        z_end = min(z_values)

        cleanup_pass = TurningPass(
            x_level=0.0,
            z_start=z_start,
            z_end=z_end,
            pass_index=0,
            pass_type=PassType.CLEANUP,
            moves=moves,
            swept_region=None,
        )

        return [cleanup_pass]

    def _filter_turning_edges(
        self,
        edges: List['EdgeData'],
        stock: StockDef,
        mode: MachiningMode,
    ) -> List['EdgeData']:
        """Filter out closure segments, keeping only the turning portion."""
        tol = 1e-4
        stock_dia = stock.diameter
        z_end_val = stock.z_end

        turning = []
        for edge in edges:
            sx, sz = edge.start
            ex, ez = edge.end

            if abs(sx - stock_dia) < tol and abs(ex - stock_dia) < tol:
                continue
            if abs(sx) < tol and abs(ex) < tol:
                continue
            if abs(sz - z_end_val) < tol and abs(ez - z_end_val) < tol:
                continue
            if abs(sx - stock_dia) < tol or abs(ex - stock_dia) < tol:
                if abs(sz - ez) < tol:
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
