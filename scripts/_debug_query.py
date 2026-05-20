"""Debug the boundary_at_x query for Arc OD profile."""
import sys
sys.path.insert(0, r'c:\Users\jhonick\linuxcnc\Industry CAM Engine')

from models import *
from geometry.zone_builder import build_zones
from geometry.zone_query import ZoneQueryAPI

# Arc OD profile
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

print("Building zones...")
zone_set = build_zones(profile, stock, tool, roughing)
zq = ZoneQueryAPI(zone_set)
print("Zones built OK")

# First, let's check what the finished_part boundary looks like
print("\n=== Finished Part Boundary (wire extraction) ===")
fp_edges = zq.boundary_wire_extraction("finished_part")
for e in fp_edges:
    if e.edge_type == "ARC":
        print(f"  ARC: ({e.start[0]:.4f}, {e.start[1]:.4f}) -> ({e.end[0]:.4f}, {e.end[1]:.4f}), center=({e.center[0]:.4f}, {e.center[1]:.4f}), R={e.radius:.4f}")
    else:
        print(f"  LINE: ({e.start[0]:.4f}, {e.start[1]:.4f}) -> ({e.end[0]:.4f}, {e.end[1]:.4f})")

# Check MTR boundary
print("\n=== Material to Rough Boundary (wire extraction) ===")
mtr_edges = zq.boundary_wire_extraction("material_to_rough")
for e in mtr_edges:
    if e.edge_type == "ARC":
        print(f"  ARC: ({e.start[0]:.4f}, {e.start[1]:.4f}) -> ({e.end[0]:.4f}, {e.end[1]:.4f}), center=({e.center[0]:.4f}, {e.center[1]:.4f}), R={e.radius:.4f}")
    else:
        print(f"  LINE: ({e.start[0]:.4f}, {e.start[1]:.4f}) -> ({e.end[0]:.4f}, {e.end[1]:.4f})")

# Now query at specific X levels
print("\n=== boundary_at_x() queries (MTR zone) ===")
print(f"{'X_dia':<8} {'X_rad':<8} {'Intervals':<60} {'NX Expected'}")
print("-" * 120)

# NX ground truth (in radius coords, converted to diameter for query):
test_cases = [
    (1.500, "full length (stock OD)"),
    (1.450, "first DOC level"),
    (1.250, "NX: Z[-0.4673, -1.5327]"),
    (1.100, "NX: Z[-0.4865, -1.5135]"),
    (1.050, "NX: Z[-0.4931, -1.5069]"),
    (1.002, "NX: Z[-0.4997, -1.5003]"),
]

for x_dia, expected in test_cases:
    intervals = zq.boundary_at_x(x_dia, "material_to_rough")
    int_str = ", ".join([f"Z[{zs:.4f} -> {ze:.4f}]" for zs, ze in intervals])
    if not int_str:
        int_str = "(empty)"
    print(f"{x_dia:<8.4f} {x_dia/2:<8.4f} {int_str:<60} {expected}")

# Also query the finished_part zone to see if the arc is correct there
print("\n=== boundary_at_x() queries (Finished Part zone) ===")
for x_dia, expected in test_cases:
    intervals = zq.boundary_at_x(x_dia, "finished_part")
    int_str = ", ".join([f"Z[{zs:.4f} -> {ze:.4f}]" for zs, ze in intervals])
    if not int_str:
        int_str = "(empty)"
    print(f"{x_dia:<8.4f} {x_dia/2:<8.4f} {int_str:<60}")
