"""Can this tool reach every part of the finished contour? (arc strategy Phase 1)

docs/handoffs/2026-11-10-arc-segment-strategy.md, Principle D (tool-reach
checks; OD and ID differ only by a mirror).

Model. Work in the tool's own frame: feeding toward the chuck (-Z), material
BELOW the contour (OD). ID mirrors r (material is outside); a left-hand tool
mirrors Z (and the direction of travel is reversed to stay canonical). Measure
a direction's angle phi from -Z round toward +r (air side): -Z = 0, +r = 90,
+Z = 180, -r = -90.

The insert is a wedge at the nose between its front edge (angle F) and back
edge (angle B), from the tool table (I / J; CNMG in a 95 deg holder = 95 /
175, VNMG neutral = 72.5 / 107.5). At a point where the contour runs in
direction t (in the direction the finish pass travels), the air is the half
plane [phi(t), phi(t) + 180]. The wedge fits only if

    phi(t) <= F            the contour may rise no steeper than the front edge
    phi(t) >= B - 180      and fall no steeper than the back edge's clearance

Checked at every tangent the contour has (both ends of every line, both ends
and every quadrant point of every arc, corner breaks included), so concave
corners are covered too (each side is checked against its own edge).

So a CNMG at 95/175 climbs a square shoulder (90 <= 95) but can follow a
falling contour only 5 deg: a groove wall, the back of a bead, a back taper
need a tool with more back clearance (VNMG 72.5 deg).
The nose radius does not change the tangents; it is ignored here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

from geometry.arc_entry import quadrant_centre, radius_arc_centre, radius_arc_sweep

# A violation smaller than this (degrees) is not reported: tool-table angles are
# insert defaults, not measured holders.
REACH_TOL_DEG = 1.0


@dataclass(frozen=True)
class ReachProblem:
    x_dia: float            # where (start of the offending piece), diameter
    z: float
    phi: float              # contour direction in the tool frame, degrees
    limit: float            # the tool's limit it breaks, degrees
    kind: str               # "rise" (front edge) or "fall" (back edge)


def _tangents_of(c0: dict, c1: dict) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
    """[(point (r, z), unit travel direction)] along one contour piece c0 -> c1
    (coords from geometry.zone_builder._profile_to_radius_coords)."""
    p0 = (c0["x_radius"], c0["z"])
    p1 = (c1["x_radius"], c1["z"])
    d = (p1[0] - p0[0], p1[1] - p0[1])
    L = math.hypot(*d)
    if L < 1e-9:
        return []
    centre, sweep, R = None, 0.0, 0.0
    if c1.get("quadrant", False):
        centre = quadrant_centre(p0, p1, c1.get("quadrant_sign", 1))
        a0 = math.atan2(p0[1] - centre[1], p0[0] - centre[0])
        a1 = math.atan2(p1[1] - centre[1], p1[0] - centre[0])
        sweep = math.atan2(math.sin(a1 - a0), math.cos(a1 - a0))
        R = math.hypot(p0[0] - centre[0], p0[1] - centre[1])
    elif abs(c1.get("radius", 0.0) or 0.0) > 1e-9 and str(c1.get("type", "")).lower().endswith("arc"):
        r = c1["radius"]
        centre = radius_arc_centre(p0, p1, r)
        if centre is not None:
            sweep = radius_arc_sweep(p0, p1, centre, r)
            R = abs(r)
    if centre is None or abs(sweep) < 1e-9 or R < 1e-9:
        u = (d[0] / L, d[1] / L)
        return [(p0, u), (p1, u)]
    a0 = math.atan2(p0[1] - centre[1], p0[0] - centre[0])
    angles = [a0, a0 + sweep]
    k = math.ceil(min(a0, a0 + sweep) / (math.pi / 2))
    while k * math.pi / 2 < max(a0, a0 + sweep):
        angles.append(k * math.pi / 2)                 # quadrant points: tangent extremes
        k += 1
    s = 1.0 if sweep > 0 else -1.0
    out = []
    for a in sorted(angles, key=lambda a: (a - a0) * s):
        pt = (centre[0] + R * math.cos(a), centre[1] + R * math.sin(a))
        out.append((pt, (-s * math.sin(a), s * math.cos(a))))
    return out


def contour_tangents(profile) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
    """Every (point, unit direction) the finished contour has, in profile order,
    corner breaks included. Radius space."""
    from geometry.arc_entry import normalize_profile
    from geometry.zone_builder import _profile_to_radius_coords
    coords = _profile_to_radius_coords(normalize_profile(profile))
    out = []
    for c0, c1 in zip(coords, coords[1:]):
        out.extend(_tangents_of(c0, c1))
    return out


def _phi(t, mode_id: bool, left_hand: bool) -> float:
    tr, tz = t
    if mode_id:
        tr = -tr
    if left_hand:
        tr, tz = -tr, tz           # mirror Z (tz -> -tz) and reverse travel (-t)
    return math.degrees(math.atan2(tr, -tz))


def tool_applies(tool) -> bool:
    """Only turning / boring tools with known edge angles are checked."""
    from models.tool import ToolType
    f, b = getattr(tool, "front_angle", 0.0), getattr(tool, "back_angle", 0.0)
    if tool.tool_type not in (ToolType.TURNING, ToolType.BORING):
        return False
    return not (f == 0.0 and b == 0.0) and b > f


def reach_problems(profile, tool, tol_deg: float = REACH_TOL_DEG) -> List[ReachProblem]:
    """Places on the finished contour this tool's insert cannot follow. Empty
    when the tool's edge angles are unknown (0 / 0) or it is not a turning or
    boring tool."""
    from models.profile import MachiningMode
    from models.tool import ToolDirection
    if not tool_applies(tool):
        return []
    F, B = tool.front_angle, tool.back_angle
    mode_id = profile.mode == MachiningMode.ID
    left = tool.direction == ToolDirection.LEFT
    out: List[ReachProblem] = []
    for pt, t in contour_tangents(profile):
        phi = _phi(t, mode_id, left)
        if phi > F + tol_deg:
            out.append(ReachProblem(2 * pt[0], pt[1], phi, F, "rise"))
        elif phi < B - 180.0 - tol_deg:
            out.append(ReachProblem(2 * pt[0], pt[1], phi, B - 180.0, "fall"))
    return out


def reach_messages(profile, tool) -> List[str]:
    """Operator wording, one line per distinct place (worst first)."""
    from models.profile import MachiningMode
    probs = reach_problems(profile, tool)
    if not probs:
        return []
    seen, msgs = set(), []
    od = profile.mode != MachiningMode.ID
    name = f"T{tool.tool_number}" + (f" ({tool.description})" if tool.description else "")
    for p in sorted(probs, key=lambda p: -abs(p.phi - p.limit)):
        key = (round(p.x_dia, 3), round(p.z, 3), p.kind)
        if key in seen:
            continue
        seen.add(key)
        if p.kind == "fall":
            angle = -p.phi
            clear = -p.limit
            what = ("falls toward the chuck" if od else "opens up toward the chuck")
            msgs.append(
                f"{name} can't follow the contour at X{p.x_dia:.4f} Z{p.z:.4f}: it {what} at "
                f"{angle:.1f} deg but the back edge clears only {clear:.1f} deg "
                f"(front/back {tool.front_angle:g}/{tool.back_angle:g}). The insert would rub "
                f"or gouge there. Use a tool with at least {angle:.0f} deg of back clearance "
                f"(back angle {180 - angle:.0f} or less, e.g. a 35 deg VNMG in a neutral holder "
                f"has 72.5), or change the contour.")
        else:
            msgs.append(
                f"{name} can't follow the contour at X{p.x_dia:.4f} Z{p.z:.4f}: it "
                f"{'climbs' if od else 'steps in'} at {p.phi:.1f} deg (an undercut beyond "
                f"the front edge at {p.limit:g} deg). Use a tool whose front angle is at least "
                f"{p.phi:.0f}, a left-hand tool, or change the contour.")
    return msgs


# ----------------------------------------------------------------------
# Leave what the tool can't reach (owner decision 2026-11-11)
# ----------------------------------------------------------------------
#
# Instead of refusing the program, the finished contour is replaced by the one
# the insert CAN follow: where the contour falls (or climbs) more steeply than
# the insert allows, the stretch is bridged by a straight line at the insert's
# limit angle, from where the trouble starts to where that line meets the
# contour again. Everything downstream (roughing, finish, validation, G-code)
# runs unchanged on that contour, so the unreachable material is simply left on
# the part, and each region is reported with its X/Z range, why, and which
# inserts from pipeline/insert_geometry_lookup.py would reach it. The operator
# cuts it in its own block with a suitable tool. Multi-tool segment builds that
# know what is already cut are future work.
#
# Why the line is exact: the material a wedge-shaped tool can never remove is
# the part swept along the wedge's edge directions (a point is reachable only
# if the whole wedge placed there is in air). For a falling stretch that sweep
# is bounded by the ray from the first point where the fall exceeds the back
# clearance, in the back-edge direction; for an over-steep climb, the same
# thing seen from the other end (Z mirrored, order reversed).

_TURNING_INSERTS = ("CNMG", "CCMT", "WNMG", "DNMG", "DCMT", "VNMG", "TNMG", "SNMG")
_DENSIFY_DEG = 0.5


def _piece_geom(c0, c1):
    """(centre, sweep, R) of an arc piece c0 -> c1, or None for a line."""
    p0, p1 = (c0["x_radius"], c0["z"]), (c1["x_radius"], c1["z"])
    if c1.get("quadrant", False):
        c = quadrant_centre(p0, p1, c1.get("quadrant_sign", 1))
        a0 = math.atan2(p0[1] - c[1], p0[0] - c[0])
        a1 = math.atan2(p1[1] - c[1], p1[0] - c[0])
        return c, math.atan2(math.sin(a1 - a0), math.cos(a1 - a0)), math.hypot(p0[0] - c[0], p0[1] - c[1])
    r = c1.get("radius", 0.0) or 0.0
    if abs(r) > 1e-9 and str(c1.get("type", "")).lower().endswith("arc"):
        c = radius_arc_centre(p0, p1, r)
        if c is not None:
            return c, radius_arc_sweep(p0, p1, c, r), abs(r)
    return None


def _densify(coords):
    """Polyline of the contour in radius space, and for each polyline segment
    the coord piece k (coords[k] -> coords[k+1]) it lies on."""
    pts = [(coords[0]["x_radius"], coords[0]["z"])]
    seg_piece = []
    for k in range(len(coords) - 1):
        c0, c1 = coords[k], coords[k + 1]
        p1 = (c1["x_radius"], c1["z"])
        g = _piece_geom(c0, c1)
        if g is None:
            sub = [p1]
        else:
            c, sw, R = g
            a0 = math.atan2(pts[-1][1] - c[1], pts[-1][0] - c[0])
            n = max(2, int(math.ceil(abs(math.degrees(sw)) / _DENSIFY_DEG)))
            sub = [(c[0] + R * math.cos(a0 + sw * i / n), c[1] + R * math.sin(a0 + sw * i / n))
                   for i in range(1, n)] + [p1]
        for q in sub:
            if math.hypot(q[0] - pts[-1][0], q[1] - pts[-1][1]) > 1e-12:
                pts.append(q)
                seg_piece.append(k)
    return pts, seg_piece


def _ray_hit(a, u, p, q):
    """t > 0 where the ray a + t u meets segment p-q, or None."""
    d = (q[0] - p[0], q[1] - p[1])
    den = u[0] * d[1] - u[1] * d[0]
    if abs(den) < 1e-15:
        return None
    w = (p[0] - a[0], p[1] - a[1])
    t = (w[0] * d[1] - w[1] * d[0]) / den
    s = (w[0] * u[1] - w[1] * u[0]) / den
    if t > 1e-9 and -1e-9 <= s <= 1 + 1e-9:
        return t
    return None


def _shadow_pass(pts, max_fall_deg, tol_deg):
    """Canonical frame (material below, travel -Z). Returns bridges
    [(segA, A, segB, B)]: the contour from A (start of polyline segment segA)
    to B (on segment segB) is replaced by the line A-B. segB None: to the end."""
    th = math.radians(max_fall_deg)
    u = (-math.sin(th), -math.cos(th))
    out = []
    cur, i, n = pts[0], 0, len(pts) - 1
    floor = 0                        # can't back up past the last bridge end

    def steeper(a, b):               # chord a -> b falls more steeply than the limit
        d = (b[0] - a[0], b[1] - a[1])
        return math.hypot(*d) > 1e-12 and math.degrees(math.atan2(d[0], -d[1])) < -max_fall_deg

    while i < n:
        nxt = pts[i + 1]
        d = (nxt[0] - cur[0], nxt[1] - cur[1])
        if math.hypot(*d) < 1e-12:
            i += 1
            cur = pts[i]
            continue
        phi = math.degrees(math.atan2(d[0], -d[1]))
        if phi < -(max_fall_deg + tol_deg):
            # start where the contour first got steeper than the limit itself (on a
            # convex arc that is the tangent point, within the densify step)
            while i - 1 >= floor and cur == pts[i] and steeper(pts[i - 1], pts[i]):
                i -= 1
                cur = pts[i]
            best = None
            for j in range(i + 1, n):
                t = _ray_hit(cur, u, pts[j], pts[j + 1])
                if t is not None and (best is None or t < best[0]):
                    best = (t, j)
            if best is None:                           # runs out past the end of the contour
                zt = pts[n][1]
                t = (zt - cur[1]) / u[1] if u[1] < -1e-12 else 0.0
                out.append((i, cur, None, (cur[0] + t * u[0], cur[1] + t * u[1])))
                break
            t, j = best
            b = (cur[0] + t * u[0], cur[1] + t * u[1])
            out.append((i, cur, j, b))
            i, cur, floor = j, b, j + 1
            continue
        i += 1
        cur = pts[i]
    return out


def _signed_radius(c0, c1):
    """A piece as a signed-R arc (+R = clockwise), for splitting a Q."""
    g = _piece_geom(c0, c1)
    if g is None:
        return 0.0
    c, sw, R = g
    return R if sw < 0 else -R


def _piece_to(c0, c1, p):
    """Coord element for the piece c0 -> c1 cut short to end at point p
    (same circle for arcs; a partial quadrant becomes a signed R)."""
    g = _piece_geom(c0, c1)
    if g is None:
        return {"type": c1["type"], "x_radius": p[0], "z": p[1], "radius": 0.0,
                "quadrant": False, "quadrant_sign": 1}
    c, _sw, R = g
    a = math.atan2(p[1] - c[1], p[0] - c[0])                  # snap onto the circle
    p = (c[0] + R * math.cos(a), c[1] + R * math.sin(a))
    return {"type": c1["type"], "x_radius": p[0], "z": p[1], "radius": _signed_radius(c0, c1),
            "quadrant": False, "quadrant_sign": 1}


def _line(p, kind):
    return {"type": kind, "x_radius": p[0], "z": p[1], "radius": 0.0,
            "quadrant": False, "quadrant_sign": 1}


def _apply_bridges(coords, seg_piece, bridges, line_type):
    """New coords with each bridge's stretch replaced by a straight line.
    bridges: [(segA, A, segB or None, B)] in forward order, non-overlapping."""
    out = [dict(coords[0])]
    k_next = 1                       # next original element to copy (it ends piece k_next-1)
    for segA, A, segB, B in bridges:
        if segA == -1:               # the line starts the contour (undercut back to the face)
            out = [dict(coords[0], x_radius=A[0], z=A[1])]
            out.append(_line(B, line_type))
            kb = seg_piece[segB]
            end = coords[kb + 1]
            if math.hypot(B[0] - end["x_radius"], B[1] - end["z"]) > 1e-9:
                e = dict(end)
                if _piece_geom(coords[kb], coords[kb + 1]) is not None:
                    e["radius"] = _signed_radius(coords[kb], coords[kb + 1])
                    e["quadrant"] = False
                out.append(e)
            k_next = kb + 2
            continue
        ka = seg_piece[segA]
        out.extend(dict(c) for c in coords[k_next:ka + 1])
        start = coords[ka]
        if math.hypot(A[0] - start["x_radius"], A[1] - start["z"]) > 1e-9:
            out.append(_piece_to(coords[ka], coords[ka + 1], A))
        out.append(_line(B, line_type))
        if segB is None:
            return out
        kb = seg_piece[segB]
        end = coords[kb + 1]
        if math.hypot(B[0] - end["x_radius"], B[1] - end["z"]) > 1e-9:
            e = dict(end)
            if e.get("quadrant", False) or _piece_geom(coords[kb], coords[kb + 1]) is not None:
                e["radius"] = _signed_radius(coords[kb], coords[kb + 1])
                e["quadrant"] = False
            out.append(e)
        k_next = kb + 2
    out.extend(dict(c) for c in coords[k_next:])
    return out


def _canon(pts, s, mirror_z):
    q = [(s * r, z) for r, z in pts]
    if mirror_z:
        q = [(r, -z) for r, z in reversed(q)]
    return q


def _uncanon_point(p, s, mirror_z):
    r, z = p
    if mirror_z:
        z = -z
    return (s * r, z)


def _reaches(dirs, front, back, mode_id, left, tol=REACH_TOL_DEG):
    for t in dirs:
        phi = _phi(t, mode_id, left)
        if phi > front + tol or phi < back - 180.0 - tol:
            return False
    return True


def suggest_tools(region_dirs, all_dirs, mode_id: bool):
    """(whole_part, this_region_only): insert names (with hand) from the insert
    table that reach the whole contour / only this region."""
    from pipeline.insert_geometry_lookup import INSERT_GEOMETRY
    whole, region = [], []
    seen = set()
    for code in _TURNING_INSERTS:
        f, b = INSERT_GEOMETRY[code]
        for left in (False, True):
            key = (f, b, left)
            name = ("left-hand " if left else "") + code
            if not _reaches(region_dirs, f, b, mode_id, left):
                continue
            if _reaches(all_dirs, f, b, mode_id, left):
                whole.append((name, f, b, key in seen))
            else:
                region.append((name, f, b, key in seen))
            seen.add(key)
    return whole, region


def _fmt_suggest(items):
    """'DNMG/DCMT (62.5/117.5), VNMG (72.5/107.5), right- or left-hand'."""
    hands = {}
    for name, f, b, _ in items:
        left = name.startswith("left-hand ")
        hands.setdefault((f, b), [set(), set()])[1 if left else 0].add(name.replace("left-hand ", ""))
    parts = []
    # right-hand-capable first (same hand as most programs), at most three groups
    order = sorted(hands.items(), key=lambda kv: (not kv[1][0], -(kv[0][1] - kv[0][0])))[:3]
    for (f, b), (rh, lh) in order:
        codes = "/".join(sorted(rh | lh))
        hand = ("right- or left-hand" if rh and lh else "left-hand" if lh else "right-hand")
        parts.append(f"{codes} ({f:g}/{b:g}, {hand})")
    return "; ".join(parts)


@dataclass(frozen=True)
class UncutRegion:
    x_min: float
    x_max: float           # diameter
    z_min: float
    z_max: float
    depth: float           # most material left, normal to the bridge line, inches
    worst_deg: float       # steepest fall / climb in the region
    limit_deg: float
    kind: str              # "fall" or "rise"
    line_from: Tuple[float, float]     # bridge line, (X dia, Z)
    line_to: Tuple[float, float]
    message: str
    outline: Tuple[Tuple[float, float], ...] = ()   # drawn contour + bridge, closed, (X dia, Z)


def make_reachable(profile, tool, tol_deg: float = REACH_TOL_DEG):
    """(profile the tool can cut, [UncutRegion]). The same profile object and []
    when nothing is out of reach or the check does not apply."""
    from dataclasses import replace as dc_replace
    from models.profile import MachiningMode, ProfileMove, SegmentType
    from models.tool import ToolDirection
    from geometry.arc_entry import normalize_profile
    from geometry.zone_builder import _profile_to_radius_coords

    if not tool_applies(tool) or not reach_problems(profile, tool, tol_deg):
        return profile, []
    F, B = tool.front_angle, tool.back_angle
    mode_id = profile.mode == MachiningMode.ID
    left = tool.direction == ToolDirection.LEFT
    s = -1.0 if (mode_id != left) else 1.0              # r mirror (ID, LH) - see _phi
    coords = _profile_to_radius_coords(normalize_profile(profile))
    line_type = coords[0]["type"]
    regions_raw = []

    for kind, mirror_z, max_fall in (("fall", False, 180.0 - B), ("rise", True, F)):
        pts, seg_piece = _densify(coords)
        cp = _canon(pts, s, mirror_z)
        # rise: Z mirrored + order reversed turns "climb <= F" into "fall <= F"
        bridges = _shadow_pass(cp, max_fall, tol_deg)
        if not bridges:
            continue
        n = len(pts) - 1
        fwd = []
        for segA, A, segB, Bp in bridges:
            A0, B0 = _uncanon_point(A, s, mirror_z), _uncanon_point(Bp, s, mirror_z)
            if not mirror_z:
                fwd.append((segA, A0, segB, B0))
            else:                                   # reversed order: swap ends
                sa = (n - 1 - segB) if segB is not None else 0
                sb = n - 1 - segA
                if segB is None:                    # ran past the START of the contour
                    sa, B0 = -1, (B0[0], pts[0][1])
                fwd.append((sa, B0, sb, A0))
        fwd.sort(key=lambda b: b[0])
        coords = _apply_bridges(coords, seg_piece, fwd, line_type)
        for sa, P, sb, Q in fwd:
            last = n if sb is None else sb + 1
            stretch = [P] + pts[max(sa, 0) + 1:last] + [Q]       # the contour being bridged
            regions_raw.append((kind, P, Q, stretch))

    moves = []
    for c in coords:
        q = c.get("quadrant", False)
        moves.append(ProfileMove(
            segment_type=c["type"] if isinstance(c["type"], SegmentType) else SegmentType(str(c["type"]).lower()),
            x=2.0 * c["x_radius"], z=c["z"],
            radius=0.0 if q else float(c.get("radius", 0.0) or 0.0),
            quadrant=bool(q), quadrant_sign=c.get("quadrant_sign", 1) if q else 1))
    new_profile = dc_replace(profile, segments=moves,
                             corner_breaks=[None] * max(0, len(moves) - 1))

    # Report: the original contour between the bridge ends, per region
    all_dirs = [t for _, t in contour_tangents(profile)]
    regions = []
    name = f"T{tool.tool_number}" + (f" ({tool.description})" if tool.description else "")
    for kind, P, Q, stretch in regions_raw:
        dirs = []
        for a, b in zip(stretch, stretch[1:]):
            L = math.hypot(b[0] - a[0], b[1] - a[1])
            if L > 1e-12:
                dirs.append(((b[0] - a[0]) / L, (b[1] - a[1]) / L))
        phis = [_phi(t, mode_id, left) for t in dirs] or [0.0]
        worst = -min(phis) if kind == "fall" else max(phis)
        limit = 180.0 - B if kind == "fall" else F
        lx, lz = Q[0] - P[0], Q[1] - P[1]
        L = math.hypot(lx, lz) or 1.0
        depth = max(abs((p[0] - P[0]) * lz - (p[1] - P[1]) * lx) / L for p in stretch)
        xs = [2 * p[0] for p in stretch]
        whole, region_only = suggest_tools(dirs, all_dirs, mode_id)
        if whole:
            fix = f"Insert(s) that reach the whole contour: {_fmt_suggest(whole)}."
        elif region_only:
            fix = (f"Cut it as its own block with: {_fmt_suggest(region_only)}"
                   f" - or a grooving tool.")
        else:
            # no one insert covers the whole region: name what reaches the part
            # this tool can't (the over-steep side), the rest it cuts itself
            bad = [d for d in dirs if not _reaches([d], F, B, mode_id, left)]
            w2, r2 = suggest_tools(bad, all_dirs, mode_id)
            side = _fmt_suggest(w2 + r2)
            fix = ("No single turning insert reaches all of it: use a grooving or form tool in its "
                   "own block" + (f", or cut the {'falling' if kind == 'fall' else 'undercut'} side "
                                  f"with {side} and the rest with this tool." if side else "."))
        if kind == "fall":
            why = (f"the contour {'falls toward the chuck' if not mode_id else 'opens up deeper in'} "
                   f"at up to {worst:.1f} deg, and {name}'s back edge clears only {limit:.1f} deg")
        else:
            why = (f"the contour {'climbs' if not mode_id else 'steps in'} at up to {worst:.1f} deg, "
                   f"past {name}'s front edge at {limit:g} deg (an undercut)")
        msg = (f"Left uncut: X{min(xs):.4f}-X{max(xs):.4f}, Z{max(P[1], Q[1]):.4f} to "
               f"Z{min(P[1], Q[1]):.4f} - {why}. The tool follows a straight line from "
               f"X{2 * P[0]:.4f} Z{P[1]:.4f} to X{2 * Q[0]:.4f} Z{Q[1]:.4f} instead, leaving up "
               f"to {depth:.4f} of material. {fix}")
        outline = tuple((2 * p[0], p[1]) for p in stretch) + ((2 * P[0], P[1]),)
        regions.append(UncutRegion(min(xs), max(xs), min(P[1], Q[1]), max(P[1], Q[1]), depth,
                                   worst, limit, kind, (2 * P[0], P[1]), (2 * Q[0], Q[1]), msg,
                                   outline))
    return new_profile, regions
