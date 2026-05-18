"""Quadrant Graphic Widget — Visual arc quadrant selector.

Draws a circle divided into four 90° arcs with the selected quadrant
highlighted in the accent color. Used in the Arc Jog mode UI to show
which quadrant is active.
"""

from PyQt5.QtWidgets import QWidget
from PyQt5.QtGui import QPainter, QPen, QColor
from PyQt5.QtCore import Qt, QRectF

from arc_jog_logic import Quadrant
from theme import COLORS


class QuadrantGraphic(QWidget):
    """80×80 pixel quadrant selector graphic.

    Draws a circle divided into four 90° arcs. The selected quadrant
    is highlighted in the accent color; others are drawn in text_dim.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(60, 60)
        self._selected = Quadrant.BOTTOM_RIGHT

    def set_quadrant(self, quadrant: Quadrant):
        """Update the highlighted quadrant and repaint."""
        self._selected = quadrant
        self.update()

    def paintEvent(self, event):
        """Draw the quadrant circle with highlighted arc."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        cx, cy = 30, 30  # center
        r = 24            # radius in pixels

        # Pen styles
        pen_inactive = QPen(QColor(COLORS['text_dim']), 2)
        pen_active = QPen(QColor(COLORS['accent']), 3)

        # Qt drawArc uses 1/16th degree units, 0° = 3 o'clock position
        # Positive angles go counter-clockwise
        quadrant_arcs = {
            Quadrant.TOP_RIGHT: (0, 90 * 16),
            Quadrant.TOP_LEFT: (90 * 16, 90 * 16),
            Quadrant.BOTTOM_LEFT: (180 * 16, 90 * 16),
            Quadrant.BOTTOM_RIGHT: (270 * 16, 90 * 16),
        }

        rect = QRectF(cx - r, cy - r, 2 * r, 2 * r)
        for quad, (start, span) in quadrant_arcs.items():
            if quad == self._selected:
                painter.setPen(pen_active)
            else:
                painter.setPen(pen_inactive)
            painter.drawArc(rect, start, span)

        # Draw dotted crosshair lines through center
        pen_cross = QPen(QColor(COLORS['border']), 1, Qt.DotLine)
        painter.setPen(pen_cross)
        painter.drawLine(cx, cy - r - 4, cx, cy + r + 4)
        painter.drawLine(cx - r - 4, cy, cx + r + 4, cy)

        painter.end()
