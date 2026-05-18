"""Quick test to verify SyncedPlayback frame building."""
import sys
sys.path.insert(0, r'c:\Users\jhonick\linuxcnc\Industry CAM Engine')

from models import *
from pipeline.pipeline import execute
from outputs.gcode_writer import GCodeWriter

segments = [
    ProfileMove(SegmentType.LINE, 0.0, 0.0),
    ProfileMove(SegmentType.LINE, 1.0, 0.0),
    ProfileMove(SegmentType.LINE, 1.0, -0.5),
    ProfileMove(SegmentType.ARC, 1.0, -1.5, radius=-1.0),
    ProfileMove(SegmentType.LINE, 1.0, -2.0),
]
breaks = [None]*4
profile = ClosedProfile(segments=segments, corner_breaks=breaks, mode=MachiningMode.OD, z_end=-2.0)
stock = StockDef(diameter=1.5, x_start=0.0, z_start=0.1, z_end=-2.0, mode=MachiningMode.OD)
tool = ToolDef(1, 0.016, 80.0, 0.375, ToolOrientation.OD_FRONT_RIGHT, ToolDirection.RIGHT)
roughing = RoughingParams(doc_dia=0.05, feed=0.005, strategy=RoughingStrategy.STAIRCASE, fin_allowance=0.002)
finishing = FinishingParams(passes=1, doc_dia=0.002, feed=0.003)

result = execute(profile, stock, tool, roughing, finishing)
pr = result.plan_result
gcode = GCodeWriter().write(pr)
lines = gcode.splitlines()

# Replicate the SyncedPlayback logic
frames = []
x_pos = 0.0
z_pos = 0.0

for i, line in enumerate(lines):
    stripped = line.strip()
    if not stripped or stripped.startswith(";"):
        continue
    if not stripped.startswith("N"):
        continue

    comment_start = stripped.find("(")
    code_part = stripped[:comment_start].strip() if comment_start >= 0 else stripped
    tokens = code_part.split()
    if len(tokens) < 2:
        continue

    try:
        n_num = int(tokens[0][1:])
    except (ValueError, IndexError):
        continue

    g_code = None
    for token in tokens[1:]:
        if token in ("G00", "G01", "G02", "G03"):
            g_code = token
            break

    if g_code is None:
        continue

    for token in tokens[1:]:
        if token.startswith("X") and len(token) > 1:
            try:
                x_pos = float(token[1:])
            except ValueError:
                pass
        elif token.startswith("Z") and len(token) > 1:
            try:
                z_pos = float(token[1:])
            except ValueError:
                pass

    x_radius = x_pos / 2.0
    frames.append((i, n_num, x_radius, z_pos, g_code))

print(f"Total frames: {len(frames)}")
print(f"\nFirst 10 frames:")
for idx, (line_idx, n_num, x_r, z, gcode_type) in enumerate(frames[:10]):
    actual_line = lines[line_idx].strip()
    print(f"  Frame {idx+1}: line {line_idx+1:3d} | N{n_num:4d} | {gcode_type} X{x_r*2:.4f} Z{z:.4f}")
    print(f"           Actual: {actual_line[:70]}")
