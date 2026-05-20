"""Export DXF and G-code for the ID Bore profile."""
import sys
import os
import math
sys.path.insert(0, r'c:\Users\jhonick\linuxcnc\Industry CAM Engine')

import ezdxf
from models import *
from models.moves import ToolMove, MoveType, PassType
from pipeline.pipeline import execute
from outputs.gcode_writer import GCodeWriter

# Stepped ID bore profile (NX ground truth parameters)
segments = [
    ProfileMove(SegmentType.LINE, 1.200, 0.000),
    ProfileMove(SegmentType.LINE, 1.200, -1.000),
    ProfileMove(SegmentType.LINE, 0.800, -1.000),
    ProfileMove(SegmentType.LINE, 0.800, -1.500),
]
breaks = [None, None, None]
profile = ClosedProfile(segments=segments, corner_breaks=breaks, mode=MachiningMode.ID, z_end=-1.5)
stock = StockDef(
    diameter=2.000, x_start=1.200, z_start=0.050, z_end=-1.5,
    mode=MachiningMode.ID, pilot_hole_dia=0.500,
)
tool = ToolDef(1, 0.008, 55.0, 0.250, ToolOrientation.ID_FRONT_RIGHT, ToolDirection.RIGHT)
roughing = RoughingParams(doc_dia=0.050, feed=0.003, strategy=RoughingStrategy.STAIRCASE, fin_allowance=0.002)
finishing = FinishingParams(passes=1, doc_dia=0.002, feed=0.002)

# Run full pipeline
result = execute(profile, stock, tool, roughing, finishing)
print(f"Status: {result.status.value}")
print(f"Validations: {len(result.validations)}")

if not result.plan_result:
    print("Pipeline blocked!")
    for v in result.validations:
        print(f"  [{v.severity.value}] {v.message}")
    sys.exit(1)

pr = result.plan_result
print(f"Passes: face={len(pr.face_passes)} rough={len(pr.roughing_passes)} "
      f"cleanup={len(pr.cleanup_passes)} finish={len(pr.finish_passes)}")
print(f"Total moves: {pr.move_count}")

# Output directory
output_dir = r'c:\Users\jhonick\linuxcnc\Industry CAM Engine\reference\CAD Reference\Engine Output\ID Bore'
os.makedirs(output_dir, exist_ok=True)

# --- Generate G-code ---
writer = GCodeWriter()
gcode = writer.write(pr)
gcode_path = os.path.join(output_dir, 'ID_Bore_Staircase.ngc')
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
doc.layers.add("PILOT_HOLE", color=8)
doc.layers.add("TOOLPATH_ROUGH", color=3)
doc.layers.add("TOOLPATH_CLEANUP", color=94)
doc.layers.add("TOOLPATH_FINISH", color=5)
doc.layers.add("TOOLPATH_RAPID", color=1)
doc.layers.add("TOOLPATH_FACE", color=14)

# Draw stock rectangle (cross-section in XZ plane, X=radius)
stock_pts = [
    (stock.pilot_hole_dia / 2 * MM, stock.z_start * MM),
    (stock.diameter / 2 * MM, stock.z_start * MM),
    (stock.diameter / 2 * MM, stock.z_end * MM),
    (stock.pilot_hole_dia / 2 * MM, stock.z_end * MM),
    (stock.pilot_hole_dia / 2 * MM, stock.z_start * MM),
]
for i in range(len(stock_pts) - 1):
    msp.add_line(stock_pts[i], stock_pts[i+1], dxfattribs={"layer": "STOCK"})

# Draw profile (bore wall)
for i in range(len(segments) - 1):
    seg = segments[i]
    next_seg = segments[i + 1]
    x1_r = seg.x / 2.0
    z1 = seg.z
    x2_r = next_seg.x / 2.0
    z2 = next_seg.z
    msp.add_line(
        (x1_r * MM, z1 * MM),
        (x2_r * MM, z2 * MM),
        dxfattribs={"layer": "PROFILE"}
    )

# Draw pilot hole boundary
msp.add_line(
    (stock.pilot_hole_dia / 2 * MM, 0),
    (stock.pilot_hole_dia / 2 * MM, stock.z_end * MM),
    dxfattribs={"layer": "PILOT_HOLE"}
)

# Draw toolpath from moves
prev_x_r = None
prev_z = None
for move in pr.tool_moves:
    x_r = move.x / 2.0
    z = move.z
    if prev_x_r is not None and prev_z is not None:
        if abs(x_r - prev_x_r) < 0.00001 and abs(z - prev_z) < 0.00001:
            prev_x_r = x_r
            prev_z = z
            continue

        # Determine layer
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

        # Check if it's an arc move
        if (move.move_type in (MoveType.ARC_CW, MoveType.ARC_CCW) and
                (abs(move.center_i) > 0.0001 or abs(move.center_k) > 0.0001)):
            ci = move.center_i / 2.0
            ck = move.center_k
            cx_r = prev_x_r + ci
            cz = prev_z + ck
            r = math.sqrt(ci**2 + ck**2)
            sa = math.degrees(math.atan2(prev_z - cz, prev_x_r - cx_r))
            ea = math.degrees(math.atan2(z - cz, x_r - cx_r))
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

dxf_path = os.path.join(output_dir, 'ID_Bore_Staircase.dxf')
doc.saveas(dxf_path)
print(f"DXF written: {dxf_path}")

# Summary
print(f"\n--- Pass Summary ---")
print(f"Face: {len(pr.face_passes)} passes")
for p in pr.face_passes:
    print(f"  X={p.x_level:.4f} dia, Z[{p.z_start:.4f} -> {p.z_end:.4f}]")

print(f"\nRoughing: {len(pr.roughing_passes)} passes")
for p in pr.roughing_passes:
    print(f"  X={p.x_level:.4f} dia, Z[{p.z_start:.4f} -> {p.z_end:.4f}]")

print(f"\nCleanup: {len(pr.cleanup_passes)} passes")
for p in pr.cleanup_passes:
    move_types = [m.move_type.value for m in p.moves]
    print(f"  X={p.x_level:.4f}, moves: {move_types}")

print(f"\nFinish: {len(pr.finish_passes)} passes")
for p in pr.finish_passes:
    move_types = [m.move_type.value for m in p.moves]
    print(f"  X={p.x_level:.4f}, moves: {move_types}")
