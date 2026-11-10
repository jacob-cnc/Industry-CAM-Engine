"""Vertex picking for the corner-break tool (pure logic, screen pixels).

Rules carried over from DXF-Tooling's selection code, plus the agreed
tie-breakers for vertices that sit on (or almost on) top of each other:

  1. nearest vertex within the pixel tolerance wins (tolerance in PIXELS,
     so picking feels the same at any zoom);
  2. a real tie (distances within `tie_px`): the vertex whose own two
     segments point most nearly toward the cursor - i.e. click on the side
     of the corner you mean;
  3. still tied: prefer a vertex that is already selected (a click toggles
     what you are looking at instead of jumping to its neighbour);
  4. still tied: return all tied vertices so the caller can ask (chooser).

All inputs are screen coordinates (x, y) in pixels.
"""

import math
from typing import List, Optional, Sequence, Tuple

Point = Tuple[float, float]

PICK_TOL_PX = 20.0     # generous: mouse and touchscreen
TIE_PX = 2.0
SIDE_MARGIN_DEG = 5.0  # side rule must win by this much to decide


def pick_vertex(click: Point, pts: Sequence[Point],
                prev_pts: Sequence[Optional[Point]],
                next_pts: Sequence[Optional[Point]],
                selected: Sequence[int] = (),
                tol_px: float = PICK_TOL_PX,
                tie_px: float = TIE_PX) -> List[int]:
    """Indices of the picked vertex: [] = nothing in range, [i] = decided,
    [i, j, ...] = unresolvable tie (ask the user).

    prev_pts[i] / next_pts[i]: the far ends of vertex i's incoming and
    outgoing segments (screen), or None if unknown.
    """
    dists = [math.dist(click, p) for p in pts]
    cands = [i for i, d in enumerate(dists) if d <= tol_px]
    if not cands:
        return []
    best = min(dists[i] for i in cands)
    tied = sorted((i for i in cands if dists[i] - best <= tie_px), key=lambda i: dists[i])
    if len(tied) == 1:
        return tied

    # Rule 2: side of the corner.
    def side_score(i):
        vx, vy = click[0] - pts[i][0], click[1] - pts[i][1]
        if math.hypot(vx, vy) < 1e-9:
            return None
        best_ang = None
        for far in (prev_pts[i], next_pts[i]):
            if far is None:
                continue
            sx, sy = far[0] - pts[i][0], far[1] - pts[i][1]
            if math.hypot(sx, sy) < 1e-9:
                continue
            cos = (vx * sx + vy * sy) / (math.hypot(vx, vy) * math.hypot(sx, sy))
            ang = math.degrees(math.acos(max(-1.0, min(1.0, cos))))
            best_ang = ang if best_ang is None else min(best_ang, ang)
        return best_ang

    scores = {i: side_score(i) for i in tied}
    scored = sorted((s, i) for i, s in scores.items() if s is not None)
    if len(scored) == len(tied) and len(scored) >= 2 \
            and scored[1][0] - scored[0][0] >= SIDE_MARGIN_DEG:
        return [scored[0][1]]

    # Rule 3: already selected.
    sel = [i for i in tied if i in set(selected)]
    if len(sel) == 1:
        return sel
    return tied
