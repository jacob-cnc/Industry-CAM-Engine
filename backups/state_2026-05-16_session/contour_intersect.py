"""Contour intersection module for Industry CAM Engine.

Finds Z intervals at a given X level by intersecting a horizontal line
against the MTR zone boundary wire, then classifying segments as inside/outside
using OCCT's face classifier.

This decouples toolpath planning from the BRepAlgoAPI_Section-against-Face approach
(which can miss internal boundary crossings on complex zone shapes). Instead:
  1. Extract the zone's boundary wire(s)
  2. Intersect a horizontal line edge against the wire(s)
  3. Classify resulting segments via point-in-face test

All inputs: DIAMETER for X, INCHES for Z.
All outputs: INCHES for Z values.

Imports from: models/, geometry/zone_builder (ZoneSet only)
"""

from typing import List, Tuple, Optional

from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
from OCP.BRep import BRep_Tool
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_EDGE, TopAbs_VERTEX, TopAbs_WIRE, TopAbs_FACE
from OCP.TopoDS import TopoDS
from OCP.gp import gp_Pnt
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRepTools import BRepTools
from OCP.BRepClass import BRepClass_FaceClassifier
from OCP.TopAbs import TopAbs_IN, TopAbs_ON, TopAbs_OUT

from build123d import Face, Sketch

from models.constants import TOLERANCE
from geometry.zone_builder import ZoneSet


class ContourIntersect:
    """Finds material intervals at a given X level by intersecting against zone boundary wires.

    Uses OCCT operations exclusively — no hand math for geometry.

    Usage:
        ci = ContourIntersect(zone_set)
        intervals = ci.intervals_at_x(x_dia=1.45, zone_name="material_to_rough")
        # Returns [(z_begin_1, z_term_1), (z_begin_2, z_term_2), ...]
    """

    def __init__(self, zone_set: ZoneSet):
        self._zones = zone_set
        # Cache: the actual TopoDS_Face for point-in-face classification
        self._face_cache: dict = {}
        # Cache: the raw shape (may be Compound) for wire extraction
        self._shape_cache: dict = {}
        # Cache: extracted wires
        self._wire_cache: dict = {}

    def intervals_at_x(
        self, x_dia: float, zone_name: str = "material_to_rough"
    ) -> List[Tuple[float, float]]:
        """Find Z intervals where a horizontal line at x_dia passes through the zone.

        Process:
          1. Get the zone's OCP face (for classification) and raw shape (for wires)
          2. Build a horizontal line edge at x_radius spanning Z=-10 to Z=+10
          3. Intersect line against ALL wires of the shape (outer + inner/holes)
          4. Collect intersection Z values
          5. Sort Z values, form candidate segments between consecutive points
          6. Test each segment midpoint against the face (IN = material)
          7. Return intervals where midpoint classifies as IN or ON

        Args:
            x_dia: X position in DIAMETER
            zone_name: Which zone to query

        Returns:
            List of (z_begin, z_terminate) tuples, sorted Z descending.
            z_begin > z_terminate for each pair.
        """
        ocp_face = self._get_ocp_face(zone_name)
        if ocp_face is None:
            return []

        raw_shape = self._get_raw_shape(zone_name)
        wires = self._get_wires(zone_name, raw_shape)
        if not wires:
            return []

        x_radius = x_dia / 2.0

        # Build horizontal line edge spanning well beyond any part geometry
        z_far_pos = 10.0
        z_far_neg = -10.0
        p1 = gp_Pnt(x_radius, z_far_pos, 0.0)
        p2 = gp_Pnt(x_radius, z_far_neg, 0.0)

        try:
            line_edge = BRepBuilderAPI_MakeEdge(p1, p2).Edge()
        except Exception:
            return []

        # Intersect line against each wire and collect Z values
        z_values = set()

        for wire in wires:
            self._intersect_line_wire(line_edge, wire, z_values)

        if not z_values:
            # No intersections — line might be entirely inside or outside.
            # Test a single point to determine.
            if self._point_in_face(ocp_face, x_radius, 0.0):
                # Entire line is inside — but we need actual Z bounds from the face.
                return self._full_extent_interval(ocp_face, x_radius)
            return []

        # Sort Z values descending (highest Z first = closest to face)
        z_sorted = sorted(z_values, reverse=True)

        # Form candidate segments between consecutive intersection points
        # and classify each by midpoint
        intervals = []
        for i in range(len(z_sorted) - 1):
            z_begin = z_sorted[i]
            z_terminate = z_sorted[i + 1]

            # Skip degenerate segments
            if z_begin - z_terminate < TOLERANCE:
                continue

            # Test midpoint
            z_mid = (z_begin + z_terminate) / 2.0
            if self._point_in_face(ocp_face, x_radius, z_mid):
                intervals.append((z_begin, z_terminate))

        return intervals

    def _intersect_line_wire(self, line_edge, wire, z_values: set) -> None:
        """Intersect a line edge against a wire, adding Z values to the set.

        Uses BRepAlgoAPI_Section(wire, line_edge) — OCCT finds all
        intersection points between the line and every edge in the wire.
        """
        try:
            section = BRepAlgoAPI_Section(wire, line_edge)
            section.Build()
            if not section.IsDone():
                return
        except Exception:
            return

        # Extract vertices (intersection points)
        explorer = TopExp_Explorer(section.Shape(), TopAbs_VERTEX)
        while explorer.More():
            vertex = TopoDS.Vertex_s(explorer.Current())
            pnt = BRep_Tool.Pnt_s(vertex)
            z_values.add(round(pnt.Y(), 8))  # Y in sketch plane = Z in lathe
            explorer.Next()

        # Also check edges (collinear overlaps produce edges, not just vertices)
        edge_explorer = TopExp_Explorer(section.Shape(), TopAbs_EDGE)
        while edge_explorer.More():
            edge = TopoDS.Edge_s(edge_explorer.Current())
            curve = BRepAdaptor_Curve(edge)
            z_values.add(round(curve.Value(curve.FirstParameter()).Y(), 8))
            z_values.add(round(curve.Value(curve.LastParameter()).Y(), 8))
            edge_explorer.Next()

    def _point_in_face(self, ocp_face, x_radius: float, z: float) -> bool:
        """Test if a point is inside the face using BRepClass_FaceClassifier.

        Uses gp_Pnt (3D point projected onto face) rather than gp_Pnt2d
        (UV parametric) because the face is planar in the XY plane and
        the 3D classifier correctly maps world coordinates.

        Returns True if the point classifies as IN or ON the face boundary.
        """
        pnt = gp_Pnt(x_radius, z, 0.0)

        try:
            classifier = BRepClass_FaceClassifier(ocp_face, pnt, TOLERANCE)
            state = classifier.State()
            return state == TopAbs_IN or state == TopAbs_ON
        except Exception:
            return False

    def _full_extent_interval(
        self, ocp_face, x_radius: float
    ) -> List[Tuple[float, float]]:
        """When no boundary crossings found but point is inside, find Z extent.

        This handles the case where the horizontal line is entirely within the zone
        (no boundary crossings). We find the Z extent by testing points along Z
        until we find the boundaries.

        In practice this shouldn't happen for the MTR zone at valid X levels,
        but it's a safety fallback.
        """
        # Find Z bounds by scanning — start from Z=0 going negative
        z_top = None
        z_bot = None

        # Scan from +5 to -5 in coarse steps to find approximate bounds
        for z_test in [z * 0.01 for z in range(500, -500, -1)]:
            if self._point_in_face(ocp_face, x_radius, z_test):
                if z_top is None:
                    z_top = z_test
                z_bot = z_test

        if z_top is not None and z_bot is not None and z_top - z_bot > TOLERANCE:
            return [(z_top, z_bot)]
        return []

    def _get_ocp_face(self, zone_name: str):
        """Get the OCP TopoDS_Face for a named zone (cached).

        The boolean cut may produce a TopoDS_Compound. We need to extract
        the actual TopoDS_Face from it for face classification to work.
        """
        if zone_name in self._face_cache:
            return self._face_cache[zone_name]

        face_or_sketch = self._get_zone_object(zone_name)
        if face_or_sketch is None:
            self._face_cache[zone_name] = None
            return None

        ocp_face = self._extract_ocp_face(face_or_sketch)
        self._face_cache[zone_name] = ocp_face
        return ocp_face

    def _get_raw_shape(self, zone_name: str):
        """Get the raw OCP shape (may be Compound) for wire extraction (cached).

        Wire extraction needs the full shape (which may be a Compound from boolean ops)
        because wires live on the compound, not necessarily on a single extracted face.
        """
        if zone_name in self._shape_cache:
            return self._shape_cache[zone_name]

        face_or_sketch = self._get_zone_object(zone_name)
        if face_or_sketch is None:
            self._shape_cache[zone_name] = None
            return None

        raw_shape = self._extract_raw_shape(face_or_sketch)
        self._shape_cache[zone_name] = raw_shape
        return raw_shape

    def _get_wires(self, zone_name: str, raw_shape) -> list:
        """Get all wires (outer + inner) from the raw shape (cached)."""
        if zone_name in self._wire_cache:
            return self._wire_cache[zone_name]

        wires = []
        if raw_shape is None:
            self._wire_cache[zone_name] = wires
            return wires

        # Extract ALL wires from the shape (outer boundary + any holes)
        wire_explorer = TopExp_Explorer(raw_shape, TopAbs_WIRE)
        while wire_explorer.More():
            wires.append(wire_explorer.Current())
            wire_explorer.Next()

        self._wire_cache[zone_name] = wires
        return wires

    def _get_zone_object(self, zone_name: str):
        """Get the Build123d Face/Sketch for a named zone."""
        zone_map = {
            "finished_part": self._zones.finished_part,
            "finish_allowance": self._zones.finish_allowance,
            "material_to_rough": self._zones.material_to_rough,
            "true_face": self._zones.true_face,
            "stock": self._zones.stock_face,
        }
        return zone_map.get(zone_name)

    def _extract_ocp_face(self, face_or_sketch):
        """Extract the underlying OCP TopoDS_Face from a Build123d object.

        Always returns a TopoDS_Face (not a Compound), which is required
        for BRepClass_FaceClassifier to work. Boolean operations often produce
        Compounds wrapped in Build123d Face objects — we dig through to find
        the actual TopoDS_Face.
        """
        if face_or_sketch is None:
            return None

        try:
            # Get the raw wrapped shape regardless of Build123d type
            if isinstance(face_or_sketch, Sketch):
                faces = face_or_sketch.faces()
                if faces:
                    raw = faces[0].wrapped
                else:
                    return None
            elif isinstance(face_or_sketch, Face):
                raw = face_or_sketch.wrapped
            elif hasattr(face_or_sketch, 'wrapped'):
                raw = face_or_sketch.wrapped
            else:
                raw = face_or_sketch

            # If raw is already a TopoDS_Face, return it
            from OCP.TopoDS import TopoDS_Face as OCP_Face_Type
            if isinstance(raw, OCP_Face_Type):
                return raw

            # Otherwise, extract the first TopoDS_Face from the shape (Compound, etc.)
            face_explorer = TopExp_Explorer(raw, TopAbs_FACE)
            if face_explorer.More():
                return TopoDS.Face_s(face_explorer.Current())
        except Exception:
            pass
        return None

    def _extract_raw_shape(self, face_or_sketch):
        """Extract the raw OCP shape from a Build123d object.

        Returns the underlying shape as-is (may be Compound, Face, etc.)
        Used for wire extraction where we need all wires from the full shape.
        """
        if face_or_sketch is None:
            return None

        try:
            if isinstance(face_or_sketch, Sketch):
                faces = face_or_sketch.faces()
                if faces:
                    return faces[0].wrapped
                return None
            if isinstance(face_or_sketch, Face):
                return face_or_sketch.wrapped
            if hasattr(face_or_sketch, 'wrapped'):
                return face_or_sketch.wrapped
            return face_or_sketch
        except Exception:
            pass
        return None
