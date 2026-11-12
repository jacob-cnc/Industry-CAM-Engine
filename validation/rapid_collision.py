"""Do the program's rapids touch material that is still there? (basic check)

Replays the G-code as LinuxCNC runs it (rs274, validation/cut_regions.py:
parse_canon) IN ORDER, keeping the material that remains:

    remaining = stock
    feed move  -> remaining -= what the insert sweeps (nose circle + insert outline)
    rapid move -> hit = (what the insert sweeps) & remaining     -> a COLLISION if not empty
                  clearance = distance from the insert sweep to remaining

The insert outline is cut_regions' wedge (front / back edge angles from the tool
table, WEDGE_LEN long); the holder beyond it is not modelled. Coordinates
(r, z) radius space; reported X values are diameters.

Built 2026-11-12 to choose the roughing retract rule for pockets (owner: "use
the tools we've got for gouging/collision detection and run some sims").
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

from validation.cut_regions import (NOSE_QUAD_SEGS, _translate, _wedge, nose_offset,
                                    parse_canon, run_rs274, stock_polygon)

HIT_DEPTH = 0.0002       # in: material thinner than this (largest inscribed circle's
                         # diameter) is contact / polygon noise, not a collision


@dataclass
class RapidReport:
    index: int                           # rapid number in the program (0-based, rapids only)
    section: str
    start: Tuple[float, float]           # (X dia, Z)
    end: Tuple[float, float]
    hit_area: float                      # in^2 of remaining material inside the sweep
    hit_depth: float                     # in, thickest part of it (inscribed circle diameter)
    clearance: float                     # in, insert sweep to remaining material (0 if hit)
    hit_bounds: Optional[Tuple[float, float, float, float]] = None   # X dia min/max, Z min/max

    @property
    def collides(self) -> bool:
        return self.hit_depth > HIT_DEPTH


def _sweep(tool, pts, mode_id: bool):
    off = nose_offset(tool)
    cpts = [(r + off[0], z + off[1]) for r, z in pts]
    R = max(tool.nose_radius, 1e-6)
    g = LineString(cpts).buffer(R, NOSE_QUAD_SEGS) if len(cpts) > 1 \
        else Point(cpts[0]).buffer(R, NOSE_QUAD_SEGS)
    w = _wedge(tool, mode_id)
    if w is not None:
        hulls = [Polygon(_translate(w, *a) + _translate(w, *b)).convex_hull
                 for a, b in zip(cpts, cpts[1:])] or [Polygon(_translate(w, *cpts[0]))]
        g = unary_union([g] + hulls)
    return g


def _depth(geom) -> float:
    """Diameter of the largest circle inside geom (0 for empty / slivers)."""
    import shapely
    if geom.is_empty or geom.area < 1e-12:
        return 0.0
    parts = getattr(geom, "geoms", [geom])
    best = 0.0
    for g in parts:
        if g.geom_type != "Polygon" or g.area < 1e-12:
            continue
        best = max(best, 2.0 * shapely.maximum_inscribed_circle(g, 1e-6).length)
    return best


def check_rapids(gcode: str, plan_result) -> List[RapidReport]:
    """Every rapid of the program with what it hits and its clearance."""
    from models.profile import MachiningMode
    pr = plan_result
    mode_id = pr.profile.mode == MachiningMode.ID
    tools = {pr.tool.tool_number: pr.tool}
    ft = getattr(pr, "finish_tool", None)
    if ft is not None:
        tools[ft.tool_number] = ft
    moves = parse_canon(run_rs274(gcode, tools.values()))
    remaining = stock_polygon(pr.stock, mode_id)
    out: List[RapidReport] = []
    for mv in moves:
        t = tools.get(mv.tool)
        if t is None:
            continue
        sweep = _sweep(t, mv.pts, mode_id)
        if mv.rapid:
            hit = sweep.intersection(remaining)
            area, depth, b = hit.area, _depth(hit), None
            clear = 0.0 if depth > HIT_DEPTH else sweep.distance(remaining)
            if depth > HIT_DEPTH:
                x0, z0, x1, z1 = hit.bounds
                b = (2 * x0, 2 * x1, z0, z1)
            out.append(RapidReport(len(out), mv.section, (2 * mv.pts[0][0], mv.pts[0][1]),
                                   (2 * mv.pts[-1][0], mv.pts[-1][1]), area, depth, clear, b))
        else:
            remaining = remaining.difference(sweep)
            if not remaining.is_valid:
                remaining = remaining.buffer(0)
    return out


def summary(reports: List[RapidReport]) -> dict:
    """Counts for regression output: collisions, hit area, closest rapid."""
    hits = [r for r in reports if r.collides]
    clear = [r.clearance for r in reports if not r.collides]
    return {"rapids": len(reports), "collisions": len(hits),
            "hit_area": sum(r.hit_area for r in hits),
            "max_depth": max((r.hit_depth for r in hits), default=0.0),
            "min_clearance": min(clear) if clear else None,
            "first_collision": (None if not hits else
                                {"section": hits[0].section, "start": hits[0].start,
                                 "end": hits[0].end, "area": hits[0].hit_area,
                                 "depth": hits[0].hit_depth,
                                 "bounds": hits[0].hit_bounds})}
