"""Material removal by the true-scale insert (tool-graphic plan 2026-11-13, T5).

The material a move removes is the insert outline (geometry/tool_outline.py)
swept along the controlled-point path. The outline is convex (every ISO shape,
round, groove blade, thread form), so for each straight step p0 -> p1 the
swept area is exactly the convex hull of the outline at p0 and at p1; arcs
come densified from the interpreter (chord error 2e-5"), so their sweep is a
chain of such hulls. All by Shapely; no hand geometry.

Only feed moves cut (feed, arc, thread). The same sweep also finds, before
anything is cut:
  * RUB   - stock touched by the insert's NON-cutting boundary (anything but
            the nose arc and the two edges either side of it) on a feed move;
  * RAPID - stock in the path of a rapid.
A hit counts only where the material it passes through is thicker than
GRAZE: the nose-radius cusp a pass leaves at a shoulder (~.003 thick for
R.016), grazed by the retract, or contact tangent along a finished wall, is
not a crash or a rub.

Coordinates: (r, z), r = radius.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np
import shapely
from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union

Point = Tuple[float, float]
GRAZE = 0.004            # in: hits thinner than this are grazing contact
EDGE_CLEAR = 2e-4        # in: the non-cutting boundary starts this far from the cutting edges
GRID = 1e-7              # snap-rounding grid for the booleans (as validation/cut_regions)
FEEDS = ("feed", "arc", "thread")


def _snap(g):
    return shapely.set_precision(g, GRID)


SIMPLIFY = 2e-5          # in: outline simplified this close before sweeping


BODY_SIMPLIFY = 1e-4     # in: the rest of the insert (away from the nose)


def outline_polygon(outline) -> Polygon:
    """The insert polygon of a ToolOutline (controlled point at the origin):
    the nose arc at full resolution (it makes the cut surface), the rest of
    the body simplified to BODY_SIMPLIFY. Convex, so the hull of the two."""
    body = Polygon(outline.outline).buffer(0).simplify(BODY_SIMPLIFY)
    nose = outline.cutting_edges[1] if len(outline.cutting_edges) == 3 else outline.outline
    pts = shapely.multipoints(np.concatenate([np.asarray(body.exterior.coords), np.asarray(nose)]))
    return shapely.convex_hull(pts)


def non_cutting_segments(outline) -> np.ndarray:
    """(S, 2, 2) straight pieces of the outline's boundary that are NOT the
    cutting edges (nose + its two edges), pulled back EDGE_CLEAR from them.
    Empty for a round insert (all cutting)."""
    ring = LineString(outline.outline).simplify(SIMPLIFY)
    edges = [LineString(e) for e in outline.cutting_edges if len(e) >= 2]
    back = ring.difference(unary_union(edges).buffer(EDGE_CLEAR)) if edges else Polygon()
    segs = []
    for line in getattr(back, "geoms", [back]):
        if line.is_empty or not hasattr(line, "coords"):
            continue
        c = np.asarray(line.coords)
        segs.extend(np.stack([c[:-1], c[1:]], axis=1))
    return np.asarray(segs).reshape(-1, 2, 2)


def step_hulls(body: Polygon, pts) -> np.ndarray:
    """Convex hull of the body at each pair of consecutive points: the exact
    area a convex body sweeps on that straight step."""
    pts = np.asarray(pts, dtype=float)
    v = np.asarray(body.exterior.coords)[:-1]
    clouds = shapely.multipoints(np.concatenate([v[None] + pts[:-1, None], v[None] + pts[1:, None]], axis=1))
    return shapely.convex_hull(clouds)


def sweep(body: Polygon, pts) -> Polygon:
    """The convex body swept along pts (union of step_hulls)."""
    if len(pts) < 2 or body.is_empty:
        return Polygon()
    return _snap(shapely.union_all(step_hulls(body, pts)))


LEAD_PROBE = 1e-4        # in: how far ahead of a segment's midpoint the lead test looks


def leading_strips(body: Polygon, segs: np.ndarray, p0: np.ndarray, p1: np.ndarray) -> np.ndarray:
    """Strips the segments sweep over while LEADING the body, one per (step,
    segment). A segment leads on a step when a point just ahead of its
    midpoint (LEAD_PROBE along the step) is outside the body - a trailing
    segment sweeps back across the body itself."""
    if len(p0) == 0 or len(segs) == 0:
        return np.array([], dtype=object)
    step = p1 - p0                                                # (N, 2) steps p0 -> p1
    length = shapely.length(shapely.linestrings(np.stack([p0, p1], axis=1)))
    ok = length > 0
    scale = np.where(ok, LEAD_PROBE / np.where(ok, length, 1.0), 0.0)
    mid = segs.mean(axis=1)                                       # (S, 2)
    probe = mid[None] + (step * scale[:, None])[:, None]          # (N, S, 2)
    shapely.prepare(body)
    lead = ~shapely.contains_xy(body, probe[..., 0], probe[..., 1]) & ok[:, None]
    n, k = np.nonzero(lead)
    if len(n) == 0:
        return np.array([], dtype=object)
    a0 = segs[k, 0] + p0[n]
    b0 = segs[k, 1] + p0[n]
    a1 = segs[k, 0] + p1[n]
    b1 = segs[k, 1] + p1[n]
    rings = np.stack([a0, b0, b1, a1, a0], axis=1)
    return shapely.convex_hull(shapely.multipoints(rings))         # a valid strip polygon


@dataclass
class MoveCut:
    removed: object                    # area removed by this move (empty for rapids)
    rub: object                        # non-cutting boundary into stock (feed moves)
    rapid_hit: object                  # rapid into stock


@dataclass
class MaterialRun:
    """Stock left after each move, and what each move hit."""
    stock: object
    after: List[object] = field(default_factory=list)       # material after move k
    cuts: List[Optional[MoveCut]] = field(default_factory=list)

    def before(self, k: int):
        return self.after[k - 1] if k > 0 else self.stock

    @property
    def warnings(self) -> List[Tuple[int, str, object]]:
        """(move index, "rub" | "rapid", area) for every hit, in order."""
        out = []
        for k, c in enumerate(self.cuts):
            if c is None:
                continue
            if not c.rub.is_empty:
                out.append((k, "rub", c.rub))
            if not c.rapid_hit.is_empty:
                out.append((k, "rapid", c.rapid_hit))
        return out


def _hit(region, material):
    """The material in region, if any of it is thicker than GRAZE."""
    g = region.intersection(material)
    if g.is_empty or g.buffer(-GRAZE / 2.0).is_empty:
        return Polygon()
    return g


def run_material(stock, moves) -> MaterialRun:
    """moves: (kind, outline or None, pts) per move, in program order. A move
    with no outline (tool not drawable) sweeps nothing - its warnings can't be
    known; the caller says so."""
    mat = _snap(stock)
    run = MaterialRun(stock=mat)
    cache = {}
    empty = Polygon()
    for kind, outline, pts in moves:
        if outline is None or len(pts) < 2:
            run.after.append(mat)
            run.cuts.append(None)
            continue
        key = id(outline)
        if key not in cache:
            cache[key] = (outline_polygon(outline), non_cutting_segments(outline))
        body, back = cache[key]
        # nothing near the stock: no sweep needed
        reach = box(*LineString(pts).bounds).buffer(_radius(body))
        if mat.is_empty or not reach.intersects(mat):
            run.after.append(mat)
            run.cuts.append(MoveCut(empty, empty, empty))
            continue
        # only the steps where the insert meets the stock matter
        hulls = step_hulls(body, pts)
        shapely.prepare(mat)
        touch = shapely.intersects(mat, hulls)
        if not touch.any():
            cut = MoveCut(empty, empty, empty)
        elif kind in FEEDS:
            swept = _snap(shapely.union_all(hulls[touch]))
            removed = swept.intersection(mat)
            pp = np.asarray(pts, dtype=float)
            strips = leading_strips(body, back, pp[:-1][touch], pp[1:][touch])
            rub = _hit(_snap(shapely.union_all(strips)), mat) if len(strips) else empty
            cut = MoveCut(removed, rub, empty)
            if not removed.is_empty:
                mat = _snap(mat.difference(swept))
        else:
            cut = MoveCut(empty, empty, _hit(_snap(shapely.union_all(hulls[touch])), mat))
        run.after.append(mat)
        run.cuts.append(cut)
    return run


def _radius(body: Polygon) -> float:
    """Distance from the controlled point (origin) to the furthest outline point."""
    return shapely.hausdorff_distance(shapely.points(0.0, 0.0), body.exterior) + 1e-6


def apply_sweeps(material, swept_pieces):
    """material minus the union of swept pieces (the live cut, Run tab)."""
    if material is None or not len(swept_pieces):
        return material
    return _snap(material.difference(shapely.union_all(swept_pieces)))


def stock_box(r_in: float, r_out: float, z_back: float, z_front: float):
    """The bar as a rectangle in (r, z)."""
    return box(r_in, z_back, r_out, z_front)
