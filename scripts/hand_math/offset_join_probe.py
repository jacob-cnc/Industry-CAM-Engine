#!/usr/bin/env python3
"""Where does the kernel's SHARP-join offset fail, closed face vs open wire? (basic)

Contour roughing offsets the CLOSED finished-part face (profile + the engine's
closure to the centreline and along the back face). For some profiles OCCT's
sharp (Kind.INTERSECTION) join returns a null shape and kernel_offset falls back
to rounded joins (logged, not shown to the operator). The finish and cleanup
passes instead offset the profile's OPEN wire (ZoneQueryAPI.profile_offset_edges).

For each program and each roughing offset distance this asks the kernel, with
sharp joins only and no fallback:
    face   offset of the closed finished-part face (what contour roughing does)
    wire   offset of the open profile wire (what finish / cleanup do)
and prints which distances fail. Read-only: no engine code is changed.

usage: offset_join_probe.py prog.json [...]   (from the repo root; OD offset programs)
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.getcwd())


def probe(path):
    from build123d import Kind, Side, offset as b3d_offset
    from pipeline.model_builder import build_from_fields
    from geometry.zone_builder import build_zones, profile_to_radius_coords, _build_face_from_coords
    from models.tool import ToolDef, ToolDirection, ToolOrientation, ToolType
    d = json.load(open(path))
    st, ro = d["stock"], d["roughing"]
    tool = ToolDef(4, 0.016, 80, 0.5, ToolOrientation(2), ToolDirection.RIGHT, ToolType.TURNING,
                   front_angle=95.0, back_angle=175.0)
    p, s, r, f = build_from_fields(
        segments=d["segments"], stock_dia=st["diameter"], x_start=st.get("x_start", 0.0),
        z_start=st.get("z_start", 0.1), z_end=st["z_end"], stock_back_z=st["z_end"], mode="od",
        pilot_hole_dia=0.0, doc_dia=ro["doc_dia"], feed=ro["feed"], strategy="offset_contour",
        fin_allowance=ro["fin_allowance"], peck_enabled=False, peck_length=None, spindle_rpm=1000,
        finish_passes=1, finish_doc_dia=0.002, finish_feed=0.003, finish_spring_pass=False,
        tool_def=tool, x_park=3, z_park=1, corner_breaks=[])
    zones = build_zones(p, s, tool, r)
    face = zones.finished_part
    wire = _build_face_from_coords(profile_to_radius_coords(p), p, closed=False)
    from build123d import Wire
    wire = Wire(wire.edges())
    fin_r, doc_r = r.fin_allowance / 2.0, r.doc_dia / 2.0
    R = tool.nose_radius
    face_fail, wire_fail, n = [], [], 0
    dist = fin_r + doc_r + R
    while dist < s.diameter / 2.0:
        n += 1
        try:
            res = b3d_offset(face, amount=dist, kind=Kind.INTERSECTION)
            if not res.faces():
                face_fail.append(dist)
        except Exception:
            face_fail.append(dist)
        try:
            res = wire.offset_2d(dist, kind=Kind.INTERSECTION, side=Side.LEFT, closed=False)
            if not res.edges():
                wire_fail.append(dist)
        except Exception:
            wire_fail.append(dist)
        dist += doc_r
    fmt = lambda xs: (f"{len(xs)} fail, from {min(xs):.4f}" if xs else "all OK")
    print(f"{os.path.basename(path)[:44]:44s} {n:3d} distances | closed face: {fmt(face_fail):24s} | open wire: {fmt(wire_fail)}")


if __name__ == "__main__":
    for prog in sys.argv[1:]:
        try:
            probe(prog)
        except Exception as exc:
            print(f"{os.path.basename(prog)[:44]:44s} probe error: {type(exc).__name__}: {exc}")
