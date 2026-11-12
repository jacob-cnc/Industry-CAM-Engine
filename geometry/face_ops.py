"""Kernel face operations for planners: first face, move, clip, walk.

Created 2026-11-12 (structure cleanup, step 4b) when raw OCP / build123d moved
out of the planners; the cleanup planner's old face-offset route, whose
face builder and sharp-only offset also lived here briefly, turned out to have
no callers and was removed the same day (hand-math branch). Used by
planners/contour_roughing_planner.py. Planners hold the returned shapes as
OPAQUE HANDLES and only pass them back to these functions.

Coordinates: sketch plane X = radius, Y = Z. Edge records returned to
planners use DIAMETER for X:
    ((start_x_dia, start_z), (end_x_dia, end_z), "LINE", None, 0.0)
    ((start_x_dia, start_z), (end_x_dia, end_z), "ARC", (centre_x_dia, centre_z), radius)
"""
from __future__ import annotations

from typing import Optional

from build123d import BuildLine, BuildSketch, Line, make_face
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.BRepTools import BRepTools, BRepTools_WireExplorer
from OCP.GeomAbs import GeomAbs_Circle, GeomAbs_Line
from OCP.TopAbs import TopAbs_FACE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS
from OCP.gp import gp_Trsf, gp_Vec



def first_ocp_face(shape) -> Optional[object]:
    """The first face of a build123d shape as an OCP face, or None if it has none."""
    faces = shape.faces() if hasattr(shape, "faces") else []
    return faces[0].wrapped if faces else None


def translate_face(ocp_face, dr: float, dz: float):
    """The face moved by (dr, dz) in the sketch plane (X = radius, Y = Z)."""
    tr = gp_Trsf()
    tr.SetTranslation(gp_Vec(dr, dz, 0.0))
    return TopoDS.Face_s(BRepBuilderAPI_Transform(ocp_face, tr, True).Shape())


def clip_to_box(ocp_face, x_min_r: float, x_max_r: float, z_top: float, z_bot: float) -> list:
    """Outer wires of every face of (ocp_face ∩ rectangle), in the kernel's
    face order. Empty list if the rectangle can't be built, the boolean isn't
    done, or nothing is left. Raises on kernel exceptions."""
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
    wires = []
    explorer = TopExp_Explorer(common_op.Shape(), TopAbs_FACE)
    while explorer.More():
        wires.append(BRepTools.OuterWire_s(TopoDS.Face_s(explorer.Current())))
        explorer.Next()
    return wires


def wire_edges(wire) -> list:
    """The wire's edges in traversal order as edge records (see module doc),
    each oriented along the traversal.

    Arcs come as canonical <= 90 deg pieces with the kernel's true sweep
    (geometry/arc_math).

    DEBT: edges that are neither lines nor circles are SILENTLY DROPPED (both
    planners did this). Offsets of lines/arcs only give lines/arcs, so it does
    not trigger today - but a dropped edge would be a missing cut.
    Raises on kernel exceptions.
    """
    from geometry.arc_math import arc_from_kernel, split_at_quadrants
    exp = BRepTools_WireExplorer(wire)
    out = []
    while exp.More():
        edge = exp.Current()
        cur = BRepAdaptor_Curve(edge)
        pf = cur.Value(cur.FirstParameter())
        pl = cur.Value(cur.LastParameter())
        vp = BRep_Tool.Pnt_s(exp.CurrentVertex())
        df = ((vp.X() - pf.X())**2 + (vp.Y() - pf.Y())**2)**0.5
        dl = ((vp.X() - pl.X())**2 + (vp.Y() - pl.Y())**2)**0.5
        ps, pe = (pf, pl) if df <= dl else (pl, pf)
        sd, sz = ps.X() * 2.0, ps.Y()
        ed, ez = pe.X() * 2.0, pe.Y()
        ct = cur.GetType()
        if ct == GeomAbs_Line:
            out.append(((sd, sz), (ed, ez), "LINE", None, 0.0))
        elif ct == GeomAbs_Circle:
            ci = cur.Circle()
            loc = ci.Location()
            pm = cur.Value(0.5 * (cur.FirstParameter() + cur.LastParameter()))
            arc = arc_from_kernel((ps.X(), ps.Y()), (pm.X(), pm.Y()), (pe.X(), pe.Y()),
                                  (loc.X(), loc.Y()), ci.Radius())
            for piece in split_at_quadrants(arc):
                out.append(((piece.start[0] * 2, piece.start[1]),
                            (piece.end[0] * 2, piece.end[1]), "ARC",
                            (loc.X() * 2, loc.Y()), ci.Radius()))
        exp.Next()
    return out


def line_intersection(p0, p1, q0, q1):
    """Where the infinite line through p0, p1 meets the one through q0, q1,
    or None if they are parallel (or a line is degenerate). Points are
    (X diameter, Z); solved by the kernel (IntAna2d) in radius space."""
    from OCP.IntAna2d import IntAna2d_AnaIntersection
    from OCP.gp import gp_Dir2d, gp_Lin2d, gp_Pnt2d

    def lin(a, b):
        d = (b[0] / 2.0 - a[0] / 2.0, b[1] - a[1])
        if abs(d[0]) < 1e-15 and abs(d[1]) < 1e-15:
            return None
        return gp_Lin2d(gp_Pnt2d(a[0] / 2.0, a[1]), gp_Dir2d(*d))

    la, lb = lin(p0, p1), lin(q0, q1)
    if la is None or lb is None:
        return None
    inter = IntAna2d_AnaIntersection(la, lb)
    if not inter.IsDone() or inter.ParallelElements() or inter.IdenticalElements() \
            or inter.NbPoints() != 1:
        return None
    pt = inter.Point(1).Value()
    return (2.0 * pt.X(), pt.Y())


def circle_of(edge):
    """(centre, radius) of a circular edge, else None."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GeomAbs import GeomAbs_Circle
    ad = BRepAdaptor_Curve(edge.wrapped)
    if ad.GetType() != GeomAbs_Circle:
        return None
    c = ad.Circle()
    return (c.Location().X(), c.Location().Y()), c.Radius()
