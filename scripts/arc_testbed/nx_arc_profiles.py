"""Turn the owner's NX corner-break parts into ARC-SEGMENT profiles.

Walks the NX broken outline (tests/fixtures/nx_corner_break/{broken,id_broken}.stp)
and emits the profile an operator would type if every fillet were its own arc
segment: points in (Ø, Z) mm, arcs with centre, radius, sweep and the engine's
current RadiusArc sign (side of chord: +R centre RIGHT of travel, sketch
X = radius, Y = Z). Ground truth = the NX elements.

usage (repo root on PYTHONPATH, miniforge python):
    python nx_arc_profiles.py od|id
"""
import json, math, os, sys
sys.path.insert(0, "tests/unit")
from test_corner_breaks_od_nx import nx_elements

FIX = "tests/fixtures/nx_corner_break"


def walk(path, mode):
    els = nx_elements(path)
    edges = []
    for kind, (a, b), extra in els:
        a = (round(a[0], 6), round(a[1], 6)); b = (round(b[0], 6), round(b[1], 6))
        edges.append((kind, a, b, extra))
    adj = {}
    for e in edges:
        adj.setdefault(e[1], []).append(e)
        adj.setdefault(e[2], []).append(e)
    if mode == "od":
        # start at the front face rim of the OD profile: largest r at z = 0 that
        # is not the stock - the profile starts where the face (from r=0) ends.
        start = max((p for p in adj if p[0] == 0.0 and p[1] > 0), key=lambda p: p[1])
        prev_edge = next(e for e in adj[start] if {e[1], e[2]} >= {start} and
                         (e[1][0] == e[2][0] == 0.0))
    else:
        # ID: bore mouth = smallest r at z = 0 above the axis
        start = min((p for p in adj if p[0] == 0.0 and p[1] > 0), key=lambda p: p[1])
        prev_edge = next(e for e in adj[start] if e[1][0] == e[2][0] == 0.0)
    out, cur, used = [], start, {id(prev_edge)}
    while True:
        nxt = [e for e in adj[cur] if id(e) not in used]
        if not nxt:
            break
        e = nxt[0]
        used.add(id(e))
        other = e[2] if e[1] == cur else e[1]
        out.append((e[0], cur, other, e[3]))
        cur = other
        if cur[1] == 0.0:                                  # reached the axis
            break
        if mode == "od" and cur[1] == max(p[1] for p in adj) and cur[0] == min(p[0] for p in adj):
            break
    return out


def signed_radius(start, end, centre, r):
    """Engine RadiusArc sign. start/end/centre as (z, r)."""
    sx, sy, ex, ey = start[1], start[0], end[1], end[0]
    cx, cy = centre[1], centre[0]
    side = (ex - sx) * (cy - sy) - (ey - sy) * (cx - sx)
    return -r if side > 0 else r


def sweep_deg(start, end, centre):
    a0 = math.atan2(start[1] - centre[1], start[0] - centre[0])
    a1 = math.atan2(end[1] - centre[1], end[0] - centre[0])
    d = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
    return math.degrees(d)


def profile(mode):
    path = os.path.join(FIX, "broken.stp" if mode == "od" else "id_broken.stp")
    segs = []
    for kind, a, b, extra in walk(path, mode):
        if not segs:
            segs.append({"type": "line", "x": 2 * a[1], "z": a[0], "radius": 0.0})
        if kind == "arc":
            centre = (extra[0], extra[1])
            r = extra[2]
            segs.append({"type": "arc", "x": 2 * b[1], "z": b[0],
                         "radius": signed_radius(a, b, centre, r),
                         "_centre_dia_z": (2 * centre[1], centre[0]), "_R": r,
                         "_sweep": round(sweep_deg(a, b, centre), 3)})
        else:
            segs.append({"type": "line", "x": 2 * b[1], "z": b[0], "radius": 0.0})
    return segs


if __name__ == "__main__":
    mode = sys.argv[1]
    segs = profile(mode)
    for s in segs:
        extra = f"  R{s['_R']:.3f} sweep {s['_sweep']:+.1f}  centre Ø{s['_centre_dia_z'][0]:.3f} Z{s['_centre_dia_z'][1]:.3f}  engine R{s['radius']:+.3f}" if s["type"] == "arc" else ""
        print(f"{s['type']:4s} Ø{s['x']:8.4f} Z{s['z']:8.4f}{extra}")
    json.dump(segs, open(ff"{mode}_segments_mm.json", "w"), indent=1)
