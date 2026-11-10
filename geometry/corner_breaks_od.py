"""OD corner breaks: equal-leg chamfers and fillets at profile vertices.

OD ONLY. ID profiles keep the legacy path in zone_builder until an ID
reference part validates their (different) build parameters. Do not reuse
this module for ID without that validation.

Vertex numbering (owner's convention): V1 is the corner at the first profile
point, between the implied front face (centreline -> first point at Z0) and
segment 1. Vertex Vk sits at profile point k-1, i.e. corner_breaks[k-1].
The last profile point (into the closure) has no vertex.

Geometry is computed in RADIUS space, (r, z), from each neighbour's real
tangent direction at the vertex: no implied origins. Line-line vertices are
solved exactly. A vertex with an arc / quadrant neighbour falls back to the
legacy chord-based construction and is reported as UNVALIDATED (arc corner
breaks are the next phase).

Trim policy (owner decision, matches NX "cliff edge" behaviour): vertices are
processed V1 upward and an earlier break keeps its full size. When a later
break does not fit on a segment already consumed by its neighbour:
  * fillet: keeps radius R and its tangency to the side that has room; the
    arc is cut short where it meets the neighbouring break (it passes through
    that break's end point), leaving a reported kink there;
  * chamfer: the short leg is clipped to the room left, the other leg keeps
    its size (no longer equal-leg).
Every trim produces a VertexReport describing where and why.

Validated against the NX reference part
tests/fixtures/nx_corner_break/ (see tests/unit/test_corner_breaks_od_nx.py).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from models.profile import ClosedProfile, CornerBreakType, SegmentType

EPS = 1e-9
# Legacy fallback default when a size/radius of 0 slips through.
_DEFAULT_SIZE = 0.015


@dataclass
class VertexReport:
    """What happened at one vertex (only vertices with a requested break)."""
    vertex: int                  # 1-based V number
    z: float                     # sharp-corner location
    x_dia: float
    break_type: str              # "chamfer" | "fillet"
    requested: float             # chamfer leg or fillet radius
    # "ok" | "trimmed" (NX-style, may leave a kink) | "smoothed" (rolled onto
    # / adjusted for a neighbour, tangent) | "unvalidated" | "skipped"
    status: str
    message: str = ""
    kink_deg: float = 0.0        # direction change left at a cut-short end
    corner: str = ""             # "convex" | "concave" | "" (OD material side)

    @property
    def label(self) -> str:
        return f"V{self.vertex}"


@dataclass
class VertexGeometry:
    """Exact break geometry at one solved (line-line) vertex, radius space.
    Consumers that draw the profile (the Program-tab preview) use this so
    they show exactly what the engine machines."""
    vertex: int                         # 1-based V number (point index + 1)
    t_in: Tuple[float, float]           # (r, z) where the incoming segment ends
    t_out: Tuple[float, float]          # (r, z) where the outgoing segment starts
    kind: str                           # "chamfer" (straight) | "fillet" (arc)
    center: Optional[Tuple[float, float]] = None   # fillet centre (r, z)
    radius: float = 0.0                            # fillet radius


@dataclass
class OdCornerResult:
    coords: List[dict]                        # zone_builder coordinate format
    reports: List[VertexReport] = field(default_factory=list)
    # point index -> geometry, for every vertex solved by this module (not
    # the legacy arc-adjacent fallback, not skipped vertices).
    geometry: dict = field(default_factory=dict)

    @property
    def trims(self) -> List[VertexReport]:
        return [r for r in self.reports if r.status == "trimmed"]

    @property
    def smoothable(self) -> List[VertexReport]:
        """NX-style cut-short fillets that 'smooth' could roll onto their
        earlier neighbour (point indices = vertex - 1)."""
        return [r for r in self.reports if r.status == "trimmed"
                and r.break_type == "fillet" and r.kink_deg > 0
                and "Smoothing" not in r.message]


# ----------------------------------------------------------------------
# Small vector helpers in (r, z)
# ----------------------------------------------------------------------

def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1])


def _mul(a, k):
    return (a[0] * k, a[1] * k)


def _len(a):
    return math.hypot(a[0], a[1])


def _unit(a):
    n = _len(a)
    return (a[0] / n, a[1] / n) if n > EPS else (0.0, 0.0)


def _cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1]


def _signed_arc_radius(start, end, center, radius) -> float:
    """Build123d RadiusArc sign for a minor arc start->end about center.
    Verified empirically: +R puts the centre to the RIGHT of travel
    (sketch X = radius, Y = Z), -R to the LEFT."""
    side = _cross(_sub(end, start), _sub(center, start))
    return -radius if side > 0 else radius


def _angle_between(u, v) -> float:
    """Unsigned angle in degrees between two unit directions."""
    return math.degrees(math.acos(max(-1.0, min(1.0, _dot(u, v)))))


def _od_corner_kind(u_in, u_out) -> str:
    """Convex/concave for OD (material between profile and centreline).

    Travel runs from the front face toward the chuck; on OD the material is
    on the RIGHT of travel in (r, z) (toward r = 0 for a -Z run). A turn
    away from the material (left turn, cross > 0) is a concave corner.
    """
    c = _cross(u_in, u_out)
    if abs(c) < 1e-12:
        return ""
    return "concave" if c > 0 else "convex"


# ----------------------------------------------------------------------
# Solver
# ----------------------------------------------------------------------

def build_od_corner_coords(profile: ClosedProfile) -> OdCornerResult:
    """Profile segments -> zone_builder coordinate descriptors with corner
    breaks applied, plus a per-vertex report. OD profiles only."""
    from models.profile import MachiningMode
    if profile.mode != MachiningMode.OD:
        raise ValueError("build_od_corner_coords is OD-only")

    segs = profile.segments
    if not segs:
        return OdCornerResult([])
    breaks = list(profile.corner_breaks or [])
    pts = [(s.x / 2.0, s.z) for s in segs]          # (r, z) sharp points
    n = len(pts)
    reports: List[VertexReport] = []

    # Start of the run INTO each point: point i is reached from pts[i-1];
    # point 0 from the implied face start (r = 0, z = first z).
    def seg_start(i):
        return pts[i - 1] if i > 0 else (0.0, pts[0][1])

    def seg_is_line(i):
        """Is the move arriving at point i a straight line?"""
        if i == 0:
            return True                             # implied face
        s = segs[i]
        return s.segment_type == SegmentType.LINE and not s.quadrant \
            and abs(s.radius) < EPS

    # consumed_from_start[i] = how far along the move INTO point i an earlier
    # break (at point i-1) already reaches, measured from the move's start.
    consumed_from_start = [0.0] * n
    # Direction in which an earlier break's element ENDS on the move into
    # point i (used to measure the kink when a later break is cut short
    # against it).
    break_end_dir = [None] * n
    # Per point: (trim_in point, element dict) or (legacy entries, None).
    plan = {}
    geometry = {}

    for i in range(n - 1):                          # vertex V(i+1) at pts[i]
        cb = breaks[i] if i < len(breaks) else None
        if cb is None or cb.break_type == CornerBreakType.NONE:
            continue
        kind = "chamfer" if cb.break_type == CornerBreakType.CHAMFER else "fillet"
        size = (cb.size if kind == "chamfer" else cb.radius) or _DEFAULT_SIZE
        c = pts[i]
        a = seg_start(i)
        b = pts[i + 1]
        rep = VertexReport(vertex=i + 1, z=c[1], x_dia=c[0] * 2.0,
                           break_type=kind, requested=size, status="ok")

        if not (seg_is_line(i) and seg_is_line(i + 1)):
            plan[i] = _legacy_vertex(i, segs, pts, cb, kind, size, seg_start)
            rep.status = "unvalidated"
            rep.message = (f"{rep.label}: next to an arc segment; built with the "
                           f"legacy chord method (not yet validated)")
            reports.append(rep)
            continue

        len_in = _len(_sub(c, a))
        len_out = _len(_sub(b, c))
        if len_in < EPS or len_out < EPS:
            rep.status = "skipped"
            rep.message = f"{rep.label}: zero-length neighbour segment, no break applied"
            reports.append(rep)
            continue
        u_in = _unit(_sub(c, a))
        u_out = _unit(_sub(b, c))
        turn = _angle_between(u_in, u_out)          # 0 = straight on
        rep.corner = _od_corner_kind(u_in, u_out)
        if turn < 1e-6 or turn > 180 - 1e-6:
            rep.status = "skipped"
            rep.message = f"{rep.label}: no corner (collinear or reversal), no break applied"
            reports.append(rep)
            continue

        room_in = len_in - consumed_from_start[i]   # earlier break wins
        room_out = len_out                          # later vertex adapts to us
        if room_in < EPS:
            # The earlier break already reaches this corner: there is no
            # segment left to put a break on (a fillet would collapse to a
            # point, a chamfer to a straight line).
            rep.status = "skipped"
            rep.message = (f"{rep.label}: {kind} {_fmt(size)} not applied. The segment "
                           f"into {rep.label} is used up by the V{i} break, so there is "
                           f"no room left for it.")
            reports.append(rep)
            continue

        if kind == "chamfer":
            leg_in = min(size, room_in)
            leg_out = min(size, room_out)
            t_in = _sub(c, _mul(u_in, leg_in))
            t_out = _add(c, _mul(u_out, leg_out))
            if leg_in < size - EPS or leg_out < size - EPS:
                rep.status = "trimmed"
                rep.message = _chamfer_trim_msg(rep, size, leg_in, leg_out, i, consumed_from_start)
            plan[i] = (t_in, {"type": SegmentType.LINE, "x_radius": t_out[0],
                              "z": t_out[1], "radius": 0.0})
            geometry[i] = VertexGeometry(i + 1, t_in, t_out, "chamfer")
            consumed_from_start[i + 1] = leg_out
            break_end_dir[i + 1] = _unit(_sub(t_out, t_in))
        else:
            half = math.radians(180.0 - turn) / 2.0          # interior half-angle
            t = size / math.tan(half)                        # tangent length
            bis = _unit(_add(_mul(u_in, -1.0), u_out))
            center = _add(c, _mul(bis, size / math.sin(half)))
            t_in = _sub(c, _mul(u_in, t))
            t_out = _add(c, _mul(u_out, t))
            if t <= room_in + EPS and t <= room_out + EPS:
                pass                                          # fits exactly
            elif t > room_in + EPS and t <= room_out + EPS:
                # Cut short on the incoming side: stays tangent to the
                # outgoing segment, passes through where room ends.
                anchor = _sub(c, _mul(u_in, room_in))
                # What arrives at the anchor: the earlier break's element if
                # it consumed this whole segment, otherwise the segment itself.
                # The anchor IS the earlier break's end point (the rest of the
                # segment is used by this fillet), so the earlier break's end
                # direction is what arrives there; else the segment itself.
                arriving = u_in
                if consumed_from_start[i] > EPS and break_end_dir[i] is not None:
                    arriving = break_end_dir[i]
                rolled = None
                smooth_note = ""
                if getattr(cb, "trim", "nx") == "smooth":
                    prev_g = geometry.get(i - 1)
                    if consumed_from_start[i] > EPS and prev_g is not None:
                        rolled = _roll_onto(prev_g, c, u_out, size, center, room_out)
                        if rolled is None:
                            smooth_note = (" Smoothing was not possible here (no tangent "
                                           "fit on the earlier break), so it was cut short.")
                    else:
                        smooth_note = (" Smoothing needs an earlier break to roll onto; "
                                       "there is none, so it was cut short.")
                if rolled is not None:
                    t_in, t_out, center, prev_new_end = rolled
                    prev_g = geometry[i - 1]
                    old_len = _break_length(prev_g)
                    prev_g.t_out = prev_new_end
                    pt_in, pel = plan[i - 1]
                    pel["x_radius"], pel["z"] = prev_new_end
                    if prev_g.kind == "fillet":
                        pel["radius"] = _signed_arc_radius(prev_g.t_in, prev_new_end,
                                                           prev_g.center, prev_g.radius)
                    prev_rep = next((r for r in reports if r.vertex == i), None)
                    if prev_rep is not None:
                        new_len = _break_length(prev_g)
                        verb = "lengthened" if new_len > old_len + 1e-9 else "shortened"
                        prev_rep.status = "smoothed"
                        prev_rep.message = (
                            f"{prev_rep.label}: {prev_g.kind} {verb} from "
                            f"{_fmt(old_len)} to {_fmt(new_len)} long (along its own "
                            f"line/arc) so the smoothed {rep.label} fillet meets it "
                            f"tangentially.")
                    rep.status = "smoothed"
                    rep.kink_deg = 0.0
                    rep.message = (
                        f"{rep.label}: fillet R{_fmt(size)} smoothed. The segment into "
                        f"{rep.label} had {_fmt(room_in)} left after the V{i} break (needs "
                        f"{_fmt(t)}), so the fillet keeps R{_fmt(size)} and rolls onto the "
                        f"V{i} {prev_g.kind}: tangent to it, no kink.")
                else:
                    center, t_out, kink = _cliff_fillet(anchor, c, u_out, size, center,
                                                        incoming_dir=arriving)
                    t_in = anchor
                    rep.status = "trimmed"
                    rep.kink_deg = kink
                    rep.message = (
                        f"{rep.label}: fillet R{_fmt(size)} cut short. The segment into "
                        f"{rep.label} had {_fmt(room_in)} left"
                        + (f" after the V{i} break" if consumed_from_start[i] > EPS else "")
                        + f" (needs {_fmt(t)}). The arc keeps R{_fmt(size)} and its "
                        f"tangency to the next segment, and ends at that break with a "
                        f"{kink:.1f}° direction change." + smooth_note)
            elif t > room_out + EPS and t <= room_in + EPS:
                anchor = _add(c, _mul(u_out, room_out))
                center, t_in, kink = _cliff_fillet(anchor, c, _mul(u_in, -1.0), size,
                                                   center, incoming_dir=_mul(u_out, -1.0))
                t_out = anchor
                rep.status = "trimmed"
                rep.kink_deg = kink
                rep.message = (
                    f"{rep.label}: fillet R{_fmt(size)} cut short. The segment after "
                    f"{rep.label} is only {_fmt(room_out)} long (needs {_fmt(t)}). "
                    f"The arc keeps R{_fmt(size)} and its tangency to the previous "
                    f"segment, and ends at the next corner with a {kink:.1f}° "
                    f"direction change.")
            else:
                # Neither side has room: shrink to the room available (stays
                # tangent). Not an NX-matched case; reported as such.
                t_fit = min(room_in, room_out)
                r_fit = t_fit * math.tan(half)
                t_in = _sub(c, _mul(u_in, t_fit))
                t_out = _add(c, _mul(u_out, t_fit))
                center = _add(c, _mul(bis, r_fit / math.sin(half)))
                rep.status = "trimmed"
                rep.message = (f"{rep.label}: fillet R{_fmt(size)} does not fit on either "
                               f"side ({_fmt(room_in)} / {_fmt(room_out)} available, needs "
                               f"{_fmt(t)}); reduced to R{_fmt(r_fit)} to stay tangent.")
                size = r_fit
            arc_r = _len(_sub(t_in, center))
            plan[i] = (t_in, {"type": SegmentType.ARC, "x_radius": t_out[0],
                              "z": t_out[1],
                              "radius": _signed_arc_radius(t_in, t_out, center, arc_r)})
            geometry[i] = VertexGeometry(i + 1, t_in, t_out, "fillet", center, arc_r)
            consumed_from_start[i + 1] = _len(_sub(t_out, c))
            # Arc tangent at its end point, in the direction of travel.
            rad_end = _unit(_sub(t_out, center))
            end_dir = (-rad_end[1], rad_end[0])
            if _dot(end_dir, u_out) < 0:
                end_dir = _mul(end_dir, -1.0)
            break_end_dir[i + 1] = end_dir
        reports.append(rep)

    # Emit coordinates in zone_builder's format.
    coords: List[dict] = []
    for i, seg in enumerate(segs):
        entry_type = seg.segment_type if i > 0 else SegmentType.LINE
        if i in plan:
            trim_in, element = plan[i]
            if isinstance(trim_in, list):              # legacy fallback entries
                coords.extend(trim_in)
                continue
            coords.append({"type": entry_type, "x_radius": trim_in[0],
                           "z": trim_in[1], "radius": seg.radius})
            coords.append(element)
        else:
            coords.append({"type": seg.segment_type, "x_radius": pts[i][0],
                           "z": pts[i][1], "radius": seg.radius,
                           "quadrant": seg.quadrant,
                           "quadrant_sign": seg.quadrant_sign})
    return OdCornerResult(coords, reports, geometry)


def _break_length(g: "VertexGeometry") -> float:
    """Length of a break element (chamfer chord or fillet arc)."""
    if g.kind == "fillet" and g.center is not None:
        a = _unit(_sub(g.t_in, g.center))
        b = _unit(_sub(g.t_out, g.center))
        return g.radius * math.radians(_angle_between(a, b))
    return _len(_sub(g.t_out, g.t_in))


def _on_minor_arc(p, g, tol=1e-9) -> bool:
    """Is p on the minor arc of fillet g (between g.t_in and g.t_out)?"""
    a = _unit(_sub(g.t_in, g.center))
    b = _unit(_sub(g.t_out, g.center))
    q = _unit(_sub(p, g.center))
    full = _angle_between(a, b)
    return abs(_angle_between(a, q) + _angle_between(q, b) - full) < 1e-6 \
        and _angle_between(a, q) > 1e-7


def _roll_onto(prev_g, corner, u_out, radius, nominal_center, room_out):
    """'Smooth' trim: a fillet of `radius` tangent to the outgoing line
    (through `corner` along `u_out`) AND tangent to the earlier break
    `prev_g` (chamfer line or fillet arc), instead of ending at its end.

    Returns (start on the earlier break, end on the outgoing line, centre,
    new end of the earlier break) or None when no valid tangent fit exists:
    the touch point must lie on the earlier break itself, the end point on
    the outgoing segment's room, and the joint must be truly tangent.
    """
    normal = (-u_out[1], u_out[0])
    if _dot(_sub(nominal_center, corner), normal) < 0:
        normal = _mul(normal, -1.0)
    base = _add(corner, _mul(normal, radius))      # centre line: base + s*u_out

    def end_ok(t_out):
        along = _dot(_sub(t_out, corner), u_out)
        return -1e-9 <= along <= room_out + 1e-9

    candidates = []
    if prev_g.kind == "chamfer":
        d = _unit(_sub(prev_g.t_out, prev_g.t_in))
        n_d = (-d[1], d[0])
        # Centre is `radius` from the chamfer line, on the nominal side.
        for sgn in (1.0, -1.0):
            off = _add(prev_g.t_in, _mul(n_d, sgn * radius))
            # base + s*u_out lies on the line off + k*d
            den = _cross(u_out, d)
            if abs(den) < 1e-12:
                continue
            s = _cross(_sub(off, base), d) / den
            center = _add(base, _mul(u_out, s))
            touch = _sub(center, _mul(n_d, sgn * radius))
            k = _dot(_sub(touch, prev_g.t_in), d)
            # The touch point may be on the chamfer (it is shortened) or on
            # its extension through the leftover segment room (it is
            # lengthened, along its own line): both stay one straight line.
            if k <= 1e-9:
                continue
            t_out = _sub(center, _mul(normal, radius))
            if end_ok(t_out):
                candidates.append((touch, t_out, center, touch))
    elif prev_g.kind == "fillet" and prev_g.center is not None:
        c2, r2 = prev_g.center, prev_g.radius
        for dist in (radius + r2, abs(radius - r2)):
            if dist < 1e-9:
                continue
            dd = _sub(base, c2)
            bq = 2.0 * _dot(dd, u_out)
            cq = _dot(dd, dd) - dist * dist
            disc = bq * bq - 4.0 * cq
            if disc < 0:
                continue
            for s in ((-bq + math.sqrt(disc)) / 2.0, (-bq - math.sqrt(disc)) / 2.0):
                center = _add(base, _mul(u_out, s))
                for touch in (_add(c2, _mul(_unit(_sub(center, c2)), r2)),
                              _sub(c2, _mul(_unit(_sub(center, c2)), r2))):
                    if abs(_len(_sub(touch, center)) - radius) > 1e-7:
                        continue
                    if not _on_minor_arc(touch, prev_g):
                        continue
                    t_out = _sub(center, _mul(normal, radius))
                    if end_ok(t_out):
                        candidates.append((touch, t_out, center, touch))
    # Tangency in the direction of travel at the joint.
    good = []
    for touch, t_out, center, new_end in candidates:
        prev_dir = _prev_end_dir(prev_g, touch)
        rad = _unit(_sub(touch, center))
        arc_dir = (-rad[1], rad[0])
        if _dot(arc_dir, _sub(t_out, touch)) < 0:
            arc_dir = _mul(arc_dir, -1.0)
        if _angle_between(prev_dir, arc_dir) < 1e-4:
            good.append((touch, t_out, center, new_end))
    if not good:
        return None
    return min(good, key=lambda g: _len(_sub(g[2], nominal_center)))


def _prev_end_dir(prev_g, at):
    """Travel direction of the earlier break element at point `at`."""
    if prev_g.kind == "chamfer":
        return _unit(_sub(prev_g.t_out, prev_g.t_in))
    rad = _unit(_sub(at, prev_g.center))
    d = (-rad[1], rad[0])
    # Orient along the arc's travel (from t_in toward t_out).
    rad_in = _unit(_sub(prev_g.t_in, prev_g.center))
    turn = _cross(rad_in, _unit(_sub(prev_g.t_out, prev_g.center)))
    if (turn > 0) != (_cross(rad, d) > 0):
        d = _mul(d, -1.0)
    return d


def od_vertex_kinds(profile: ClosedProfile) -> dict:
    """Convex / concave for EVERY vertex (point index -> str), whether or
    not it has a break - for labelling vertices in the corner-break tool.
    Uses segment chords (exact for lines; a label only for arc neighbours)."""
    segs = profile.segments
    pts = [(s.x / 2.0, s.z) for s in segs]
    kinds = {}
    for i in range(len(pts) - 1):
        a = pts[i - 1] if i > 0 else (0.0, pts[0][1])
        u_in, u_out = _unit(_sub(pts[i], a)), _unit(_sub(pts[i + 1], pts[i]))
        kinds[i] = _od_corner_kind(u_in, u_out) if u_in != (0.0, 0.0) and \
            u_out != (0.0, 0.0) else ""
    return kinds


def _cliff_fillet(anchor, corner, u_tan, radius, nominal_center, incoming_dir):
    """Fillet of `radius` tangent to the line through `corner` along `u_tan`
    and passing through `anchor` (NX cliff-edge roll-off).

    The centre lies on the line offset `radius` from the tangent line, on the
    nominal centre's side, at distance `radius` from `anchor`; of the two
    candidates the one nearest the nominal centre is used.
    Returns (centre, tangent point on the line, kink at anchor in degrees).
    """
    normal = (-u_tan[1], u_tan[0])
    if _dot(_sub(nominal_center, corner), normal) < 0:
        normal = _mul(normal, -1.0)
    base = _add(corner, _mul(normal, radius))     # a point on the centre line
    # Centre = base + s * u_tan with |centre - anchor| = radius.
    d = _sub(base, anchor)
    bq = 2.0 * _dot(d, u_tan)
    cq = _dot(d, d) - radius * radius
    disc = bq * bq - 4.0 * cq
    if disc < 0:
        disc = 0.0                                 # tangent touch
    roots = [(-bq + math.sqrt(disc)) / 2.0, (-bq - math.sqrt(disc)) / 2.0]
    centers = [_add(base, _mul(u_tan, s)) for s in roots]
    center = min(centers, key=lambda p: _len(_sub(p, nominal_center)))
    tangent_pt = _sub(center, _mul(normal, radius))
    # Arc direction at the anchor vs the segment arriving at it.
    radial = _unit(_sub(anchor, center))
    arc_dir = (-radial[1], radial[0])
    if _dot(arc_dir, _sub(tangent_pt, anchor)) < 0:
        arc_dir = _mul(arc_dir, -1.0)
    kink = _angle_between(_unit(incoming_dir), arc_dir)
    return center, tangent_pt, kink


def _chamfer_trim_msg(rep, size, leg_in, leg_out, i, consumed):
    parts = []
    if leg_in < size - EPS:
        parts.append(f"the segment into {rep.label} had only {_fmt(leg_in)} left"
                     + (f" after the V{i} break" if consumed[i] > EPS else ""))
    if leg_out < size - EPS:
        parts.append(f"the segment after {rep.label} is only {_fmt(leg_out)} long")
    return (f"{rep.label}: chamfer {_fmt(size)} trimmed to legs {_fmt(leg_in)} / "
            f"{_fmt(leg_out)} because " + " and ".join(parts) + ".")


def _fmt(v: float) -> str:
    return f"{v:.4f}".rstrip("0").rstrip(".") if abs(v) >= 1e-4 else "0"


def _legacy_vertex(i, segs, pts, cb, kind, size, seg_start):
    """Arc-adjacent vertex: the pre-existing chord-based construction
    (40 % clamp), kept unchanged until arc corner breaks are validated.
    Returns (list_of_coord_entries, None) in the plan's legacy form."""
    c = pts[i]
    a = seg_start(i)
    b = pts[i + 1]
    arr = _sub(c, a)
    dep = _sub(b, c)
    la, ld = _len(arr), _len(dep)
    seg = segs[i]
    if la < EPS or ld < EPS:
        return ([{"type": seg.segment_type if i else SegmentType.LINE,
                  "x_radius": c[0], "z": c[1], "radius": seg.radius}], None)
    ua, ud = _unit(arr), _unit(dep)
    entry_type = seg.segment_type if i else SegmentType.LINE
    if kind == "chamfer":
        tb, tf = min(size, la * 0.4), min(size, ld * 0.4)
        p1 = _sub(c, _mul(ua, tb))
        p2 = _add(c, _mul(ud, tf))
        return ([{"type": entry_type, "x_radius": p1[0], "z": p1[1], "radius": seg.radius},
                 {"type": SegmentType.LINE, "x_radius": p2[0], "z": p2[1], "radius": 0.0}],
                None)
    dot = max(-1.0, min(1.0, _dot(_mul(ua, -1.0), ud)))
    half = math.acos(dot) / 2.0
    if half <= 1e-6:
        return ([{"type": entry_type, "x_radius": c[0], "z": c[1], "radius": seg.radius}], None)
    t = size / math.tan(half)
    t1 = _sub(c, _mul(ua, min(t, la * 0.4)))
    t2 = _add(c, _mul(ud, min(t, ld * 0.4)))
    signed = -size if _cross(ua, ud) > 0 else size
    return ([{"type": entry_type, "x_radius": t1[0], "z": t1[1], "radius": seg.radius},
             {"type": SegmentType.ARC, "x_radius": t2[0], "z": t2[1], "radius": signed}],
            None)
