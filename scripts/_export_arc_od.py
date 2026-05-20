"""Export DXF and G-code for the Arc OD profile — round-trip test.

Profile: Straight section → convex arc → straight section
Arc Reference ground truth: 175934-001_01-Arc Reference.dxf

Profile segments (diameter, Z):
  (0.000, 0.000) → start at centerline, face
  (1.000, 0.000) → horizontal to X=1.0 dia at Z=0
  (1.000, -0.500) → vertical down to Z=-0.5
  ARC to (1.000, -1.500) with R=1.000 (convex, CCW in lathe coords)
  (1.000, -2.000) → vertical down to Z=-2.0

Stock: 1.500 dia, Z_start=0.1, Z_end=-2.0
"""
import sys
import os
sys.path.insert(0, r'c:\Users\jhonick\linuxcnc\Industry CAM Engine')

import ezdxf
from models import *
from pipeline.pipeline import execute
from outputs.gcode_writer import GCodeWriter
from outputs.gcode_parser import parse as parse_gcode

# Build Arc OD profile
# The arc goes from (1.000 dia, -0.500) to (1.000 dia, -1.500)
# It's a convex arc (bulges outward) with radius 1.000 (in radius = 0.500 radius units)
# In the DXF ground truth: center=(-0.366, -1.000) radius=1.000 (in radius coords)
# Converting to diameter coords for our engine:
#   center_x_dia = -0.366 * 2 = -0.732 (but this is the Build123d center, not user input)
#   User specifies: endpoint + signed radius
#   Arc from (1.000 dia, -0.500) to (1.000 dia, -1.500), radius = +1.000 (CW = G02)
#   Actually looking at the DXF: start_angle=330, end_angle=30, going CCW
#   In lathe coords (X=radius, Z=Z): the arc is CCW → negative radius in our convention

segments = [
    ProfileMove(SegmentType.LINE, 0.000, 0.000),    # Start at centerline, face
    ProfileMove(SegmentType.LINE, 1.000, 0.000),    # Horizontal to X=1.0 dia
    ProfileMove(SegmentType.LINE, 1.000, -0.500),   # Vertical down to Z=-0.5
    ProfileMove(SegmentType.ARC, 1.000, -1.500, radius=-1.000),  # CCW arc to Z=-1.5 (negative = CCW/G03)
    ProfileMove(SegmentType.LINE, 1.000, -2.000),   # Vertical down to Z=-2.0
]
breaks = [None, None, None, None]
profile = ClosedProfile(segments=segments, corner_breaks=breaks, mode=MachiningMode.OD, z_end=-2.0)
stock = StockDef(diameter=1.500, x_start=0.0, z_start=0.1, z_end=-2.0, mode=MachiningMode.OD)
tool = ToolDef(1, 0.016, 80.0, 0.375, ToolOrientation.OD_FRONT_RIGHT, ToolDirection.RIGHT)
roughing = RoughingParams(doc_dia=0.050, feed=0.005, strategy=RoughingStrategy.STAIRCASE, fin_allowance=0.002)
finishing = FinishingParams(passes=1, doc_dia=0.002, feed=0.003)

# Execute pipeline
print("Executing pipeline for Arc OD profile...")
result = execute(profile, stock, tool, roughing, finishing)

if result.status != PipelineStatus.SUCCESS:
    print(f"Pipeline FAILED: {result.status.value}")
    for v in result.validations:
        print(f"  [{v.severity.value}] {v.message}")
    sys.exit(1)

pr = result.plan_result
print(f"Pipeline SUCCESS: {len(pr.roughing_passes)} rough passes, {len(pr.tool_moves)} total moves")

# Create output folder
output_dir = r'c:\Users\jhonick\linuxcnc\Industry CAM Engine\reference\CAD Reference\Engine Output\Arc OD'
os.makedirs(output_dir, exist_ok=True)

# --- Generate G-code ---
writer = GCodeWriter()
gcode = writer.write(pr)
gcode_path = os.path.join(output_dir, 'Arc_OD.ngc')
with open(gcode_path, 'w') as f:
    f.write(gcode)
print(f"G-code written: {gcode_path} ({len(gcode.splitlines())} lines)")

# --- Generate DXF ---
MM = 25.4
doc = ezdxf.new("R2010", setup=True)
msp = doc.modelspace()

# Create layers
doc.layers.add("PROFILE", color=7)
doc.layers.add("ROUGHING_BOUNDARY", color=3)
doc.layers.add("STOCK", color=8)
doc.layers.add("TOOLPATH_FEED", color=3)
doc.layers.add("TOOLPATH_RAPID", color=1)
doc.layers.add("ZONES_FINISHED_PART", color=4)
doc.layers.add("ZONES_MTR", color=1)
doc.layers.add("ZONES_TRUE_FACE", color=14)
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

# True face zone
fin_r = roughing.fin_allowance / 2.0
true_face = [(0.0, fin_r), (stock.diameter, fin_r), (stock.diameter, stock.z_start), (0.0, stock.z_start)]
draw_polygon(true_face, "ZONES_TRUE_FACE")

# Stock boundary
stock_poly = [(0.0, stock.z_start), (stock.diameter, stock.z_start), (stock.diameter, stock.z_end), (0.0, stock.z_end)]
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

dxf_path = os.path.join(output_dir, 'Arc_OD.dxf')
doc.saveas(dxf_path)
print(f"DXF written: {dxf_path}")

# --- Round-trip validation ---
print(f"\n--- Round-Trip Validation ---")
print(f"Original tool_moves: {len(pr.tool_moves)}")
print(f"Parsed from G-code:  {len(parsed_moves)}")
print(f"G-code lines:        {len(gcode.splitlines())}")

# Check for validation issues
if pr.validations:
    print(f"\nValidation results:")
    for v in pr.validations:
        print(f"  [{v.severity.value}] {v.message}")
else:
    print(f"\n✓ Zero validation issues — Shapely gouge check PASSED")

print(f"\nFiles in: {output_dir}")
