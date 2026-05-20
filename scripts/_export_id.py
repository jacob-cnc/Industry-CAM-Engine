"""Export DXF and G-code for the ID (bore) profile — round-trip test.

Profile: Stepped bore
ID Reference ground truth: 175933-001_01-ID Reference DXF.dxf

From the DXF (all in radius coords, converting to diameter for engine):
  Profile boundary (finished part inner wall):
    X=1.200 dia (0.600 radius), Z=0 → Z=-1.0
    X=0.800 dia (0.400 radius), Z=-1.0 → Z=-1.5

Stock: 2.000 dia (1.0 radius), pilot hole 0.500 dia (0.25 radius)
Z_start=0.05, Z_end=-1.5

ID mode: tool cuts INWARD (increasing X from pilot hole toward profile)
"""
import sys
import os
sys.path.insert(0, r'c:\Users\jhonick\linuxcnc\Industry CAM Engine')

import ezdxf
from models import *
from pipeline.pipeline import execute
from outputs.gcode_writer import GCodeWriter
from outputs.gcode_parser import parse as parse_gcode

# Build ID (bore) profile
# The bore profile defines the INNER wall of the finished part
# X values are diameter (user-facing)
# Profile goes from large bore (1.2 dia) to smaller bore (0.8 dia) — a stepped bore
segments = [
    ProfileMove(SegmentType.LINE, 1.200, 0.000),    # Start at bore diameter, face
    ProfileMove(SegmentType.LINE, 1.200, -1.000),   # Bore wall down to Z=-1.0
    ProfileMove(SegmentType.LINE, 0.800, -1.000),   # Step inward to 0.8 dia at Z=-1.0
    ProfileMove(SegmentType.LINE, 0.800, -1.500),   # Continue bore to Z=-1.5
]
breaks = [None, None, None]
profile = ClosedProfile(segments=segments, corner_breaks=breaks, mode=MachiningMode.ID, z_end=-1.5)
stock = StockDef(
    diameter=2.000,
    x_start=1.200,  # Approach X (bore entry diameter)
    z_start=0.05,
    z_end=-1.5,
    mode=MachiningMode.ID,
    pilot_hole_dia=0.500,
)
tool = ToolDef(1, 0.016, 80.0, 0.375, ToolOrientation.ID_FRONT_RIGHT, ToolDirection.LEFT)
roughing = RoughingParams(doc_dia=0.050, feed=0.004, strategy=RoughingStrategy.STAIRCASE, fin_allowance=0.002)
finishing = FinishingParams(passes=1, doc_dia=0.002, feed=0.002)

# Execute pipeline
print("Executing pipeline for ID (bore) profile...")
result = execute(profile, stock, tool, roughing, finishing)

if result.status != PipelineStatus.SUCCESS:
    print(f"Pipeline FAILED: {result.status.value}")
    for v in result.validations:
        print(f"  [{v.severity.value}] {v.message}")
    # Try with warnings overridden
    if result.status == PipelineStatus.SUCCESS_WITH_WARNINGS:
        pr = result.plan_result
        print("\nProceeding with warnings...")
    else:
        sys.exit(1)
else:
    pr = result.plan_result

print(f"Pipeline {result.status.value}: {len(pr.roughing_passes)} rough passes, {len(pr.tool_moves)} total moves")

# Create output folder
output_dir = r'c:\Users\jhonick\linuxcnc\Industry CAM Engine\reference\CAD Reference\Engine Output\ID Bore'
os.makedirs(output_dir, exist_ok=True)

# --- Generate G-code ---
writer = GCodeWriter()
gcode = writer.write(pr)
gcode_path = os.path.join(output_dir, 'ID_Bore.ngc')
with open(gcode_path, 'w') as f:
    f.write(gcode)
print(f"G-code written: {gcode_path} ({len(gcode.splitlines())} lines)")

# --- Generate DXF ---
MM = 25.4
doc = ezdxf.new("R2010", setup=True)
msp = doc.modelspace()

# Create layers
doc.layers.add("PROFILE", color=7)
doc.layers.add("STOCK", color=8)
doc.layers.add("TOOLPATH_FEED", color=3)
doc.layers.add("TOOLPATH_RAPID", color=1)
doc.layers.add("ZONES_FINISHED_PART", color=4)
doc.layers.add("ZONES_MTR", color=1)
doc.layers.add("ZONES_FIN_ALLOWANCE", color=2)

def draw_polygon(coords_dia_z, layer):
    for i in range(len(coords_dia_z)):
        j = (i + 1) % len(coords_dia_z)
        x1_r = coords_dia_z[i][0] / 2.0
        z1 = coords_dia_z[i][1]
        x2_r = coords_dia_z[j][0] / 2.0
        z2 = coords_dia_z[j][1]
        msp.add_line(
            (x1_r * MM, z1 * MM, 0),
            (x2_r * MM, z2 * MM, 0),
            dxfattribs={"layer": layer}
        )

# Draw zone polygons
draw_polygon(pr.finished_part_boundary, "ZONES_FINISHED_PART")
draw_polygon(pr.material_to_rough_boundary, "ZONES_MTR")
draw_polygon(pr.finish_allowance_boundary, "ZONES_FIN_ALLOWANCE")

# Stock boundary
stock_poly = [(stock.pilot_hole_dia, stock.z_start), (stock.diameter, stock.z_start),
              (stock.diameter, stock.z_end), (stock.pilot_hole_dia, stock.z_end)]
draw_polygon(stock_poly, "STOCK")

# Profile from segments
for i in range(len(pr.profile.segments) - 1):
    seg = pr.profile.segments[i]
    next_seg = pr.profile.segments[i + 1]
    x1_r = seg.x / 2.0
    z1 = seg.z
    x2_r = next_seg.x / 2.0
    z2 = next_seg.z
    msp.add_line(
        (x1_r * MM, z1 * MM, 0),
        (x2_r * MM, z2 * MM, 0),
        dxfattribs={"layer": "PROFILE"}
    )

# Toolpath from G-code round-trip
parsed_moves = parse_gcode(gcode)
prev_x_r = None
prev_z = None
for move in parsed_moves:
    x_r = move.x / 2.0
    z = move.z
    if prev_x_r is not None and prev_z is not None:
        if abs(x_r - prev_x_r) < 0.00001 and abs(z - prev_z) < 0.00001:
            prev_x_r = x_r
            prev_z = z
            continue
        if move.move_type == MoveType.RAPID:
            layer = "TOOLPATH_RAPID"
        else:
            layer = "TOOLPATH_FEED"
        msp.add_line(
            (prev_x_r * MM, prev_z * MM, 0),
            (x_r * MM, z * MM, 0),
            dxfattribs={"layer": layer}
        )
    prev_x_r = x_r
    prev_z = z

msp.add_point((0, 0, 0), dxfattribs={"layer": "0"})

dxf_path = os.path.join(output_dir, 'ID_Bore.dxf')
doc.saveas(dxf_path)
print(f"DXF written: {dxf_path}")

# --- Round-trip validation ---
print(f"\n--- Round-Trip Validation ---")
print(f"Original tool_moves: {len(pr.tool_moves)}")
print(f"Parsed from G-code:  {len(parsed_moves)}")
print(f"G-code lines:        {len(gcode.splitlines())}")

if pr.validations:
    print(f"\nValidation results:")
    for v in pr.validations:
        print(f"  [{v.severity.value}] {v.message}")
else:
    print(f"\n✓ Zero validation issues — Shapely gouge check PASSED")

print(f"\nFiles in: {output_dir}")
