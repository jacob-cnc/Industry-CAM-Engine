"""Export DXF and G-code for Arc OD with contour roughing strategy."""
import sys, os, math
sys.path.insert(0, r'c:\Users\jhonick\linuxcnc\Industry CAM Engine')

import ezdxf
from models import *
from models.moves import ToolMove, MoveType, PassType
from pipeline.pipeline import execute
from outputs.gcode_writer import GCodeWriter

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
roughing = RoughingParams(doc_dia=0.050, feed=0.005, strategy=RoughingStrategy.OFFSET_CONTOUR, fin_allowance=0.002)
finishing = FinishingParams(passes=1, doc_dia=0.002, feed=0.003)

result = execute(profile, stock, tool, roughing, finishing)
pr = result.plan_result
print(f"Status: {result.status.value}, Passes: rough={len(pr.roughing_passes)}")

# G-code
writer = GCodeWriter()
gcode = writer.write(pr)
out_dir = r'c:\Users\jhonick\linuxcnc\Industry CAM Engine\reference\CAD Reference\Engine Output\Arc OD Contour'
os.makedirs(out_dir, exist_ok=True)
gcode_path = os.path.join(out_dir, 'Arc_OD_Contour.ngc')
with open(gcode_path, 'w') as f:
    f.write(gcode)
print(f"G-code: {gcode_path} ({len(gcode.splitlines())} lines)")

# DXF
MM = 25.4
doc = ezdxf.new("R2010", setup=True)
msp = doc.modelspace()
doc.layers.add("PROFILE", color=7)
doc.layers.add("STOCK", color=8)
doc.layers.add("TOOLPATH_ROUGH", color=3)
doc.layers.add("TOOLPATH_FINISH", color=5)
doc.layers.add("TOOLPATH_RAPID", color=1)
doc.layers.add("TOOLPATH_FACE", color=14)

# Stock
pts = [(0, stock.z_start*MM),(stock.diameter/2*MM, stock.z_start*MM),
       (stock.diameter/2*MM, stock.z_end*MM),(0, stock.z_end*MM),(0, stock.z_start*MM)]
for i in range(len(pts)-1):
    msp.add_line(pts[i], pts[i+1], dxfattribs={"layer":"STOCK"})

# Profile
for i in range(len(segments)-1):
    seg, ns = segments[i], segments[i+1]
    x1r, z1, x2r, z2 = seg.x/2, seg.z, ns.x/2, ns.z
    if ns.segment_type == SegmentType.ARC and ns.radius != 0:
        cx_r, cz, r = -0.366, -1.0, 1.0
        sa = math.degrees(math.atan2(z1-cz, x1r-cx_r))
        ea = math.degrees(math.atan2(z2-cz, x2r-cx_r))
        msp.add_arc(center=(cx_r*MM,cz*MM), radius=r*MM, start_angle=ea, end_angle=sa, dxfattribs={"layer":"PROFILE"})
    else:
        msp.add_line((x1r*MM,z1*MM),(x2r*MM,z2*MM), dxfattribs={"layer":"PROFILE"})

# Toolpath
prev_xr, prev_z = None, None
for move in pr.tool_moves:
    xr, z = move.x/2, move.z
    if prev_xr is not None and prev_z is not None:
        if abs(xr-prev_xr)<0.00001 and abs(z-prev_z)<0.00001:
            prev_xr, prev_z = xr, z
            continue
        if move.move_type == MoveType.RAPID:
            layer = "TOOLPATH_RAPID"
        elif move.pass_type == PassType.FACE:
            layer = "TOOLPATH_FACE"
        elif move.pass_type == PassType.FINISH:
            layer = "TOOLPATH_FINISH"
        else:
            layer = "TOOLPATH_ROUGH"
        if (move.move_type in (MoveType.ARC_CW, MoveType.ARC_CCW) and
                (abs(move.center_i)>0.0001 or abs(move.center_k)>0.0001)):
            ci, ck = move.center_i/2, move.center_k
            cxr, czz = prev_xr+ci, prev_z+ck
            r = math.sqrt(ci**2+ck**2)
            sa = math.degrees(math.atan2(prev_z-czz, prev_xr-cxr))
            ea = math.degrees(math.atan2(z-czz, xr-cxr))
            msp.add_arc(center=(cxr*MM,czz*MM), radius=r*MM, start_angle=ea, end_angle=sa, dxfattribs={"layer":layer})
        else:
            msp.add_line((prev_xr*MM,prev_z*MM),(xr*MM,z*MM), dxfattribs={"layer":layer})
    prev_xr, prev_z = xr, z

dxf_path = os.path.join(out_dir, 'Arc_OD_Contour.dxf')
doc.saveas(dxf_path)
print(f"DXF: {dxf_path}")
