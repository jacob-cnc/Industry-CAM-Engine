"""Orientation Graphic Widget — Live insert shape and orientation preview.

Renders a 160×160 pixel graphic of the insert from the SAME true-scale model
the Manual / Run / sim screens draw (geometry/tool_outline.py, tool-graphic
plan 2026-11-13), scaled to fit:
- Insert body at its true proportions (ISO shape, IC, nose radius)
- Cutting edges and nose arc highlighted in the accent colour
- Control point crosshair at LinuxCNC's controlled point (Q1-Q8 imaginary tip,
  Q9 nose centre)
Drawn like the main graphs: Z+ right, X+ DOWN (front-tool lathe).

Used inside ToolGeometryRow to give operators a visual confirmation
that the tool setup matches the physical tool.
"""

from typing import List, Optional, Tuple

from PyQt5.QtWidgets import QWidget
from PyQt5.QtGui import QPainter, QPen, QColor, QBrush, QPainterPath, QPolygonF
from PyQt5.QtCore import Qt, QPointF, QRectF

from gui.colors import COLORS
from models.tool import InsertSpec


# Colors for the orientation graphic
_BG_COLOR = QColor(COLORS["bg_panel"])
_SHAPE_COLOR = QColor(COLORS["text_disabled"])
_EDGE_COLOR = QColor("#E56E72")  # Warm orange-crimson accent for cutting edges
_NOSE_COLOR = QColor(COLORS["border_focused"])
_CROSSHAIR_COLOR = QColor("#F0F4F8")
_BODY_FILL = QColor(COLORS["bg_surface"])


class OrientationGraphicWidget(QWidget):
    """160×160 pixel custom paint widget showing the insert and its controlled point."""

    _MARGIN = 14.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(160, 160)
        self._spec: Optional[InsertSpec] = InsertSpec(1, 0.016, 95.0, 175.0, "C")
        self._outline = None
        self._problem = ""
        self._rebuild()

    def set_spec(self, spec: InsertSpec) -> None:
        """Show this insert (see tools.tool_card_data.insert_spec)."""
        self._spec = spec
        self._rebuild()
        self.update()

    def set_params(self, insert_code: str, orientation: int, nose_radius: float,
                   front_angle: float, back_angle: float) -> None:
        """Older call (insert family + table words, size unknown)."""
        from tools.insert_geometry_lookup import INSERT_SHAPE
        shape = INSERT_SHAPE.get(insert_code, "custom")
        self.set_spec(InsertSpec(max(1, min(9, orientation)), nose_radius, front_angle,
                                 back_angle, shape))

    def outline(self):
        """The model outline being shown (None when the insert can't be drawn)."""
        return self._outline

    def problem(self) -> str:
        return self._problem

    def _rebuild(self) -> None:
        from geometry.tool_outline import tool_outline
        try:
            self._outline = tool_outline(self._spec)
            self._problem = ""
        except ValueError as exc:
            self._outline = None
            self._problem = str(exc)

    # -- model (r, z) -> widget pixels: Z+ right, X+ (r) DOWN ----------------
    def _mapping(self):
        o = self._outline
        pts = list(o.outline) + [(0.0, 0.0)]
        rs = [p[0] for p in pts]
        zs = [p[1] for p in pts]
        span = max(max(rs) - min(rs), max(zs) - min(zs), 1e-6)
        k = (160.0 - 2 * self._MARGIN) / span
        r_mid = (max(rs) + min(rs)) / 2.0
        z_mid = (max(zs) + min(zs)) / 2.0
        return lambda p: QPointF(80.0 + (p[1] - z_mid) * k, 80.0 + (p[0] - r_mid) * k)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), _BG_COLOR)
        if self._outline is None:
            painter.setPen(QPen(_SHAPE_COLOR, 1))
            painter.drawText(QRectF(6, 6, 148, 148), Qt.AlignCenter | Qt.TextWordWrap,
                             self._problem or "no insert")
            painter.end()
            return
        to_px = self._mapping()
        o = self._outline
        painter.setPen(QPen(_SHAPE_COLOR, 1.5))
        painter.setBrush(QBrush(_BODY_FILL))
        painter.drawPolygon(QPolygonF([to_px(p) for p in o.outline]))
        painter.setPen(QPen(_EDGE_COLOR, 3))
        painter.setBrush(Qt.NoBrush)
        for edge in o.cutting_edges:
            path = QPainterPath(to_px(edge[0]))
            for p in edge[1:]:
                path.lineTo(to_px(p))
            painter.drawPath(path)
        c = to_px(o.nose_centre)
        painter.setPen(QPen(_NOSE_COLOR, 1.5))
        painter.drawLine(QPointF(c.x() - 3, c.y()), QPointF(c.x() + 3, c.y()))
        painter.drawLine(QPointF(c.x(), c.y() - 3), QPointF(c.x(), c.y() + 3))
        tip = to_px((0.0, 0.0))
        self._draw_crosshair(painter, tip.x(), tip.y())
        if not o.size_known:
            painter.setPen(QPen(_SHAPE_COLOR, 1))
            painter.drawText(QRectF(2, 142, 156, 16), Qt.AlignCenter, "size not set")
        painter.end()

    def _draw_crosshair(self, painter: QPainter, x: float, y: float) -> None:
        """Draw a control point crosshair at the given position."""
        size = 8.0
        pen = QPen(_CROSSHAIR_COLOR, 1.5)
        pen.setStyle(Qt.SolidLine)
        painter.setPen(pen)
        painter.drawLine(QPointF(x - size, y), QPointF(x + size, y))
        painter.drawLine(QPointF(x, y - size), QPointF(x, y + size))
