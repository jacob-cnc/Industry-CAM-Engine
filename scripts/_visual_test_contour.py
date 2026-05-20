"""Visual test for Arc OD contour roughing."""
import sys
sys.path.insert(0, r'c:\Users\jhonick\linuxcnc\Industry CAM Engine')

from models import *
from pipeline.pipeline import execute
from outputs.graph_adapter import convert as graph_convert
from outputs.gcode_writer import GCodeWriter
from _visual_test_arc import SimViewer, parse_gcode_for_sim
from PyQt5.QtWidgets import QApplication

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

print("Executing pipeline...")
result = execute(profile, stock, tool, roughing, finishing)
print(f"Status: {result.status.value}")
pr = result.plan_result
graph_data = graph_convert(pr)
gcode_text = GCodeWriter().write(pr)
sim_moves = parse_gcode_for_sim(gcode_text)
print(f"Roughing passes: {len(pr.roughing_passes)}, SimMoves: {len(sim_moves)}")
print("Launching viewer...")

app = QApplication(sys.argv)
viewer = SimViewer(graph_data, gcode_text, sim_moves)
viewer.setWindowTitle("Arc OD — Contour Roughing")
viewer.show()
sys.exit(app.exec_())
