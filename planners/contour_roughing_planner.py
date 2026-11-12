"""Offset-contour roughing planner for Industry CAM Engine (OD mode)."""
from geometry.kernel import clip_to_box, first_ocp_face, offset_face, translate_face, wire_edges
from models.results import TurningPass
from models.moves import ToolMove, MoveType, PassType
from models.profile import MachiningMode


class ContourRoughingPlanner:
    """Offset-contour roughing for OD. Same offset+clip as cleanup, at DOC intervals."""

    def plan(self, zone_query, zone_set, tool, params, stock, mode, profile):
        if mode != MachiningMode.OD:
            return []
        segments = profile.segments
        if len(segments) < 2:
            return []
        doc_r = params.doc_dia / 2.0
        fin_r = params.fin_allowance / 2.0
        stock_r = stock.diameter / 2.0
        z_begin = fin_r
        # The zone builder's finished part (correct arc sides, corner breaks
        # applied). Until 2026-11-10 this planner built its own face from the
        # raw segments: no corner breaks and RadiusArc(-radius), i.e. every
        # arc bulged the wrong way (the "offset_contour gouges concave
        # fillets" symptom). That builder was kept as a fallback until
        # 2026-11-12; it could only run without a zone set (the pipeline always
        # has one) and would have produced exactly those gouges, so it is gone.
        face = getattr(zone_set, "finished_part", None) if zone_set is not None else None
        if face is None:
            raise ValueError("Contour roughing needs the zone builder's finished part "
                             "(zone_set.finished_part); none was given.")
        passes_inside_out = []
        offset = fin_r + doc_r
        # Roughing is uncompensated: LinuxCNC drives the imaginary tip and the
        # nose sits nose_centre_offset away. So offset the part by (offset + R)
        # for the NOSE CENTRE and shift that path back to the tip. On diameters
        # and faces this is the same path as before; beside a contour falling
        # toward the chuck it keeps the nose its full clearance instead of
        # overhanging the flank (found by the G-code section check 2026-11-11).
        from models.tool import nose_centre_offset
        R = max(getattr(tool, "nose_radius", 0.0) or 0.0, 0.0)
        off = nose_centre_offset(tool) if R > 0 else (0.0, 0.0)
        for idx in range(100):
            ocp_face = self._do_offset(face, offset + R)
            if ocp_face is not None and R > 0:
                ocp_face = translate_face(ocp_face, -off[0], -off[1])
            if ocp_face is None:
                break
            edges = self._clip_and_extract(ocp_face, fin_r, stock_r, z_begin, stock.z_end)
            if not edges:
                break
            moves = self._to_moves(edges, params)
            if not moves:
                break
            x_lvl = self._x_level(edges)
            passes_inside_out.append(TurningPass(
                x_level=x_lvl, z_start=z_begin, z_end=min(m.z for m in moves),
                pass_index=idx, pass_type=PassType.ROUGH, moves=moves, swept_region=None))
            offset += doc_r
        result = []
        for i, p in enumerate(reversed(passes_inside_out)):
            result.append(TurningPass(x_level=p.x_level, z_start=p.z_start, z_end=p.z_end,
                pass_index=i, pass_type=p.pass_type, moves=p.moves, swept_region=p.swept_region))
        return result

    def _do_offset(self, face, dist):
        """Offset face outward by dist. Returns OCP face or None."""
        try:
            return first_ocp_face(offset_face(face, dist, what="contour roughing pass"))
        except Exception:
            return None

    def _clip_and_extract(self, ocp_face, x_min_r, x_max_r, z_top, z_bot):
        """Clip offset face to turning region, extract ordered turning edges.
        
        Handles split passes: when clipping produces multiple disconnected faces
        (arc exceeds stock OD), extracts edges from ALL faces and joins them
        with a retract→reposition→feed-in sequence between sections.
        
        Retract goes to stock OD + 0.005" clearance (safe from arc bulge).
        """
        try:
            all_face_edges = []
            for wire in clip_to_box(ocp_face, x_min_r, x_max_r, z_top, z_bot):
                edges = self._wire_to_edges(wire, x_min_r * 2, x_max_r * 2, z_top, z_bot)
                if edges:
                    all_face_edges.append(edges)
        except Exception:
            return []

        if not all_face_edges:
            return []
        if len(all_face_edges) == 1:
            return all_face_edges[0]

        # Multiple faces (shouldn't happen with current geometry, but handle gracefully)
        # Sort by highest Z, concatenate
        all_face_edges.sort(key=lambda edges: -max(max(e[0][1], e[1][1]) for e in edges))
        combined = []
        for face_edges in all_face_edges:
            combined.extend(face_edges)
        return combined

    def _wire_to_edges(self, wire, xmin_d, xmax_d, z_top, z_bot):
        """Extract edges from wire, filter clip boundaries, order top-to-bottom."""
        try:
            raw = wire_edges(wire)
        except Exception:
            return []
        tol = 1e-4
        keep = []
        for e in raw:
            s, en = e[0], e[1]
            # Filter edges that lie entirely on clip boundaries (no material there)
            # X_min boundary (centerline / pilot hole)
            if abs(s[0] - xmin_d) < tol and abs(en[0] - xmin_d) < tol:
                continue
            # Stock OD boundary: remove if either endpoint touches Z_bot or Z_top
            # (these are clip artifacts, not real cutting geometry).
            # Keep only true connectors between split arc sections (both endpoints
            # are at stock OD but neither touches Z_top or Z_bot).
            if abs(s[0] - xmax_d) < tol and abs(en[0] - xmax_d) < tol:
                at_z_top = abs(s[1] - z_top) < tol or abs(en[1] - z_top) < tol
                at_z_bot = abs(s[1] - z_bot) < tol or abs(en[1] - z_bot) < tol
                if at_z_top or at_z_bot:
                    continue
                # Neither endpoint at Z boundary — true connector between split arcs
            # Z_top boundary (face)
            if abs(s[1] - z_top) < tol and abs(en[1] - z_top) < tol:
                continue
            # Z_bot boundary (bottom)
            if abs(s[1] - z_bot) < tol and abs(en[1] - z_bot) < tol:
                continue
            keep.append(e)
        if not keep:
            return []
        return self._order(keep)

    def _order(self, edges):
        """Order edges from highest Z to lowest Z, chaining by endpoint matching."""
        remaining = list(edges)
        remaining.sort(key=lambda e: -max(e[0][1], e[1][1]))
        f = remaining[0]
        if f[0][1] < f[1][1]:
            remaining[0] = (f[1], f[0], f[2], f[3], f[4])
        ordered = [remaining.pop(0)]
        while remaining:
            ce = ordered[-1][1]
            found = False
            for i, e in enumerate(remaining):
                if abs(e[0][0] - ce[0]) < 0.001 and abs(e[0][1] - ce[1]) < 0.001:
                    ordered.append(remaining.pop(i))
                    found = True
                    break
                if abs(e[1][0] - ce[0]) < 0.001 and abs(e[1][1] - ce[1]) < 0.001:
                    ordered.append((e[1], e[0], e[2], e[3], e[4]))
                    remaining.pop(i)
                    found = True
                    break
            if not found:
                break
        return ordered

    def _to_moves(self, edges, params):
        """Convert edges to ToolMoves.
        
        Emits a feed move to the first edge's start point so that arc I/K
        values (which are relative to the arc start) are correct in the
        assembled move sequence.
        """
        moves = []
        for idx, e in enumerate(edges):
            s, en, tp, ctr, rad = e
            # Emit a positioning feed to the start of the first edge
            # so that arc I/K offsets are relative to the correct point.
            if idx == 0:
                moves.append(ToolMove(MoveType.FEED, s[0], s[1],
                             feed=params.feed, pass_type=PassType.ROUGH))
            if tp == "RAPID":
                moves.append(ToolMove(MoveType.RAPID, en[0], en[1],
                             feed=0.0, pass_type=PassType.ROUGH))
            elif tp == "FEED_IN":
                moves.append(ToolMove(MoveType.FEED, en[0], en[1],
                             feed=params.feed, pass_type=PassType.ROUGH))
            elif tp == "LINE":
                moves.append(ToolMove(MoveType.FEED, en[0], en[1],
                             feed=params.feed, pass_type=PassType.ROUGH))
            elif tp == "ARC":
                # Short sweep is exact on a canonical <= 90 deg piece. The old
                # test, (c - s) x (e - s) < 0 -> ARC_CW, was the negation of
                # the rule every other planner uses: since the 2026-11-10
                # G-code dialect fix LinuxCNC ran these arcs the long way
                # round (e.g. -359 deg instead of +1 deg).
                from geometry.kernel import short_sweep
                sw = short_sweep((s[0] / 2.0, s[1]), (en[0] / 2.0, en[1]), (ctr[0] / 2.0, ctr[1]))
                mt = MoveType.ARC_CW if sw < 0 else MoveType.ARC_CCW
                moves.append(ToolMove(mt, en[0], en[1], feed=params.feed,
                             radius=rad if mt == MoveType.ARC_CW else -rad,
                             center_i=ctr[0] - s[0], center_k=ctr[1] - s[1],
                             pass_type=PassType.ROUGH))
        return moves

    def _x_level(self, edges):
        """Min X of vertical line segments = pass X level."""
        xs = [e[0][0] for e in edges if e[2] == "LINE" and abs(e[0][0] - e[1][0]) < 0.001]
        return min(xs) if xs else (edges[0][0][0] if edges else 0.0)
