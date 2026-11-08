"""Orientation Graphic Widget — Live insert shape and orientation preview.

Renders a 160×160 pixel graphic showing:
- Insert shape outline derived from front/back cutting edge angles
- Orientation-based rotation/mirror for Q1–Q9 positions
- Nose radius circle at the tool tip
- Control point crosshair at the programmed point
- Cutting edges highlighted in accent color

Used inside ToolGeometryRow to give operators a visual confirmation
that the tool setup matches the physical tool.
"""

import math
from typing import Tuple

from PyQt5.QtWidgets import QWidget
from PyQt5.QtGui import QPainter, QPen, QColor, QBrush, QPainterPath, QPolygonF
from PyQt5.QtCore import Qt, QPointF, QRectF

from gui.colors import COLORS


# Colors for the orientation graphic
_BG_COLOR = QColor(COLORS["bg_panel"])
_SHAPE_COLOR = QColor(COLORS["text_disabled"])
_EDGE_COLOR = QColor("#E56E72")  # Warm orange-crimson accent for cutting edges
_NOSE_COLOR = QColor(COLORS["border_focused"])
_CROSSHAIR_COLOR = QColor("#F0F4F8")
_BODY_FILL = QColor(COLORS["bg_surface"])


class OrientationGraphicWidget(QWidget):
    """160×160 pixel custom paint widget showing insert orientation.

    Displays the insert shape, cutting edges, nose radius circle,
    and control point crosshair based on the current tool parameters.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(160, 160)

        # Current parameters
        self._insert_code: str = "CNMG"
        self._orientation: int = 1
        self._nose_radius: float = 0.016
        self._front_angle: float = 95.0
        self._back_angle: float = 175.0

    def set_params(
        self,
        insert_code: str,
        orientation: int,
        nose_radius: float,
        front_angle: float,
        back_angle: float,
    ) -> None:
        """Update all rendering parameters and repaint.

        Args:
            insert_code: ISO insert designation (e.g. "CNMG", "RCMT").
            orientation: LinuxCNC orientation code Q1–Q9.
            nose_radius: Tool nose radius in inches.
            front_angle: Front cutting edge angle in degrees.
            back_angle: Back cutting edge angle in degrees.
        """
        self._insert_code = insert_code
        self._orientation = max(1, min(9, orientation))
        self._nose_radius = nose_radius
        self._front_angle = front_angle
        self._back_angle = back_angle
        self.update()

    def paintEvent(self, event) -> None:
        """Render the insert shape with orientation, nose radius, and crosshair."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Fill background
        painter.fillRect(self.rect(), _BG_COLOR)

        # Center of widget
        cx, cy = 80.0, 80.0

        # Check for round insert (RCMT or both angles == 0)
        is_round = self._front_angle == 0.0 and self._back_angle == 0.0

        if is_round:
            self._draw_round_insert(painter, cx, cy)
        else:
            self._draw_angular_insert(painter, cx, cy)

        painter.end()

    def _draw_round_insert(self, painter: QPainter, cx: float, cy: float) -> None:
        """Draw a round insert (RCMT, Grooving with 0/0 angles)."""
        radius = 40.0  # Display radius for the round insert shape

        # Draw insert body (circle)
        painter.setPen(QPen(_SHAPE_COLOR, 2))
        painter.setBrush(QBrush(_BODY_FILL))
        painter.drawEllipse(QPointF(cx, cy), radius, radius)

        # Highlight the cutting edge (full circle perimeter) in accent
        painter.setPen(QPen(_EDGE_COLOR, 3))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), radius, radius)

        # Nose radius circle at the tip position based on orientation
        tip_x, tip_y = self._get_round_tip_position(cx, cy, radius)
        nose_display_r = max(6.0, min(20.0, self._nose_radius * 800))
        painter.setPen(QPen(_NOSE_COLOR, 1.5))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(tip_x, tip_y), nose_display_r, nose_display_r)

        # Control point crosshair at the programmed point (tip of nose arc)
        self._draw_crosshair(painter, tip_x, tip_y)

    def _get_round_tip_position(
        self, cx: float, cy: float, radius: float
    ) -> Tuple[float, float]:
        """Get the tip position for a round insert based on orientation.

        Screen: Z+ right, X+ down (front-tool lathe, as LinuxCNC Fig 2.16).
        """
        # For Q9 (center), tip is at center
        if self._orientation == 9:
            return cx, cy

        # Screen angle of the cutting corner (0 = right/+Z, 90 = up/-X),
        # per LinuxCNC 2.9.6 Fig 2.16 drawn with X+ DOWN (front-tool lathe).
        angle_map = {
            1: 45.0,    # corner -X,+Z
            2: 135.0,   # corner -X,-Z  (RH OD turning toward chuck)
            3: 225.0,   # corner +X,-Z  (conventional boring bar)
            4: 315.0,   # corner +X,+Z
            5: 0.0,     # +Z
            6: 90.0,    # -X
            7: 180.0,   # -Z
            8: 270.0,   # +X
        }
        angle_deg = angle_map.get(self._orientation, 45.0)
        angle_rad = math.radians(angle_deg)
        tip_x = cx + radius * math.cos(angle_rad)
        tip_y = cy - radius * math.sin(angle_rad)
        return tip_x, tip_y

    def _draw_angular_insert(self, painter: QPainter, cx: float, cy: float) -> None:
        """Draw an angular insert shape based on front/back angles and orientation.

        Lathe operator's POV coordinate frame:
            - Z+ = screen RIGHT (toward tailstock)
            - X+ = screen UP (increasing diameter, screen Y negative)
            - Spindle/chuck on the LEFT

        The canonical shape (Q1) has the tool tip pointing toward top-right
        (+X, +Z), which is the standard OD right-hand turning position.

        Front angle: angle of the front cutting edge measured from Z+ axis
        Back angle: angle of the back cutting edge measured from Z+ axis
        Both measured clockwise when viewed from the operator's position.
        """
        # Scale factor for display
        scale = 50.0

        # In the operator's POV:
        # - Z+ is screen right (positive screen X)
        # - X+ is screen up (negative screen Y)
        #
        # The front/back angles are measured from Z+ axis clockwise.
        # For Q1 canonical: tip at top-right, edges extend toward bottom-left.
        #
        # Edge vectors FROM the tip (pointing away from tip into the insert body):
        # Front edge: at (180 + front_angle) from Z+ in lathe coords
        # Back edge: at (180 + back_angle) from Z+ in lathe coords
        # (180° because edges go AWAY from the tip, into the body)

        front_body_angle = math.radians(180.0 - self._front_angle)
        back_body_angle = math.radians(180.0 - self._back_angle)

        # Convert to screen coords: Z+ = screen +X, X+ = screen -Y
        front_dx = math.cos(front_body_angle) * scale   # Z component → screen X
        front_dy = math.sin(front_body_angle) * scale   # X component → screen Y (inverted)

        back_dx = math.cos(back_body_angle) * scale
        back_dy = math.sin(back_body_angle) * scale

        # Build polygon: tip → front edge end → body corner → back edge end
        tip = QPointF(0, 0)
        front_end = QPointF(front_dx, front_dy)
        back_end = QPointF(back_dx, back_dy)

        # For narrow inserts (threading, V-shape), use a triangle.
        # For wider inserts (turning), use a parallelogram body.
        included_angle = self._back_angle - self._front_angle
        if included_angle <= 65.0:
            # Narrow insert (threading, V-shape): triangle with a flat back
            # The back of the insert is a line connecting the two edge endpoints
            # extended slightly for visual body mass
            mid_x = (front_dx + back_dx) / 2.0
            mid_y = (front_dy + back_dy) / 2.0
            # Extend the body behind the midpoint
            body_depth = scale * 0.6
            body_dir_x = mid_x / max(0.01, math.sqrt(mid_x**2 + mid_y**2))
            body_dir_y = mid_y / max(0.01, math.sqrt(mid_x**2 + mid_y**2))
            body_pt = QPointF(mid_x + body_dir_x * body_depth,
                              mid_y + body_dir_y * body_depth)
            polygon = QPolygonF([tip, front_end, body_pt, back_end])
        else:
            # Standard insert (turning): parallelogram body
            body_corner = QPointF(front_dx + back_dx, front_dy + back_dy)
            polygon = QPolygonF([tip, front_end, body_corner, back_end])

        # Orient: mirror for corner orientations Q1-Q4; for Q5-Q8 rotate so the
        # corner points along the axis (corner direction = away from the body).
        transform = self._get_orientation_transform()
        rot = 0.0
        if self._orientation in self._AXIS_DIRECTIONS:
            n = polygon.count()
            bx = sum(polygon.at(i).x() for i in range(n)) / n
            by = sum(polygon.at(i).y() for i in range(n)) / n
            tx_, ty_ = self._AXIS_DIRECTIONS[self._orientation]
            rot = math.atan2(ty_, tx_) - math.atan2(-by, -bx)
        cos_r, sin_r = math.cos(rot), math.sin(rot)

        transformed = QPolygonF()
        for i in range(polygon.count()):
            pt = polygon.at(i)
            tx, ty = self._apply_transform(pt.x(), pt.y(), transform)
            tx, ty = tx * cos_r - ty * sin_r, tx * sin_r + ty * cos_r
            transformed.append(QPointF(cx + tx, cy + ty))

        # Offset tip toward its quadrant edge
        tip_offset = self._get_tip_offset()
        final_polygon = QPolygonF()
        for i in range(transformed.count()):
            pt = transformed.at(i)
            final_polygon.append(QPointF(pt.x() + tip_offset[0], pt.y() + tip_offset[1]))

        # Draw the insert body
        painter.setPen(QPen(_SHAPE_COLOR, 1.5))
        painter.setBrush(QBrush(_BODY_FILL))
        painter.drawPolygon(final_polygon)

        # Highlight cutting edges (the two edges adjacent to the tip)
        painter.setPen(QPen(_EDGE_COLOR, 3))
        tip_pt = final_polygon.at(0)
        front_pt = final_polygon.at(1)
        back_pt = final_polygon.at(3)
        painter.drawLine(tip_pt, front_pt)
        painter.drawLine(tip_pt, back_pt)

        # Draw nose radius circle at the tip
        nose_display_r = max(4.0, min(16.0, self._nose_radius * 600))
        painter.setPen(QPen(_NOSE_COLOR, 1.5))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(tip_pt, nose_display_r, nose_display_r)

        # Control point crosshair at the programmed point (at the tip)
        self._draw_crosshair(painter, tip_pt.x(), tip_pt.y())

    # LinuxCNC tool orientation (2.9.6 manual, Fig 2.16), drawn the way the
    # main graphs and the manual show a FRONT-TOOL lathe: Z+ right, X+ DOWN
    # (toward the operator). The "corner" is the cutting corner relative to the
    # nose centre:
    #   Q1 -X,+Z   Q2 -X,-Z (RH OD turning)   Q3 +X,-Z (conventional boring bar)
    #   Q4 +X,+Z   Q5 +Z   Q6 -X   Q7 -Z   Q8 +X   Q9 centre
    # Before 2026-11-08 this widget drew Q1<->Q2 and Q3<->Q4 swapped and Q5-Q8 as
    # copies of Q1-Q4 (so a boring bar only looked right as Q8).
    # Corners reuse the canonical polygon's mirror transforms; the canonical
    # (1, 1) shape has its corner pointing up-left (= Q2).
    _CORNER_TRANSFORMS = {
        1: (-1.0, 1.0),    # up-right
        2: (1.0, 1.0),     # up-left (canonical)
        3: (1.0, -1.0),    # down-left  (was this widget's "Q8"/"Q4" picture)
        4: (-1.0, -1.0),   # down-right
    }
    # Screen unit vector of the corner direction for axis-aligned Q5-Q8.
    _AXIS_DIRECTIONS = {5: (1.0, 0.0), 6: (0.0, -1.0), 7: (-1.0, 0.0), 8: (0.0, 1.0)}

    def _get_orientation_transform(self) -> Tuple[float, float]:
        """Mirror transform for corner orientations Q1-Q4 (identity otherwise)."""
        return self._CORNER_TRANSFORMS.get(self._orientation, (1.0, 1.0))

    def _apply_transform(
        self, x: float, y: float, transform: Tuple[float, float]
    ) -> Tuple[float, float]:
        """Apply mirror transform to a point."""
        mx, my = transform
        return x * mx, y * my

    def _get_tip_offset(self) -> Tuple[float, float]:
        """Offset that moves the corner toward its side of the widget so the
        insert body fills the opposite area."""
        offset = 20.0
        if self._orientation in self._AXIS_DIRECTIONS:
            dx, dy = self._AXIS_DIRECTIONS[self._orientation]
            return (dx * offset * 1.4, dy * offset * 1.4)
        corner = {
            1: (offset, -offset),     # up-right
            2: (-offset, -offset),    # up-left
            3: (-offset, offset),     # down-left
            4: (offset, offset),      # down-right
        }
        return corner.get(self._orientation, (0.0, 0.0))

    def _draw_crosshair(
        self, painter: QPainter, x: float, y: float
    ) -> None:
        """Draw a control point crosshair at the given position."""
        size = 8.0
        pen = QPen(_CROSSHAIR_COLOR, 1.5)
        pen.setStyle(Qt.SolidLine)
        painter.setPen(pen)
        painter.drawLine(QPointF(x - size, y), QPointF(x + size, y))
        painter.drawLine(QPointF(x, y - size), QPointF(x, y + size))
