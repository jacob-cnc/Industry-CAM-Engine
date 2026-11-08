#!/usr/bin/env python3
"""Print each tool type's orientation options as ASCII art (rendered from the
real Tools-tab widget). Run from the repo root:
    QT_QPA_PLATFORM=offscreen /usr/bin/python3 scripts/preview_tool_orientations.py
"""
import sys, os
sys.path.insert(0, os.getcwd())
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QColor
app = QApplication(sys.argv)
from gui.components.orientation_graphic import OrientationGraphicWidget, _EDGE_COLOR, _CROSSHAIR_COLOR, _BODY_FILL, _NOSE_COLOR
from pipeline.tool_card_data import TYPE_ORIENTATIONS
from pipeline.insert_geometry_lookup import get_angles
W, H = 26, 13           # characters per panel
def near(c, ref, tol=40):
    return abs(c.red()-ref.red()) + abs(c.green()-ref.green()) + abs(c.blue()-ref.blue()) < tol
def panel(insert, q):
    w = OrientationGraphicWidget(); w.resize(160, 160)
    fa, ba = get_angles(insert)
    w.set_params(insert, q, 0.016, fa, ba)
    img = w.grab().toImage()
    rows = []
    for r in range(H):
        line = ""
        for col in range(W):
            x0, y0 = int(col * 160 / W), int(r * 160 / H)
            x1, y1 = int((col + 1) * 160 / W), int((r + 1) * 160 / H)
            hits = {"o": 0, "#": 0, ".": 0}
            for y in range(y0, y1):
                for x in range(x0, x1):
                    c = QColor(img.pixel(x, y))
                    if near(c, _CROSSHAIR_COLOR) or near(c, _NOSE_COLOR): hits["o"] += 1
                    elif near(c, _EDGE_COLOR, 60): hits["#"] += 1
                    elif near(c, _BODY_FILL, 18): hits["."] += 1
            line += "o" if hits["o"] > 3 else "#" if hits["#"] > 2 else "." if hits["."] > (x1-x0)*(y1-y0)//2 else " "
        rows.append(line)
    return rows
TYPES = [("Turning RH", "CNMG"), ("Turning LH", "CNMG"), ("Boring Bar", "CCMT"),
         ("Threading External", "60° UN/Metric"), ("Threading Internal", "60° UN/Metric"), ("Grooving/Parting", "Grooving")]
print("View: chuck LEFT, Z+ RIGHT, X+ DOWN (toward you).  # = cutting edges  o = control point  . = insert body\n")
for t, ins in TYPES:
    qs = TYPE_ORIENTATIONS[t]
    panels = [panel(ins, q) for q in qs]
    print(f"== {t}  ({ins})")
    print("   ".join(f"Q{q}{' (default)' if i == 0 else ''}".center(W) for i, q in enumerate(qs)))
    print("   ".join("+" + "-" * (W - 2) + "+" for _ in qs))
    for r in range(H):
        print("   ".join("|" + p[r][1:-1] + "|" for p in panels))
    print("   ".join("+" + "-" * (W - 2) + "+" for _ in qs))
    print()
