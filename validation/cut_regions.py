"""What the program actually cuts, from LinuxCNC's own interpreter.

docs/handoffs/2026-11-11-zone-shading-plan.md. The graph's shaded sections
(face stock, roughing, cleanup/finish band, finished part, left uncut) are
computed from the G-code as LinuxCNC will run it, not from what the planner
meant, so the shading can't disagree with the program:

1. The block's G-code goes through `rs274` (standalone interpreter, no realtime)
   with a tool table holding exactly the program's tools (nose diameter,
   orientation, zero offsets). A "(ICAM_SECTION ...)" comment is put after each
   "; === ... ===" section header so every canonical move carries its section.
   No matching back to planner moves.
2. rs274 reports every move - compensated (G41/G42) or not - as the path of the
   IMAGINARY TIP for the tool's orientation Q (checked: a G42 45 deg chamfer comes
   out exactly the drawn line shifted by TNR*(1-1/sqrt2) along -X-Z for Q2). So the
   nose centre is that point minus TNR * the Q direction, and the nose sweeps a
   circle of TNR around it.
3. The rest of the insert (the wedge between its front and back edges, tool table
   I/J) removes material too: a roughing step deeper than the nose radius is cut
   by the leading edge. It is swept as a convex insert outline; where it would
   overlap the intended part (only within the 1 deg reach tolerance) it doesn't
   count, the nose sweep alone decides the part edge.
4. Sections, by exact boolean operations on one set of geometry (Shapely):
     removed   = (nose sweep U wedge sweep outside the part) inside the stock
     as cut    = stock - removed                 -> "finished part" (+ "uncut")
     face      = removed by FACE moves
     rough     = removed by ROUGHING moves, not already by face
     band      = removed by CLEANUP / FINISH moves, not already above
   They partition the stock (checked). Two error sections are found, never
   expected: GOUGE (intended part removed) and NOT REMOVED (material the program
   should take but doesn't, beyond the nose-radius fillet in concave corners).
Coordinates: (r, z) radius space internally; outlines are returned for the
graph as lists of (z, r) rings.
"""

from __future__ import annotations

import math
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box
from shapely.ops import unary_union

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHORD_ERR = 2e-5              # inches: arcs densified this close (well under a pixel)
NOSE_QUAD_SEGS = 64           # circle segments per quarter for the nose (TNR .016 -> 5e-6")
WEDGE_LEN = 0.25              # inches of each insert edge counted as cutting
THIN = 1e-4                   # error regions thinner than 2*THIN are numerical noise
AREA_EPS = 1e-7               # in^2
GRID = 1e-7                   # inches: boolean ops run snap-rounded on this grid. Near-
                              # coincident edges (a nose sweep along the stock edge, the
                              # centre-overshoot entry) made plain GEOS overlay fail with
                              # "Unable to determine overlay result geometry dimension".


def _poly(g):
    """Only the area of a result: snap-rounded overlay can return a collection
    with stray lines / points, which the next overlay refuses (mixed dimension)."""
    if g is None or g.is_empty:
        return Polygon()
    if g.geom_type in ("Polygon", "MultiPolygon"):
        return g
    parts = []
    for p in getattr(g, "geoms", []):
        if p.geom_type == "Polygon":
            parts.append(p)
        elif p.geom_type == "MultiPolygon":
            parts.extend(p.geoms)
    return MultiPolygon(parts) if len(parts) > 1 else (parts[0] if parts else Polygon())


# The lathe GUI runs the system Python with Shapely 1.8 (no grid_size, no
# union_all); the test environment has Shapely 2. Both must work.
try:
    import shapely as _shp
    _SHAPELY2 = hasattr(_shp, "union_all")
except Exception:                                  # pragma: no cover
    _SHAPELY2 = False


def _snap(g):
    """Coordinates rounded to GRID (Shapely 1.8 retry after an overlay failure)."""
    from shapely.ops import transform
    return _poly(transform(lambda x, y, z=None: (
        __import__("numpy").round(__import__("numpy").asarray(x) / GRID) * GRID,
        __import__("numpy").round(__import__("numpy").asarray(y) / GRID) * GRID), g).buffer(0))


def _op18(fn, *gs):
    try:
        return _poly(fn(*gs))
    except Exception:                              # GEOS robustness: snap and retry once
        return _poly(fn(*[_snap(g) for g in gs]))


def _u(geoms):
    geoms = [_poly(g) for g in geoms if g is not None and not g.is_empty]
    geoms = [g for g in geoms if not g.is_empty]
    if not geoms:
        return Polygon()
    if _SHAPELY2:
        return _poly(_shp.union_all(geoms, grid_size=GRID))
    return _op18(lambda *gs: unary_union(list(gs)), *geoms)


def _d(a, b):
    if _SHAPELY2:
        return _poly(_shp.difference(_poly(a), _poly(b), grid_size=GRID))
    return _op18(lambda x, y: x.difference(y), _poly(a), _poly(b))


def _i(a, b):
    if _SHAPELY2:
        return _poly(_shp.intersection(_poly(a), _poly(b), grid_size=GRID))
    return _op18(lambda x, y: x.intersection(y), _poly(a), _poly(b))

SECTION_OF_HEADER = (         # "; === <header> ===" -> section; first match wins
    ("CLEANUP", "cleanup"), ("FINISH", "finish"), ("SPRING", "finish"),   # before ROUGH: the cleanup
    ("FACE", "face"), ("ROUGH", "rough"),                          # header says "roughing boundary"
)



class CutRegionsUnavailable(RuntimeError):
    """rs274 missing or the program didn't run: no shading rather than wrong shading."""


# ----------------------------------------------------------------------
# 1. LinuxCNC's interpretation of the program
# ----------------------------------------------------------------------

def tag_sections(gcode: str) -> str:
    """Copy of the program with an (ICAM_SECTION x) comment after each section
    header, so rs274's canonical output carries the section of every move."""
    out = []
    for line in gcode.splitlines():
        out.append(line)
        m = re.match(r"\s*;\s*===\s*(.+?)\s*===", line)
        if m:
            name = m.group(1).upper()
            sec = next((s for key, s in SECTION_OF_HEADER if key in name), "other")
            out.append(f"(ICAM_SECTION {sec})")
    return "\n".join(out) + "\n"


def run_rs274(gcode: str, tools) -> str:
    """Canonical output of the tagged program. tools: iterable of ToolDef."""
    exe = shutil.which("rs274")
    if exe is None:
        raise CutRegionsUnavailable("LinuxCNC's rs274 interpreter is not installed")
    ini = os.path.join(REPO, "industry-cam.ini")
    with tempfile.TemporaryDirectory() as d:
        tbl = os.path.join(d, "tool.tbl")
        with open(tbl, "w") as fh:
            seen = set()
            for t in tools:
                if t is None or t.tool_number in seen:
                    continue
                seen.add(t.tool_number)
                q = int(getattr(t.orientation, "value", t.orientation) or 0)
                fh.write(f"T{t.tool_number} P{t.tool_number} X0 Z0 D{2 * t.nose_radius:.6f} "
                         f"I{t.front_angle:.1f} J{t.back_angle:.1f} Q{q} ;\n")
        var = os.path.join(d, "v.var")
        with open(var, "w") as fh:
            fh.write("5220\t1.000000\n")
        prog = os.path.join(d, "p.ngc")
        with open(prog, "w") as fh:
            fh.write(tag_sections(gcode))
        out = os.path.join(d, "canon.txt")
        p = subprocess.run([exe, "-i", ini, "-t", tbl, "-v", var, prog, out],
                           stdin=subprocess.DEVNULL, capture_output=True, text=True,
                           timeout=60, cwd=d)
        canon = open(out).read() if os.path.exists(out) else ""
    if "PROGRAM_END" not in canon:
        tail = (p.stdout + p.stderr).strip().splitlines()[-1:]
        raise CutRegionsUnavailable(f"LinuxCNC's interpreter did not run the program to the end: {tail}")
    return canon


@dataclass
class CanonMove:
    section: str
    tool: int
    rapid: bool
    pts: List[Tuple[float, float]]     # tip path, (r, z), densified, start included


def parse_canon(canon: str) -> List[CanonMove]:
    """Moves from rs274 canonical output (X is a radius there)."""
    moves: List[CanonMove] = []
    pos: Optional[Tuple[float, float]] = None
    section, tool = "other", 0
    for line in canon.splitlines():
        m = re.search(r'COMMENT\("ICAM_SECTION (\w+)"\)', line)
        if m:
            section = m.group(1)
            continue
        m = re.search(r"SELECT_TOOL\((\d+)\)", line)
        if m:
            tool = int(m.group(1))
            continue
        m = re.search(r"(STRAIGHT_FEED|STRAIGHT_TRAVERSE)\(([^)]*)\)", line)
        if m:
            v = [float(x) for x in m.group(2).split(",")]
            new = (v[0], v[2])
            if pos is not None and (abs(new[0] - pos[0]) > 1e-12 or abs(new[1] - pos[1]) > 1e-12):
                moves.append(CanonMove(section, tool, m.group(1) == "STRAIGHT_TRAVERSE", [pos, new]))
            pos = new
            continue
        m = re.search(r"ARC_FEED\(([^)]*)\)", line)
        if m and pos is not None:
            v = [float(x) for x in m.group(1).split(",")]
            ze, xe, zc, xc, rot = v[:5]                  # G18: first axis Z, second X
            a0 = math.atan2(pos[0] - xc, pos[1] - zc)    # angle in (z, x), Z -> X positive
            a1 = math.atan2(xe - xc, ze - zc)
            ccw = (a1 - a0) % (2 * math.pi)
            sweep = ccw if rot > 0 else ccw - 2 * math.pi
            if ccw == 0.0:
                # start == end: LinuxCNC runs a FULL circle (2026-11-12: tiny
                # roughing arcs rounded to this; treating it as no move hid it)
                sweep = 2 * math.pi if rot > 0 else -2 * math.pi
            R = math.hypot(pos[0] - xc, pos[1] - zc)
            n = 1
            if R > 1e-9 and abs(sweep) > 1e-12:
                step = 2 * math.acos(max(-1.0, 1 - CHORD_ERR / R)) if R > CHORD_ERR else math.pi
                n = max(2, int(math.ceil(abs(sweep) / max(step, 1e-4))))
            pts = [pos] + [(xc + R * math.sin(a0 + sweep * k / n), zc + R * math.cos(a0 + sweep * k / n))
                           for k in range(1, n)] + [(xe, ze)]
            moves.append(CanonMove(section, tool, False, pts))
            pos = (xe, ze)
    return moves


# ----------------------------------------------------------------------
# 2. What each move sweeps
# ----------------------------------------------------------------------

def nose_offset(tool) -> Tuple[float, float]:
    """Nose centre minus imaginary tip, (r, z) (models.tool.nose_centre_offset)."""
    from models.tool import nose_centre_offset
    return nose_centre_offset(tool)


def _wedge(tool, mode_id: bool) -> Optional[Polygon]:
    """Insert outline around the nose centre at (0, 0): the nose circle plus the
    two edges (front / back angle, tool frame) WEDGE_LEN long, convex. None when
    the edge angles are unknown."""
    from models.tool import ToolDirection
    F, B = getattr(tool, "front_angle", 0.0), getattr(tool, "back_angle", 0.0)
    if F == 0.0 and B == 0.0 or B <= F:
        return None
    sr = -1.0 if mode_id else 1.0
    sz = -1.0 if tool.direction == ToolDirection.LEFT else 1.0
    R = tool.nose_radius
    pts = []
    for ang in (F, B):
        a = math.radians(ang)
        d = (sr * math.sin(a), sz * -math.cos(a))           # edge direction from the nose
        pts.append((d[0] * WEDGE_LEN, d[1] * WEDGE_LEN))
    circle = Point(0, 0).buffer(max(R, 1e-6), NOSE_QUAD_SEGS)
    return unary_union([circle, Polygon([(0, 0)] + pts)]).convex_hull


def _translate(poly: Polygon, dx: float, dy: float) -> List[Tuple[float, float]]:
    return [(x + dx, y + dy) for x, y in poly.exterior.coords]


def swept_regions(moves: List[CanonMove], tools: Dict[int, object], mode_id: bool):
    """Per section: (nose sweep, wedge sweep) as Shapely geometry, (r, z)."""
    nose: Dict[str, list] = {}
    wedge: Dict[str, list] = {}
    for mv in moves:
        if mv.rapid:
            continue
        t = tools.get(mv.tool)
        if t is None:
            raise CutRegionsUnavailable(f"tool T{mv.tool} in the program is not known")
        off = nose_offset(t)
        cpts = [(r + off[0], z + off[1]) for r, z in mv.pts]
        R = max(t.nose_radius, 1e-6)
        nose.setdefault(mv.section, []).append(
            LineString(cpts).buffer(R, NOSE_QUAD_SEGS) if len(cpts) > 1
            else Point(cpts[0]).buffer(R, NOSE_QUAD_SEGS))
        w = _wedge(t, mode_id)
        if w is not None:
            hulls = []
            for a, b in zip(cpts, cpts[1:]):
                hulls.append(Polygon(_translate(w, *a) + _translate(w, *b)).convex_hull)
            wedge.setdefault(mv.section, []).append(unary_union(hulls))
    return ({k: unary_union(v) for k, v in nose.items()},
            {k: unary_union(v) for k, v in wedge.items()})


# ----------------------------------------------------------------------
# 3. Sections
# ----------------------------------------------------------------------

@dataclass
class CutSections:
    face: object
    rough: object
    cleanup: object           # removed by the cleanup (semi-finish) pass
    finish: object            # removed by the finish pass(es): the finish allowance
    finished: object          # as cut, minus the declared uncut regions
    uncut: object
    gouge: object             # errors: should be empty
    not_removed: object
    stock: object
    notes: List[str] = field(default_factory=list)

    @property
    def band(self):
        """Cleanup + finish together (what roughing leaves for the contour passes)."""
        return _u([self.cleanup, self.finish])

    def rings(self, name: str) -> List[List[Tuple[float, float]]]:
        """Closed rings of a section for drawing, as (z, r) points: exterior and
        interior rings of every polygon (draw with odd-even fill)."""
        return geom_rings(getattr(self, name))

    @property
    def ok(self) -> bool:
        return self.gouge.is_empty and self.not_removed.is_empty


def geom_rings(g) -> List[List[Tuple[float, float]]]:
    out = []
    if g is None or g.is_empty:
        return out
    polys = [g] if isinstance(g, Polygon) else [p for p in getattr(g, "geoms", []) if isinstance(p, Polygon)]
    for p in polys:
        if p.is_empty:
            continue
        out.append([(z, r) for r, z in p.exterior.coords])
        for hole in p.interiors:
            out.append([(z, r) for r, z in hole.coords])
    return out


def _thick(g):
    """Drop slivers thinner than 2*THIN (numerical noise), keep real regions whole."""
    if g.is_empty:
        return g
    core = g.buffer(-THIN)
    if core.is_empty:
        return Polygon()
    return g.intersection(core.buffer(THIN * 3)).buffer(0)


def stock_polygon(stock, mode_id: bool):
    """The bar this block cuts, (r, z): from the axis (OD) or pilot hole (ID) to
    the stock radius, from the stock front (Z start) to Z end."""
    r_in = stock.pilot_hole_dia / 2.0 if mode_id else 0.0
    # Z start <= allowance means the face is already at Z0; the model then raises
    # z_start for approach clearance only (StockDef.face_at_z0) - no stock there.
    front = 0.0 if getattr(stock, "face_at_z0", False) else max(stock.z_start, 0.0)
    return box(r_in, stock.z_end, stock.diameter / 2.0, front)


def part_polygon(profile, stock, mode_id: bool):
    """The intended finished part of this block (the contour it is programmed to
    cut, i.e. after tool-reach bridging), (r, z), closed toward the material."""
    from geometry.tool_reach import densify_coords
    from geometry.zone_builder import profile_to_radius_coords
    pts, _ = densify_coords(profile_to_radius_coords(profile))
    if mode_id:
        R = stock.diameter / 2.0 + 1.0
        ring = [(R, pts[0][1])] + pts + [(R, pts[-1][1])]
    else:
        ring = [(0.0, pts[0][1])] + pts + [(0.0, pts[-1][1])]
    return Polygon(ring).buffer(0)


def _concave_corner_zone(profile, tool_radius: float, mode_id: bool):
    """Where the nose radius legitimately leaves material: within ~1.5 TNR of the
    contour's concave corners."""
    from geometry.tool_reach import densify_coords
    from geometry.zone_builder import profile_to_radius_coords
    pts, _ = densify_coords(profile_to_radius_coords(profile))
    zone = []
    s = -1.0 if mode_id else 1.0
    for a, b, c in zip(pts, pts[1:], pts[2:]):
        u = (b[0] - a[0], b[1] - a[1])
        v = (c[0] - b[0], c[1] - b[1])
        cross = u[0] * v[1] - u[1] * v[0]
        # OD travel -Z with material below: a turn toward the material (concave) is cross > 0
        if s * cross > 1e-12:
            zone.append(Point(b).buffer(1.6 * tool_radius + THIN))
    return unary_union(zone) if zone else Polygon()


def compute_sections(gcode: str, plan_result, uncut_outlines=()) -> CutSections:
    """All shaded sections of one profile block, from its G-code as LinuxCNC runs it."""
    from models.profile import MachiningMode
    pr = plan_result
    mode_id = pr.profile.mode == MachiningMode.ID
    tools = {pr.tool.tool_number: pr.tool}
    ft = getattr(pr, "finish_tool", None)
    if ft is not None:
        tools[ft.tool_number] = ft
    for t in tools.values():
        if t.nose_radius < 1e-4 and _wedge(t, mode_id) is None:
            raise CutRegionsUnavailable(
                f"T{t.tool_number} has no nose radius or edge angles in the tool table, so the "
                f"graph can't tell what it removes")
    moves = parse_canon(run_rs274(gcode, tools.values()))
    nose, wedge = swept_regions(moves, tools, mode_id)

    stock = stock_polygon(pr.stock, mode_id)
    part = part_polygon(pr.profile, pr.stock, mode_id)

    def removed(sec):
        g = nose.get(sec, Polygon())
        w = wedge.get(sec)
        if w is not None:
            g = _u([g, _d(w, part)])
        return _i(g, stock)

    face = removed("face")
    rough = _d(removed("rough"), face)
    cleanup = _d(removed("cleanup"), _u([face, rough]))
    finish = _d(removed("finish"), _u([face, rough, cleanup]))
    other = _d(removed("other"), _u([face, rough, cleanup, finish]))
    if not other.is_empty:          # anything cut outside the known sections joins the finish
        finish = _u([finish, other])
    taken = _u([face, rough, cleanup, finish])
    as_cut = _d(stock, taken)

    uncut_polys = [Polygon([(x / 2.0, z) for x, z in o]).buffer(0) for o in uncut_outlines if len(o) >= 3]
    uncut = _i(_u(uncut_polys), as_cut) if uncut_polys else Polygon()
    finished = _d(as_cut, uncut)

    nose_all = _u(list(nose.values()))
    gouge = _thick(_i(_i(part, stock), nose_all))
    tnr = max(t.nose_radius for t in tools.values())
    # Judged only over the profile's own range (Z0 and back): stock in front of Z0
    # that this block doesn't face (X start setting) is the operator's choice; it
    # still shows, as part of what the program leaves.
    # Also not judged: within a nose radius of the Z end (the bar goes on past
    # it, passes end there and leave nose scallops on that artificial edge) and of
    # the contour's start point (with the face left on, that corner is concave).
    margin = 1.6 * tnr + THIN
    judged = box(-10.0, pr.stock.z_end + margin, 10.0, 0.0)
    from geometry.tool_reach import densify_coords
    from geometry.zone_builder import profile_to_radius_coords
    start = densify_coords(profile_to_radius_coords(pr.profile))[0][0]
    expected = unary_union([_concave_corner_zone(pr.profile, tnr, mode_id),
                            Point(start).buffer(margin)])
    excess = _d(_i(_d(as_cut, part), judged), expected)
    not_removed = _thick(excess)

    notes = []
    if not gouge.is_empty:
        b = gouge.bounds
        notes.append(f"GRAPH CHECK: the program cuts into the finished part near "
                     f"X{2 * b[0]:.4f}-X{2 * b[2]:.4f} Z{b[1]:.4f}-Z{b[3]:.4f} (shown hatched red).")
    if not not_removed.is_empty:
        b = not_removed.bounds
        notes.append(f"GRAPH CHECK: material the program should remove is left near "
                     f"X{2 * b[0]:.4f}-X{2 * b[2]:.4f} Z{b[1]:.4f}-Z{b[3]:.4f} (shown hatched red).")
    # partition check (exact by construction; guards future edits)
    total = face.area + rough.area + cleanup.area + finish.area + as_cut.area
    if abs(total - stock.area) > max(AREA_EPS, 1e-6 * stock.area):
        notes.append(f"GRAPH CHECK: shaded sections don't add up to the stock "
                     f"({total:.6f} vs {stock.area:.6f} in^2); shading may be wrong.")
    return CutSections(face, rough, cleanup, finish, finished, uncut, gouge, not_removed, stock, notes)
