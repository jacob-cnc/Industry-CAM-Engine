"""Visual test for ID Bore profile — graph viewer with toolpath simulation + G-code panel.

Reuses the SimViewer from _visual_test_arc.py with ID bore data.
"""
import sys
sys.path.insert(0, r'c:\Users\jhonick\linuxcnc\Industry CAM Engine')

from models import *
from pipeline.pipeline import execute
from outputs.graph_adapter import convert as graph_convert
from outputs.gcode_writer import GCodeWriter

# Import the SimViewer and parser from the arc test
from _visual_test_arc import SimViewer, parse_gcode_for_sim

from PyQt5.QtWidgets import QApplication

# ID Bore profile (NX ground truth parameters)
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

print("Executing pipeline...")
result = execute(profile, stock, tool, roughing, finishing)
print(f"Status: {result.status.value}")

if result.status not in (PipelineStatus.SUCCESS, PipelineStatus.SUCCESS_WITH_WARNINGS):
    for v in result.validations:
        print(f"  [{v.severity.value}] {v.message}")
    sys.exit(1)

pr = result.plan_result
graph_data = graph_convert(pr)
gcode_text = GCodeWriter().write(pr)

# Parse G-code into SimMoves
sim_moves = parse_gcode_for_sim(gcode_text)

print(f"Passes: face={len(pr.face_passes)} rough={len(pr.roughing_passes)} "
      f"cleanup={len(pr.cleanup_passes)} finish={len(pr.finish_passes)}")
print(f"G-code: {len(gcode_text.splitlines())} lines")
print(f"SimMoves: {len(sim_moves)} motion commands")
print("Launching viewer...")

app = QApplication(sys.argv)
viewer = SimViewer(graph_data, gcode_text, sim_moves)
viewer.setWindowTitle("ID Bore Profile — Toolpath Simulation")
viewer.show()
sys.exit(app.exec_())
