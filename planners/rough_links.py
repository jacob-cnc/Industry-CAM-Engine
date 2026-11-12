"""Roughing retracts and approaches (owner rule 2026-11-12).

Each roughing pass gets its exit (retract_moves) and its entry (approach_moves)
here; the pipeline validates exactly these moves and the G-code writer emits
them (until 2026-11-12 the writer used its own retract logic, which the
post-planning validator never saw).

Owner rule:
  * pass 1 retracts to stock OD + .005 (OD) / pilot hole - .001 (ID: pass 1
    may be shallower than .005);
  * pass n retracts to the previous pass's highest X + .005 (OD) / lowest X
    - .005 (ID), arcs included (kernel arc extents); + / - .010 when the pass
    runs off a free end (no stock beyond it), clearing the nose scallops there;
  * a pass that ends at a wall or shoulder (stock just beyond its end) pulls
    off at 45 deg: away from the wall in Z by the same radial distance it
    retracts in X (never back past the pass's own start), else straight in X;
  * the next pass: rapid along Z at that X to its start, rapid in to the
    level already cut there, feed the rest;
  * the LAST pass retracts to the pass-1 target (outside the stock / in the
    pilot hole), so whatever comes next starts clear of all material.

Pockets (owner: "most of the time you'd want to fully exit"): a retract or a
Z traverse at the rule's X is only used inside the CORRIDOR already cleared
there - every Z it crosses must lie in the Z span of an earlier pass whose
path stays on the far side of that X (each pass clears everything beyond its
own path across its own span). Otherwise the move first exits the pocket: to
the nearest X just beyond an earlier pass covering the whole Z range (the
pocket's mouth), or to the pass-1 target if none does. scripts/hand_math/rapid_report.py and the
rapid-collision check (validation/rapid_collision.py) verify the result.

Points are (X diameter, Z).
"""
from __future__ import annotations

import math
from dataclasses import replace
from typing import Callable, List, Optional, Tuple

from geometry.kernel import Arc, r_extent, sweep_piece
from models.moves import MoveType, PassType, ToolMove

OD_CLEAR = 0.005          # retract beyond the previous pass (diameter)
ID_CLEAR = 0.005
FREE_END_CLEAR = 0.010    # ... when the pass runs off a free end: the nose-radius
                          # scallops left on that edge stand up to ~.0023 a side
                          # (owner 2026-11-12)
OD_FIRST_CLEAR = 0.005    # pass 1: beyond stock OD
ID_FIRST_CLEAR = 0.001    # pass 1: inside the pilot hole (pass 1 may be < .005 deep)
FIRST_Z_CLEAR = 0.050     # pass 1 arrives this far in front of the stock face first
_ARCS = (MoveType.ARC_CW, MoveType.ARC_CCW)
_TOL = 1e-6


def pass_x_extent(p) -> Tuple[float, float]:
    """(lowest, highest) X diameter a roughing pass reaches, arcs included. The
    pass starts at (x_level, z_start), where its approach ends."""
    pos = (p.x_level, p.z_start)
    lo = hi = pos[0]
    for m in p.moves:
        if m.move_type in _ARCS:
            s = (pos[0] / 2.0, pos[1])
            e = (m.x / 2.0, m.z)
            c = ((pos[0] + m.center_i) / 2.0, pos[1] + m.center_k)
            # internal ARC_CW = clockwise in (r, z) = negative sweep
            sgn = -1.0 if m.move_type == MoveType.ARC_CW else 1.0
            r0, r1 = r_extent(Arc(s, e, c, math.dist(s, c), sweep_piece(s, e, c, sgn)))
            lo, hi = min(lo, 2.0 * r0), max(hi, 2.0 * r1)
        lo, hi = min(lo, m.x), max(hi, m.x)
        pos = (m.x, m.z)
    return lo, hi


def _end(p) -> Tuple[float, float]:
    return (p.moves[-1].x, p.moves[-1].z) if p.moves else (p.x_level, p.z_end)


def plan_rough_links(passes, stock, is_id: bool, feed: float,
                     material_beyond: Callable[[Tuple[float, float]], bool]) -> list:
    """The roughing passes with approach_moves / retract_moves planned.

    ``material_beyond(point)``: is there stock (or part) at this point - asked
    just past each pass's end to decide the 45 deg pull-off."""
    passes = list(passes)
    if not passes:
        return passes
    side = -1.0 if is_id else 1.0                       # +X is "away" for OD
    first_target = (max(0.0, stock.pilot_hole_dia - ID_FIRST_CLEAR) if is_id
                    else stock.diameter + OD_FIRST_CLEAR)
    extents = [pass_x_extent(p) for p in passes]
    spans = [(min(p.z_start, p.z_end, *(m.z for m in p.moves)) if p.moves else min(p.z_start, p.z_end),
              max(p.z_start, p.z_end)) for p in passes]

    def beyond(x, y):           # is x at or beyond y on the away side?
        return side * (x - y) >= -_TOL

    def corridor_ok(x: float, z_a: float, z_b: float, upto: int) -> bool:
        """Is X = x clear for every Z in [z_a, z_b], given passes 0..upto cut?"""
        if beyond(x, first_target):
            return True                                  # outside the bar / in the pilot hole
        lo, hi = min(z_a, z_b), max(z_a, z_b)
        cover = sorted(spans[j] for j in range(upto + 1)
                       if beyond(x, extents[j][1] if not is_id else extents[j][0]))
        reach = lo
        for a, b in cover:
            if a > reach + _TOL:
                break
            reach = max(reach, b)
            if reach >= hi - _TOL:
                return True
        return reach >= hi - _TOL

    def cleared_level(z: float, upto: int) -> float:
        """The X already cut at Z (the deepest earlier pass level covering it),
        or the pass-1 target if none has."""
        levels = [passes[j].x_level for j in range(upto + 1)
                  if spans[j][0] - _TOL <= z <= spans[j][1] + _TOL]
        if not levels:
            return first_target
        return max(levels) if is_id else min(levels)

    def exit_x(x: float, z_a: float, z_b: float, upto: int) -> float:
        """The X for a move across Z [z_a, z_b]: x itself if its corridor is
        clear, else the nearest X that is - just beyond an earlier pass that
        covers the whole range (the pocket's mouth) - else the pass-1 target."""
        if corridor_ok(x, z_a, z_b, upto):
            return x
        clear = ID_CLEAR if is_id else OD_CLEAR
        cands = sorted({(extents[j][0] - clear) if is_id else (extents[j][1] + clear)
                        for j in range(upto + 1)}, key=lambda c: side * c)
        for c in cands:
            if beyond(c, x) and corridor_ok(c, z_a, z_b, upto):
                return max(0.0, c) if is_id else c
        return first_target

    out = []
    pos: Optional[Tuple[float, float]] = None            # where the previous retract ended
    for i, p in enumerate(passes):
        # --- approach: Z at the current X (exit fully first if needed), in, feed
        approach: List[ToolMove] = []
        start = (p.x_level, p.z_start)
        if pos is None:
            # first pass: arrive in front of the face, outside the material,
            # then straight along Z (a diagonal into a pilot hole clips its mouth)
            approach.append(_rapid(first_target, max(stock.z_start, p.z_start) + FIRST_Z_CLEAR))
            approach.append(_rapid(first_target, p.z_start))
            x_now = first_target
        else:
            x_now = pos[0]
            if abs(pos[1] - p.z_start) > _TOL:
                x_exit = exit_x(x_now, pos[1], p.z_start, i - 1)
                if abs(x_exit - x_now) > _TOL:
                    approach.append(_rapid(x_exit, pos[1]))      # out of the pocket first
                    x_now = x_exit
                approach.append(_rapid(x_now, p.z_start))
        level = cleared_level(p.z_start, i - 1) if i > 0 else first_target
        # rapid only through what is already cut, toward this pass's level
        if side * (x_now - level) > _TOL and side * (level - start[0]) > _TOL:
            approach.append(_rapid(level, p.z_start))
        approach.append(ToolMove(MoveType.FEED, start[0], p.z_start,
                                 feed=feed, pass_type=PassType.TRANSITION))

        # --- retract: owner's target, 45 deg off a wall, full exit outside the corridor
        end = _end(p)
        travel_up = p.z_start >= end[1]                  # pass ran toward -Z
        back = 1.0 if travel_up else -1.0                # Z direction away from the end wall
        wall = material_beyond((end[0], end[1] - back * 0.001))
        clear = (ID_CLEAR if is_id else OD_CLEAR) if wall else FREE_END_CLEAR
        last = i == len(passes) - 1
        # The LAST pass always exits fully: what follows (the cleanup / finish
        # contour approach) rises along Z at the X it is given and knows nothing
        # of the material still standing - from a pocket's X it ran .0225 into
        # the cleanup band of a neck part (2026-11-12, found by the rapid check).
        target = first_target if (i == 0 or last) else (
            extents[i - 1][0] - clear if is_id else extents[i - 1][1] + clear)
        if is_id:
            target = max(0.0, target)
        dz = 0.0
        if wall:
            dz = min(abs(target - end[0]) / 2.0, abs(p.z_start - end[1]))   # 45 deg, <= own length
        z_off = end[1] + back * dz
        if not corridor_ok(target, end[1], z_off, i):
            target = exit_x(target, end[1], z_off, i)
            if wall:
                dz = min(abs(target - end[0]) / 2.0, abs(p.z_start - end[1]))
                z_off = end[1] + back * dz
        retract = [_rapid(target, z_off)]
        pos = (target, z_off)
        out.append(replace(p, approach_moves=tuple(approach), retract_moves=tuple(retract)))
    return out


def _rapid(x, z) -> ToolMove:
    return ToolMove(MoveType.RAPID, x, z, pass_type=PassType.TRANSITION)
