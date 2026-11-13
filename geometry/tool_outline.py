"""True-scale insert outline for the screen graphic (tool-graphic plan 2026-11-13).

Frame: the tool's CONTROLLED POINT is at (0, 0). That is LinuxCNC's imaginary
tip for Q1-Q8 and the nose centre for Q9: the point the work position (DRO)
reports once the tool's offsets are applied. Coordinates are (r, z) in inches:
r = radius (X / 2), z = Z, the same space the screen graphs plot.

Placement:
  * nose centre = controlled point - nose_radius * Q direction
    (models.tool.nose_centre_offset, LinuxCNC 2.9.6 Fig 2.16, front-tool lathe);
  * the insert's cutting corner is turned so its two edges leave at the tool
    table's front / back angles (I / J). Angles are measured as in
    geometry/tool_reach.py: from the feed direction round toward the air side.
    Q1-Q4 give that frame directly (feed along the corner's Z side, air
    opposite its X side); Q6 / Q8 use the Q2 / Q3 frame; Q5 / Q7 face along Z;
  * the body is the ISO shape at its true inscribed circle (IC), every corner
    rounded with the nose radius.

Owner decisions (2026-11-13): insert only - no holder, no boring bar.

Everything is built by the kernel (build123d / OCCT: rectangles, rotations,
booleans, 2D fillets); no trigonometry here (owner rule: no hand math in
geometry/).
"""

from __future__ import annotations

import functools
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import build123d as bd

from models.tool import InsertSpec, Q_TIP_DIRECTION

Point = Tuple[float, float]          # (r, z)

# Size used when the insert size is not known (drawn, but labelled).
NOMINAL_IC = {"thread": 0.375, "groove": 0.25}
NOMINAL_IC_DEFAULT = 0.5

# Q -> (feed direction, air direction) as angles in the kernel's XY plane,
# where X = Z (machine) and Y = r. 0 = +Z, 90 = +r, 180 = -Z, 270 = -r.
_FRAMES = {
    1: (0.0, 90.0), 2: (180.0, 90.0), 3: (180.0, 270.0), 4: (0.0, 270.0),
    5: (270.0, 180.0), 6: (180.0, 90.0), 7: (270.0, 0.0), 8: (180.0, 270.0),
    9: (180.0, 90.0),
}

# Points sampled per arc for drawing (the arc's true centre / radius are kept).
_ARC_SAMPLES = 24


@dataclass(frozen=True)
class ToolOutline:
    """The insert, in (r, z) inches, controlled point at (0, 0)."""
    outline: List[Point]                     # closed polygon (first point repeated last)
    nose_centre: Point
    nose_radius: float
    cutting_edges: List[List[Point]]         # polylines: front edge, nose arc, back edge
    ic: float                                # size drawn
    size_known: bool                         # False: drawn at a nominal size
    notes: List[str] = field(default_factory=list)

    def translated(self, r: float, z: float) -> "ToolOutline":
        """The same outline with its controlled point at (r, z)."""
        def mv(p):
            return (p[0] + r, p[1] + z)
        return ToolOutline([mv(p) for p in self.outline], mv(self.nose_centre),
                           self.nose_radius, [[mv(p) for p in e] for e in self.cutting_edges],
                           self.ic, self.size_known, list(self.notes))


# ---------------------------------------------------------------------------
# Kernel shapes. Each is built with its cutting corner on +X (kernel XY),
# corner bisector along -X into the body.
# ---------------------------------------------------------------------------

def _half_plane(normal_deg: float, dist: float, big: float):
    """Region {p : n . p <= dist}, n at normal_deg (a big rectangle)."""
    return bd.Rot(0, 0, normal_deg) * bd.Pos(dist - big / 2.0, 0) * bd.Rectangle(big, big)


def _intersect(planes):
    out = planes[0]
    for p in planes[1:]:
        out = out & p
    return out


def _body(shape: str, ic: float, included: float):
    big = 20.0 * max(ic, 0.1)
    h = ic / 2.0
    if shape == "R":
        return bd.Circle(h)
    if shape == "T" or (shape == "thread" and abs(included - 60.0) < 1e-6):
        return _intersect([_half_plane(a, h, big) for a in (180.0, 60.0, -60.0)])
    if shape == "W":                     # 80 deg trigon: corners 80 / 160 alternating
        return _intersect([_half_plane(a, h, big) for a in (50.0, 70.0, 170.0, 190.0, 290.0, 310.0)])
    if shape == "thread":                # 55 / 29 deg forms: the tooth wedge cut to the IC triangle
        tri = _intersect([_half_plane(a, h, big) for a in (180.0, 60.0, -60.0)])
        corner_x = ic                    # the triangle's +X corner (circumradius = 2 x inradius)
        side = 90.0 - included / 2.0
        wedge = _intersect([bd.Pos(corner_x, 0) * _half_plane(side, 0.0, big),
                            bd.Pos(corner_x, 0) * _half_plane(-side, 0.0, big)])
        return tri & wedge
    # rhombic (C, D, V, S) and custom: two strips of width IC crossing at the
    # included angle -> the acute corners lie on the X axis.
    return (bd.Rot(0, 0, included / 2.0) * bd.Rectangle(big, ic)) & \
           (bd.Rot(0, 0, -included / 2.0) * bd.Rectangle(big, ic))


def _faces_wire(sk):
    return sk.faces()[0].outer_wire()


def _sample_edge(e) -> List[Point]:
    """Points along an edge. Arcs include their quadrant points, so the drawn
    outline reaches the arc's true X / Z extremes (the touch-off lines)."""
    if e.geom_type.name != "CIRCLE":
        ts = [0.0, 1.0]
    else:
        ts = {i / _ARC_SAMPLES for i in range(_ARC_SAMPLES + 1)}
        c, rad = e.arc_center, e.radius
        for q in (bd.Vector(rad, 0), bd.Vector(0, rad), bd.Vector(-rad, 0), bd.Vector(0, -rad)):
            pt = c + q                                  # the circle's X / Z extreme
            if e.distance_to(pt) < 1e-9:
                t = e.param_at_point(pt)
                if 0.0 < t < 1.0:
                    ts.add(t)
        ts = sorted(ts)
    return [((e @ t).Y, (e @ t).X) for t in ts]


def _ordered_edges(sk):
    return list(_faces_wire(sk).order_edges()) if hasattr(_faces_wire(sk), "order_edges") \
        else list(_faces_wire(sk).edges())


def _polyline(edges) -> List[Point]:
    pts: List[Point] = []
    for e in edges:
        seg = _sample_edge(e)
        if pts and abs(pts[-1][0] - seg[0][0]) + abs(pts[-1][1] - seg[0][1]) > 1e-9:
            seg = seg[::-1]
        pts.extend(seg if not pts else seg[1:])
    return pts


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=64)
def tool_outline(spec: InsertSpec) -> ToolOutline:
    """The true-scale outline of this insert, controlled point at (0, 0).

    Raises ValueError (with an operator-readable reason) when the tool table
    does not describe a drawable insert; the screens then keep the dot.
    """
    q = spec.orientation if spec.orientation in _FRAMES else 2
    r = max(float(spec.nose_radius), 0.0)
    dr, dz = Q_TIP_DIRECTION[q]
    centre = (-dr * r, -dz * r)                    # (r, z), nose centre
    notes: List[str] = []
    size_known = spec.ic > 0
    ic = spec.ic if size_known else NOMINAL_IC.get(spec.shape, NOMINAL_IC_DEFAULT)
    if not size_known:
        notes.append(f"insert size unknown - drawn at a nominal {ic:.3f} IC")

    if spec.shape == "groove":
        return _groove(spec, q, r, centre, ic, size_known, notes)
    if spec.shape == "R":
        return _round(spec, r, centre, ic, size_known, notes)
    if spec.front_angle == 0.0 and spec.back_angle == 0.0:
        raise ValueError("edge angles unknown (I0 J0) - set the insert or its angles to draw it")

    included = spec.back_angle - spec.front_angle
    if included <= 0.0 or included >= 180.0:
        raise ValueError(f"insert angles I{spec.front_angle:g} J{spec.back_angle:g} "
                         "do not make a corner (J must be greater than I)")
    shape = spec.shape if spec.shape in ("C", "D", "V", "T", "S", "W", "thread") else "custom"
    body = _body(shape, ic, included)
    if r > 0.0:
        body = bd.fillet(body.vertices(), r)

    # The cutting corner's nose arc: the arc whose centre is furthest along +X.
    arcs = [e for e in body.edges() if e.geom_type.name == "CIRCLE"]
    nose = max(arcs, key=lambda e: e.arc_center.X) if arcs else None
    if nose is not None:
        local_centre = nose.arc_center
    else:                                          # sharp corner: the vertex on +X
        v = max(body.vertices(), key=lambda v: v.X)
        local_centre = bd.Vector(v.X, v.Y, 0)

    # Turn the corner so the body bisector points along the tool table's
    # (I + J) / 2 direction, then put the nose centre where Q says.
    feed, air = _FRAMES[q]
    sense = 1.0 if (air - feed) % 360.0 == 90.0 else -1.0
    bisector = feed + sense * (spec.front_angle + spec.back_angle) / 2.0
    turn = bisector - 180.0
    placed = bd.Pos(centre[1], centre[0]) * bd.Rot(0, 0, turn) * \
        bd.Pos(-local_centre.X, -local_centre.Y) * body

    edges = _ordered_edges(placed)
    outline = _polyline(edges)
    if outline and outline[0] != outline[-1]:
        outline.append(outline[0])

    cutting = _cutting_edges(edges, centre, r)
    return ToolOutline(outline, centre, r, cutting, ic, size_known, notes)


def _cutting_edges(edges, centre: Point, r: float) -> List[List[Point]]:
    """The nose arc and the two straight edges either side of it."""
    if r <= 0.0:
        # sharp corner: the two edges meeting nearest the controlled point
        near = sorted(edges, key=lambda e: min(abs((e @ t).X - centre[1]) + abs((e @ t).Y - centre[0])
                                                for t in (0.0, 1.0)))[:2]
        return [_sample_edge(e) for e in near]
    idx = None
    for i, e in enumerate(edges):
        if e.geom_type.name == "CIRCLE":
            c = e.arc_center
            if abs(c.X - centre[1]) < 1e-7 and abs(c.Y - centre[0]) < 1e-7:
                idx = i
                break
    if idx is None:
        return []
    n = len(edges)
    return [_sample_edge(edges[(idx - 1) % n]), _sample_edge(edges[idx]),
            _sample_edge(edges[(idx + 1) % n])]


def _round(spec, r, centre, ic, size_known, notes) -> ToolOutline:
    """Round insert: a circle of the insert diameter about the nose centre."""
    rad = ic / 2.0
    if spec.orientation != 9 and r > 0 and abs(rad - r) > 1e-4:
        notes.append(f"round insert: tool table nose radius {r:.4f} is not half the "
                     f"insert diameter {ic:.4f}")
    if spec.orientation == 9:
        centre = (0.0, 0.0)
    circle = bd.Pos(centre[1], centre[0]) * bd.Circle(rad)
    edges = _ordered_edges(circle)
    outline = _polyline(edges)
    return ToolOutline(outline, centre, rad, [outline], ic, size_known, notes)


def _groove(spec, q, r, centre, length, size_known, notes) -> ToolOutline:
    """Grooving / parting blade: blade width along Z, `length` away from the
    work (the air side), both tip corners rounded with the nose radius. The
    controlled-point corner is the Q corner; Q6 / Q8 centre the blade."""
    w = spec.blade_width
    if w <= 0.0:
        w = max(2.0 * r, 0.125)
        notes.append(f"blade width not set - drawn {w:.3f} wide")
    dr, dz = Q_TIP_DIRECTION[q]
    up = -1.0 if dr > 0 else 1.0                   # body goes away from the tip side in r
    if dz < 0:
        z0, z1 = 0.0, w
    elif dz > 0:
        z0, z1 = -w, 0.0
    else:
        z0, z1 = -w / 2.0, w / 2.0
    r0, r1 = (0.0, length) if up > 0 else (-length, 0.0)
    rect = bd.Pos((z0 + z1) / 2.0, (r0 + r1) / 2.0) * bd.Rectangle(z1 - z0, r1 - r0)
    tip_r = r0 if up > 0 else r1
    if r > 0.0:
        tips = [v for v in rect.vertices() if abs(v.Y - tip_r) < 1e-9]
        rect = bd.fillet(tips, min(r, w / 2.0 - 1e-6) if w / 2.0 <= r else r)
    edges = _ordered_edges(rect)
    outline = _polyline(edges)
    if outline and outline[0] != outline[-1]:
        outline.append(outline[0])
    tip_edges = [_sample_edge(e) for e in edges
                 if min(abs((e @ 0.0).Y - tip_r), abs((e @ 1.0).Y - tip_r)) < r + 1e-6]
    return ToolOutline(outline, centre, r, tip_edges, length, size_known, notes)
