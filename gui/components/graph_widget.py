"""Machining graph widget for Industry CAM Engine.

Reusable PyQtGraph-based widget for both Program Tab and Edit Tab.
Provides: zone shading, toolpath trace, crosshair with coordinate readout,
profile boundary, stock boundary, playback tool dot.

All coordinates displayed in RADIUS internally, axis labels show DIAMETER.

Aspect ratio is locked 1:1 — arcs display as true circles, geometry is always
accurate. The view may have empty space on one axis for non-square parts, but
the user can pan/zoom freely to focus on the area of interest.
"""

import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtGui
import numpy as np
from typing import List, Optional

from gui.colors import COLORS, FONTS
from outputs.graph_adapter import GraphData, ToolpathSegment


class DiameterAxisItem(pg.AxisItem):
    """X axis that displays diameter while plotting in radius coordinates."""

    def tickStrings(self, values, scale, spacing):
        if spacing < 0.001:
            return [f"{v * 2.0:.5f}" for v in values]
        elif spacing < 0.01:
            return [f"{v * 2.0:.4f}" for v in values]
        elif spacing < 0.1:
            return [f"{v * 2.0:.3f}" for v in values]
        else:
            return [f"{v * 2.0:.2f}" for v in values]


class PrecisionZAxisItem(pg.AxisItem):
    """Z axis with adaptive precision."""

    def tickStrings(self, values, scale, spacing):
        if spacing < 0.001:
            return [f"{v:.5f}" for v in values]
        elif spacing < 0.01:
            return [f"{v:.4f}" for v in values]
        elif spacing < 0.1:
            return [f"{v:.3f}" for v in values]
        else:
            return [f"{v:.2f}" for v in values]


class MachiningGraphWidget(pg.PlotWidget):
    """Reusable graph widget for machining visualization.

    Features:
    - 1:1 aspect ratio (arcs display as true circles, geometry is accurate)
    - Crosshair with coordinate readout (radius + diameter for X)
    - Zone shading (filled polygons)
    - Toolpath trace (PlotCurveItem per move type, color-coded)
    - Profile boundary (bold white)
    - Stock boundary rectangle (dashed)
    - Animated tool dot for playback
    - Double-click to auto-fit view

    Signals:
        coordinate_changed(float, float): Emitted on mouse move (x_radius, z)
    """

    coordinate_changed = QtCore.pyqtSignal(float, float)

    def __init__(self, parent=None):
        # Create custom axes
        x_axis = DiameterAxisItem(orientation='left')
        z_axis = PrecisionZAxisItem(orientation='bottom')

        super().__init__(
            parent=parent,
            axisItems={'left': x_axis, 'bottom': z_axis},
            background=COLORS['graph_bg'],
        )

        self._setup_plot()
        self._setup_crosshair()
        self._tool_dot = None
        self._next_seg_item = None
        self._rapid_items = []
        self._graph_data: Optional[GraphData] = None
        self._material_fill_items: list = []

        # Idle coordinate overlay (QLabel in screen space, not data space)
        from PyQt5.QtWidgets import QLabel
        from PyQt5.QtCore import QTimer
        self._coord_overlay = QLabel(self)
        self._coord_overlay.setStyleSheet(
            f"background-color: rgba(30, 53, 72, 220);"
            f"color: {COLORS['text_primary']};"
            f"font-family: {FONTS['mono_family']};"
            f"font-size: 9pt;"
            f"padding: 4px 6px;"
            f"border: 1px solid {COLORS['border_normal']};"
            f"border-radius: 3px;"
        )
        self._coord_overlay.setVisible(False)
        self._coord_overlay.raise_()

        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.timeout.connect(self._show_coord_overlay)
        self._last_mouse_screen_pos = None
        self._last_mouse_data_pos = None

    def _setup_plot(self):
        """Configure the plot area — Y inverted for operator POV, 1:1 aspect."""
        plot_item = self.getPlotItem()
        plot_item.showGrid(x=True, y=True, alpha=0.3)

        # Set axis labels
        plot_item.setLabel('left', 'X (Diameter)', units='in')
        plot_item.setLabel('bottom', 'Z', units='in')

        # Invert Y axis so X+ is at the bottom (operator's POV: tool comes down)
        vb = self.getViewBox()
        vb.invertY(True)
        vb.setMouseEnabled(x=True, y=True)

        # Lock 1:1 aspect ratio — geometry is always accurate.
        # X axis is in RADIUS internally, Z in inches. ratio=1.0 means
        # 1 inch of radius = 1 inch of Z on screen.
        vb.setAspectLocked(True, ratio=1.0)

    def mouseDoubleClickEvent(self, event):
        """Double-click to auto-fit the view back to the full part."""
        self.getViewBox().autoRange()
        event.accept()

    def _setup_crosshair(self):
        """Set up crosshair lines and coordinate label."""
        self._vline = pg.InfiniteLine(angle=90, movable=False,
                                      pen=pg.mkPen(COLORS['graph_crosshair'], width=1))
        self._hline = pg.InfiniteLine(angle=0, movable=False,
                                      pen=pg.mkPen(COLORS['graph_crosshair'], width=1))
        self.addItem(self._vline, ignoreBounds=True)
        self.addItem(self._hline, ignoreBounds=True)

        # Connect mouse move
        self.scene().sigMouseMoved.connect(self._on_mouse_moved)

    def _on_mouse_moved(self, pos):
        """Update crosshair position and emit coordinate signal."""
        if self.sceneBoundingRect().contains(pos):
            mouse_point = self.getViewBox().mapSceneToView(pos)
            x_radius = mouse_point.y()  # Y in plot = X radius (lathe convention)
            z = mouse_point.x()         # X in plot = Z (lathe convention)

            self._vline.setPos(z)
            self._hline.setPos(x_radius)
            self.coordinate_changed.emit(x_radius, z)

            # Track position and restart idle timer for coordinate overlay
            self._last_mouse_data_pos = (x_radius, z)
            # Map scene pos to widget-local coordinates for overlay placement
            self._last_mouse_screen_pos = self.mapFromScene(pos)
            self._coord_overlay.setVisible(False)
            self._idle_timer.start(1500)  # Show after 1.5s idle

    def _show_coord_overlay(self):
        """Show coordinate overlay at the cursor position after idle timeout."""
        if self._last_mouse_data_pos is None or self._last_mouse_screen_pos is None:
            return
        x_radius, z = self._last_mouse_data_pos
        x_dia = x_radius * 2.0
        self._coord_overlay.setText(f"X {x_dia:.6f} dia\nZ {z:.6f}")
        self._coord_overlay.adjustSize()
        # Position the label near the cursor (offset slightly so it doesn't cover crosshair)
        px = int(self._last_mouse_screen_pos.x()) + 15
        py = int(self._last_mouse_screen_pos.y()) - 10
        # Keep within widget bounds
        if px + self._coord_overlay.width() > self.width():
            px = int(self._last_mouse_screen_pos.x()) - self._coord_overlay.width() - 15
        if py < 0:
            py = int(self._last_mouse_screen_pos.y()) + 15
        self._coord_overlay.move(px, py)
        self._coord_overlay.setVisible(True)
        self._coord_overlay.raise_()

    def set_graph_data(self, data: GraphData):
        """Load complete graph data. Replaces all current display items."""
        self.clear()
        self._setup_crosshair()
        self._tool_dot = None
        self._next_seg_item = None
        self._profile_overlay_items = []
        self._material_fill_items = []
        self._graph_data = data

        # Note: In our graph, X-axis (horizontal) = Z, Y-axis (vertical) = X radius
        # This matches the lathe operator's view (Z horizontal, X vertical)

        # Material removal visualization — DISABLED (zone shading removed, material sim shelved)
        # Zone shading was visually cluttered and material sim not accurate yet.
        # When material sim is re-enabled, restore: self.set_material_to_stock()

        # Stock boundary rectangle
        x_min_r, x_max_r, z_min, z_max = data.stock_rect
        stock_pen = pg.mkPen(COLORS['graph_stock'], width=1, style=QtCore.Qt.DashLine)
        stock_x = [z_min, z_max, z_max, z_min, z_min]
        stock_y = [x_min_r, x_min_r, x_max_r, x_max_r, x_min_r]
        self.plot(stock_x, stock_y, pen=stock_pen)

        # Profile boundary — not drawn. The toolpath traces show the actual cutting
        # path accurately. The kernel-extracted boundary has OCCT numerical tolerance
        # (~0.0001") that creates a visible gap vs the exact toolpath coordinates.

        # Toolpath segments (color-coded by move type)
        # Initially hidden — revealed progressively during sim playback
        # or all at once via "Show All"
        self._rapid_items = []
        self._toolpath_items = []  # ALL toolpath PlotDataItems (for show/hide)
        for segment in data.toolpath_segments:
            color = self._get_segment_color(segment)
            style = QtCore.Qt.DashLine if segment.move_type.value == 'rapid' else QtCore.Qt.SolidLine
            pen = pg.mkPen(color, width=1, style=style)
            item = self.plot(segment.z_coords, segment.x_coords, pen=pen)
            item.setVisible(False)  # Hidden until playback reveals it
            self._toolpath_items.append(item)
            if segment.move_type.value == 'rapid':
                self._rapid_items.append(item)

        # Centerline (pronounced X=0 line)
        if data.centerline_z_range != (0, 0):
            z_min_cl, z_max_cl = data.centerline_z_range
            cl_pen = pg.mkPen('#FFFFFF40', width=2, style=QtCore.Qt.DashDotLine)
            self.plot([z_min_cl, z_max_cl], [0, 0], pen=cl_pen)

        # Auto-fit view to show everything (small padding for grid visibility at edges)
        self.getViewBox().autoRange(padding=0.05)

    def set_tool_position(self, x_radius: float, z: float):
        """Update animated tool dot position during playback."""
        if self._tool_dot is None:
            self._tool_dot = pg.ScatterPlotItem(
                size=16,
                brush=pg.mkBrush(COLORS['graph_tool_dot']),
                pen=pg.mkPen('#00000099', width=2),
            )
            self._tool_dot.setZValue(20)
            self.addItem(self._tool_dot)

        self._tool_dot.setData([z], [x_radius])

    def highlight_next_segment(self, move_index: int):
        """Show the upcoming segment as a dotted preview line (next move to be executed).

        Call with move_index=-1 or out-of-range to clear the highlight.
        """
        if self._next_seg_item is None:
            self._next_seg_item = self.plot(
                [], [],
                pen=pg.mkPen('#FFFFFF55', width=2, style=QtCore.Qt.DotLine),
            )
            self._next_seg_item.setZValue(15)

        if (not self._graph_data or
                move_index < 0 or
                move_index >= len(self._graph_data.toolpath_segments)):
            self._next_seg_item.setData([], [])
            return

        seg = self._graph_data.toolpath_segments[move_index]
        self._next_seg_item.setData(seg.z_coords, seg.x_coords)

    def set_rapids_visible(self, visible: bool):
        """Show or hide all rapid move lines."""
        for item in self._rapid_items:
            if visible:
                item.setVisible(True)
            else:
                item.setVisible(False)
        self._rapids_hidden = not visible

    def reveal_toolpath_up_to(self, move_index: int):
        """Reveal toolpath segments up to and including the given move index.

        Called during playback to progressively show the toolpath as the
        tool dot advances. Respects rapids visibility toggle.
        """
        for i, item in enumerate(self._toolpath_items):
            if i <= move_index:
                # Show unless it's a rapid and rapids are hidden
                if item in self._rapid_items and getattr(self, '_rapids_hidden', False):
                    item.setVisible(False)
                else:
                    item.setVisible(True)

    def show_all_toolpath(self):
        """Reveal all toolpath segments at once (Show All button)."""
        rapids_hidden = getattr(self, '_rapids_hidden', False)
        for item in self._toolpath_items:
            if item in self._rapid_items and rapids_hidden:
                item.setVisible(False)
            else:
                item.setVisible(True)

    def hide_all_toolpath(self):
        """Hide all toolpath segments (Reset button)."""
        for item in self._toolpath_items:
            item.setVisible(False)

    def set_profile_overlay(self, segments: list):
        """Draw profile contour overlay on the graph.

        Args:
            segments: List of (z_coords, x_coords) tuples, each a sub-path
                      in radius/inches coordinates (same format as preview).
        """
        import pyqtgraph as pg
        from PyQt5.QtGui import QColor
        from pyqtgraph.Qt import QtCore as _QtCore

        # Remove any existing overlay items
        for item in getattr(self, '_profile_overlay_items', []):
            self.removeItem(item)
        self._profile_overlay_items = []

        profile_color = QColor(COLORS['graph_profile'])
        profile_color.setAlpha(180)
        profile_pen = pg.mkPen(profile_color, width=2, style=_QtCore.Qt.SolidLine)

        for seg_z, seg_x in segments:
            item = self.plot(seg_z, seg_x, pen=profile_pen)
            item.setZValue(5)  # Above zones, below tool dot
            self._profile_overlay_items.append(item)

    def set_profile_visible(self, visible: bool):
        """Show or hide the profile contour overlay."""
        for item in getattr(self, '_profile_overlay_items', []):
            item.setVisible(visible)

    def clear_toolpath(self):
        """Clear toolpath display (return to preview mode)."""
        self.clear()
        self._setup_crosshair()
        self._tool_dot = None
        self._graph_data = None

    def _get_segment_color(self, segment: ToolpathSegment) -> str:
        """Get color for a toolpath segment based on move type."""
        move_type = segment.move_type.value
        if move_type == 'rapid':
            return COLORS['graph_rapid']
        elif move_type in ('arc_cw', 'arc_ccw'):
            return COLORS['graph_arc']
        else:
            return COLORS['graph_feed']

    def _render_material_polygon(self, coord_arrays: List[tuple]):
        """Update the vector polygon fill items for material display.

        Clears any existing material fill items and renders new ones from
        the provided coordinate arrays. Each tuple in coord_arrays is
        (x_arr, z_arr) representing one component polygon (supports
        MultiPolygon via multiple tuples).

        Uses PlotCurveItem with fillLevel for zoom-independent vector
        rendering — no rasterization, stays sharp at all zoom levels.

        Args:
            coord_arrays: List of (x_ndarray, z_ndarray) tuples, one per
                component polygon. X is in RADIUS, Z in INCHES.
        """
        # Clear existing material fill items
        for item in self._material_fill_items:
            self.removeItem(item)
        self._material_fill_items.clear()

        if not coord_arrays:
            return

        # Material fill brush — semi-transparent steel blue
        material_brush = pg.mkBrush(100, 140, 180, 100)

        for x_arr, z_arr in coord_arrays:
            if len(x_arr) < 3 or len(z_arr) < 3:
                continue

            # In our graph: horizontal axis = Z, vertical axis = X (radius)
            # PlotCurveItem uses (x_data, y_data) where x_data maps to
            # horizontal and y_data maps to vertical.
            # fillLevel fills down to a horizontal baseline in the vertical axis.
            # We set fillLevel to the polygon's minimum X (radius) value so the
            # fill covers the entire polygon area from top to bottom boundary.
            fill_level = float(np.min(x_arr))

            curve = pg.PlotCurveItem(
                z_arr, x_arr,
                pen=pg.mkPen(None),  # Invisible boundary pen
                fillLevel=fill_level,
                brush=material_brush,
            )
            curve.setZValue(-5)  # Behind toolpath but above zone image
            self.addItem(curve)
            self._material_fill_items.append(curve)

    def set_material_state(self, pass_index: int):
        """Display the pre-computed material state after pass_index completes."""
        if not self._graph_data or not self._graph_data.material_states:
            return
        ms = self._graph_data.material_states
        if pass_index < 0 or pass_index >= len(ms.pass_states):
            return
        self._render_material_polygon(ms.pass_states[pass_index].polygons)

    def set_material_to_stock(self):
        """Reset material display to full stock polygon."""
        if not self._graph_data or not self._graph_data.material_states:
            return
        ms = self._graph_data.material_states
        self._render_material_polygon([(ms.stock_x, ms.stock_z)])

    def set_material_to_final(self):
        """Display final material state (all passes applied)."""
        if not self._graph_data or not self._graph_data.material_states:
            return
        ms = self._graph_data.material_states
        coord_arrays = list(zip(ms.final_x, ms.final_z))
        self._render_material_polygon(coord_arrays)

    def render_move_state(self, coord_arrays: List[tuple]):
        """Render pre-computed per-move material state directly.

        Accepts polygon coordinate arrays from move_states[move_index] and
        renders them via _render_material_polygon(), bypassing the
        progress-based logic in set_partial_material() entirely.

        This enables per-move granularity rendering during playback — the
        SimViewerWidget looks up the pre-computed move_states entry for the
        current tool_moves index and passes it here for direct display.

        Args:
            coord_arrays: List of (x_ndarray, z_ndarray) tuples representing
                the material polygon at this specific move. Same format as
                MaterialSimData.move_states[index].
        """
        self._render_material_polygon(coord_arrays)

    def set_partial_material(self, pass_index: int, progress: float):
        """Display partial material removal within a pass.

        progress: 0.0 (pass start) to 1.0 (pass complete)
        For smooth intra-pass rendering during playback.

        At progress <= 0: show previous pass state (or stock if first pass)
        At progress >= 1: show this pass's completed state
        For intermediate values: show previous pass state
        (The SimViewerWidget handles per-move granularity via move_states)
        """
        if not self._graph_data or not self._graph_data.material_states:
            return
        ms = self._graph_data.material_states

        if progress >= 1.0:
            # Pass complete — show completed state
            self.set_material_state(pass_index)
            return

        if progress <= 0.0 or pass_index <= 0:
            # Show previous pass state (or stock if first pass)
            if pass_index <= 0:
                self.set_material_to_stock()
            else:
                self.set_material_state(pass_index - 1)
            return

        # For intermediate progress: show previous pass state
        # (The SimViewerWidget handles per-move granularity via move_states)
        self.set_material_state(pass_index - 1)

    def _draw_zones_as_image(self, data):
        """Rasterize all zone polygons into a single RGBA ImageItem.

        This is the nuclear option — bypasses all pyqtgraph fill rendering
        and just paints colored pixels at the right data coordinates.
        ImageItem is well-tested and scales correctly with zoom/pan.
        """
        import numpy as np
        from PyQt5.QtGui import QColor

        # Determine the data extent from stock rect
        x_min_r, x_max_r, z_min, z_max = data.stock_rect
        if x_max_r <= x_min_r or z_max <= z_min:
            return

        # Image resolution: ~200 pixels per inch of data range
        ppi = 200
        z_range = z_max - z_min
        x_range = x_max_r - x_min_r
        img_w = max(10, int(z_range * ppi))
        img_h = max(10, int(x_range * ppi))

        # Cap at reasonable size
        img_w = min(img_w, 800)
        img_h = min(img_h, 800)

        # Create RGBA image (H x W x 4), initialized transparent
        img = np.zeros((img_h, img_w, 4), dtype=np.uint8)

        # For each zone, rasterize the polygon into the image
        for zone in data.zone_shadings:
            if not zone.z_coords or not zone.x_coords or len(zone.z_coords) < 3:
                continue

            color_hex = COLORS.get(zone.color_key, COLORS['graph_zone_material'])
            color = QColor(color_hex[:7])
            if len(color_hex) == 9:
                alpha = int(color_hex[7:9], 16)
            else:
                alpha = 80

            r, g, b = color.red(), color.green(), color.blue()

            # Convert zone polygon to pixel coordinates
            z_coords = zone.z_coords
            x_coords = [max(0.0, x) for x in zone.x_coords]

            # Map data coords to pixel coords
            # pixel_col = (z - z_min) / z_range * img_w
            # pixel_row = (x - x_min_r) / x_range * img_h
            poly_pixels = []
            for z, x in zip(z_coords, x_coords):
                col = int((z - z_min) / z_range * (img_w - 1))
                row = int((x - x_min_r) / x_range * (img_h - 1))
                col = max(0, min(img_w - 1, col))
                row = max(0, min(img_h - 1, row))
                poly_pixels.append((row, col))

            # Scanline fill the polygon into the image
            self._scanline_fill(img, poly_pixels, r, g, b, alpha)

        # Create ImageItem positioned at the correct data coordinates
        # The graph has invertY(True) — Y increases downward on screen.
        # ImageItem renders with row 0 at the bottom by default.
        # With invertY, we need to flip the image vertically so row 0 (x_min_r)
        # appears at the top of the display (smallest X = top with invertY).
        img = np.flip(img, axis=0)

        img_item = pg.ImageItem(image=img)
        img_item.setRect(z_min, x_min_r, z_range, x_range)
        img_item.setZValue(-10)  # Behind everything else
        self.addItem(img_item)

    @staticmethod
    def _scanline_fill(img, poly_pixels, r, g, b, a):
        """Simple scanline polygon fill into an RGBA numpy array.

        poly_pixels: list of (row, col) tuples forming a closed polygon.
        """
        import numpy as np

        if len(poly_pixels) < 3:
            return

        h, w = img.shape[:2]

        # Find row extent
        rows = [p[0] for p in poly_pixels]
        min_row = max(0, min(rows))
        max_row = min(h - 1, max(rows))

        n = len(poly_pixels)

        for row in range(min_row, max_row + 1):
            # Find all X intersections with polygon edges at this row
            intersections = []
            for i in range(n):
                j = (i + 1) % n
                r1, c1 = poly_pixels[i]
                r2, c2 = poly_pixels[j]

                # Check if this edge crosses the current row
                if (r1 <= row < r2) or (r2 <= row < r1):
                    # Interpolate column at this row
                    if r2 != r1:
                        t = (row - r1) / (r2 - r1)
                        col = c1 + t * (c2 - c1)
                        intersections.append(int(col))

            # Sort intersections and fill between pairs
            intersections.sort()
            for k in range(0, len(intersections) - 1, 2):
                col_start = max(0, intersections[k])
                col_end = min(w - 1, intersections[k + 1])
                if col_start <= col_end:
                    # Alpha blend
                    img[row, col_start:col_end + 1, 0] = r
                    img[row, col_start:col_end + 1, 1] = g
                    img[row, col_start:col_end + 1, 2] = b
                    img[row, col_start:col_end + 1, 3] = a
