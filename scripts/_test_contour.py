"""Test contour roughing on Arc OD profile."""
import sys
sys.path.insert(0, r'c:\Users\jhonick\linuxcnc\Industry CAM Engine')

from models import *
from pipeline.pipeline import execute

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

print(f"Status: {result.status.value}")
print(f"Validations: {len(result.validations)}")
for v in result.validations[:5]:
    print(f"  [{v.severity.value}] {v.message}")

if result.plan_result:
    pr = result.plan_result
    print(f"\nPass counts:")
    print(f"  Face: {len(pr.face_passes)}")
    print(f"  Roughing: {len(pr.roughing_passes)} (expected ~10)")
    print(f"  Cleanup: {len(pr.cleanup_passes)} (expected 0 for contour)")
    print(f"  Finish: {len(pr.finish_passes)}")
    print(f"  Total moves: {pr.move_count}")
    
    print(f"\nRoughing passes:")
    for i, p in enumerate(pr.roughing_passes):
        arc_moves = [m for m in p.moves if m.move_type in (MoveType.ARC_CW, MoveType.ARC_CCW)]
        line_moves = [m for m in p.moves if m.move_type == MoveType.FEED]
        print(f"  Pass {i+1}: X={p.x_level:.4f} dia ({p.x_level/2:.4f}r), "
              f"Z[{p.z_start:.4f}->{p.z_end:.4f}], "
              f"lines={len(line_moves)}, arcs={len(arc_moves)}")
        if arc_moves:
            for am in arc_moves:
                print(f"    Arc: X={am.x:.4f} Z={am.z:.4f} I={am.center_i:.4f} K={am.center_k:.4f}")
