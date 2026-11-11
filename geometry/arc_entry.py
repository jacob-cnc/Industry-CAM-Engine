"""Arc ENTRY rules (arc strategy Phase 1, owner decisions 2026-11-11).

docs/handoffs/2026-11-10-arc-segment-strategy.md

1. Q / -Q is a TRUE CIRCULAR quarter (ellipses are retired). A quadrant arc is
   tangent to the Z axis direction at one end and to the X (radial) direction at
   the other, so its legs must be equal: |dX|/2 == |dZ| == R. The centre is the
   corner of the bounding box:
       +Q  centre (start r, end z)  - leaves radially, arrives along Z
       -Q  centre (end r, start z)  - leaves along Z, arrives radially
   Unequal legs are refused with the nearest valid end points offered.

2. An arc that begins and ends at the SAME X is two quadrants (owner, 2026-11-11):
   e.g. X1 Z0 -> X1 Z-1 as +Q is cut as +Q to the apex then -Q back:
       X1.0 Z0  -> X2.0 Z-0.5 (+Q)  -> X1.0 Z-1.0 (-Q)      (OD, R .5)
   (X is DIAMETER: a .5 radius bump moves the diameter by 1.0.)
   Which way it bulges: +Q bulges toward the tool (OD: bigger diameter, a bead;
   ID: smaller diameter, a bump into the bore); -Q the other way (a groove).
   Same-Z quadrants (a radial chord) have no defined bulge and are refused.

3. A radius (R) arc whose path passes its own X extreme - every same-X R arc,
   and any arc that bulges past the larger/smaller end diameter - is split at that
   extreme into two arcs with the same signed R (same circle, same direction).
   Each piece then stays inside its end diameters, which the planners, staircase
   logic and validators assume. This replaces the old "Arc ... exceeds X bounds"
   refusal.

The split is done on the profile (profile_from_fields and pipeline.execute) so
generation is always right, and by the Program tab on the segment rows when the
operator leaves the row, so what is cut is what is listed.

Points here: dicts / ProfileMoves carry X as DIAMETER; the maths is in RADIUS
space (r, z), the same frame as geometry/arc_math.py.
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import List, Optional, Sequence, Tuple

# Leg equality for a circular quadrant, radius inches. Coordinates are entered to
# 4 decimals on the diameter (.00005 on the radius); anything within this is
# built through the exact end points with the mean radius.
QUADRANT_LEG_TOL = 0.0002
# Below this an X or Z delta counts as zero (same X / same Z), radius inches.
SAME_TOL = 1e-5
# An arc must pass its X extreme by more than this to be split, radius inches
# (well above the 4-decimal rounding of a split point shown in the segment list).
EXTREME_TOL = 1e-4


def _is_q(radius) -> int:
    """+1 for "Q", -1 for "-Q", 0 otherwise (works on dict rows)."""
    if isinstance(radius, str):
        t = radius.strip().upper()
        if t == "Q":
            return 1
        if t == "-Q":
            return -1
    return 0


# ----------------------------------------------------------------------
# Circular quadrant
# ----------------------------------------------------------------------

def quadrant_centre(p0: Tuple[float, float], p1: Tuple[float, float], sign: int) -> Tuple[float, float]:
    """Centre of a circular quadrant arc, (r, z) in, (r, z) out."""
    return (p0[0], p1[1]) if sign > 0 else (p1[0], p0[1])


def quadrant_points(p0, p1, sign: int, n: int = 32) -> List[Tuple[float, float]]:
    """Points along the circular quadrant from p0 to p1 (radius space), exact ends."""
    c = quadrant_centre(p0, p1, sign)
    rad = 0.5 * (math.hypot(p0[0] - c[0], p0[1] - c[1]) + math.hypot(p1[0] - c[0], p1[1] - c[1]))
    a0 = math.atan2(p0[1] - c[1], p0[0] - c[0])
    a1 = math.atan2(p1[1] - c[1], p1[0] - c[0])
    sw = math.atan2(math.sin(a1 - a0), math.cos(a1 - a0))      # a quarter: short sweep
    pts = [p0]
    for k in range(1, n):
        a = a0 + sw * k / n
        pts.append((c[0] + rad * math.cos(a), c[1] + rad * math.sin(a)))
    pts.append(p1)
    return pts


def quadrant_mid(p0, p1, sign: int) -> Tuple[float, float]:
    """The 45 deg point of the circular quadrant (for a three-point arc)."""
    return quadrant_points(p0, p1, sign, n=2)[1]


def quadrant_problem(x0: float, z0: float, x1: float, z1: float) -> Optional[str]:
    """Why a Q / -Q from (x0, z0) to (x1, z1) (X = diameter) can't be built as one
    circular quadrant, or None. Same-X quadrants are fine: they are split."""
    dr, dz = abs(x1 - x0) / 2.0, abs(z1 - z0)
    if dr < SAME_TOL and dz < SAME_TOL:
        return "Quadrant arc has zero length."
    if dr < SAME_TOL:
        return None                                      # same X: two quadrants
    if dz < SAME_TOL:
        return ("A quadrant arc can't start and end at the same Z. Enter it as two "
                "quadrant arcs (to the high or low point, then back), or use a radius.")
    if abs(dr - dz) <= QUADRANT_LEG_TOL:
        return None
    z_alt = z0 + math.copysign(dr, z1 - z0)
    x_alt = x0 + math.copysign(2.0 * dz, x1 - x0)
    return (f"A quadrant arc is a true quarter circle: the X change (on the radius) must "
            f"equal the Z change. From X{x0:.4f} Z{z0:.4f} this one changes X by "
            f"{2 * dr:.4f} (radius {dr:.4f}) but Z by {dz:.4f}. "
            f"For R{dr:.4f} end at X{x1:.4f} Z{z_alt:.4f}; for R{dz:.4f} end at "
            f"X{x_alt:.4f} Z{z1:.4f}; or enter a radius instead of Q.")


# ----------------------------------------------------------------------
# Radius arcs: centre, sweep, X extreme
# ----------------------------------------------------------------------

def radius_arc_centre(p0, p1, radius: float) -> Optional[Tuple[float, float]]:
    """Centre of the minor arc for the signed-radius convention of ProfileMove
    (+R = clockwise in (r, z) = internal ARC_CW). Same rule as
    validation/pre_planning_validator._compute_arc_center. (r, z) in and out."""
    dx, dz = p1[0] - p0[0], p1[1] - p0[1]
    d = math.hypot(dx, dz)
    R = abs(radius)
    if d < 1e-12 or R < 1e-12:
        return None
    h = math.sqrt(max(R * R - (d / 2.0) ** 2, 0.0))
    mx, mz = (p0[0] + p1[0]) / 2.0, (p0[1] + p1[1]) / 2.0
    px, pz = -dz / d, dx / d
    c1 = (mx + h * px, mz + h * pz)
    c2 = (mx - h * px, mz - h * pz)
    cr1 = (p0[0] - c1[0]) * (p1[1] - c1[1]) - (p0[1] - c1[1]) * (p1[0] - c1[0])
    if radius > 0:
        return c1 if cr1 < 0 else c2
    return c1 if cr1 > 0 else c2


def radius_arc_sweep(p0, p1, centre, radius: float) -> float:
    """Signed sweep: clockwise (negative) for +R, counter-clockwise for -R."""
    a0 = math.atan2(p0[1] - centre[1], p0[0] - centre[0])
    a1 = math.atan2(p1[1] - centre[1], p1[0] - centre[0])
    ccw = (a1 - a0) % (2.0 * math.pi)
    return ccw - 2.0 * math.pi if radius > 0 and ccw > 0 else ccw


def radius_arc_x_extreme(p0, p1, radius: float) -> Optional[Tuple[float, float]]:
    """The (r, z) point where a radius arc passes its own X extreme beyond both
    end points, or None if it stays inside its end diameters."""
    c = radius_arc_centre(p0, p1, radius)
    if c is None:
        return None
    R = abs(radius)
    sw = radius_arc_sweep(p0, p1, c, radius)
    a0 = math.atan2(p0[1] - c[1], p0[0] - c[0])
    for ext in (0.0, math.pi):                          # +r extreme, -r extreme
        rel = (ext - a0) % (2.0 * math.pi) if sw > 0 else (a0 - ext) % (2.0 * math.pi)
        if 0.0 < rel < abs(sw):
            p = (c[0] + R * math.cos(ext), c[1] + R * math.sin(ext))
            if (p[0] > max(p0[0], p1[0]) + EXTREME_TOL) or (p[0] < min(p0[0], p1[0]) - EXTREME_TOL):
                return p
    return None


# ----------------------------------------------------------------------
# The split
# ----------------------------------------------------------------------

def _split_one(x0, z0, x1, z1, radius, mode_od: bool):
    """Pieces [(x_dia, z, radius)] for one arc row, or None to keep it.
    radius is the row's radius field (number, "Q" or "-Q")."""
    q = _is_q(radius)
    if q:
        dr, dz = abs(x1 - x0) / 2.0, abs(z1 - z0)
        if dr >= SAME_TOL or dz < SAME_TOL:
            return None
        R = dz / 2.0
        out = 1.0 if (q > 0) == mode_od else -1.0      # +Q bulges toward the tool
        apex_x = x0 + out * 2.0 * R
        if apex_x <= 0.0:
            return None                                 # through the centreline: let validation say so
        zm = (z0 + z1) / 2.0
        return [(apex_x, zm, "Q"), (x0, z1, "-Q")]
    try:
        r = float(radius)
    except (TypeError, ValueError):
        return None
    if abs(r) < 1e-9:
        return None
    p = radius_arc_x_extreme((x0 / 2.0, z0), (x1 / 2.0, z1), r)
    if p is None:
        return None
    return [(2.0 * p[0], p[1], r), (x1, z1, r)]


def _fmt_radius(radius) -> str:
    return radius if isinstance(radius, str) else f"R{abs(float(radius)):.4f}"


def split_rows(segments: Sequence[dict], corner_breaks: Optional[Sequence] = None,
               mode: str = "od", only: Optional[int] = None):
    """Split the arc rows that rules 2 and 3 say are two pieces.

    segments: Program-tab rows {"type", "x" (dia), "z", "radius"}; corner_breaks:
    the vertex list (len = len(segments) - 1; element k = the corner at the END of
    segment k), or None. only: split just that row index.
    Returns (segments, corner_breaks, notes); new lists, inputs untouched. The new
    vertex between two pieces gets no corner break (it is a smooth tangent point).
    """
    segs = [dict(s) for s in segments]
    breaks = None if corner_breaks is None else list(corner_breaks)
    notes: List[str] = []
    od = str(getattr(mode, "value", mode)).lower() != "id"
    i = len(segs) - 1
    while i >= 1:                                       # back to front: indices stay valid
        s = segs[i]
        if (only is None or i == only) and str(s.get("type", "line")).lower() == "arc":
            p = segs[i - 1]
            x0, z0 = float(p.get("x", 0.0)), float(p.get("z", 0.0))
            x1, z1 = float(s.get("x", 0.0)), float(s.get("z", 0.0))
            pieces = _split_one(x0, z0, x1, z1, s.get("radius", 0.0), od)
            if pieces:
                (ax, az, r1), (bx, bz, r2) = pieces
                segs[i:i + 1] = [dict(s, x=ax, z=az, radius=r1), dict(s, x=bx, z=bz, radius=r2)]
                if breaks is not None:
                    breaks.insert(i, None)
                notes.append(
                    f"Segment {i + 1}: the arc X{x0:.4f} Z{z0:.4f} -> X{x1:.4f} Z{z1:.4f} "
                    f"({_fmt_radius(s.get('radius'))}) passes its "
                    f"{'largest' if ax > max(x0, x1) else 'smallest'} diameter, so it is cut as two "
                    f"arcs that meet at X{ax:.4f} Z{az:.4f} "
                    f"({_fmt_radius(r1)} then {_fmt_radius(r2)}).")
        i -= 1
    notes.reverse()
    return segs, breaks, notes


def normalize_profile(profile):
    """ClosedProfile with every two-piece arc split (rules 2 and 3). Idempotent;
    returns the same object when nothing changes."""
    from models.profile import ProfileMove, SegmentType

    segs = profile.segments
    rows = []
    for m in segs:
        if m.segment_type == SegmentType.ARC and m.quadrant:
            r = "Q" if m.quadrant_sign > 0 else "-Q"
        else:
            r = m.radius
        rows.append({"type": m.segment_type.value, "x": m.x, "z": m.z, "radius": r})
    new_rows, new_breaks, notes = split_rows(rows, list(profile.corner_breaks), profile.mode)
    if not notes:
        return profile
    moves = []
    for row in new_rows:
        q = _is_q(row["radius"])
        moves.append(ProfileMove(
            segment_type=SegmentType(row["type"]),
            x=float(row["x"]), z=float(row["z"]),
            radius=0.0 if q else float(row["radius"]),
            quadrant=bool(q), quadrant_sign=q if q else 1,
        ))
    if len(new_breaks) != len(moves) - 1:               # profile built without breaks
        new_breaks = (list(new_breaks) + [None] * len(moves))[:max(0, len(moves) - 1)]
    return replace(profile, segments=moves, corner_breaks=new_breaks)
