"""Quick visual test — shows the graph with pipeline output.
Run this to see the toolpath visualization.
Close the window to exit.
"""
import sys
sys.path.insert(0, r'c:\Users\jhonick\linuxcnc\Industry CAM Engine')

from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QLabel
from PyQt5.QtCore import Qt

from models import *
from pipeline.pipeline import execute
from outputs.graph_adapter import convert
from gui.colors import COLORS, STYLESHEET
from gui.components.graph_widget import MachiningGraphWidget

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
print("Executing pipeline...")
result = execute(profile, stock, tool, roughing, finishing)
print(f"Status: {result.status.value}")

if result.plan_result:
    # Convert to graph data
    graph_data = convert(result.plan_result)
    print(f"Graph data: {len(graph_data.toolpath_segments)} segments, {len(graph_data.playback_frames)} frames")

    # Create Qt app
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLESHEET)

    window = QMainWindow()
    window.setWindowTitle("Industry CAM Engine — Visual Test")
    window.setGeometry(100, 100, 1200, 700)

    central = QWidget()
    layout = QVBoxLayout(central)

    # Coordinate readout label
    coord_label = QLabel("X: ---  Z: ---")
    coord_label.setStyleSheet(f"color: {COLORS['text_primary']}; font-family: JetBrains Mono; font-size: 14pt;")
    layout.addWidget(coord_label)

    # Graph widget
    graph = MachiningGraphWidget()
    graph.set_graph_data(graph_data)
    layout.addWidget(graph)

    # Connect coordinate readout
    def on_coord_changed(x_r, z):
        x_dia = x_r * 2.0
        coord_label.setText(f"X: {x_r:.5f}\" (Ø{x_dia:.4f})  Z: {z:.5f}\"")

    graph.coordinate_changed.connect(on_coord_changed)

    window.setCentralWidget(central)
    window.show()

    print("Window open — close to exit.")
    sys.exit(app.exec_())
else:
    print("Pipeline failed — no visual output")
    for v in result.validations:
        print(f"  [{v.severity.value}] {v.message}")
