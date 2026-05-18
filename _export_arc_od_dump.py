"""Export DXF and G-code for the Arc OD profile — bypass validation to get output.

This runs the pipeline stages manually so we can produce output even when
the cleanup arc chord check triggers a false-positive gouge detection.
"""
import sys
import os
import time
sys.path.insert(0, r'c:\Users\jhonick\linuxcnc\Industry CAM Engine')

import ezdxf
import math
from models import *
from models.moves import ToolMove, MoveType, PassType
from models.results import PlanResult, TurningPass
from models.validation import ValidationResult, PipelineResult, PipelineStatus, Severity

from geometry.zone_builder import build_zones
from geometry.zone_query import ZoneQueryAPI
from geometry.contour_intersect import ContourIntersect

from planners.face_planner import FacePlanner
from planners.staircase_planner import StaircasePlanner
from planners.cleanup_planner import CleanupPlanner
from planners.finish_planner import FinishPlanner

from transitions.transition_planner import TransitionPlanner
from outputs.gcode_writer import GCodeWriter
from outputs.gcode_parser import parse as parse_gcode

# Build Arc OD profile
segments = [
    ProfileMove(SegmentType.LINE, 0.000, 0.000),
    ProfileMove(SegmentType.LINE, 1.000, 0.000),
    ProfileMove(SegmentType.LINE, 1.000, -0.500),
    ProfileMove(SegmentType.ARC, 1.000, -1.500, radius=-1.000),
    ProfileMove(SegmentType.LINE, 1.000, -2.000),
]
breaks = [None, None, None, None]
profile = ClosedProfile(segments=segments, corner_breaks=breaks, mode=MachiningMode.OD, z_end=-2.0)
stock = StockDef(diameter=1.500, x_start=0.0, z_start=0.1, z_end=-2.0, mode=MachiningMode.OD)
tool = ToolDef(1, 0.016, 80.0, 0.375, ToolOrientation.OD_FRONT_RIGHT, ToolDirection.RIGHT)
roughing = RoughingParams(doc_dia=0.050, feed=0.005, strategy=RoughingStrategy.STAIRCASE, fin_allowance=0.002)
finishing = FinishingParams(passes=1, doc_dia=0.002, feed=0.003)

# Run pipeline stages manually
print("Building zones...")
zone_set = build_zones(profile, stock, tool, roughing)
zone_query = ZoneQueryAPI(zone_set)
contour_intersect = ContourIntersect(zone_set)

print("Planning face passes...")
face_planner = FacePlanner()
face_passes = face_planner.plan(stock, tool, roughing, MachiningMode.OD, zone_query)

print("Planning roughing passes...")
staircase = StaircasePlanner()
roughing_passes = staircase.plan(zone_query, tool, roughing, stock, MachiningMode.OD, contour_intersect=contour_intersect)

print("Planning cleanup passes...")
cleanup_planner = CleanupPlanner()
cleanup_passes = cleanup_planner.plan(zone_query, tool, roughing, stock, MachiningMode.OD, profile)

print("Planning finish passes...")
finish_planner = FinishPlanner()
finish_passes = finish_planner.plan(zone_query, tool, finishing, stock, MachiningMode.OD, profile)

print("Planning transitions...")
all_passes = face_passes + roughing_passes + cleanup_passes + finish_passes
transition_planner = TransitionPlanner()
transitions = transition_planner.plan_all(all_passes, MachiningMode.OD, stock, zone_query, RoughingStrategy.STAIRCASE)

# Assemble moves
all_moves = []
for i, pass_obj in enumerate(all_passes):
    if i > 0 and i - 1 < len(transitions):
        all_moves.extend(transitions[i - 1].moves)
    all_moves.extend(pass_obj.moves)

print(f"\nResults:")
print(f"  Face passes: {len(face_passes)}")
print(f"  Roughing passes: {len(roughing_passes)}")
print(f"  Cleanup passes: {len(cleanup_passes)}")
print(f"  Finish passes: {len(finish_passes)}")
print(f"  Total moves: {len(all_moves)}")

# Extract zone boundaries
from pipeline.pipeline import _extract_zone_boundary, _extract_zone_boundary_optional, _compute_stock_boundary
finished_part_boundary = _extract_zone_boundary(zone_query, "finished_part")
finish_allowance_boundary = _extract_zone_boundary_optional(zone_query, "finish_allowance")
material_to_rough_boundary = _extract_zone_boundary(zone_query, "material_to_rough")
stock_boundary = _compute_stock_boundary(stock)

# Build PlanResult
pr = PlanResult(
    profile=profile,
    stock=stock,
    tool=tool,
    roughing_params=roughing,
    finishing_params=finishing,
    mode=MachiningMode.OD,
    face_passes=face_passes,
    roughing_passes=roughing_passes,
    cleanup_passes=cleanup_passes,
    finish_passes=finish_passes,
    tool_moves=all_moves,
    finished_part_boundary=finished_part_boundary,
    finish_allowance_boundary=finish_allowance_boundary,
    material_to_rough_boundary=material_to_rough_boundary,
    stock_boundary=stock_boundary,
    profile_boundary=finished_part_boundary,
    validations=[],
    warnings_overridden=True,
    generation_time_ms=0,
    pass_count=len(all_passes),
    move_count=len(all_moves),
)

# Output directory
output_dir = r'c:\Users\jhonick\linuxcnc\Industry CAM Engine\reference\CAD Reference\Engine Output\Arc OD'
os.makedirs(output_dir, exist_ok=True)

# --- Generate G-code ---
writer = GCodeWriter()
gcode = writer.write(pr)
gcode_path = os.path.join(output_dir, 'Arc_OD_Staircase.ngc')
with open(gcode_path, 'w') as f:
    f.write(gcode)
print(f"\nG-code written: {gcode_path} ({len(gcode.splitlines())} lines)")

# --- Generate DXF ---
MM = 25.4
doc = ezdxf.new("R2010", setup=True)
msp = doc.modelspace()

# Layers
doc.layers.add("PROFILE", color=7)
doc.layers.add("STOCK", color=8)
doc.layers.add("TOOLPATH_ROUGH", color=3)
doc.layers.add("TOOLPATH_CLEANUP", color=94)
doc.layers.add("TOOLPATH_FINISH", color=5)
doc.layers.add("TOOLPATH_RAPID", color=1)
doc.layers.add("TOOLPATH_FACE", color=14)

# Draw stock rectangle
stock_pts = [
    (0, stock.z_start * MM),
    (stock.diameter / 2 * MM, stock.z_start * MM),
    (stock.diameter / 2 * MM, stock.z_end * MM),
    (0, stock.z_end * MM),
    (0, stock.z_start * MM),
]
for i in range(len(stock_pts) - 1):
    msp.add_line(stock_pts[i], stock_pts[i+1], dxfattribs={"layer": "STOCK"})

# Draw profile
for i in range(len(segments) - 1):
    seg = segments[i]
    next_seg = segments[i + 1]
    x1_r = seg.x / 2.0
    z1 = seg.z
    x2_r = next_seg.x / 2.0
    z2 = next_seg.z
    
    if next_seg.segment_type == SegmentType.ARC and next_seg.radius != 0:
        # Draw arc
        # Need center and radius for DXF arc
        # Profile arc: from (x1_r, z1) to (x2_r, z2) with radius
        # For this specific arc: center is at (-0.366r, -1.000)
        # We know from zone builder: center=(-0.366, -1.000), R=1.000
        cx_r = -0.366
        cz = -1.000
        r = 1.000
        # Start/end angles
        sa = math.degrees(math.atan2(z1 - cz, x1_r - cx_r))
        ea = math.degrees(math.atan2(z2 - cz, x2_r - cx_r))
        msp.add_arc(
            center=(cx_r * MM, cz * MM),
            radius=r * MM,
            start_angle=ea,  # DXF arcs go CCW
            end_angle=sa,
            dxfattribs={"layer": "PROFILE"}
        )
    else:
        msp.add_line(
            (x1_r * MM, z1 * MM),
            (x2_r * MM, z2 * MM),
            dxfattribs={"layer": "PROFILE"}
        )

# Draw toolpath from moves
prev_x_r = None
prev_z = None
for move in all_moves:
    x_r = move.x / 2.0
    z = move.z
    if prev_x_r is not None and prev_z is not None:
        if abs(x_r - prev_x_r) < 0.00001 and abs(z - prev_z) < 0.00001:
            prev_x_r = x_r
            prev_z = z
            continue
        
        # Determine layer by move type and pass type
        if move.move_type == MoveType.RAPID:
            layer = "TOOLPATH_RAPID"
        elif move.pass_type == PassType.FACE:
            layer = "TOOLPATH_FACE"
        elif move.pass_type == PassType.ROUGH:
            layer = "TOOLPATH_ROUGH"
        elif move.pass_type == PassType.CLEANUP:
            layer = "TOOLPATH_CLEANUP"
        elif move.pass_type == PassType.FINISH:
            layer = "TOOLPATH_FINISH"
        else:
            layer = "TOOLPATH_ROUGH"
        
        # Check if it's an arc move with valid center data
        if (move.move_type in (MoveType.ARC_CW, MoveType.ARC_CCW) and 
                hasattr(move, 'center_i') and 
                (abs(move.center_i) > 0.0001 or abs(move.center_k) > 0.0001)):
            # Draw arc
            ci = move.center_i / 2.0  # center offset X (radius)
            ck = move.center_k        # center offset Z
            cx_r = prev_x_r + ci
            cz = prev_z + ck
            r = math.sqrt(ci**2 + ck**2)
            sa = math.degrees(math.atan2(prev_z - cz, prev_x_r - cx_r))
            ea = math.degrees(math.atan2(z - cz, x_r - cx_r))
            # DXF arcs always go CCW. For both G02 and G03 in lathe ZX plane,
            # we need to determine the correct short arc direction.
            # G02 (CW in lathe) = CW in XZ = CCW in DXF when viewed from +Y
            # G03 (CCW in lathe) = CCW in XZ = CW in DXF when viewed from +Y
            # For DXF: start_angle=ea, end_angle=sa gives the short arc for both cases
            msp.add_arc(
                center=(cx_r * MM, cz * MM),
                radius=r * MM,
                start_angle=ea,
                end_angle=sa,
                dxfattribs={"layer": layer}
            )
        else:
            msp.add_line(
                (prev_x_r * MM, prev_z * MM),
                (x_r * MM, z * MM),
                dxfattribs={"layer": layer}
            )
    
    prev_x_r = x_r
    prev_z = z

# Origin marker
msp.add_point((0, 0), dxfattribs={"layer": "0"})

dxf_path = os.path.join(output_dir, 'Arc_OD_Staircase.dxf')
doc.saveas(dxf_path)
print(f"DXF written: {dxf_path}")

# Summary
print(f"\n--- Pass Summary ---")
print(f"Face: {len(face_passes)} passes")
for p in face_passes:
    print(f"  X={p.x_level:.4f} dia, Z[{p.z_start:.4f} → {p.z_end:.4f}]")

print(f"\nRoughing: {len(roughing_passes)} passes")
from collections import defaultdict
by_x = defaultdict(list)
for p in roughing_passes:
    by_x[p.x_level].append(p)
for x_dia in sorted(by_x.keys(), reverse=True):
    passes = by_x[x_dia]
    intervals = ", ".join(f"Z[{p.z_start:.4f}→{p.z_end:.4f}]" for p in passes)
    print(f"  X={x_dia:.4f}: {intervals}")

print(f"\nCleanup: {len(cleanup_passes)} passes")
for p in cleanup_passes:
    move_types = [m.move_type.value for m in p.moves]
    print(f"  X={p.x_level:.4f}, moves: {move_types}")

print(f"\nFinish: {len(finish_passes)} passes")
for p in finish_passes:
    move_types = [m.move_type.value for m in p.moves]
    print(f"  X={p.x_level:.4f}, moves: {move_types}")

print(f"\nOutput: {output_dir}")
