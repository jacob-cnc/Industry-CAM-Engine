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
from typing import List, Tuple


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


def _contour_coords(profile):
    from geometry.arc_entry import normalize_profile
    from geometry.zone_builder import profile_to_radius_coords
    return profile_to_radius_coords(normalize_profile(profile))


def _edges_of(coords):
    """The kernel edge of every contour piece coords[k] -> coords[k+1] (None for
    zero length), built exactly like the finished part (zone_builder)."""
    from geometry.zone_builder import edge_from_coords
    return [edge_from_coords(a, b) for a, b in zip(coords, coords[1:])]


def _unit(v):
    n = math.hypot(v[0], v[1])
    return (v[0] / n, v[1] / n) if n > 1e-15 else (0.0, 0.0)


def _edge_tangents(e) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
    """[(point, unit travel direction)] at both ends of a kernel edge and, on an
    arc, at every quadrant point inside it (where its direction is axis-
    aligned: the steepest / flattest tangents)."""
    ts = {0.0, 1.0}
    if e.geom_type.name == "CIRCLE":
        for ang in (0.0, 90.0, 180.0, 270.0):
            ts.update(t for t in e.find_tangent(ang) if 0.0 < t < 1.0)
    out = []
    for t in sorted(ts):
        p, d = e.position_at(t), e.tangent_at(t)
        out.append(((p.X, p.Y), _unit((d.X, d.Y))))
    return out


def contour_tangents(profile) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
    """Every (point, unit direction) the finished contour has, in profile order,
    corner breaks included. Radius space; from the kernel's own edges."""
    out = []
    for e in _edges_of(_contour_coords(profile)):
        if e is not None:
            out.extend(_edge_tangents(e))
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
# inserts from tools/insert_geometry_lookup.py would reach it. The operator
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


def densify_coords(coords):
    """Polyline of the contour in radius space, ON the kernel's edges
    (geometry.zone_builder.sample_outline), and for each polyline segment the
    coord piece k (coords[k] -> coords[k+1]) it lies on."""
    from geometry.zone_builder import sample_outline
    pieces = sample_outline(coords)
    pts = list(pieces[0])
    seg_piece = []
    for k, piece in enumerate(pieces[1:]):
        if piece is None:
            piece = [pts[-1], (coords[k + 1]["x_radius"], coords[k + 1]["z"])]
        for q in piece[1:]:
            if math.hypot(q[0] - pts[-1][0], q[1] - pts[-1][1]) > 1e-12:
                pts.append(q)
                seg_piece.append(k)
    return pts, seg_piece


def _snap_len(tool) -> float:
    """Shortest contour piece left after a bridge's concave corner (inches)."""
    return 4.0 * max(getattr(tool, "nose_radius", 0.0), 0.0) + 0.010


class _Frame:
    """The tool's canonical frame: material below, travel toward -Z, the check
    is "falls no steeper than max_fall". s mirrors r (ID, left hand - see
    _phi); mirror_z also reverses the travel (a climb seen from the other end
    is a fall). Points map by (s r, +/- z); travel directions by the same map,
    negated when the order is reversed."""

    def __init__(self, s: float, mirror_z: bool):
        self.s, self.m = s, mirror_z

    def point(self, p):                      # real -> canonical (and back: same map)
        return (self.s * p[0], -p[1] if self.m else p[1])

    def travel(self, d):                     # real forward direction -> canonical travel
        c = (self.s * d[0], -d[1] if self.m else d[1])
        return (-c[0], -c[1]) if self.m else c

    def real_travel(self, c):                # canonical travel -> real forward direction
        if self.m:
            c = (-c[0], -c[1])
        return (self.s * c[0], -c[1] if self.m else c[1])


def _phi_c(c) -> float:
    """Canonical travel direction's angle from -Z toward +r, degrees."""
    return math.degrees(math.atan2(c[0], -c[1]))


def _kernel_bridges(coords, frame: _Frame, max_fall: float, tol_deg: float, snap_len: float):
    """Bridges in FORWARD piece order: [(kA, A, kB, B)] - the contour from A (on
    piece kA; kA = -1: the line starts the contour) to B (on piece kB; None: to
    the end) is replaced by the line A-B. Everything from the kernel: where the
    contour gets steeper than max_fall (a line's start, or the arc point whose
    tangent reaches the limit - Edge.find_tangent), and where the ray at the
    limit meets the contour again (edge intersections)."""
    from build123d import Line, Vector
    edges = _edges_of(coords)
    n_pc = len(edges)
    order = list(range(n_pc))[::-1] if frame.m else list(range(n_pc))   # canonical order
    th = math.radians(max_fall)
    u_c = (-math.sin(th), -math.cos(th))                               # canonical limit direction

    def cpar(t):                     # canonical param -> real param on the edge
        return 1.0 - t if frame.m else t

    def phi_at(k, t):                # canonical phi at canonical param t of piece k
        d = edges[k].tangent_at(cpar(t))
        return _phi_c(frame.travel((d.X, d.Y)))

    def pos(k, t):
        p = edges[k].position_at(cpar(t))
        return (p.X, p.Y)

    def limit_param(k):
        """Canonical param on piece k where the canonical direction is exactly
        the limit (a line: its whole length, so 0)."""
        e = edges[k]
        if e.geom_type.name != "CIRCLE":
            return 0.0
        dr = frame.real_travel(u_c)
        ang = math.degrees(math.atan2(dr[1], dr[0])) % 360.0
        ts = [cpar(t) for t in e.find_tangent(ang) if -1e-9 <= t <= 1 + 1e-9]
        return min(ts) if ts else 0.0

    out_c = []                        # canonical: (iA, A, iB or None, B), i = index into order
    i, floor = 0, 0
    t0 = 0.0                          # canonical param where the walk resumes on order[i]
    while i < n_pc:
        k = order[i]
        if edges[k] is None:
            i, t0 = i + 1, 0.0
            continue
        steep_end = phi_at(k, 1.0) < -(max_fall + tol_deg)
        steep_start = phi_at(k, max(t0, 0.0)) < -(max_fall + tol_deg)
        if not (steep_start or steep_end):
            i, t0 = i + 1, 0.0
            continue
        # Where the contour first got steeper than the limit itself (no
        # tolerance): walk back over pieces that are steeper than the limit end
        # to end, stop inside the piece where it crosses the limit; never back
        # past where the last bridge ended (floor) or past a resumed mid-piece
        # point.
        if steep_start and t0 > 1e-12:
            iA, tA = i, t0
        elif steep_start:
            iA, tA = i, 0.0
            while iA - 1 >= floor and edges[order[iA - 1]] is not None \
                    and phi_at(order[iA - 1], 1.0) < -max_fall:
                iA -= 1
                if phi_at(order[iA], 0.0) >= -max_fall:      # it crosses the limit inside
                    tA = limit_param(order[iA])
                    break
        else:                                                # an arc turning steeper
            iA, tA = i, max(limit_param(k), t0)
        A = pos(order[iA], tA)
        # the ray at the limit from A, and where it meets the contour again
        Ar = frame.point(A)
        far = frame.point((Ar[0] + 50.0 * u_c[0], Ar[1] + 50.0 * u_c[1]))
        ray = Line(A, far)
        best = None
        for jj in range(iA, n_pc):
            kk = order[jj]
            if edges[kk] is None:
                continue
            for q in edges[kk].find_intersection_points(ray):
                d = math.hypot(q.X - A[0], q.Y - A[1])
                if d > 1e-7 and (best is None or d < best[0]):
                    best = (d, jj, (q.X, q.Y))
        if best is None:                                  # runs out past the end of the contour
            last = frame.point(pos(order[-1], 1.0))
            t = (last[1] - Ar[1]) / u_c[1] if u_c[1] < -1e-12 else 0.0
            out_c.append((iA, A, None, frame.point((Ar[0] + t * u_c[0], Ar[1] + t * u_c[1]))))
            break
        _, jB, B = best
        # Don't leave a sliver of a contour piece after the concave corner the
        # line makes: LinuxCNC's cutter comp refuses a short arc or line there
        # ("... in concave corner cannot be reached by the tool without
        # gouging"). Run the line on to the end of that piece instead: further
        # along the rising contour, so it falls less and stays in air.
        eB = edges[order[jB]]
        tB = cpar(eB.param_at_point(Vector(B[0], B[1], 0)))
        rest = eB.length * (1.0 - tB)
        if snap_len > 0.0 and rest < snap_len:
            B = pos(order[jB], 1.0)
            tB = 1.0
        out_c.append((iA, A, jB, B))
        i, t0 = (jB, tB) if tB < 1.0 - 1e-12 else (jB + 1, 0.0)
        floor = i
    # forward piece indices
    fwd = []
    for iA, A, iB, B in out_c:
        kA = order[iA]
        if not frame.m:
            fwd.append((kA, A, order[iB] if iB is not None else None, B))
        else:                                             # reversed: swap ends
            if iB is None:                                # ran past the START of the contour
                start_z = coords[0]["z"]
                fwd.append((-1, (B[0], start_z), kA, A))
            else:
                fwd.append((order[iB], B, kA, A))
    fwd.sort(key=lambda b: b[0])
    return fwd


def _arc_end_at(coords, k, p, edges):
    """Coord element for piece k cut short to end at p (a line, or a plain arc
    of the same circle with its signed radius - a partial quadrant is no longer
    a quadrant)."""
    c1 = coords[k + 1]
    e = edges[k]
    base = {"type": c1["type"], "x_radius": p[0], "z": p[1], "radius": 0.0,
            "quadrant": False, "quadrant_sign": 1}
    if e is None or e.geom_type.name != "CIRCLE":
        return base
    from geometry.corner_breaks_od import _circle_of, _signed_arc_radius
    centre, R = _circle_of(e)
    p0 = (coords[k]["x_radius"], coords[k]["z"])
    base["radius"] = _signed_arc_radius(p0, (c1["x_radius"], c1["z"]), centre, R)
    return base


def _line(p, kind):
    return {"type": kind, "x_radius": p[0], "z": p[1], "radius": 0.0,
            "quadrant": False, "quadrant_sign": 1}


def _apply_bridges(coords, bridges, line_type):
    """New coords with each bridge's stretch replaced by a straight line.
    bridges: [(kA, A, kB or None, B)] in forward order, non-overlapping."""
    edges = _edges_of(coords)

    def tail(kb, B):
        """The rest of piece kb after B (same circle for an arc)."""
        end = coords[kb + 1]
        if math.hypot(B[0] - end["x_radius"], B[1] - end["z"]) <= 1e-9:
            return []
        return [_arc_end_at(coords, kb, (end["x_radius"], end["z"]), edges)
                if edges[kb] is not None and edges[kb].geom_type.name == "CIRCLE" else dict(end)]

    out = [dict(coords[0])]
    k_next = 1                       # next original element to copy (it ends piece k_next-1)
    for ka, A, kb, B in bridges:
        if ka == -1:                 # the line starts the contour (undercut back to the face)
            out = [dict(coords[0], x_radius=A[0], z=A[1]), _line(B, line_type)] + tail(kb, B)
            k_next = kb + 2
            continue
        out.extend(dict(c) for c in coords[k_next:ka + 1])
        start = coords[ka]
        if math.hypot(A[0] - start["x_radius"], A[1] - start["z"]) > 1e-9:
            out.append(_arc_end_at(coords, ka, A, edges))
        out.append(_line(B, line_type))
        if kb is None:
            return out
        out.extend(tail(kb, B))
        k_next = kb + 2
    out.extend(dict(c) for c in coords[k_next:])
    return out


def _stretch(coords, ka, A, kb, B, step=0.002):
    """Points (r, z) along the original contour from A (piece ka) to B (piece
    kb; None = to the end), sampled on the kernel's edges - for the report."""
    from build123d import Vector
    edges = _edges_of(coords)
    last = len(edges) - 1 if kb is None else kb
    pts = [A]
    for k in range(max(ka, 0), last + 1):
        e = edges[k]
        if e is None:
            continue
        t0 = e.param_at_point(Vector(A[0], A[1], 0)) if k == ka else 0.0
        t1 = e.param_at_point(Vector(B[0], B[1], 0)) if (k == kb) else 1.0
        n = max(1, int(math.ceil(e.length * abs(t1 - t0) / step)))
        for i in range(1, n + 1):
            p = e.position_at(t0 + (t1 - t0) * i / n)
            pts.append((p.X, p.Y))
    if kb is None or math.hypot(pts[-1][0] - B[0], pts[-1][1] - B[1]) > 1e-9:
        pts.append(B)
    return pts


def _reaches(dirs, front, back, mode_id, left, tol=REACH_TOL_DEG):
    for t in dirs:
        phi = _phi(t, mode_id, left)
        if phi > front + tol or phi < back - 180.0 - tol:
            return False
    return True


def suggest_tools(region_dirs, all_dirs, mode_id: bool):
    """(whole_part, this_region_only): insert names (with hand) from the insert
    table that reach the whole contour / only this region."""
    from tools.insert_geometry_lookup import INSERT_GEOMETRY
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
    if not tool_applies(tool) or not reach_problems(profile, tool, tol_deg):
        return profile, []
    F, B = tool.front_angle, tool.back_angle
    mode_id = profile.mode == MachiningMode.ID
    left = tool.direction == ToolDirection.LEFT
    s = -1.0 if (mode_id != left) else 1.0              # r mirror (ID, LH) - see _phi
    coords = _contour_coords(profile)
    line_type = coords[0]["type"]
    regions_raw = []

    for kind, mirror_z, max_fall in (("fall", False, 180.0 - B), ("rise", True, F)):
        bridges = _kernel_bridges(coords, _Frame(s, mirror_z), max_fall, tol_deg, _snap_len(tool))
        if not bridges:
            continue
        stretches = [(kind, A, Q, _stretch(coords, ka, A, kb, Q)) for ka, A, kb, Q in bridges]
        coords = _apply_bridges(coords, bridges, line_type)
        regions_raw.extend(stretches)

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
