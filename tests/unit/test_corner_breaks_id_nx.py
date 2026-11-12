"""ID corner breaks validated against the owner's NX ID reference part.

Fixtures (owner-made in NX 2026-11-10, mm, turning axis = model X, front face
at X0): tests/fixtures/nx_corner_break/id_sharp.stp and id_broken.stp.
Ø36 bar, blind stepped bore (mouth Ø30, bottom at Z-27).

Breaks NX applied (V1 = bore mouth, numbering as for OD):
  V1 C1 (along the front face, outward), V2 R0.5, V3 R0.25, V4 C1,
  V6 R2, V7 C2; V5 and V8-V10 sharp. No trim conflicts.

Before this test the engine built ID breaks with the legacy chord method:
V1's chamfer went INTO the bore (face direction taken from the centreline)
and V4/V6/V7 were clamped to 40 % of the shorter neighbour.
"""

import os

import pytest

from models.profile import (
    ClosedProfile, CornerBreak, CornerBreakType, MachiningMode, ProfileMove,
    SegmentType,
)
from tests.unit.test_corner_breaks_od_nx import nx_elements, _close

FIX = os.path.join(os.path.dirname(__file__), "..", "fixtures", "nx_corner_break")

# Sharp ID profile as an operator enters it: (Ø, Z), bore mouth first, down
# to the centre at the bottom of the blind bore.
ID_POINTS = [(30, 0), (30, -6), (27, -6), (27, -12), (30, -12), (30, -18),
             (21, -18), (21, -21), (24, -21), (24, -27), (0, -27)]
_C = lambda s: CornerBreak(CornerBreakType.CHAMFER, size=s)
_R = lambda s: CornerBreak(CornerBreakType.FILLET, radius=s)
ID_BREAKS = [_C(1), _R(0.5), _R(0.25), _C(1), None, _R(2), _C(2), None, None, None]


def _profile(breaks):
    segs = [ProfileMove(SegmentType.LINE, x=d, z=z) for d, z in ID_POINTS]
    return ClosedProfile(segments=segs, corner_breaks=breaks, mode=MachiningMode.ID,
                         z_end=-27.0)


def _chain(coords):
    """zone_builder coords -> elements [(kind, sorted ends (z, r), centre)]."""
    import math
    out, prev = [], None
    for c in coords:
        p = (c["z"], c["x_radius"])
        if prev is not None and math.dist(p, prev) > 1e-9:
            if c["type"] == SegmentType.ARC and abs(c.get("radius", 0.0)) > 1e-12:
                rr = c["radius"]
                # Build123d RadiusArc in sketch (X = r, Y = z): +R centre RIGHT of travel.
                sx, sy, ex, ey = prev[1], prev[0], p[1], p[0]
                dx, dy = ex - sx, ey - sy
                ln = math.hypot(dx, dy)
                h = math.sqrt(max(rr * rr - (ln / 2) ** 2, 0.0))
                s = 1.0 if rr > 0 else -1.0
                cx = (sx + ex) / 2 + s * (dy / ln) * h
                cy = (sy + ey) / 2 + s * (-dx / ln) * h
                out.append(("arc", tuple(sorted([prev, p])), (cy, cx, abs(rr))))
            else:
                out.append(("line", tuple(sorted([prev, p])), None))
        prev = p
    return out


def _nx_profile_elements(path):
    """NX elements on the bore profile: drops the bar OD, the back face and
    the part of the front face outside the bore-mouth break."""
    keep = []
    for kind, (a, b), extra in nx_elements(path):
        if a[1] == b[1] == 18.0 or a[0] == b[0] == -33.0:
            continue
        if a[0] == b[0] == 0.0 and min(a[1], b[1]) >= 15.0 and kind == "line" \
                and max(a[1], b[1]) == 18.0:
            continue
        keep.append((kind, tuple(sorted([a, b])), extra))
    return keep


def _match(el, others):
    kind, ends, extra = el
    return any(o[0] == kind and _close(ends[0], o[1][0]) and _close(ends[1], o[1][1])
               and (kind == "line" or _close(extra, o[2])) for o in others)


def _engine(breaks):
    from geometry.zone_builder import profile_to_radius_coords
    return _chain(profile_to_radius_coords(_profile(breaks)))


def test_sharp_profile_matches_nx_sharp_part():
    """Each entered segment is a face of the NX sharp part."""
    nx = _nx_profile_elements(os.path.join(FIX, "id_sharp.stp"))
    eng = _engine([None] * (len(ID_POINTS) - 1))
    # Sharp NX front face runs Ø30..Ø36 (dropped above); the rest must match.
    missing = [e for e in eng if not _match(e, nx)]
    assert not missing, missing


def test_id_breaks_match_nx_element_by_element():
    nx = _nx_profile_elements(os.path.join(FIX, "id_broken.stp"))
    eng = _engine(ID_BREAKS)
    missing = [e for e in nx if not _match(e, eng)]
    extra = [e for e in eng if not _match(e, nx)]
    assert not missing, f"NX elements the engine did not build: {missing}"
    assert not extra, f"engine elements NX does not have: {extra}"


def test_v1_chamfer_runs_out_along_the_front_face():
    """Regression: the legacy method put the bore-mouth chamfer into the bore."""
    eng = _engine(ID_BREAKS)
    v1 = [e for e in eng if e[0] == "line" and _close(e[1][0], (-1.0, 15.0))]
    assert v1 and _close(v1[0][1][1], (0.0, 16.0)), v1


def test_id_reports_and_corner_kinds():
    from geometry.corner_breaks_od import build_od_corner_coords, od_vertex_kinds
    prof = _profile(ID_BREAKS)
    result = build_od_corner_coords(prof)
    by_v = {r.vertex: r for r in result.reports}
    assert sorted(by_v) == [1, 2, 3, 4, 6, 7]
    assert all(r.status == "ok" for r in by_v.values())
    kinds = {k + 1: v for k, v in od_vertex_kinds(prof).items()}
    assert kinds == {1: "convex", 2: "concave", 3: "convex", 4: "convex", 5: "concave",
                     6: "concave", 7: "convex", 8: "convex", 9: "concave", 10: "concave"}
    for v, r in by_v.items():
        assert r.corner == kinds[v], v


def test_od_unchanged_by_id_support():
    """The OD face still starts at the centreline (V1 direction +r)."""
    from geometry.corner_breaks_od import _face_start
    assert _face_start([(3.0, 0.0)], is_id=False) == (0.0, 0.0)
    r, z = _face_start([(3.0, 0.0)], is_id=True)
    assert r > 3.0 and z == 0.0


def test_corner_break_tool_shows_id_vertices_as_validated():
    """The Program-tab tool solves ID breaks with the validated solver: real
    convex/concave labels, no 'unvalidated' status (was: every ID break)."""
    from PyQt5.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication([])
    from gui.program_tab import ProgramTab
    mm = lambda v: v / 25.4
    tab = ProgramTab()
    try:
        _check_id_tool_rows(tab, mm)
    finally:
        # Close and delete it like the other Program-tab tests do. Left to the
        # garbage collector, the top-level tab's C++ side was freed while its
        # posted events / timers were still queued; the next teardown's
        # processEvents() then segfaulted, depending on when GC happened to run.
        tab.close()
        tab.deleteLater()


def _check_id_tool_rows(tab, mm):
    tab._load_program_data({
        "version": 1, "block_type": "ID Profile",
        "stock": {"diameter": mm(36), "x_start": mm(20), "z_start": 0.1, "z_end": mm(-27),
                  "pilot_hole_dia": mm(20), "mode": "id"},
        "roughing": {"tool_number": 1}, "finishing": {"tool_number": 1},
        "segments": [{"type": "line", "x": mm(d), "z": mm(z), "radius": 0.0}
                     for d, z in ID_POINTS[:-1]],
        "corner_breaks": [{"type": "chamfer", "size": mm(1), "angle": 45.0, "radius": 0.0},
                          {"type": "fillet", "size": 0.0, "angle": 45.0, "radius": mm(0.5)}]
        + [None] * 7})
    assert tab._get_machining_mode() == "id"
    tab._btn_cb_tool.setChecked(True)
    tab._refresh_cb_state()
    rows = {r["index"] + 1: r for r in tab._cb_panel._rows}
    assert rows[1]["corner"] == "convex" and rows[2]["corner"] == "concave"
    assert rows[1]["status"] == "ok" and rows[2]["status"] == "ok"
    assert sorted(k + 1 for k in tab._od_corner_result().geometry) == [1, 2]
