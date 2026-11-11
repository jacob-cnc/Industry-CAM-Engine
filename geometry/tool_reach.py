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
