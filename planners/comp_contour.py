"""Cutter-comp contour planning: how a cleanup / finish contour is entered,
cut and left under G41/G42 (planned here, emitted by outputs/gcode_writer.py).

Moved out of the G-code writer 2026-11-12 (hand-math inquiry C3): these are
CAM decisions about where the tool goes, so they belong before output, where
the pipeline can see them and the writer only formats them. The rules are the
writer's, unchanged (each one's history is in its comment):

  * the contour start skips approach artefacts at the head of the pass (ID
    face leads, an OD drop onto the face, a lead over an already-finished face);
  * comp entry: straight down the wall line; for an OD contour starting with
    a face (or at the centre) one nose radius before the start (+.002 past
    centre); collinear with a sloped first cut;
  * a sliver first move is protected by ending the entry higher, in air;
  * arc pieces are re-joined (the kernel splits arcs <= 90 deg);
  * concave arcs no larger than the nose radius are cut as sharp corners;
  * a comp lead-out stops the nose at the contour end when material lies
    beyond it (kernel point-in-face queries, supplied by the pipeline);
  * line-line corners LinuxCNC comp cannot reach are refused here.

Geometry answers come from the kernel (a sharpened corner = the kernel's
line intersection); what remains is move arithmetic (directions, back-off
along a move) and check_concave_corners, which predicts LinuxCNC's OWN comp
arithmetic (R*tan(turn/2)) rather than part geometry.

Points are (X diameter, Z).
"""
from __future__ import annotations

import math
from dataclasses import replace
from typing import Callable, List, Optional, Tuple

from geometry.kernel import line_intersection, short_sweep
from models.constants import CONTOUR_FEED_IN_DIA  # noqa: F401  (documented: the writer's feed-in)
from models.moves import MoveType
from models.results import CompContour, SharpenedCorner
from models.tool import ToolDirection

Point = Tuple[float, float]

# How far past the centreline the nose goes when a contour starts at X0, on
# top of the nose radius (owner 2026-11-11).
CENTRE_OVERSHOOT = 0.002
# Extra length of the comp entry / lead-out move beyond 2 x TNR (inches).
COMP_ENTRY_MARGIN = 0.010
# A concave arc this close to the nose radius (or smaller) has no usable
# cutter-comp offset path (offset radius <= 0.0001").
SMALL_CONCAVE_ARC_MARGIN = 0.0001
_ARCS = (MoveType.ARC_CW, MoveType.ARC_CCW)


def comp_code_for(direction, is_id: bool) -> str:
    """G41/G42 for a tool direction and side (LinuxCNC G18 lathe rules)."""
    if direction == ToolDirection.NEUTRAL:
        return "G40"
    right_code, left_code = ("G41", "G42") if is_id else ("G42", "G41")
    return right_code if direction == ToolDirection.RIGHT else left_code


def _turns_left(move_type) -> bool:
    """Does this arc turn left in LinuxCNC's G18 plane (G03)? (outputs/gcode_dialect:
    internal ARC_CW is written as G03.)"""
    return move_type == MoveType.ARC_CW


def plan_comp_contour(moves, start: Point, tool, is_id: bool, z_clear_stock: float,
                      face_at_z0: bool, label: str,
                      part_contains: Optional[Callable[[Point], bool]] = None,
                      stock_contains: Optional[Callable[[Point], bool]] = None) -> CompContour:
    """The comp plan of one contour pass starting from ``start``.

    ``part_contains`` / ``stock_contains`` say whether a point is strictly
    inside the finished part / the stock (kernel queries in the pipeline);
    without them no lead-out is planned. Raises ValueError for contours
    LinuxCNC comp cannot cut (small concave arc not between lines, a line too
    short before a concave corner).
    """
    sx, sz = start
    has_tnr = tool.nose_radius > 0.0001
    comp_code = comp_code_for(tool.direction, is_id) if has_tnr else "G40"
    r = tool.nose_radius if has_tnr else 0.0
    moves = list(moves)

    # Contour start: skip approach artefacts at the head of the pass.
    k, px, pz = 0, sx, sz
    while k < len(moves) and moves[k].move_type in (MoveType.FEED, MoveType.RAPID):
        mv = moves[k]
        if abs(mv.x - px) < 1e-9 and abs(mv.z - pz) < 1e-9:   # zero length
            k += 1
            continue
        radial = abs(mv.z - pz) < 1e-9 and abs(mv.x - px) > 1e-9
        # ID lead across the mouth from the approach height (Z0+.001) down
        # to the contour start is air too, though not exactly radial. Kept,
        # comp treated it as a wall and stopped the nose short of a mouth
        # chamfer (up to .005 left proud; G-code section check 2026-11-11).
        near_radial = (abs(mv.z - pz) <= 0.002 and abs(mv.x - px) / 2.0 > 5.0 * abs(mv.z - pz)
                       and abs(mv.x - px) > 1e-9)
        if is_id and near_radial and not radial:
            radial = True
        # OD with the face already at Z0 (operator Z start <= allowance, no stock in front):
        # a lead moving INWARD from X start to the contour start runs over the
        # finished face in air. Kept, comp treated it as a wall and stopped the
        # nose short of a face chamfer (the ID mouth-chamfer problem, mirrored).
        mostly_radial = abs(mv.x - px) / 2.0 > 5.0 * abs(mv.z - pz)
        if not is_id and mostly_radial and mv.x < px - 1e-9 and face_at_z0:
            px, pz = mv.x, mv.z
            k += 1
            continue
        tiny_axial = abs(mv.x - px) < 1e-9 and 0 < abs(mv.z - pz) < max(2.0 * r, 0.005)
        nxt_radial = (k + 1 < len(moves) and abs(moves[k + 1].z - mv.z) < 1e-9)
        if is_id and radial:                      # ID face lead: air
            px, pz = mv.x, mv.z
            k += 1
            continue
        if not is_id and tiny_axial and nxt_radial:   # OD drop onto the face
            px, pz = mv.x, mv.z
            k += 1
            continue
        break
    first = moves[k] if k < len(moves) else None
    feed = first.feed if first is not None and first.feed > 0 else 0.0

    min_len = 2.0 * r + COMP_ENTRY_MARGIN
    # If the contour starts straight down the entry line with a sliver
    # (2026-11-09 GCH ID cleanup: entry stopped at Z0+fin = .0015, first
    # move .0006 to .0009, then a concave chamfer corner), end the entry
    # higher - still in air on the same line - so that first contour move
    # is long enough for LinuxCNC to shorten it at the corner (R*tan(turn/2))
    # instead of aborting with "straight feed in concave corner cannot be
    # reached". The entry itself must stay air-only: LinuxCNC moves the
    # tool sideways onto the offset path along the whole entry move.
    if (first is not None and first.move_type == MoveType.FEED
            and abs(first.x - px) < 1e-9 and first.z < pz - 1e-9
            and pz - first.z < min_len):
        pz = first.z + min_len
    z_clear = max(z_clear_stock, pz + min_len)
    face_first = (first is not None and first.move_type == MoveType.FEED
                  and abs(first.z - pz) < 1e-9 and abs(first.x - px) > 1e-9)
    od_face_entry = (not is_id) and face_first and comp_code == "G42"
    # A contour that starts AT THE CENTRE (X start 0 / segment 1 at X0) with
    # something other than a face - a dome, a cone point - is entered the same
    # way: across the centreline, then straight into the first cut.
    at_centre = abs(px) < 1e-6
    centre_entry = ((not is_id) and comp_code == "G42" and at_centre and not od_face_entry
                    and first is not None and first.x > px + 1e-9)
    if od_face_entry or centre_entry:
        outward = 1.0 if first.x > px else -1.0
        # one nose radius before the start (diameter) puts the nose centre on
        # it after LinuxCNC's inside-corner clip; at the centre go a further
        # .002 past, so no nib is left (owner 2026-11-11: nose radius + .002)
        past = r + (CENTRE_OVERSHOOT if at_centre else 0.0)
        entry_x = px - outward * 2.0 * past
        od_face_entry = True
    else:
        entry_x = px
    # Contour starting with a SLOPED line toward the chuck (a bore-mouth
    # chamfer, an OD chamfer at the face): enter collinear with it, from the
    # air behind its start. A vertical entry made a corner there that comp
    # treats as inside, stopping the nose short of the top of the chamfer.
    entry_z = pz
    # Only a genuinely sloped first cut (>= 15 deg off radial): a near-radial
    # lead (a face move .001 off level) would be extended almost flat and
    # far out - that sent an entry to X18.2 (caught 2026-11-11, never released).
    collinear = False
    if (comp_code != "G40" and not od_face_entry and first is not None
            and first.move_type == MoveType.FEED
            and abs(first.x - px) > 1e-9 and first.z < pz - 1e-9):
        ur, uz = (first.x - px) / 2.0, first.z - pz
        L = (ur * ur + uz * uz) ** 0.5
        if abs(uz) / L >= 0.2588:                   # sin 15 deg
            t = min_len / (abs(uz) / L)             # back along it until min_len above the start
            entry_x = px - 2.0 * (ur / L) * t
            entry_z = pz - (uz / L) * t
            collinear = is_id or entry_x >= 0.0     # never past the centreline on OD
            if not collinear:
                entry_x, entry_z = px, pz

    contour = merge_arc_pieces(moves[k:], (px, pz))
    sharpened: List[SharpenedCorner] = []
    if comp_code != "G40":
        contour, sharpened = sharpen_small_concave_arcs(contour, (px, pz), r, comp_code, label)

    # Comp-on polyline for the concave-corner check (None = arc end), as the
    # writer will emit it: entry, contour, lead-out.
    path: list = ([(entry_x, entry_z), (px, pz)] if collinear
                  else [(entry_x, z_clear), (entry_x, pz)])
    if od_face_entry:
        path.append((px, pz))

    def _track(pt):
        if pt is None or path[-1] is None or \
                abs(pt[0] - path[-1][0]) > 1e-9 or abs(pt[1] - path[-1][1]) > 1e-9:
            path.append(pt)       # zero-length moves are suppressed in output

    pos = prev = (px, pz)
    for move in contour:
        prev = pos
        pos = (move.x, move.z)
        _track(None if move.move_type in _ARCS else pos)

    lead = None
    if comp_code != "G40" and part_contains is not None and stock_contains is not None:
        lead = comp_lead_out(prev, pos, r, comp_code, [m.z for m in contour],
                             part_contains, stock_contains)
        if lead is not None:
            _track(lead)
    if comp_code != "G40":
        check_concave_corners(path, r, comp_code, label)

    return CompContour(comp_code=comp_code, nose_radius=tool.nose_radius, feed=feed,
                       start=(px, pz), entry=(entry_x, entry_z), z_clear=z_clear,
                       collinear=collinear, face_entry=od_face_entry,
                       contour=tuple(contour), sharpened=tuple(sharpened), lead_out=lead)


def merge_arc_pieces(moves, start: Point, tol: float = 1e-6) -> list:
    """Re-join consecutive arc moves on the same circle, same direction, feed
    and pass (the kernel splits arcs into <= 90 deg pieces, see
    geometry/arc_math.py). Keeps the G-code of an unsplit arc unchanged and
    lets the concave-arc rule see the whole arc."""
    out = []                 # merged moves
    run_start = None         # start point of out[-1]
    run_sweep = 0.0          # |sweep| accumulated in out[-1] (radians)
    pos = start
    for m in moves:
        end = (m.x, m.z)
        if m.move_type in _ARCS:
            centre = (pos[0] + m.center_i, pos[1] + m.center_k)
            piece = abs(short_sweep((pos[0] / 2.0, pos[1]), (end[0] / 2.0, end[1]),
                                    (centre[0] / 2.0, centre[1])))
            last = out[-1] if out else None
            if (last is not None and last.move_type == m.move_type
                    and abs(last.feed - m.feed) < 1e-12 and last.pass_type == m.pass_type):
                last_centre = (run_start[0] + last.center_i, run_start[1] + last.center_k)
                if (abs(last_centre[0] - centre[0]) < tol and abs(last_centre[1] - centre[1]) < tol
                        and run_sweep + piece < 2.0 * math.pi - 1e-6):
                    out[-1] = replace(last, x=m.x, z=m.z)
                    run_sweep += piece
                    pos = end
                    continue
            run_sweep = piece
        else:
            run_sweep = 0.0
        out.append(m)
        run_start = pos
        pos = end
    return out


def sharpen_small_concave_arcs(moves, start: Point, r: float, comp_code: str,
                               label: str) -> Tuple[list, List[SharpenedCorner]]:
    """Cut concave arcs with radius <= the nose radius as a sharp corner.

    Owner decision 2026-11-10: the nose cannot make an inside radius smaller
    than itself, so a concave fillet R <= TNR is cut exactly like the sharp
    inside corner (the tool leaves R = TNR there). LinuxCNC cannot offset such
    an arc under G41/G42 ("Tool radius not less than arc radius with comp").
    The two neighbouring lines are extended to their intersection and the arc
    is dropped; each one is returned so the operator is told (the writer adds
    a note and a program comment). Not silent: the part gets a larger corner
    radius than drawn.

    Concave = the arc turns toward the comp side: G03 turns left in G18
    (Z, X-radius), and left is the G41 side (same rule as
    check_concave_corners).
    """
    side = 1.0 if comp_code == "G41" else -1.0
    mv = list(moves)
    done: List[SharpenedCorner] = []
    i = 0
    while i < len(mv):
        m = mv[i]
        if m.move_type not in _ARCS:
            i += 1
            continue
        turn = 1.0 if _turns_left(m.move_type) else -1.0
        radius = math.hypot(m.center_i / 2.0, m.center_k)
        if turn * side <= 0 or radius > r + SMALL_CONCAVE_ARC_MARGIN:
            i += 1
            continue
        a_end = (mv[i - 1].x, mv[i - 1].z) if i > 0 else start
        where = f"{label}: concave arc R{radius:.4f} ending at X{m.x:.4f} Z{m.z:.4f}"
        prev_ok = i > 0 and mv[i - 1].move_type == MoveType.FEED
        next_ok = i + 1 < len(mv) and mv[i + 1].move_type == MoveType.FEED
        if not (prev_ok and next_ok):
            raise ValueError(
                f"{where} is not larger than the tool nose radius ({r:.4f}) and is "
                "not between two straight moves, so it cannot be cut as a sharp "
                "corner. Use a fillet larger than the nose radius, or a tool with "
                "a smaller nose radius.")
        p0 = (mv[i - 2].x, mv[i - 2].z) if i > 1 else start
        corner = line_intersection(p0, a_end, (m.x, m.z), (mv[i + 1].x, mv[i + 1].z))
        if corner is None:
            raise ValueError(f"{where}: the lines on either side are parallel; "
                             "it cannot be cut as a sharp corner.")
        mv[i - 1] = replace(mv[i - 1], x=corner[0], z=corner[1])
        del mv[i]
        done.append(SharpenedCorner(radius=radius, corner=corner))
    return mv, done


def check_concave_corners(path, r: float, comp_code: str, label: str) -> None:
    """Reject line-line corners LinuxCNC comp cannot reach (fail at planning).

    At a corner that turns toward the comp side LinuxCNC shortens the incoming
    line by R*tan(turn/2); if the line is shorter than that it aborts with
    "straight feed in concave corner cannot be reached by the tool without
    gouging". Points are (X diameter, Z); ``None`` marks the end of an arc
    (corners touching arcs are not checked here). Turn sign is in LinuxCNC's
    G18 plane (Z, X-radius): left (+) = G41 side.
    """
    side = 1.0 if comp_code == "G41" else -1.0
    for i in range(1, len(path) - 1):
        a, b, c = path[i - 1], path[i], path[i + 1]
        if a is None or b is None or c is None:
            continue
        d1 = (b[1] - a[1], (b[0] - a[0]) / 2.0)
        d2 = (c[1] - b[1], (c[0] - b[0]) / 2.0)
        l1, l2 = math.hypot(*d1), math.hypot(*d2)
        if l1 < 1e-9 or l2 < 1e-9:
            continue
        cross = (d1[0] * d2[1] - d1[1] * d2[0]) / (l1 * l2)
        dot = (d1[0] * d2[0] + d1[1] * d2[1]) / (l1 * l2)
        if side * cross <= 1e-9:
            continue                          # straight or convex
        turn = math.atan2(abs(cross), dot)
        need = r * math.tan(turn / 2.0)
        if l1 < need - 1e-6:
            raise ValueError(
                f"{label}: the move to X{b[0]:.4f} Z{b[1]:.4f} is {l1:.4f}\" long "
                f"but cutter comp needs {need:.4f}\" before that concave corner "
                "(LinuxCNC would stop with 'straight feed in concave corner "
                "cannot be reached'). Use a smaller nose radius or a longer "
                "segment.")


def comp_lead_out(prev: Point, end: Point, r: float, comp_code: str, contour_z: List[float],
                  part_contains: Callable[[Point], bool],
                  stock_contains: Callable[[Point], bool]) -> Optional[Point]:
    """End of a lead-out that stops the nose AT the contour end when material
    lies beyond it, else None.

    With comp on, LinuxCNC ends the last move with the nose centre on the
    endpoint, so the nose overhangs the end by R along the move (sim
    2026-11-08: OD finish reported Z-0.8155 for Z-0.8). Into air that is fine
    (it cleans e.g. the pilot-hole edge); into material it would cut R past
    the programmed part. Then a compensated lead-out toward the tool's air
    side is added before G40, so LinuxCNC clips the last move.
    """
    dx_r, dz = (end[0] - prev[0]) / 2.0, end[1] - prev[1]
    length = math.hypot(dx_r, dz)
    if length < 1e-9:
        return None
    ux_r, uz = dx_r / length, dz / length
    probe = (end[0] + 2.0 * ux_r * (r + 0.002), end[1] + uz * (r + 0.002))
    zs = list(contour_z) + [end[1]]
    in_span = min(zs) - 1e-9 <= probe[1] <= max(zs) + 1e-9
    material = part_contains(probe) or (stock_contains(probe) and not in_span)
    if not material:
        return None
    # Air side = the comp side: left normal for G41, right for G42, in the
    # (Z, X-radius) plane LinuxCNC uses for G18.
    nz, nx = (-ux_r, uz) if comp_code == "G41" else (ux_r, -uz)
    lead = 2.0 * r + COMP_ENTRY_MARGIN
    return (end[0] + 2.0 * nx * lead, end[1] + nz * lead)
