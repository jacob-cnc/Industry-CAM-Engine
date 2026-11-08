"""Quadrant Graphic Widget — Visual arc quadrant selector.

Draws a circle divided into four 90° arcs with the selected quadrant
highlighted. Used in the compound slide Arc mode UI.
"""

from PyQt5.QtWidgets import QWidget
from PyQt5.QtGui import QPainter, QPen, QColor
import math

from PyQt5.QtCore import Qt, QRectF, QPointF

from gui.colors import COLORS
from hal.compound_logic import Quadrant


class QuadrantGraphic(QWidget):
    """60×60 pixel quadrant selector graphic.

    Draws a circle divided into four 90° arcs. The selected quadrant
    is highlighted in accent color; others are drawn dim.
    Dotted crosshair lines through center provide visual reference.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(150, 150)
        self._selected = Quadrant.SE
        self._endpoints = None   # (start_angle, end_angle), logic convention

    def set_quadrant(self, quadrant: Quadrant):
        """Update the highlighted quadrant and repaint."""
        self._selected = quadrant
        self.update()

    def set_endpoints(self, start_angle: float, end_angle: float):
        """Mark the arc start (green dot) and end (red dot).

        Angles use the arc logic's convention: point = center + R*(sin a, cos a)
        with sin -> X (radius) and cos -> Z. On this widget Z+ is right and
        X+ is down (graph invertY), so the screen point is
        (cx + r*cos a, cy + r*sin a).
        """
        self._endpoints = (start_angle, end_angle)
        self.update()

    def paintEvent(self, event):
        """Draw the quadrant circle with highlighted arc.

        Orientation matches the operator's POV (graph has invertY=True):
            X+ (larger diameter) = bottom of graphic
            Z+ (away from headstock) = right of graphic
        So NE = top-right, NW = top-left, SW = bottom-left, SE = bottom-right.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        cx, cy = 75, 75
        r = 60

        pen_inactive = QPen(QColor(COLORS['text_disabled']), 2)
        pen_active = QPen(QColor("#2F8CFF"), 5)  # Bright blue, thick for visibility

        # Qt drawArc: 1/16th degree units, 0° = 3 o'clock, positive = CCW
        # Widget has normal screen coords (Y down). Operator POV on graph has invertY (X+ = down).
        # Match the widget quadrants to what the operator sees on the graph:
        #   SE = larger X, +Z = bottom-right of graph = bottom-right of widget
        #   NE = smaller X, +Z = top-right of graph = top-right of widget
        #   SW = larger X, -Z = bottom-left of graph = bottom-left of widget
        #   NW = smaller X, -Z = top-left of graph = top-left of widget
        quadrant_arcs = {
            Quadrant.NE: (0, 90 * 16),           # top-right (0° to 90° CCW)
            Quadrant.NW: (90 * 16, 90 * 16),     # top-left (90° to 180° CCW)
            Quadrant.SW: (180 * 16, 90 * 16),    # bottom-left (180° to 270° CCW)
            Quadrant.SE: (270 * 16, 90 * 16),    # bottom-right (270° to 360° CCW)
        }

        rect = QRectF(cx - r, cy - r, 2 * r, 2 * r)
        for quad, (start, span) in quadrant_arcs.items():
            painter.setPen(pen_active if quad == self._selected else pen_inactive)
            painter.drawArc(rect, start, span)

        # Dotted crosshair
        pen_cross = QPen(QColor(COLORS['border_normal']), 1, Qt.DotLine)
        painter.setPen(pen_cross)
        painter.drawLine(cx, cy - r - 6, cx, cy + r + 6)
        painter.drawLine(cx - r - 6, cy, cx + r + 6, cy)

        # Arc start (green) / end (red) dots — drawn last so they sit on top
        if self._endpoints is not None:
            dot_r = 7
            outline = QPen(QColor(COLORS['bg_panel']), 2)
            for angle, color in zip(self._endpoints, ("#22C55E", "#FF3B3B")):
                pt = QPointF(cx + r * math.cos(angle), cy + r * math.sin(angle))
                painter.setPen(outline)
                painter.setBrush(QColor(color))
                painter.drawEllipse(pt, dot_r, dot_r)

        painter.end()
