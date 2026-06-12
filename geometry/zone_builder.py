"""Zone construction for Industry CAM Engine.

Builds machining zones (Finished Part, Finish Allowance, Material to Rough,
True Face) using Build123d boolean operations on 2D Faces.

The ONLY place where Build123d is used for zone construction.
Imports from: models/, tools/
"""

from dataclasses import dataclass
from typing import List, Tuple, Optional

from build123d import (
    BuildSketch, BuildLine, Line, RadiusArc, Spline, Vector, make_face, Sketch,
    Axis, Mode, Kind,
)
from OCP.BRep import BRep_Tool
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_EDGE, TopAbs_WIRE
from OCP.TopoDS import TopoDS
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.GeomAbs import GeomAbs_Line, GeomAbs_Circle

from models.profile import ClosedProfile, ProfileMove, SegmentType, MachiningMode
from models.stock import StockDef
from models.tool import ToolDef
from models.params import RoughingParams


@dataclass
class ZoneSet:
    """The complete set of machining zones constructed from profile + stock."""
    finished_part: object       # Build123d Face
    finish_allowance: object    # Build123d Face
    material_to_rough: object   # Build123d Face
    true_face: object           # Build123d Face
    stock_face: object          # Build123d Face
    roughing_boundary_wire: object  # Build123d Wire
    profile_boundary_wire: object   # Build123d Wire


def build_zones(
    profile: ClosedProfile,
    stock: StockDef,
    tool: ToolDef,
    roughing_params: RoughingParams,
) -> ZoneSet:
    """Construct all machining zones using Build123d boolean operations on 2D Faces.

    Steps:
    1. Build closed profile contour (user segments + closure segments)
    2. Create Finished Part face from closed contour
    3. Offset profile by fin_allowance (radius) → Roughing Boundary
       (TNR handled by G41/G42, not coordinate offset)
    4. Create Stock face from stock parameters
    5. Boolean operations to derive all zones
    6. Create True Face zone from X_start, Z_start, Stock_OD, Z=0

    All coordinates in RADIUS for Build123d sketch plane.
    X in sketch = lathe X radius
    Y in sketch = lathe Z
    """
    mode = profile.mode

    # Step 1: Build closed profile contour
    profile_coords = _profile_to_radius_coords(profile)
    closure_coords = _compute_closure_coords(profile, stock, profile_coords)
    all_coords = profile_coords + closure_coords

    # Build the finished part face from closed contour
    finished_part_face = _build_face_from_coords(all_coords, profile)

    # Step 2: Compute fin_allowance in radius
    fin_allowance_radius = roughing_params.fin_allowance / 2.0  # diameter to radius

    # Step 3: Offset profile to get roughing boundary (keep zone)
    # Use Kind.INTERSECTION for sharp corners (no fillets)
    # Keep zone is ALWAYS larger than finished part (protective buffer on all sides)
    # Positive offset expands the face outward in all directions
    offset_amount = fin_allowance_radius

    from build123d import offset as b3d_offset, Kind
    keep_zone_face = b3d_offset(finished_part_face, amount=offset_amount, kind=Kind.INTERSECTION)

    # Clip the keep zone to stock boundaries (offset may extend beyond Z_end or below X=0)
    # Build a clipping rectangle matching the stock extent
    clip_face = _build_stock_face(stock.diameter / 2.0, stock.z_start, stock.z_end, mode, stock.pilot_hole_dia / 2.0)
    
    # Intersect keep_zone with clip to remove anything outside stock
    clip_faces = clip_face.faces() if hasattr(clip_face, 'faces') else []
    keep_faces_raw = keep_zone_face.faces() if hasattr(keep_zone_face, 'faces') else []
    
    if clip_faces and keep_faces_raw:
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
        common_op = BRepAlgoAPI_Common(keep_faces_raw[0].wrapped, clip_faces[0].wrapped)
        common_op.Build()
        if common_op.IsDone():
            from build123d import Face as B3dFace
            keep_zone_face = B3dFace(common_op.Shape())
        # If common fails, keep the unclipped version (offset is still valid, just extends slightly)

    # Step 4: Build stock face for MTR computation
    # MTR stock starts at Z=fin_allowance (not Z_start) to exclude True Face Zone
    stock_radius = stock.diameter / 2.0
    x_start_radius = stock.x_start / 2.0
    
    # Full stock face (for reference)
    stock_face = _build_stock_face(stock_radius, stock.z_start, stock.z_end, mode, stock.pilot_hole_dia / 2.0)
    
    # MTR stock: only the turning area (below face, between roughing boundary X and stock OD)
    # For OD: from the first roughing boundary X to stock OD, Z=fin_allowance to Z_end
    # For ID: Z_end is clipped by fin_allowance (leave room for finish pass at bore bottom)
    if mode == MachiningMode.ID:
        mtr_z_end = stock.z_end + fin_allowance_radius
    else:
        mtr_z_end = stock.z_end
    mtr_stock_face = _build_stock_face(stock_radius, fin_allowance_radius, mtr_z_end, mode, stock.pilot_hole_dia / 2.0)

    # Step 5: Boolean subtract — MTR = mtr_stock - keep_zone
    stock_faces = mtr_stock_face.faces() if hasattr(mtr_stock_face, 'faces') else []
    keep_faces = keep_zone_face.faces() if hasattr(keep_zone_face, 'faces') else []

    if not stock_faces or not keep_faces:
        raise RuntimeError("Zone construction failed: could not extract faces for boolean operation")

    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    cut_op = BRepAlgoAPI_Cut(stock_faces[0].wrapped, keep_faces[0].wrapped)
    cut_op.Build()
    if not cut_op.IsDone():
        raise RuntimeError("Boolean subtraction (stock - keep_zone) failed. Do NOT create a fallback.")
    
    from build123d import Face as B3dFace
    material_to_rough_face = B3dFace(cut_op.Shape())

    # Step 6: True Face Zone
    true_face_face = _build_true_face(stock, mode)

    # Step 6b: Finish Allowance Zone = keep_zone - finished_part (thin band only)
    # This is the area between the profile and the roughing boundary
    keep_faces_for_fa = keep_zone_face.faces() if hasattr(keep_zone_face, 'faces') else []
    fp_faces = finished_part_face.faces() if hasattr(finished_part_face, 'faces') else []
    
    if keep_faces_for_fa and fp_faces:
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut as BRepCut_FA
        fa_cut = BRepCut_FA(keep_faces_for_fa[0].wrapped, fp_faces[0].wrapped)
        fa_cut.Build()
        if fa_cut.IsDone():
            finish_allowance_face = B3dFace(fa_cut.Shape())
        else:
            finish_allowance_face = keep_zone_face  # Fallback to full keep zone
    else:
        finish_allowance_face = keep_zone_face

    return ZoneSet(
        finished_part=finished_part_face,
        finish_allowance=finish_allowance_face,
        material_to_rough=material_to_rough_face,
        true_face=true_face_face,
        stock_face=stock_face,
        roughing_boundary_wire=None,
        profile_boundary_wire=None,
    )


def _profile_to_radius_coords(profile: ClosedProfile) -> List[dict]:
    """Convert profile segments to radius coordinates for Build123d.

    Applies corner breaks (chamfers/fillets) at segment junctions by inserting
    additional geometry between profile segments. This ensures the finished part
    face has the correct shape including all corner breaks.

    Returns list of segment descriptors with coordinates in radius.
    """
    import math

    segments = profile.segments
    corner_breaks = profile.corner_breaks

    if not segments:
        return []

    # Pre-compute segment endpoints in radius for direction calculations
    seg_endpoints = []
    for seg in segments:
        seg_endpoints.append((seg.x / 2.0, seg.z))

    coords = []

    for i, seg in enumerate(segments):
        x_r = seg.x / 2.0
        z = seg.z

        # Check if there's a corner break AFTER this segment (at junction i → i+1)
        cb = None
        if corner_breaks and i < len(corner_breaks):
            cb = corner_breaks[i]

        if cb is not None and cb.break_type.value != "none" and i < len(segments) - 1:
            # There's a corner break at the junction between segment[i] and segment[i+1]
            # Compute arrival direction (toward this segment's endpoint)
            if i == 0:
                prev_x_r, prev_z = 0.0, 0.0  # implicit origin
            else:
                prev_x_r, prev_z = seg_endpoints[i - 1]

            arr_dx = x_r - prev_x_r
            arr_dz = z - prev_z
            arr_len = math.sqrt(arr_dx * arr_dx + arr_dz * arr_dz)

            # Departure direction (from junction toward next segment's endpoint)
            next_x_r, next_z = seg_endpoints[i + 1]
            dep_dx = next_x_r - x_r
            dep_dz = next_z - z
            dep_len = math.sqrt(dep_dx * dep_dx + dep_dz * dep_dz)

            if arr_len > 1e-9 and dep_len > 1e-9:
                arr_ux = arr_dx / arr_len
                arr_uz = arr_dz / arr_len
                dep_ux = dep_dx / dep_len
                dep_uz = dep_dz / dep_len

                from models.profile import CornerBreakType

                if cb.break_type == CornerBreakType.CHAMFER:
                    size = cb.size if cb.size > 0 else 0.015
                    trim_back = min(size, arr_len * 0.4)
                    trim_fwd = min(size, dep_len * 0.4)

                    # Trim point on arriving segment (back from junction)
                    p1_x = x_r - arr_ux * trim_back
                    p1_z = z - arr_uz * trim_back
                    # Trim point on departing segment (forward from junction)
                    p2_x = x_r + dep_ux * trim_fwd
                    p2_z = z + dep_uz * trim_fwd

                    # Emit trimmed endpoint for this segment
                    coords.append({
                        "type": seg.segment_type,
                        "x_radius": p1_x,
                        "z": p1_z,
                        "radius": seg.radius,
                    })
                    # Emit chamfer endpoint (line from p1 to p2)
                    coords.append({
                        "type": SegmentType.LINE,
                        "x_radius": p2_x,
                        "z": p2_z,
                        "radius": 0.0,
                    })
                    continue  # Skip the normal append

                elif cb.break_type == CornerBreakType.FILLET:
                    fillet_r = cb.radius if cb.radius > 0 else 0.015

                    # Half-angle between reversed arrival and departure
                    dot = (-arr_ux) * dep_ux + (-arr_uz) * dep_uz
                    dot = max(-1.0, min(1.0, dot))
                    half_angle = math.acos(dot) / 2.0

                    if half_angle > 1e-6:
                        tan_dist = fillet_r / math.tan(half_angle)
                        tan_dist_arr = min(tan_dist, arr_len * 0.4)
                        tan_dist_dep = min(tan_dist, dep_len * 0.4)

                        # Tangent points
                        t1_x = x_r - arr_ux * tan_dist_arr
                        t1_z = z - arr_uz * tan_dist_arr
                        t2_x = x_r + dep_ux * tan_dist_dep
                        t2_z = z + dep_uz * tan_dist_dep

                        # Auto-detect corner type from cross product of
                        # arrival × departure directions.
                        # This determines which side of the chord the arc
                        # center goes on, expressed as the Build123d RadiusArc
                        # sign convention (passed directly, no downstream flip).
                        cross = arr_ux * dep_uz - arr_uz * dep_ux

                        # Cross product sign → Build123d RadiusArc sign:
                        # Positive cross (left turn / inside corner for OD):
                        #   Center on material side → negative RadiusArc radius
                        # Negative cross (right turn / outside corner for OD):
                        #   Center on material side → positive RadiusArc radius
                        if cross > 0:
                            signed_fillet_r = -fillet_r
                        else:
                            signed_fillet_r = fillet_r

                        # Emit trimmed endpoint for this segment
                        coords.append({
                            "type": seg.segment_type,
                            "x_radius": t1_x,
                            "z": t1_z,
                            "radius": seg.radius,
                        })
                        # Emit fillet arc with signed radius (same as segment arcs)
                        coords.append({
                            "type": SegmentType.ARC,
                            "x_radius": t2_x,
                            "z": t2_z,
                            "radius": signed_fillet_r,
                        })
                        continue  # Skip the normal append

        # Normal case: no corner break, emit segment as-is
        coords.append({
            "type": seg.segment_type,
            "x_radius": x_r,
            "z": z,
            "radius": seg.radius,
            "quadrant": seg.quadrant,
            "quadrant_sign": seg.quadrant_sign,
        })

    return coords


def _compute_closure_coords(profile: ClosedProfile, stock: StockDef,
                            profile_coords: List[dict] = None) -> List[dict]:
    """Compute the 3 (or fewer) closure line segments.

    OD Mode: profile_end → (centerline, Z_end) → (centerline, Z=0) → profile_start
    ID Mode: profile_end → (stock_OD_radius, Z_end) → (stock_OD_radius, Z=0) → profile_start

    Uses actual profile_coords endpoints (which may be trimmed by corner breaks)
    to ensure the closure connects correctly.

    Returns segment descriptors in radius coordinates.
    """
    mode = profile.mode
    segments = profile.segments

    # Use actual profile coords endpoints if available (corner-break-aware)
    if profile_coords and len(profile_coords) > 0:
        profile_start_x_r = profile_coords[0]["x_radius"]
        profile_start_z = profile_coords[0]["z"]
        profile_end_x_r = profile_coords[-1]["x_radius"]
        profile_end_z = profile_coords[-1]["z"]
    else:
        profile_start_x_r = segments[0].x / 2.0
        profile_start_z = segments[0].z
        profile_end_x_r = segments[-1].x / 2.0
        profile_end_z = segments[-1].z

    closure = []

    if mode == MachiningMode.OD:
        # Closure to centerline (X=0)
        closure_x = 0.0
    else:
        # Closure to stock OD
        closure_x = stock.diameter / 2.0

    # Segment 1: profile_end → (closure_x, Z_end)
    if abs(profile_end_x_r - closure_x) > 1e-10:
        closure.append({
            "type": SegmentType.LINE,
            "x_radius": closure_x,
            "z": profile_end_z,
            "radius": 0.0,
        })

    # Segment 2: (closure_x, Z_end) → (closure_x, Z=0)
    closure.append({
        "type": SegmentType.LINE,
        "x_radius": closure_x,
        "z": 0.0,  # Z=0 is the face
        "radius": 0.0,
    })

    # Segment 3: (closure_x, Z=0) → profile_start
    if abs(closure_x - profile_start_x_r) > 1e-10 or abs(0.0 - profile_start_z) > 1e-10:
        closure.append({
            "type": SegmentType.LINE,
            "x_radius": profile_start_x_r,
            "z": profile_start_z,
            "radius": 0.0,
        })

    return closure


def _build_face_from_coords(coords: List[dict], profile: ClosedProfile) -> object:
    """Build a Build123d Face from coordinate descriptors.

    Uses BuildSketch + BuildLine + make_face pattern.
    The coords list contains segment endpoints. We draw lines/arcs between
    consecutive endpoints to form a closed wire.

    Arc segments use RadiusArc with signed radius passed directly:
      ProfileMove.radius sign = direction (+CW, -CCW)
      Build123d RadiusArc sign = which side of chord center goes on
      These conventions align: pass target["radius"] directly (no sign flip).

    Quadrant arc segments (quarter ellipse) are handled based on alignment:
    - Axis-aligned (same X or same Z within tolerance) → RadiusArc (true circular arc)
    - Off-axis (both X and Z differ) → Spline with tangent constraints (elliptical)
    """
    import math
    from models.constants import TOLERANCE

    with BuildSketch() as sketch:
        with BuildLine():
            if not coords:
                raise ValueError("Empty coordinate list for face construction")

            for i in range(len(coords)):
                next_i = (i + 1) % len(coords)
                current = coords[i]
                target = coords[next_i]

                cx, cz = current["x_radius"], current["z"]
                tx, tz = target["x_radius"], target["z"]

                # Skip zero-length segments
                if abs(cx - tx) < 1e-10 and abs(cz - tz) < 1e-10:
                    continue

                if target.get("quadrant", False):
                    # Tangent-bounded quadrant arc: classify as axis-aligned or off-axis
                    # Axis-aligned: start and end share same X or same Z (within TOLERANCE)
                    # Off-axis: both X and Z differ beyond tolerance
                    same_x = abs(cx - tx) < TOLERANCE
                    same_z = abs(cz - tz) < TOLERANCE
                    is_axis_aligned = same_x or same_z

                    quadrant_sign = target.get("quadrant_sign", 1)

                    # All quadrant arcs: use polyline from parametric ellipse math.
                    # Even axis-aligned cases use polyline to avoid OCCT offset_2d
                    # failures with RadiusArc at certain geometries.
                    import math as _math
                    dx = tx - cx
                    dz = tz - cz
                    b = abs(dx) if abs(dx) > 1e-10 else 0.0
                    a = abs(dz) if abs(dz) > 1e-10 else 0.0

                    if b < 1e-10 or a < 1e-10:
                        # Truly axis-aligned (one delta is zero) → straight line
                        # (bounding box has zero width in one dimension)
                        Line((cx, cz), (tx, tz))
                    else:
                        if quadrant_sign == 1:
                            ecx = cx
                            ecz = tz
                            sign_x = 1.0 if dx > 0 else -1.0
                            sign_z = -1.0 if dz > 0 else 1.0
                        else:
                            ecx = tx
                            ecz = cz
                            sign_x = -1.0 if dx > 0 else 1.0
                            sign_z = 1.0 if dz > 0 else -1.0

                        num_pts = 64
                        points = []
                        for j in range(num_pts + 1):
                            t = (_math.pi / 2.0) * j / num_pts
                            if quadrant_sign == 1:
                                px = ecx + sign_x * b * _math.sin(t)
                                pz = ecz + sign_z * a * _math.cos(t)
                            else:
                                px = ecx + sign_x * b * _math.cos(t)
                                pz = ecz + sign_z * a * _math.sin(t)
                            points.append((px, pz))

                        for j in range(len(points) - 1):
                            p1 = points[j]
                            p2 = points[j + 1]
                            if abs(p1[0] - p2[0]) > 1e-10 or abs(p1[1] - p2[1]) > 1e-10:
                                Line((p1[0], p1[1]), (p2[0], p2[1]))

                elif target["type"] == SegmentType.ARC and target.get("radius", 0.0) != 0.0:
                    # Arc segment: pass signed radius directly to Build123d.
                    # ProfileMove.radius sign (+CW/-CCW) matches RadiusArc's
                    # side-of-chord convention for this engine's geometry.
                    b3d_radius = target["radius"]
                    RadiusArc((cx, cz), (tx, tz), b3d_radius)
                else:
                    Line((cx, cz), (tx, tz))

        make_face()

    return sketch.sketch


def _build_stock_face(stock_radius: float, z_start: float, z_end: float,
                      mode: MachiningMode, pilot_hole_radius: float) -> object:
    """Build the stock boundary as a Build123d Face (rectangle)."""
    if mode == MachiningMode.OD:
        # OD stock: rectangle from centerline to stock OD
        with BuildSketch() as sketch:
            with BuildLine():
                Line((0.0, z_start), (stock_radius, z_start))
                Line((stock_radius, z_start), (stock_radius, z_end))
                Line((stock_radius, z_end), (0.0, z_end))
                Line((0.0, z_end), (0.0, z_start))
            make_face()
        return sketch.sketch
    else:
        # ID stock: rectangle from pilot hole to stock OD
        with BuildSketch() as sketch:
            with BuildLine():
                Line((pilot_hole_radius, z_start), (stock_radius, z_start))
                Line((stock_radius, z_start), (stock_radius, z_end))
                Line((stock_radius, z_end), (pilot_hole_radius, z_end))
                Line((pilot_hole_radius, z_end), (pilot_hole_radius, z_start))
            make_face()
        return sketch.sketch


def _build_true_face(stock: StockDef, mode: MachiningMode) -> object:
    """Build the True Face Zone as a Build123d Face.

    OD: Rectangle from X_start to Stock_OD, Z=0 to Z_start
    ID: Rectangle from Pilot_hole to X_start, Z=0 to Z_start

    Returns None if the face zone has zero area (x_min == x_max or z_start == 0).
    """
    stock_radius = stock.diameter / 2.0
    x_start_radius = stock.x_start / 2.0
    z_start = stock.z_start

    if mode == MachiningMode.OD:
        x_min = x_start_radius
        x_max = stock_radius
    else:
        x_min = stock.pilot_hole_dia / 2.0
        x_max = x_start_radius

    # Guard: no face zone if dimensions collapse
    if abs(x_max - x_min) < 1e-6 or abs(z_start) < 1e-6:
        return None

    # True face zone: from Z=0 to Z_start (positive Z = material above face)
    with BuildSketch() as sketch:
        with BuildLine():
            Line((x_min, 0.0), (x_max, 0.0))
            Line((x_max, 0.0), (x_max, z_start))
            Line((x_max, z_start), (x_min, z_start))
            Line((x_min, z_start), (x_min, 0.0))
        make_face()
    return sketch.sketch
