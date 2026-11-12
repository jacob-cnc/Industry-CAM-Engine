"""Zone Query API for Industry CAM Engine.

Wraps OCCT operations against Build123d 2D Faces for geometric queries.
This is the interface between the geometry kernel and the rest of the engine.

All inputs: DIAMETER for X, INCHES for Z.
All outputs: INCHES for Z values.

Imports from: models/, geometry/zone_builder
"""

from typing import List, Tuple, Optional
import math

from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
from OCP.BRep import BRep_Tool
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_EDGE, TopAbs_VERTEX
from OCP.TopoDS import TopoDS
from OCP.gp import gp_Pnt
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.GeomAbs import GeomAbs_Line, GeomAbs_Circle
from OCP.BRepTools import BRepTools

from build123d import Face, Wire, Edge, Sketch

from models.constants import TOLERANCE
from models.profile import MachiningMode
from geometry.zone_builder import ZoneSet


class EdgeData:
    """Extracted edge descriptor for boundary wire extraction."""

    def __init__(self, edge_type: str, start: Tuple[float, float],
                 end: Tuple[float, float], center: Optional[Tuple[float, float]] = None,
                 radius: float = 0.0, direction: str = "cw",
                 ocp_edge=None, sweep: float = 0.0):
        self.edge_type = edge_type  # "LINE", "ARC", or "CURVE"
        self.start = start          # (x_dia, z)
        self.end = end              # (x_dia, z)
        self.center = center        # (x_dia, z) for arcs
        self.radius = radius        # Arc radius (positive)
        # ARC: "cw" = negative sweep in (r, z) = MoveType.ARC_CW (see
        # geometry/arc_math.py). Geometric since Phase 0 (was always "cw").
        self.direction = direction  # "cw" or "ccw"
        self.sweep = sweep          # signed sweep, radians (ARC only)
        self.ocp_edge = ocp_edge    # Raw OCP edge for non-circular curve decomposition

    def reversed(self) -> "EdgeData":
        """Same edge travelled the other way (direction and sweep flip)."""
        flip = {"cw": "ccw", "ccw": "cw"}.get(self.direction, self.direction)
        return EdgeData(self.edge_type, start=self.end, end=self.start, center=self.center,
                        radius=self.radius, direction=flip, ocp_edge=self.ocp_edge,
                        sweep=-self.sweep)


class ZoneQueryAPI:
    """Direct geometric query interface wrapping OCCT operations against Build123d Faces.

    All inputs in DIAMETER for X, INCHES for Z.
    All outputs in INCHES for Z values.

    This class does NOT import from planners/, transitions/, or any downstream module.
    It is consumed by intervals/Fiber (via dependency injection from pipeline/).
    """

    def __init__(self, zone_set: ZoneSet):
        self._zones = zone_set

    def boundary_at_x(self, x_dia: float, zone_name: str = "material_to_rough") -> List[Tuple[float, float]]:
        """Query Z boundaries where a horizontal line at x_dia intersects the zone.

        Returns list of (z_start, z_end) interval pairs, sorted by Z descending.
        z_start > z_end for each pair (z_start is closer to face).

        Uses BRepAlgoAPI_Section internally — intersects a horizontal line with the zone Face.

        Args:
            x_dia: X position in DIAMETER
            zone_name: Which zone to query ("material_to_rough", "finished_part", etc.)

        Returns:
            List of (z_start, z_end) tuples representing material intervals at this X level.
        """
        face = self._get_face(zone_name)
        if face is None:
            return []

        x_radius = x_dia / 2.0

        # Create a horizontal line at this X level spanning the full Z range
        # Line goes from (x_radius, +10) to (x_radius, -10) — well beyond any part
        p1 = gp_Pnt(x_radius, 10.0, 0.0)
        p2 = gp_Pnt(x_radius, -10.0, 0.0)

        try:
            line_edge = BRepBuilderAPI_MakeEdge(p1, p2).Edge()
        except Exception:
            return []

        # Get the underlying OCP face
        ocp_face = self._get_ocp_face(face)
        if ocp_face is None:
            return []

        # Intersect line with face
        try:
            section = BRepAlgoAPI_Section(ocp_face, line_edge)
            section.Build()
            if not section.IsDone():
                return []
        except Exception:
            return []

        # Extract intersection vertices (Z values where line crosses face boundary)
        z_values = []
        explorer = TopExp_Explorer(section.Shape(), TopAbs_VERTEX)
        while explorer.More():
            vertex = TopoDS.Vertex_s(explorer.Current())
            pnt = BRep_Tool.Pnt_s(vertex)
            z_values.append(pnt.Y())  # Y in sketch = Z in lathe
            explorer.Next()

        # Also check edges (for segments that lie along the boundary)
        edge_explorer = TopExp_Explorer(section.Shape(), TopAbs_EDGE)
        while edge_explorer.More():
            edge = TopoDS.Edge_s(edge_explorer.Current())
            curve = BRepAdaptor_Curve(edge)
            z_values.append(curve.Value(curve.FirstParameter()).Y())
            z_values.append(curve.Value(curve.LastParameter()).Y())
            edge_explorer.Next()

        if len(z_values) < 2:
            return []

        # Sort Z values descending and pair them into intervals
        z_values = sorted(set(round(z, 8) for z in z_values), reverse=True)

        intervals = []
        for i in range(0, len(z_values) - 1, 2):
            if i + 1 < len(z_values):
                z_start = z_values[i]
                z_end = z_values[i + 1]
                if z_start - z_end > TOLERANCE:
                    intervals.append((z_start, z_end))

        return intervals

    def boundary_wire_extraction(self, zone_name: str) -> List[EdgeData]:
        """Extract boundary edges from a zone Face for Shapely polygon construction.

        Returns EdgeData objects with type (LINE/ARC), start, end, center, radius.
        Coordinates returned in DIAMETER for X, INCHES for Z.

        Args:
            zone_name: Which zone to extract boundary from

        Returns:
            List of EdgeData objects describing the boundary wire edges in order.
        """
        face = self._get_face(zone_name)
        if face is None:
            return []

        ocp_face = self._get_ocp_face(face)
        if ocp_face is None:
            return []

        # Handle case where ocp_face is actually a Compound (from boolean ops)
        from OCP.TopAbs import TopAbs_FACE
        from OCP.BRepTools import BRepTools_WireExplorer
        
        # If it's not a proper face, try to extract one
        try:
            outer_wire = BRepTools.OuterWire_s(ocp_face)
        except TypeError:
            # ocp_face might be a Compound — extract first face
            face_explorer = TopExp_Explorer(ocp_face, TopAbs_FACE)
            if face_explorer.More():
                actual_face = TopoDS.Face_s(face_explorer.Current())
                outer_wire = BRepTools.OuterWire_s(actual_face)
            else:
                return []

        return self._edge_data_from_wire(outer_wire)

    @staticmethod
    def _edge_data_from_wire(outer_wire):
        # Explore edges in wire order using CurrentVertex() for correct orientation
        from OCP.BRepTools import BRepTools_WireExplorer
        wire_explorer = BRepTools_WireExplorer(outer_wire)

        raw_edges = []
        while wire_explorer.More():
            edge = wire_explorer.Current()
            curve = BRepAdaptor_Curve(edge)

            # Get the curve's parametric start and end points
            p_first = curve.Value(curve.FirstParameter())
            p_last = curve.Value(curve.LastParameter())

            # CurrentVertex() gives us the vertex the explorer is AT —
            # this is the TRUE start of the edge in wire traversal order
            vertex = wire_explorer.CurrentVertex()
            v_pnt = BRep_Tool.Pnt_s(vertex)

            # Determine if edge is forward or reversed by comparing
            # CurrentVertex to the curve's FirstParameter point
            dist_to_first = ((v_pnt.X() - p_first.X())**2 + (v_pnt.Y() - p_first.Y())**2)**0.5
            dist_to_last = ((v_pnt.X() - p_last.X())**2 + (v_pnt.Y() - p_last.Y())**2)**0.5

            if dist_to_first <= dist_to_last:
                # Edge is forward — parametric start = wire start
                p_start = p_first
                p_end = p_last
            else:
                # Edge is reversed — parametric end = wire start
                p_start = p_last
                p_end = p_first

            # Convert from radius to diameter for output
            start_x_dia = p_start.X() * 2.0
            start_z = p_start.Y()
            end_x_dia = p_end.X() * 2.0
            end_z = p_end.Y()

            curve_type = curve.GetType()

            if curve_type == GeomAbs_Line:
                raw_edges.append(EdgeData(
                    edge_type="LINE",
                    start=(start_x_dia, start_z),
                    end=(end_x_dia, end_z),
                ))
            elif curve_type == GeomAbs_Circle:
                circle = curve.Circle()
                center = circle.Location()
                center_x_dia = center.X() * 2.0
                center_z = center.Y()
                radius = circle.Radius()

                # True sweep from the kernel: start -> mid-parameter point ->
                # end (the mid point does not depend on edge orientation).
                # Then canonical quadrant pieces (<= 90 deg, monotonic), so
                # no consumer ever has to guess a sweep (arc_math docstring).
                from geometry.arc_math import arc_from_kernel, split_at_quadrants
                p_mid = curve.Value(0.5 * (curve.FirstParameter() + curve.LastParameter()))
                arc = arc_from_kernel((p_start.X(), p_start.Y()), (p_mid.X(), p_mid.Y()),
                                      (p_end.X(), p_end.Y()), (center.X(), center.Y()),
                                      radius)
                for piece in split_at_quadrants(arc):
                    raw_edges.append(EdgeData(
                        edge_type="ARC",
                        start=(piece.start[0] * 2.0, piece.start[1]),
                        end=(piece.end[0] * 2.0, piece.end[1]),
                        center=(center_x_dia, center_z),
                        radius=radius,
                        direction="cw" if piece.is_cw else "ccw",
                        sweep=piece.sweep,
                    ))
            else:
                # Non-circular curve (ellipse, BSpline, Bezier, etc.)
                # Store the raw OCP edge for parametric decomposition by finish planner
                raw_edges.append(EdgeData(
                    edge_type="CURVE",
                    start=(start_x_dia, start_z),
                    end=(end_x_dia, end_z),
                    ocp_edge=edge,
                ))

            wire_explorer.Next()

        return raw_edges

    def profile_offset_edges(self, profile, remaining_allowance_dia: float, *, z_min: float | None = None):
        """Offset the open user contour; optionally clip the wire to stock/depth.

        This is a contour query, not a complete removal-pocket or access model.
        See docs/handoffs/2026-11-08-id-pocket-removal-model.md.
        """
        from build123d import Side, Vertex
        from geometry.zone_builder import profile_to_radius_coords, _build_face_from_coords
        if not math.isfinite(remaining_allowance_dia) or remaining_allowance_dia < 0:
            raise ValueError("Profile allowance must be finite and nonnegative.")
        coords = profile_to_radius_coords(profile)
        original = _build_face_from_coords(coords, profile, closed=False)
        wires = original.wires()
        if len(wires) != 1:
            raise RuntimeError("Profile contour must be one connected open wire.")
        wire = wires[0]
        anchor = Vertex(coords[0]["x_radius"], coords[0]["z"], 0)
        if Vertex(*tuple(wire.position_at(1))).distance_to(anchor) < Vertex(*tuple(wire.position_at(0))).distance_to(anchor):
            wire = Wire(TopoDS.Wire_s(wire.wrapped.Reversed()))
        side = Side.LEFT if profile.mode == MachiningMode.OD else Side.RIGHT
        if remaining_allowance_dia == 0:
            offset_wire = wire
        else:
            from geometry.kernel_offset import offset_wire
            try:
                offset = offset_wire(wire, remaining_allowance_dia / 2.0, side=side,
                                     closed=False, what="cleanup/finish contour")
            except RuntimeError as exc:
                # Also seen for off-axis quadrant arcs built as splines.
                raise RuntimeError(
                    f"{exc}\n\nContours with spline/elliptical segments (e.g. off-axis "
                    f"quadrant arcs) are not supported yet.") from exc
            offset_wire = Wire(offset.edges())
        if z_min is not None:
            from build123d import Compound
            from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
            from geometry.zone_builder import _build_stock_face
            bounds = self._zones.stock_face.bounding_box()
            clip = _build_stock_face(bounds.max.X, bounds.max.Y, z_min,
                                     profile.mode, bounds.min.X)
            common = BRepAlgoAPI_Common(offset_wire.wrapped, clip.faces()[0].wrapped)
            common.Build()
            if not common.IsDone():
                raise RuntimeError("Cleanup contour clipping failed.")
            clipped_edges = Compound(common.Shape()).edges()
            clipped_wires = Wire.combine(clipped_edges)
            if len(clipped_wires) != 1:
                raise RuntimeError("Cleanup clipping did not produce one connected contour.")
            offset_wire = clipped_wires[0]
        # OCCT can reverse an offset wire. Align endpoints with the source using
        # kernel distances rather than manual coordinate translation or geometry.
        def vertex(point):
            return Vertex(*tuple(point))
        source_start, source_end = vertex(wire.position_at(0)), vertex(wire.position_at(1))
        start, end = vertex(offset_wire.position_at(0)), vertex(offset_wire.position_at(1))
        forward = start.distance_to(source_start) + end.distance_to(source_end)
        backward = end.distance_to(source_start) + start.distance_to(source_end)
        ocp_wire = offset_wire.wrapped
        if backward < forward:
            ocp_wire = TopoDS.Wire_s(ocp_wire.Reversed())
        edges = self._edge_data_from_wire(ocp_wire)
        if not edges:
            raise RuntimeError("Kernel produced no profile offset contour.")
        return edges

    def _get_face(self, zone_name: str) -> Optional[object]:
        """Get the Build123d Face/Sketch for a named zone."""
        zone_map = {
            "finished_part": self._zones.finished_part,
            "finish_allowance": self._zones.finish_allowance,
            "material_to_rough": self._zones.material_to_rough,
            "true_face": self._zones.true_face,
            "stock": self._zones.stock_face,
        }
        return zone_map.get(zone_name)

    def _get_ocp_face(self, face_or_sketch) -> Optional[object]:
        """Extract the underlying OCP TopoDS_Face from a Build123d object."""
        if face_or_sketch is None:
            return None

        try:
            # If it's a Sketch, get the face from it
            if isinstance(face_or_sketch, Sketch):
                faces = face_or_sketch.faces()
                if faces:
                    return faces[0].wrapped
                return None
            # If it's already a Face
            if isinstance(face_or_sketch, Face):
                return face_or_sketch.wrapped
            # Try .wrapped directly — might be a Compound from boolean ops
            if hasattr(face_or_sketch, 'wrapped'):
                wrapped = face_or_sketch.wrapped
                # If it's a compound, extract the first face from it
                from OCP.TopAbs import TopAbs_FACE
                face_explorer = TopExp_Explorer(wrapped, TopAbs_FACE)
                if face_explorer.More():
                    return TopoDS.Face_s(face_explorer.Current())
                return wrapped
            # If it's a raw OCP shape (from boolean cut)
            from OCP.TopAbs import TopAbs_FACE
            face_explorer = TopExp_Explorer(face_or_sketch, TopAbs_FACE)
            if face_explorer.More():
                return TopoDS.Face_s(face_explorer.Current())
        except Exception:
            pass
        return None
