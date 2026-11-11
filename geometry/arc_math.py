"""Single owner of circular-arc math (Phase 0 of the arc-segment strategy,
docs/handoffs/2026-11-10-arc-segment-strategy.md).

Frame: RADIUS space, (r, z) = (X radius, Z). Sweep is the signed angle of
travel around the centre in that frame (positive = counter-clockwise with r
to the right and z up, i.e. angle measured from +r toward +z).

Internal move convention (unchanged, used by every planner and validator):
    sweep < 0  ->  MoveType.ARC_CW
    sweep > 0  ->  MoveType.ARC_CCW
outputs/gcode_dialect.py translates that to LinuxCNC G02/G03; nothing else
should map a sweep to a move type or a G-word.

An arc is identified by start, end, centre AND sweep. Never infer the sweep
from start/end/centre alone: that is ambiguous at 180 deg and wrong above it
(a concave 180 deg arc offset for the cleanup pass is 186 deg). Read it from
the geometry kernel (start -> interior point -> end) or carry it from the
operator's explicit choice.

Canonical pieces: arcs leaving the kernel are split at the quadrant
boundaries of their centre (0/90/180/270 deg). Each piece is <= 90 deg and
monotonic in r and z, so legacy "shorter sweep" consumers are correct on it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Tuple

Point = Tuple[float, float]
HALF_PI = math.pi / 2.0


def wrap(a: float) -> float:
    """Angle to (-pi, pi]."""
    a = (a + math.pi) % (2.0 * math.pi) - math.pi
    return math.pi if a == -math.pi else a


def angle_of(p: Point, c: Point) -> float:
    return math.atan2(p[1] - c[1], p[0] - c[0])


def sweep_through(start: Point, mid: Point, end: Point, centre: Point) -> float:
    """Signed sweep of the arc start -> mid -> end about centre (any size
    below 360 deg; mid is any interior point, e.g. the kernel's mid-parameter
    point, which does not depend on edge orientation)."""
    a0, am, a1 = angle_of(start, centre), angle_of(mid, centre), angle_of(end, centre)
    return wrap(am - a0) + wrap(a1 - am)


def short_sweep(start: Point, end: Point, centre: Point) -> float:
    """The shorter sweep start -> end. ONLY valid when the arc is known to be
    < 180 deg (e.g. a canonical quadrant piece)."""
    return wrap(angle_of(end, centre) - angle_of(start, centre))


@dataclass(frozen=True)
class Arc:
    """A circular arc in radius space with an explicit sweep."""
    start: Point
    end: Point
    centre: Point
    radius: float
    sweep: float            # signed, radians

    @property
    def is_cw(self) -> bool:
        return self.sweep < 0

    def point_at(self, t: float) -> Point:
        """Point at fraction t (0 = start, 1 = end) along the sweep."""
        a = angle_of(self.start, self.centre) + self.sweep * t
        return (self.centre[0] + self.radius * math.cos(a),
                self.centre[1] + self.radius * math.sin(a))

    def length(self) -> float:
        return abs(self.sweep) * self.radius


def arc_from_kernel(start: Point, mid: Point, end: Point, centre: Point,
                    radius: float) -> Arc:
    return Arc(start, end, centre, radius, sweep_through(start, mid, end, centre))


def split_at_quadrants(arc: Arc, min_len: float = 1e-5) -> List[Arc]:
    """Split at the quadrant boundaries of the centre that lie strictly
    inside the sweep. Pieces shorter than min_len (chord) are merged into the
    previous piece, so a piece is at most 90 deg plus such a sliver (an arc
    ending a hair past a quadrant line, within kernel tolerance) - always far
    below 180 deg, which is what the short-sweep rule needs."""
    a0 = angle_of(arc.start, arc.centre)
    sgn = 1.0 if arc.sweep > 0 else -1.0
    total = abs(arc.sweep)
    cuts = []
    k = math.floor(a0 / HALF_PI) if sgn > 0 else math.ceil(a0 / HALF_PI)
    while True:
        k += sgn
        travel = sgn * (k * HALF_PI - a0)
        if travel >= total - 1e-12:
            break
        if travel > 1e-12:
            cuts.append(a0 + sgn * travel)
    pts = [arc.start] + [(arc.centre[0] + arc.radius * math.cos(b),
                          arc.centre[1] + arc.radius * math.sin(b)) for b in cuts] + [arc.end]
    pieces: List[Arc] = []
    for p, q in zip(pts, pts[1:]):
        if pieces and math.dist(p, q) < min_len:
            last = pieces[-1]
            pieces[-1] = Arc(last.start, q, arc.centre, arc.radius,
                             last.sweep + sweep_piece(p, q, arc.centre, sgn))
            continue
        pieces.append(Arc(p, q, arc.centre, arc.radius, sweep_piece(p, q, arc.centre, sgn)))
    return pieces


def sweep_piece(p: Point, q: Point, centre: Point, sgn: float) -> float:
    """Sweep from p to q in direction sgn, for spans of at most one quadrant
    (plus rounding): the short sweep with the requested sign."""
    s = wrap(angle_of(q, centre) - angle_of(p, centre))
    if s * sgn < 0 and abs(s) > 1e-9:
        s += sgn * 2.0 * math.pi
    return s


def merge_co_circular(arcs: List[Arc], tol: float = 1e-7) -> List[Arc]:
    """Join consecutive pieces of the same circle travelled the same way
    (inverse of split_at_quadrants) while the total stays below 360 deg."""
    out: List[Arc] = []
    for a in arcs:
        if out:
            b = out[-1]
            if (math.dist(b.end, a.start) < tol and math.dist(b.centre, a.centre) < tol
                    and abs(b.radius - a.radius) < tol and b.sweep * a.sweep > 0
                    and abs(b.sweep + a.sweep) < 2.0 * math.pi - 1e-6):
                out[-1] = Arc(b.start, a.end, b.centre, b.radius, b.sweep + a.sweep)
                continue
        out.append(a)
    return out
