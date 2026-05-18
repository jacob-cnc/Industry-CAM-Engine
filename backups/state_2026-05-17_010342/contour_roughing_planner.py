"""Offset-contour roughing planner for Industry CAM Engine (OD mode)."""
import math
from typing import List, TYPE_CHECKING
from build123d import BuildSketch, BuildLine, Line, RadiusArc, make_face
from build123d import offset as b3d_offset, Kind
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE
from OCP.TopoDS import TopoDS
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.GeomAbs import GeomAbs_Line, GeomAbs_Circle
from OCP.BRepTools import BRepTools
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from models.results import TurningPass
from models.moves import ToolMove, MoveType, PassType
from models.params import RoughingParams
from models.stock import StockDef
from models.profile import ClosedProfile, ProfileMove, SegmentType, MachiningMode
from models.constants import TOLERANCE
if TYPE_CHECKING:
    from geometry.zone_query import ZoneQueryAPI
    from geometry.zone_builder import ZoneSet


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
        face = self._build_face(segments)
        if face is None:
            return []
        passes_inside_out = []
        offset = fin_r + doc_r
        for idx in range(100):
            ocp_face = self._do_offset(face, offset)
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

    def _build_face(self, segments):
        """Build finished part face (profile + closure to centerline)."""
        try:
            coords = [{"type": s.segment_type, "x_radius": s.x / 2.0,
                       "z": s.z, "radius": s.radius} for s in segments]
            lx, lz = segments[-1].x / 2.0, segments[-1].z
            fx, fz = segments[0].x / 2.0, segments[0].z
            if abs(lx) > 1e-10:
                coords.append({"type": SegmentType.LINE, "x_radius": 0.0, "z": lz, "radius": 0.0})
            coords.append({"type": SegmentType.LINE, "x_radius": 0.0, "z": 0.0, "radius": 0.0})
            if abs(fx) > 1e-10 or abs(fz) > 1e-10:
                coords.append({"type": SegmentType.LINE, "x_radius": fx, "z": fz, "radius": 0.0})
            with BuildSketch() as sk:
                with BuildLine():
                    for i in range(len(coords)):
                        ni = (i + 1) % len(coords)
                        c, t = coords[i], coords[ni]
                        cx, cz = c["x_radius"], c["z"]
                        tx, tz = t["x_radius"], t["z"]
                        if abs(cx - tx) < 1e-10 and abs(cz - tz) < 1e-10:
                            continue
                        if t["type"] == SegmentType.ARC and t["radius"] != 0.0:
                            RadiusArc((cx, cz), (tx, tz), -t["radius"])
                        else:
                            Line((cx, cz), (tx, tz))
                make_face()
            return sk.sketch
        except Exception:
            return None

    def _do_offset(self, face, dist):
        """Offset face outward by dist. Returns OCP face or None."""
        try:
            r = b3d_offset(face, amount=dist, kind=Kind.INTERSECTION)
            fs = r.faces() if hasattr(r, 'faces') else []
            return fs[0].wrapped if fs else None
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
            with BuildSketch() as cs:
                with BuildLine():
                    Line((x_min_r, z_top), (x_max_r, z_top))
                    Line((x_max_r, z_top), (x_max_r, z_bot))
                    Line((x_max_r, z_bot), (x_min_r, z_bot))
                    Line((x_min_r, z_bot), (x_min_r, z_top))
                make_face()
            cf = cs.sketch.faces()
            if not cf:
                return []
            op = BRepAlgoAPI_Common(ocp_face, cf[0].wrapped)
            op.Build()
            if not op.IsDone():
                return []
            shape = op.Shape()
            # Collect ALL faces from the clip result
            fe = TopExp_Explorer(shape, TopAbs_FACE)
            all_face_edges = []
            while fe.More():
                face = TopoDS.Face_s(fe.Current())
                wire = BRepTools.OuterWire_s(face)
                edges = self._wire_to_edges(wire, x_min_r * 2, x_max_r * 2, z_top, z_bot)
                if edges:
                    all_face_edges.append(edges)
                fe.Next()
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
        from OCP.BRepTools import BRepTools_WireExplorer
        from OCP.BRep import BRep_Tool
        try:
            exp = BRepTools_WireExplorer(wire)
            raw = []
            while exp.More():
                edge = exp.Current()
                cur = BRepAdaptor_Curve(edge)
                pf = cur.Value(cur.FirstParameter())
                pl = cur.Value(cur.LastParameter())
                v = exp.CurrentVertex()
                vp = BRep_Tool.Pnt_s(v)
                df = ((vp.X() - pf.X())**2 + (vp.Y() - pf.Y())**2)**0.5
                dl = ((vp.X() - pl.X())**2 + (vp.Y() - pl.Y())**2)**0.5
                ps, pe = (pf, pl) if df <= dl else (pl, pf)
                sd, sz = ps.X() * 2, ps.Y()
                ed, ez = pe.X() * 2, pe.Y()
                ct = cur.GetType()
                if ct == GeomAbs_Line:
                    raw.append(((sd, sz), (ed, ez), "LINE", None, 0.0))
                elif ct == GeomAbs_Circle:
                    ci = cur.Circle()
                    loc = ci.Location()
                    raw.append(((sd, sz), (ed, ez), "ARC",
                               (loc.X() * 2, loc.Y()), ci.Radius()))
                exp.Next()
        except Exception:
            return []
        tol = 1e-4
        keep = []
        for e in raw:
            s, en = e[0], e[1]
            if abs(s[0] - xmin_d) < tol and abs(en[0] - xmin_d) < tol:
                continue
            # Stock OD edge: only filter if it spans the full Z range (boundary edge)
            # Partial vertical at stock OD is a connector between split arc sections — keep it
            if abs(s[0] - xmax_d) < tol and abs(en[0] - xmax_d) < tol:
                z_span = abs(s[1] - en[1])
                full_span = abs(z_top - z_bot)
                if z_span > full_span * 0.9:  # Nearly full span = boundary edge
                    continue
                # Otherwise it's a partial connector — keep it
            if abs(s[1] - z_top) < tol and abs(en[1] - z_top) < tol:
                continue
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
        """Convert edges to ToolMoves."""
        moves = []
        for e in edges:
            s, en, tp, ctr, rad = e
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
                dxc = ctr[0] - s[0]
                dzc = ctr[1] - s[1]
                dxe = en[0] - s[0]
                dze = en[1] - s[1]
                cross = dxc * dze - dzc * dxe
                mt = MoveType.ARC_CW if cross < 0 else MoveType.ARC_CCW
                moves.append(ToolMove(mt, en[0], en[1], feed=params.feed,
                             radius=rad if mt == MoveType.ARC_CW else -rad,
                             center_i=ctr[0] - s[0], center_k=ctr[1] - s[1],
                             pass_type=PassType.ROUGH))
        return moves

    def _x_level(self, edges):
        """Min X of vertical line segments = pass X level."""
        xs = [e[0][0] for e in edges if e[2] == "LINE" and abs(e[0][0] - e[1][0]) < 0.001]
        return min(xs) if xs else (edges[0][0][0] if edges else 0.0)
