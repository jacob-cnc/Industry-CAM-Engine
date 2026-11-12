"""Face operations planners ask the kernel for: build, offset, move, clip, walk.

Moved verbatim from planners/cleanup_planner.py and
planners/contour_roughing_planner.py on 2026-11-12 (structure cleanup, step 4b)
so raw OCP / build123d live only in geometry/. Planners hold the returned
shapes as OPAQUE HANDLES and only pass them back to these functions; they
never call methods on them. Behaviour is unchanged on purpose - the known
debts are listed per function and in
docs/handoffs/2026-11-12-structure-cleanup-log.md for the hand-math branch.

Coordinates: sketch plane X = radius, Y = Z. Edge records returned to
planners use DIAMETER for X:
    ((start_x_dia, start_z), (end_x_dia, end_z), "LINE", None, 0.0)
    ((start_x_dia, start_z), (end_x_dia, end_z), "ARC", (centre_x_dia, centre_z), radius)
"""
from __future__ import annotations

import math
from typing import List, Optional

from build123d import BuildLine, BuildSketch, Kind, Line, RadiusArc, make_face
from build123d import offset as b3d_offset
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

from models.constants import TOLERANCE
from models.profile import SegmentType


def face_from_coords_polyline_quadrants(coords: List[dict]):
    """Closed face through `coords` (dicts with x_radius, z, type, radius,
    optional quadrant / quadrant_sign), lines and RadiusArcs between them.

    DEBT (hand-math branch): quadrant arcs with unequal legs are drawn as a
    64-segment ELLIPSE POLYLINE. The canonical builder
    (zone_builder._build_face_from_coords) makes them true circular quarters
    (owner 2026-11-11: ellipses are retired). Only cleanup_planner uses this.
    Raises on any kernel failure.
    """
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

                if target.get("quadrant", False):
                    quadrant_sign = target.get("quadrant_sign", 1)
                    _dx = tx - cx
                    _dz = tz - cz
                    _same_x = abs(_dx) < TOLERANCE
                    _same_z = abs(_dz) < TOLERANCE

                    if _same_x or _same_z:
                        _arc_r = abs(_dz) if _same_x else abs(_dx)
                        _signed_r = -_arc_r * quadrant_sign
                        RadiusArc((cx, cz), (tx, tz), _signed_r)
                    else:
                        _b, _a = abs(_dx), abs(_dz)
                        if quadrant_sign == 1:
                            _ecx, _ecz = cx, tz
                            _sx = 1.0 if _dx > 0 else -1.0
                            _sz = -1.0 if _dz > 0 else 1.0
                        else:
                            _ecx, _ecz = tx, cz
                            _sx = -1.0 if _dx > 0 else 1.0
                            _sz = 1.0 if _dz > 0 else -1.0
                        _npts = 64
                        for _j in range(_npts):
                            _t0 = (math.pi / 2.0) * _j / _npts
                            _t1 = (math.pi / 2.0) * (_j + 1) / _npts
                            if quadrant_sign == 1:
                                _x0 = _ecx + _sx * _b * math.sin(_t0)
                                _z0 = _ecz + _sz * _a * math.cos(_t0)
                                _x1 = _ecx + _sx * _b * math.sin(_t1)
                                _z1 = _ecz + _sz * _a * math.cos(_t1)
                            else:
                                _x0 = _ecx + _sx * _b * math.cos(_t0)
                                _z0 = _ecz + _sz * _a * math.sin(_t0)
                                _x1 = _ecx + _sx * _b * math.cos(_t1)
                                _z1 = _ecz + _sz * _a * math.sin(_t1)
                            if abs(_x0 - _x1) > 1e-10 or abs(_z0 - _z1) > 1e-10:
                                Line((_x0, _z0), (_x1, _z1))
                elif target["type"] == SegmentType.ARC and target["radius"] != 0.0:
                    RadiusArc((cx, cz), (tx, tz), target["radius"])
                else:
                    Line((cx, cz), (tx, tz))
        make_face()
    return sketch.sketch


def offset_face_sharp_only(face, amount: float):
    """build123d offset with sharp (Kind.INTERSECTION) joins and NO fallback.

    DEBT (hand-math branch): cleanup_planner's choice; everything else uses
    kernel_offset.offset_face (sharp, then a logged rounded-join fallback and
    a readable KernelOffsetError). Raises on kernel failure.
    """
    return b3d_offset(face, amount=amount, kind=Kind.INTERSECTION)


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


def wire_edges(wire, *, split_arcs: bool) -> list:
    """The wire's edges in traversal order as edge records (see module doc),
    each oriented along the traversal.

    split_arcs=True: arcs come as canonical <= 90 deg pieces with the kernel's
    true sweep (geometry/arc_math, contour roughing). False: whole arcs (cleanup).

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
            if split_arcs:
                pm = cur.Value(0.5 * (cur.FirstParameter() + cur.LastParameter()))
                arc = arc_from_kernel((ps.X(), ps.Y()), (pm.X(), pm.Y()), (pe.X(), pe.Y()),
                                      (loc.X(), loc.Y()), ci.Radius())
                for piece in split_at_quadrants(arc):
                    out.append(((piece.start[0] * 2, piece.start[1]),
                                (piece.end[0] * 2, piece.end[1]), "ARC",
                                (loc.X() * 2, loc.Y()), ci.Radius()))
            else:
                out.append(((sd, sz), (ed, ez), "ARC", (loc.X() * 2.0, loc.Y()), ci.Radius()))
        exp.Next()
    return out
