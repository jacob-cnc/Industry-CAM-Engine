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
from geometry.arc_helpers import is_arc_within_x_bounds
from geometry.zone_builder import _profile_to_radius_coords

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

        # Compute the offset profile using the geometry kernel
        # Completely separate paths for OD and ID — no shared logic that could regress
        if mode == MachiningMode.OD:
            offset_edges = self._compute_offset_profile(segments, fin_allowance_radius, mode, stock, z0_fin, profile)
        else:
            offset_edges = self._compute_offset_profile_id(segments, fin_allowance_radius, stock, z0_fin, profile)

        if not offset_edges:
            return []

        # The offset edges from the kernel are the turning portion of the offset wire
        # (clipped at Z0+fin or Z=0, Z_end). They start at the first turning edge.
        # Build the approach sequence to reach the first edge's start point.

        first_edge_start = offset_edges[0][0]
        offset_x_dia = first_edge_start[0]
        offset_start_z = first_edge_start[1]

        moves = []

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

    def _compute_offset_profile(
        self,
        segments: List[ProfileMove],
        fin_allowance_radius: float,
        mode: MachiningMode,
        stock: StockDef = None,
        z0_fin: float = 0.001,
        profile: ClosedProfile = None,
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

        # Build closed profile contour (profile + closure)
        try:
            # Use corner-break-aware coords if profile is available
            if profile is not None:
                coords = _profile_to_radius_coords(profile)
            else:
                coords = []
                for seg in segments:
                    coords.append({
                        "type": seg.segment_type,
                        "x_radius": seg.x / 2.0,
                        "z": seg.z,
                        "radius": seg.radius,
                    })

            # Add closure segments
            last_seg = segments[-1]
            first_seg = segments[0]

            if mode == MachiningMode.OD:
                closure_x = 0.0
            else:
                # ID closure goes to stock OD
                if stock is None:
                    return []
                closure_x = stock.diameter / 2.0

            # Closure: last coord → (closure_x, last_z) → (closure_x, 0) → first coord
            # Use actual coords endpoints (may be trimmed by corner breaks)
            last_x_r = coords[-1]["x_radius"]
            last_z = coords[-1]["z"]
            first_x_r = coords[0]["x_radius"]
            first_z = coords[0]["z"]

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
        # Keep zone is ALWAYS larger than finished part (protective buffer)
        # Positive offset expands the face outward in all directions
        try:
            offset_amount = fin_allowance_radius

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
        # Build a clipping face and intersect with the offset face to get only the turning portion
        try:
            from build123d import BuildSketch, BuildLine, Line, make_face
            from OCP.BRepAlgoAPI import BRepAlgoAPI_Common

            z_top = z0_fin  # Use the same Z start as the cleanup pass itself
            # If the profile has corner breaks near Z=0 (chamfer at face/turning
            # junction), extend the clip to include that geometry.
            # Check if any early corner break produces geometry at Z=0.
            if profile is not None and profile.corner_breaks:
                for cb in profile.corner_breaks:
                    if cb is not None and cb.break_type.value != "none":
                        # There's a corner break — extend clip to Z=0
                        z_top = 0.0
                        break
            # Z_end for clip: for ID mode, leave fin_allowance at the bottom for finish pass
            if mode == MachiningMode.ID:
                z_bot = segments[-1].z + fin_allowance_radius
            else:
                z_bot = segments[-1].z  # Z_end (most negative Z from profile)

            if mode == MachiningMode.OD:
                # OD: clip to X > x_start+fin, keeping the outer (profile-side) boundary
                x_min_r = fin_allowance_radius  # x_start(0) + fin_allowance in radius
                # Cap x_max_r at stock radius + margin (not arbitrary 10.0)
                # This keeps tolerance calculations sane for small features like chamfers.
                stock_r = stock.diameter / 2.0 if stock else 0.5
                x_max_r = stock_r + 0.1  # Small margin beyond stock OD
            else:
                # ID: clip to the bore region between pilot hole and roughing boundary
                # The turning edge is at the max X of this clip (the roughing boundary)
                pilot_r = stock.pilot_hole_dia / 2.0 if stock else 0.0
                roughing_boundary_r = segments[0].x / 2.0 - fin_allowance_radius
                x_min_r = pilot_r
                x_max_r = roughing_boundary_r + fin_allowance_radius * 2  # Include the boundary edge

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
            # Clip boundary edges run along the clip rectangle boundaries.
            # Turning edges are everything else (they follow the offset profile shape).
            #
            # Filter criteria: an edge is a clip boundary edge if BOTH endpoints are
            # near a boundary value AND the edge runs ALONG that boundary (doesn't
            # significantly span in the perpendicular direction). This prevents
            # filtering diagonal edges (like chamfers) that merely terminate at a boundary.
            z_range = abs(z_top - z_bot)
            x_range = abs(x_max_r - x_min_r) * 2.0
            tol = max(1e-4, min(z_range * 0.001, x_range * 0.001))
            x_min_dia = x_min_r * 2.0
            x_max_dia = x_max_r * 2.0
            turning_edges = []
            for edge in all_edges:
                start, end = edge[0], edge[1]
                sx, sz = start
                ex, ez = end

                # Skip edges along the clip boundary (X = x_min_dia)
                # Must be nearly vertical at x_min (both X near x_min, Z span is the extent)
                if abs(sx - x_min_dia) < tol and abs(ex - x_min_dia) < tol:
                    continue
                # Skip edges along the clip boundary (X = x_max_dia)
                if abs(sx - x_max_dia) < tol and abs(ex - x_max_dia) < tol:
                    continue
                # Skip edges along Z = z_top (face level — handled by face passes)
                # BOTH endpoints must be at z_top AND the edge must be essentially
                # horizontal (X span >> Z span). A diagonal chamfer touching z_top
                # will have significant Z span and should NOT be filtered.
                if abs(sz - z_top) < tol and abs(ez - z_top) < tol:
                    x_span = abs(sx - ex)
                    z_span = abs(sz - ez)
                    if x_span > z_span * 2.0 or x_span < tol:
                        # Horizontal edge along z_top — filter it
                        continue
                # Skip edges along Z = z_bot
                if abs(sz - z_bot) < tol and abs(ez - z_bot) < tol:
                    x_span = abs(sx - ex)
                    z_span = abs(sz - ez)
                    if x_span > z_span * 2.0 or x_span < tol:
                        continue

                turning_edges.append(edge)

            # For ID mode with a thin clip region, we may get duplicate edges
            # (same X, opposite Z direction). Keep only the one going in cutting
            # direction (from high Z to low Z = downward).
            if mode == MachiningMode.ID and len(turning_edges) > 1:
                # Check if all edges are at the same X (simple bore case)
                x_values = set()
                for edge in turning_edges:
                    x_values.add(round(edge[0][0], 4))
                    x_values.add(round(edge[1][0], 4))
                if len(x_values) == 1:
                    # All at same X — keep only the one going downward (start_z > end_z)
                    downward = [e for e in turning_edges if e[0][1] > e[1][1]]
                    if downward:
                        turning_edges = downward

            # Order edges to match the FINISH PASS direction.
            # The cleanup starts from the approach point (x_start+fin, z0+fin) and
            # traces the offset profile in the same direction as the finish pass.
            # Find the edge endpoint closest to the approach point, then chain forward.
            # This works regardless of profile shape (tapers, steps, arcs).
            if not turning_edges:
                return []

            ordered = []
            remaining = list(turning_edges)

            # The approach point is (x_start+fin, z0+fin) in diameter space.
            # Find the edge endpoint closest to this — that's where chaining begins.
            approach_x_dia = x_min_r * 2.0  # x_start + fin in diameter
            approach_z = z_top  # z0 + fin

            best_start_idx = 0
            best_dist = float('inf')
            best_reversed = False
            for i, edge in enumerate(remaining):
                sx, sz = edge[0]
                ex, ez = edge[1]
                d_start = (sx - approach_x_dia)**2 + (sz - approach_z)**2
                d_end = (ex - approach_x_dia)**2 + (ez - approach_z)**2
                if d_start < best_dist:
                    best_dist = d_start
                    best_start_idx = i
                    best_reversed = False
                if d_end < best_dist:
                    best_dist = d_end
                    best_start_idx = i
                    best_reversed = True

            # Pop the starting edge, reverse if needed
            first_edge = remaining.pop(best_start_idx)
            if best_reversed:
                start, end, etype, center, radius = first_edge
                first_edge = (end, start, etype, center, radius)
            ordered.append(first_edge)

            # Chain: pick next edge whose start matches current end
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

    def _compute_offset_profile_id(
        self,
        segments: List[ProfileMove],
        fin_allowance_radius: float,
        stock: StockDef,
        z0_fin: float,
        profile: ClosedProfile = None,
    ) -> List[tuple]:
        """Compute the ID cleanup contour by offsetting the finished part face TOWARD centerline.

        Same kernel-driven approach as OD, but with ID-specific geometry:
        - Closure goes to stock OD (not centerline)
        - Offset direction is NEGATIVE (shrink toward centerline = bore-side boundary)
        - Clip region captures the bore-side (inner) boundary of the offset face
        - Edge filter removes pilot hole, Z_top, Z_bot clip boundaries

        The offset is equidistant (kernel-driven) so arcs and tapers are handled correctly.

        Returns list of edge tuples (same format as OD version):
          LINE: ((start_x_dia, start_z), (end_x_dia, end_z), "LINE", None, 0.0)
          ARC:  ((start_x_dia, start_z), (end_x_dia, end_z), "ARC", (center_x_dia, center_z), radius)
        """
        from build123d import (
            BuildSketch, BuildLine, Line, RadiusArc, make_face,
            offset as b3d_offset, Kind,
        )
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopAbs import TopAbs_FACE
        from OCP.TopoDS import TopoDS
        from OCP.BRepAdaptor import BRepAdaptor_Curve
        from OCP.GeomAbs import GeomAbs_Line, GeomAbs_Circle
        from OCP.BRepTools import BRepTools

        if len(segments) < 2:
            return []

        # Step 1: Build the finished part face (profile + closure to stock OD)
        try:
            # Use corner-break-aware coords if profile is available
            if profile is not None:
                coords = _profile_to_radius_coords(profile)
            else:
                coords = []
                for seg in segments:
                    coords.append({
                        "type": seg.segment_type,
                        "x_radius": seg.x / 2.0,
                        "z": seg.z,
                        "radius": seg.radius,
                    })

            # ID closure goes to stock OD
            closure_x = stock.diameter / 2.0
            last_x_r = coords[-1]["x_radius"]
            last_z = coords[-1]["z"]
            first_x_r = coords[0]["x_radius"]
            first_z = coords[0]["z"]

            if abs(last_x_r - closure_x) > 1e-10:
                coords.append({"type": SegmentType.LINE, "x_radius": closure_x, "z": last_z, "radius": 0.0})
            coords.append({"type": SegmentType.LINE, "x_radius": closure_x, "z": 0.0, "radius": 0.0})
            if abs(closure_x - first_x_r) > 1e-10 or abs(0.0 - first_z) > 1e-10:
                coords.append({"type": SegmentType.LINE, "x_radius": first_x_r, "z": first_z, "radius": 0.0})

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

        # Step 2: Offset the finished part face OUTWARD by fin_allowance
        # Positive offset expands the face in all directions.
        # For ID, this moves the bore-side boundary TOWARD centerline (smaller X)
        # by fin_allowance — creating the roughing boundary.
        # The bore-side boundary of the expanded face = profile_x - fin_allowance.
        try:
            offset_amount = fin_allowance_radius
            offset_face = b3d_offset(finished_part_face, amount=offset_amount, kind=Kind.INTERSECTION)
        except Exception:
            return []

        # Step 3: Extract boundary wire from the offset face
        try:
            offset_faces = offset_face.faces() if hasattr(offset_face, 'faces') else []
            if not offset_faces:
                return []
            ocp_face = offset_faces[0].wrapped
        except Exception:
            return []

        # Step 4: Clip the offset face to the turning region
        # For ID: clip from pilot hole to just past the roughing boundary
        # This captures the bore-side boundary (the cleanup contour)
        try:
            from build123d import BuildSketch, BuildLine, Line, make_face
            from OCP.BRepAlgoAPI import BRepAlgoAPI_Common

            z_top = z0_fin
            z_bot = segments[-1].z + fin_allowance_radius  # Leave room for finish at bore bottom

            # Clip X range: from pilot hole to just past the largest roughing boundary
            # The offset face's bore-side boundary is at (profile_x - fin_allowance) for each section.
            # We need the clip to include ALL roughing boundary X values.
            pilot_r = stock.pilot_hole_dia / 2.0
            max_profile_x_r = max(seg.x / 2.0 for seg in segments)
            roughing_boundary_r = max_profile_x_r - fin_allowance_radius
            # Clip extends from pilot hole to just past the largest roughing boundary
            x_min_r = pilot_r
            x_max_r = roughing_boundary_r + fin_allowance_radius * 3  # Small margin past boundary

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

            common_op = BRepAlgoAPI_Common(ocp_face, clip_faces[0].wrapped)
            common_op.Build()
            if not common_op.IsDone():
                return []

            clipped_shape = common_op.Shape()
            face_explorer = TopExp_Explorer(clipped_shape, TopAbs_FACE)
            if not face_explorer.More():
                return []
            clipped_face = TopoDS.Face_s(face_explorer.Current())
            clipped_wire = BRepTools.OuterWire_s(clipped_face)
        except Exception:
            return []

        # Step 5: Extract edges from the clipped wire
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
                        (start_x_dia, start_z), (end_x_dia, end_z), "LINE", None, 0.0,
                    ))
                elif curve_type == GeomAbs_Circle:
                    circle = curve.Circle()
                    center = circle.Location()
                    center_x_dia = center.X() * 2.0
                    center_z = center.Y()
                    radius = circle.Radius()
                    all_edges.append((
                        (start_x_dia, start_z), (end_x_dia, end_z), "ARC",
                        (center_x_dia, center_z), radius,
                    ))

                wire_explorer.Next()

            # Step 6: Filter out clip boundary edges, keep turning edges
            tol = 1e-4
            x_min_dia = x_min_r * 2.0
            x_max_dia = x_max_r * 2.0
            turning_edges = []
            for edge in all_edges:
                start, end = edge[0], edge[1]
                sx, sz = start
                ex, ez = end

                # Skip edges at pilot hole boundary (X = x_min_dia)
                if abs(sx - x_min_dia) < tol and abs(ex - x_min_dia) < tol:
                    continue
                # Skip edges at clip X max boundary
                if abs(sx - x_max_dia) < tol and abs(ex - x_max_dia) < tol:
                    continue
                # Skip edges at Z_top (clip top boundary)
                if abs(sz - z_top) < tol and abs(ez - z_top) < tol:
                    continue
                # Skip edges at Z=fin_allowance (offset face top boundary)
                if abs(sz - fin_allowance_radius) < tol and abs(ez - fin_allowance_radius) < tol:
                    continue
                # Skip edges at Z_bot (clip bottom boundary)
                if abs(sz - z_bot) < tol and abs(ez - z_bot) < tol:
                    continue

                turning_edges.append(edge)

            if not turning_edges:
                return []

            # Step 7: Order edges from highest Z to lowest Z (cutting direction)
            # Same chaining logic as OD — find highest Z start, chain downward
            ordered = []
            remaining = list(turning_edges)

            # Sort by start Z descending to find the entry point
            remaining.sort(key=lambda e: -e[0][1])
            # Ensure first edge goes downward
            first = remaining[0]
            if first[0][1] < first[1][1]:
                start, end, etype, center, radius = first
                remaining[0] = (end, start, etype, center, radius)

            current = remaining.pop(0)
            ordered.append(current)

            while remaining:
                current_end = ordered[-1][1]
                found = False
                for i, edge in enumerate(remaining):
                    if (abs(edge[0][0] - current_end[0]) < 0.001 and
                            abs(edge[0][1] - current_end[1]) < 0.001):
                        ordered.append(remaining.pop(i))
                        found = True
                        break
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
                # Determine CW vs CCW from the sweep direction.
                # The center is correct (from RadiusArc with proper signed radius).
                # Compute sweep from start to end, normalize to [-π, π].
                import math as _math

                sx_r = start[0] / 2.0
                sz = start[1]
                ex_r = end[0] / 2.0
                ez = end[1]
                cx_r = center[0] / 2.0
                cz = center[1]

                angle_start = _math.atan2(sz - cz, sx_r - cx_r)
                angle_end = _math.atan2(ez - cz, ex_r - cx_r)
                sweep = angle_end - angle_start
                if sweep > _math.pi:
                    sweep -= 2 * _math.pi
                elif sweep < -_math.pi:
                    sweep += 2 * _math.pi

                # Negative sweep = CW = G02, Positive sweep = CCW = G03
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

    def _find_arc_center(
        self, x1_r: float, z1: float, x2_r: float, z2: float,
        radius: float, is_cw: bool
    ) -> tuple:
        """Find arc center given two endpoints and radius.

        Uses cross product to pick the center that produces the correct
        CW/CCW direction on screen (inverted Y axis).

        Empirically verified convention:
            CW on screen -> cross product (start-center) x (end-center) < 0
            CCW on screen -> cross product > 0

        Returns (center_x_radius, center_z) or None if no solution.
        """
        import math

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

        # Cross product: (start-center) x (end-center)
        ax = x1_r - c1_x
        az = z1 - c1_z
        bx = x2_r - c1_x
        bz = z2 - c1_z
        cr1 = ax * bz - az * bx

        # CW -> negative cross, CCW -> positive cross
        if is_cw:
            cx, cz = (c1_x, c1_z) if cr1 < 0 else (c2_x, c2_z)
            other_cx, other_cz = (c2_x, c2_z) if cr1 < 0 else (c1_x, c1_z)
        else:
            cx, cz = (c1_x, c1_z) if cr1 > 0 else (c2_x, c2_z)
            other_cx, other_cz = (c2_x, c2_z) if cr1 > 0 else (c1_x, c1_z)

        # Bounds-aware center selection: if the cross-product choice produces
        # an arc that exceeds X bounds, swap to the other candidate center.
        if not is_arc_within_x_bounds(cx, cz, radius, x1_r, z1, x2_r, z2, is_cw):
            # Check if the other center produces a bounded arc
            if is_arc_within_x_bounds(other_cx, other_cz, radius, x1_r, z1, x2_r, z2, not is_cw):
                cx, cz = other_cx, other_cz
            # If both centers produce out-of-bounds arcs, keep original (degenerate case)

        return (cx, cz)

    def _plan_from_zone_boundary(
        self,
        zone_query: 'ZoneQueryAPI',
        params: RoughingParams,
        stock: StockDef,
        mode: MachiningMode,
        z0_fin: float = None,
    ) -> List[TurningPass]:
        """Plan cleanup from MTR zone boundary wire extraction.

        Extracts the turning portion of the MTR zone boundary wire
        (the profile-side edges that the cleanup pass traces).
        """
        if z0_fin is None:
            z0_fin = params.fin_allowance / 4.0  # fallback

        all_edges = zone_query.boundary_wire_extraction("material_to_rough")
        if not all_edges:
            return []

        turning_edges = self._filter_turning_edges(all_edges, stock, mode)
        if not turning_edges:
            return []

        # For ID mode: edges come from wire traversal (CCW around zone).
        # Cutting direction is from Z_start downward (CW around profile-side boundary).
        # Reverse the edge list and flip each edge's start/end.
        if mode == MachiningMode.ID:
            reversed_edges = []
            for edge in reversed(turning_edges):
                # Create a new EdgeData with swapped start/end
                from geometry.zone_query import EdgeData
                reversed_edges.append(EdgeData(
                    edge_type=edge.edge_type,
                    start=edge.end,
                    end=edge.start,
                    center=edge.center,
                    radius=edge.radius,
                    direction=edge.direction,
                ))
            turning_edges = reversed_edges

        moves = self._build_moves_from_edge_data(turning_edges, params)
        if not moves:
            return []

        z_values = [m.z for m in moves]
        z_end = min(z_values)

        cleanup_pass = TurningPass(
            x_level=stock.pilot_hole_dia if mode == MachiningMode.ID else 0.0,
            z_start=z0_fin,
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
