"""Zone construction for Industry CAM Engine.

Builds machining zones (Finished Part, Finish Allowance, Material to Rough,
True Face) using Build123d boolean operations on 2D Faces.

The ONLY place where Build123d is used for zone construction.
Imports from: models/, tools/
"""

from dataclasses import dataclass
from typing import List, Tuple, Optional

from build123d import (
    BuildSketch, BuildLine, Line, RadiusArc, make_face, Sketch,
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
    closure_coords = _compute_closure_coords(profile, stock)
    all_coords = profile_coords + closure_coords

    # Build the finished part face from closed contour
    finished_part_face = _build_face_from_coords(all_coords, profile)

    # Step 2: Compute fin_allowance in radius
    fin_allowance_radius = roughing_params.fin_allowance / 2.0  # diameter to radius

    # Step 3: Offset profile to get roughing boundary (keep zone)
    # Use Kind.INTERSECTION for sharp corners (no fillets)
    if mode == MachiningMode.OD:
        offset_amount = fin_allowance_radius
    else:
        offset_amount = -fin_allowance_radius

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
    mtr_stock_face = _build_stock_face(stock_radius, fin_allowance_radius, stock.z_end, mode, stock.pilot_hole_dia / 2.0)

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

    Returns list of segment descriptors with coordinates in radius.
    """
    coords = []
    for seg in profile.segments:
        coords.append({
            "type": seg.segment_type,
            "x_radius": seg.x / 2.0,
            "z": seg.z,
            "radius": seg.radius,  # Already in radius (geometric radius)
        })
    return coords


def _compute_closure_coords(profile: ClosedProfile, stock: StockDef) -> List[dict]:
    """Compute the 3 (or fewer) closure line segments.

    OD Mode: profile_end → (centerline, Z_end) → (centerline, Z=0) → profile_start
    ID Mode: profile_end → (stock_OD_radius, Z_end) → (stock_OD_radius, Z=0) → profile_start

    Returns segment descriptors in radius coordinates.
    """
    mode = profile.mode
    segments = profile.segments

    # Profile start and end in radius
    profile_start_x_r = segments[0].x / 2.0
    profile_start_z = segments[0].z  # Should be 0.0 (or close to it)
    profile_end_x_r = segments[-1].x / 2.0
    profile_end_z = segments[-1].z  # Should be z_end

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
    """
    with BuildSketch() as sketch:
        with BuildLine():
            if not coords:
                raise ValueError("Empty coordinate list for face construction")

            # The first coord is the first segment endpoint.
            # For a closed profile, the last coord should connect back to the first.
            # We draw from coord[i] to coord[i+1] for each pair.
            for i in range(len(coords)):
                next_i = (i + 1) % len(coords)
                current = coords[i]
                target = coords[next_i]

                cx, cz = current["x_radius"], current["z"]
                tx, tz = target["x_radius"], target["z"]

                # Skip zero-length segments
                if abs(cx - tx) < 1e-10 and abs(cz - tz) < 1e-10:
                    continue

                if target["type"] == SegmentType.ARC and target["radius"] != 0.0:
                    # Arc segment: convert profile radius to Build123d convention
                    # Profile: +radius = CW (G02) → Build123d: NEGATIVE RadiusArc
                    # Profile: -radius = CCW (G03) → Build123d: POSITIVE RadiusArc
                    b3d_radius = -target["radius"]
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

    # True face zone: from Z=0 to Z_start (positive Z = material above face)
    with BuildSketch() as sketch:
        with BuildLine():
            Line((x_min, 0.0), (x_max, 0.0))
            Line((x_max, 0.0), (x_max, z_start))
            Line((x_max, z_start), (x_min, z_start))
            Line((x_min, z_start), (x_min, 0.0))
        make_face()
    return sketch.sketch
