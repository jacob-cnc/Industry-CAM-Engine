"""Export DXF and G-code debug files for the stepped OD profile."""
import sys
import os
sys.path.insert(0, r'c:\Users\jhonick\linuxcnc\Industry CAM Engine')

import ezdxf
from models import *
from pipeline.pipeline import execute
from outputs.gcode_writer import GCodeWriter

# Build stepped OD
segments = [
    ProfileMove(SegmentType.LINE, 0.000, 0.000),
    ProfileMove(SegmentType.LINE, 0.500, 0.000),
    ProfileMove(SegmentType.LINE, 0.500, -0.500),
    ProfileMove(SegmentType.LINE, 1.000, -0.500),
    ProfileMove(SegmentType.LINE, 1.000, -1.000),
]
breaks = [None, None, None, None]
profile = ClosedProfile(segments=segments, corner_breaks=breaks, mode=MachiningMode.OD, z_end=-1.0)
stock = StockDef(diameter=1.250, x_start=0.0, z_start=0.1, z_end=-1.0, mode=MachiningMode.OD)
tool = ToolDef(1, 0.016, 80.0, 0.375, ToolOrientation.OD_FRONT_RIGHT, ToolDirection.RIGHT)
roughing = RoughingParams(doc_dia=0.050, feed=0.005, strategy=RoughingStrategy.STAIRCASE, fin_allowance=0.002)
finishing = FinishingParams(passes=1, doc_dia=0.002, feed=0.003)

# Execute pipeline
result = execute(profile, stock, tool, roughing, finishing)
assert result.status == PipelineStatus.SUCCESS, f"Pipeline failed: {result.status.value}"
pr = result.plan_result

# Create output folder
output_dir = r'c:\Users\jhonick\linuxcnc\Industry CAM Engine\reference\CAD Reference\Engine Output\Stepped OD'
os.makedirs(output_dir, exist_ok=True)

# --- Generate G-code ---
writer = GCodeWriter()
gcode = writer.write(pr)
gcode_path = os.path.join(output_dir, 'Stepped_OD.ngc')
with open(gcode_path, 'w') as f:
    f.write(gcode)
print(f"G-code written: {gcode_path} ({len(gcode.splitlines())} lines)")

# --- Generate DXF ---
# All coordinates in the DXF are in RADIUS for X, INCHES for Z (matching CAD reference convention)
# DXF units: millimeters (multiply inches by 25.4)
MM = 25.4

doc = ezdxf.new("R2010", setup=True)
msp = doc.modelspace()

# Create layers
doc.layers.add("PROFILE", color=7)          # White — profile boundary
doc.layers.add("ROUGHING_BOUNDARY", color=3) # Green — roughing boundary
doc.layers.add("STOCK", color=8)            # Gray — stock boundary
doc.layers.add("TOOLPATH_FEED", color=3)    # Green — all feed moves
doc.layers.add("TOOLPATH_RAPID", color=1)   # Red — rapid moves
doc.layers.add("ZONES_FINISHED_PART", color=4)  # Cyan
doc.layers.add("ZONES_MTR", color=1)        # Red
doc.layers.add("ZONES_TRUE_FACE", color=14) # Light red
doc.layers.add("ZONES_FIN_ALLOWANCE", color=2) # Yellow

# Helper: draw a polygon as connected lines
def draw_polygon(coords_dia_z, layer):
    """Draw a closed polygon. coords are (x_diameter, z) — convert to (x_radius_mm, z_mm)."""
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

# True face zone (from stock params)
fin_r = roughing.fin_allowance / 2.0
true_face = [(0.0, fin_r), (stock.diameter, fin_r), (stock.diameter, stock.z_start), (0.0, stock.z_start)]
draw_polygon(true_face, "ZONES_TRUE_FACE")

# Stock boundary
stock_poly = [(0.0, stock.z_start), (stock.diameter, stock.z_start), (stock.diameter, stock.z_end), (0.0, stock.z_end)]
draw_polygon(stock_poly, "STOCK")

# Profile boundary (from segments)
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

# Toolpath moves — DERIVED FROM G-CODE (round-trip: write → parse → DXF)
# This ensures the DXF reflects what the machine will actually execute
from outputs.gcode_parser import parse as parse_gcode

parsed_moves = parse_gcode(gcode)
prev_x_r = None
prev_z = None
for move in parsed_moves:
    x_r = move.x / 2.0
    z = move.z

    if prev_x_r is not None and prev_z is not None:
        # Skip zero-length moves
        if abs(x_r - prev_x_r) < 0.00001 and abs(z - prev_z) < 0.00001:
            prev_x_r = x_r
            prev_z = z
            continue

        # Determine layer based on move type
        if move.move_type == MoveType.RAPID:
            layer = "TOOLPATH_RAPID"
        elif move.move_type in (MoveType.ARC_CW, MoveType.ARC_CCW):
            layer = "TOOLPATH_ROUGH"  # Arcs go on rough layer for now
        else:
            layer = "TOOLPATH_FEED"

        msp.add_line(
            (prev_x_r * MM, prev_z * MM, 0),
            (x_r * MM, z * MM, 0),
            dxfattribs={"layer": layer}
        )

    prev_x_r = x_r
    prev_z = z

# Origin point
msp.add_point((0, 0, 0), dxfattribs={"layer": "0"})

dxf_path = os.path.join(output_dir, 'Stepped_OD.dxf')
doc.saveas(dxf_path)
print(f"DXF written: {dxf_path}")
print(f"\nFiles in: {output_dir}")
