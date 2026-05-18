"""Real-time tool position graph widget for manual mode.

Shows the tool's current XZ position as a bright dot with a trailing
path of recent movement. Provides spatial awareness during manual jogging.

Reusable — could also be embedded in the Run tab for live program tracking.

Coordinates: Plot X-axis = Z (horizontal), Plot Y-axis = X radius.
Axis labels display diameter (matching DRO/G-code convention).
"""

from collections import deque

import pyqtgraph as pg
from pyqtgraph.Qt import QtCore

from gui.colors import COLORS
from gui.components.graph_widget import DiameterAxisItem, PrecisionZAxisItem
from hal.constants import X_MAX_LIMIT, Z_MAX_LIMIT


# Max trail points (at 10Hz polling = 50 seconds of history)
TRAIL_MAX_POINTS = 500


class PositionGraphWidget(pg.PlotWidget):
    """Real-time tool position graph for manual mode.

    Features:
        - Tool dot (large, bright white) at current XZ position
        - Position trail (green line of recent positions)
        - Grid with labeled axes (X diameter vertical, Z horizontal)
        - Crosshair with coordinate readout
        - Machine travel envelope (dashed rectangle)
        - Double-click to auto-fit view

    Public API:
        update_position(x_diameter, z) — call each poll cycle
        clear_trail() — reset position history
        fit_to_position(x_diameter, z, margin) — center view on position
    """

    coordinate_changed = QtCore.pyqtSignal(float, float)

    def __init__(self, parent=None):
        x_axis = DiameterAxisItem(orientation='left')
        z_axis = PrecisionZAxisItem(orientation='bottom')

        super().__init__(
            parent=parent,
            axisItems={'left': x_axis, 'bottom': z_axis},
            background=COLORS['graph_bg'],
        )

        self._trail_x: deque = deque(maxlen=TRAIL_MAX_POINTS)
        self._trail_z: deque = deque(maxlen=TRAIL_MAX_POINTS)

        self._setup_plot()
        self._setup_crosshair()
        self._setup_items()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _setup_plot(self):
        """Configure plot area — lathe operator's view."""
        plot_item = self.getPlotItem()
        plot_item.setAspectLocked(True, ratio=1)
        plot_item.showGrid(x=True, y=True, alpha=0.3)
        plot_item.setLabel('left', 'X (Diameter)', units='in')
        plot_item.setLabel('bottom', 'Z', units='in')

        # Invert Y so X+ is at bottom (operator POV)
        vb = self.getViewBox()
        vb.invertY(True)
        vb.setMouseEnabled(x=True, y=True)

        # Machine travel envelope
        x_max_r = X_MAX_LIMIT / 2.0
        envelope_pen = pg.mkPen(COLORS['border_normal'], width=1, style=QtCore.Qt.DashLine)
        env_z = [0, Z_MAX_LIMIT, Z_MAX_LIMIT, 0, 0]
        env_x = [0, 0, x_max_r, x_max_r, 0]
        self.plot(env_z, env_x, pen=envelope_pen)

        # Centerline (X=0 / spindle axis)
        cl_pen = pg.mkPen('#FFFFFF30', width=1, style=QtCore.Qt.DashDotLine)
        self.plot([0, Z_MAX_LIMIT], [0, 0], pen=cl_pen)

    def _setup_crosshair(self):
        """Crosshair lines for coordinate readout."""
        self._vline = pg.InfiniteLine(angle=90, movable=False,
                                      pen=pg.mkPen(COLORS['graph_crosshair'], width=1))
        self._hline = pg.InfiniteLine(angle=0, movable=False,
                                      pen=pg.mkPen(COLORS['graph_crosshair'], width=1))
        self.addItem(self._vline, ignoreBounds=True)
        self.addItem(self._hline, ignoreBounds=True)
        self.scene().sigMouseMoved.connect(self._on_mouse_moved)

    def _on_mouse_moved(self, pos):
        """Update crosshair and emit coordinates."""
        if self.sceneBoundingRect().contains(pos):
            pt = self.getViewBox().mapSceneToView(pos)
            self._vline.setPos(pt.x())
            self._hline.setPos(pt.y())
            self.coordinate_changed.emit(pt.y(), pt.x())  # x_radius, z

    def _setup_items(self):
        """Create the tool dot and trail plot items."""
        self._trail_item = self.plot([], [], pen=pg.mkPen(
            COLORS['graph_feed'], width=2, style=QtCore.Qt.SolidLine
        ))
        self._tool_dot = pg.ScatterPlotItem(
            size=14,
            brush=pg.mkBrush(COLORS['graph_tool_dot']),
            pen=pg.mkPen('#000000', width=1),
        )
        self.addItem(self._tool_dot)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def mouseDoubleClickEvent(self, event):
        """Double-click to auto-fit view."""
        self.getViewBox().autoRange()
        event.accept()

    def update_position(self, x_diameter: float, z: float):
        """Update tool position — call each poll cycle.

        Args:
            x_diameter: Current X position in DIAMETER (inches)
            z: Current Z position (inches)
        """
        x_radius = x_diameter / 2.0

        # Append to trail (skip if same as last point)
        if (not self._trail_x or
                abs(self._trail_x[-1] - x_radius) > 0.00005 or
                abs(self._trail_z[-1] - z) > 0.00005):
            self._trail_x.append(x_radius)
            self._trail_z.append(z)

        # Update trail line
        if len(self._trail_z) > 1:
            self._trail_item.setData(list(self._trail_z), list(self._trail_x))

        # Update tool dot
        self._tool_dot.setData([z], [x_radius])

    def clear_trail(self):
        """Clear the position trail."""
        self._trail_x.clear()
        self._trail_z.clear()
        self._trail_item.setData([], [])

    def fit_to_position(self, x_diameter: float, z: float, margin: float = 1.0):
        """Center the view on the current position with margin."""
        x_radius = x_diameter / 2.0
        vb = self.getViewBox()
        vb.setRange(
            xRange=(z - margin, z + margin),
            yRange=(x_radius - margin / 2, x_radius + margin / 2),
            padding=0.1,
        )
