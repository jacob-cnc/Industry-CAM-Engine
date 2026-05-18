"""
Following Error Strip Chart — Real-time graph for PID tuning.

Displays a scrolling time-series plot of following error for X and Z axes.
Shows FERROR and MIN_FERROR limit lines for visual reference.
Highlights when error approaches or exceeds limits.

Usage:
    graph = FollowingErrorGraph()
    graph.set_ferror_limits(ferror=0.005, min_ferror=0.001)
    # Call from timer:
    graph.add_sample(x_error, z_error)
"""

from collections import deque

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy
from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QPainter, QPen, QColor, QFont, QLinearGradient, QPainterPath

# Import theme if available, otherwise use fallback colors
try:
    from theme import COLORS, mono_font, ui_font
except ImportError:
    COLORS = {
        'bg_dark': '#0f1318',
        'bg_mid': '#1a2028',
        'bg_light': '#2a3040',
        'border': '#3a4555',
        'text': '#e8eaed',
        'text_dim': '#6b7b8f',
        'text_secondary': '#9aa8b8',
        'accent': '#e84c3d',
        'accent_blue': '#4a90d9',
        'accent_blue_lt': '#7ab3e8',
        'accent_green': '#8fbc6a',
        'accent_green_lt': '#b8d89a',
        'accent_orange': '#e8a838',
        'accent_yellow': '#f0c040',
        'dro_bg': '#0a0e12',
        'dro_text': '#e8eaed',
    }

    def mono_font(size, weight=None):
        f = QFont("Consolas", size)
        if weight:
            f.setWeight(weight)
        return f

    def ui_font(size, weight=None):
        f = QFont("Segoe UI", size)
        if weight:
            f.setWeight(weight)
        return f


class FollowingErrorGraph(QWidget):
    """Real-time strip chart showing following error for X and Z axes.

    Features:
    - Scrolling time-series display (newest data on right)
    - Configurable FERROR and MIN_FERROR limit lines
    - Color-coded traces (blue = X, green = Z)
    - Background color shifts when approaching limits
    - Auto-scaling Y axis with manual override option
    - Grid lines for easy reading
    """

    # Trace colors
    COLOR_X = QColor(74, 144, 217)       # Blue
    COLOR_Z = QColor(143, 188, 106)      # Green
    COLOR_LIMIT = QColor(232, 76, 61)    # Red
    COLOR_MIN_LIMIT = QColor(232, 168, 56)  # Orange
    COLOR_GRID = QColor(58, 69, 85, 80)  # Subtle grid
    COLOR_ZERO = QColor(100, 120, 140, 120)  # Zero line
    COLOR_BG = QColor(10, 14, 18)        # Dark background
    COLOR_WARN_BG = QColor(60, 40, 10, 40)  # Warning tint

    def __init__(self, max_points=500, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(140)
        self.setMinimumWidth(300)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Data buffers
        self._max_points = max_points
        self._x_data = deque(maxlen=max_points)
        self._z_data = deque(maxlen=max_points)

        # Limit lines (from INI FERROR / MIN_FERROR)
        self._ferror = 0.005       # Max following error at full speed
        self._min_ferror = 0.001   # Max following error at low speed

        # Display options
        self._auto_scale = True
        self._y_range = 0.002      # Manual Y range (±this value)
        self._show_x = True
        self._show_z = True
        self._show_limits = True
        self._show_grid = True

        # Peak tracking
        self._x_peak = 0.0
        self._z_peak = 0.0
        self._peak_decay = 0.999   # Slow decay for peak indicator

        # Margins for axis labels
        self._margin_left = 60
        self._margin_right = 10
        self._margin_top = 10
        self._margin_bottom = 20

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def add_sample(self, x_error, z_error):
        """Add a new error sample pair. Call from timer at 50-100ms.

        Args:
            x_error: X axis following error in inches
            z_error: Z axis following error in inches
        """
        self._x_data.append(x_error)
        self._z_data.append(z_error)

        # Update peaks
        abs_x = abs(x_error)
        abs_z = abs(z_error)
        self._x_peak = max(self._x_peak * self._peak_decay, abs_x)
        self._z_peak = max(self._z_peak * self._peak_decay, abs_z)

        self.update()  # Trigger repaint

    def set_ferror_limits(self, ferror=None, min_ferror=None):
        """Set the FERROR limit lines.

        Args:
            ferror: Max following error at full speed (inches)
            min_ferror: Max following error at low speed (inches)
        """
        if ferror is not None:
            self._ferror = ferror
        if min_ferror is not None:
            self._min_ferror = min_ferror
        self.update()

    def set_auto_scale(self, enabled):
        """Enable/disable auto-scaling of Y axis."""
        self._auto_scale = enabled
        self.update()

    def set_y_range(self, y_range):
        """Set manual Y range (±y_range). Only used when auto_scale is False."""
        self._y_range = y_range
        self.update()

    def set_show_x(self, show):
        """Show/hide X axis trace."""
        self._show_x = show
        self.update()

    def set_show_z(self, show):
        """Show/hide Z axis trace."""
        self._show_z = show
        self.update()

    def clear(self):
        """Clear all data."""
        self._x_data.clear()
        self._z_data.clear()
        self._x_peak = 0.0
        self._z_peak = 0.0
        self.update()

    def get_peaks(self):
        """Return current peak values.

        Returns:
            Tuple (x_peak, z_peak) in inches
        """
        return (self._x_peak, self._z_peak)

    # -----------------------------------------------------------------
    # Painting
    # -----------------------------------------------------------------

    def paintEvent(self, event):
        """Render the strip chart."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()

        # Plot area
        plot_left = self._margin_left
        plot_right = w - self._margin_right
        plot_top = self._margin_top
        plot_bottom = h - self._margin_bottom
        plot_w = plot_right - plot_left
        plot_h = plot_bottom - plot_top

        if plot_w < 10 or plot_h < 10:
            return

        # Determine Y range
        y_range = self._compute_y_range()

        # Background
        self._draw_background(painter, plot_left, plot_top, plot_w, plot_h, y_range)

        # Grid
        if self._show_grid:
            self._draw_grid(painter, plot_left, plot_top, plot_w, plot_h, y_range)

        # Limit lines
        if self._show_limits:
            self._draw_limits(painter, plot_left, plot_top, plot_w, plot_h, y_range)

        # Zero line
        self._draw_zero_line(painter, plot_left, plot_top, plot_w, plot_h, y_range)

        # Data traces
        if self._show_x and self._x_data:
            self._draw_trace(painter, self._x_data, self.COLOR_X,
                             plot_left, plot_top, plot_w, plot_h, y_range)
        if self._show_z and self._z_data:
            self._draw_trace(painter, self._z_data, self.COLOR_Z,
                             plot_left, plot_top, plot_w, plot_h, y_range)

        # Y-axis labels
        self._draw_y_labels(painter, plot_left, plot_top, plot_h, y_range)

        # Legend
        self._draw_legend(painter, plot_left, plot_top)

        painter.end()

    def _compute_y_range(self):
        """Compute the Y-axis range (symmetric around zero)."""
        if not self._auto_scale:
            return self._y_range

        # Auto-scale: find max absolute value in data, add 20% headroom
        max_val = 0.0001  # minimum range to avoid division by zero
        if self._x_data:
            max_val = max(max_val, max(abs(v) for v in self._x_data))
        if self._z_data:
            max_val = max(max_val, max(abs(v) for v in self._z_data))

        # Include FERROR limit in range if data is near it
        if max_val > self._min_ferror * 0.5:
            max_val = max(max_val, self._ferror * 1.1)

        return max_val * 1.2

    def _draw_background(self, painter, x, y, w, h, y_range):
        """Draw plot background with warning tint if near limits."""
        # Check if any recent data is near the limit
        warn = False
        if self._x_data or self._z_data:
            recent_x = list(self._x_data)[-20:] if self._x_data else []
            recent_z = list(self._z_data)[-20:] if self._z_data else []
            all_recent = recent_x + recent_z
            if all_recent and max(abs(v) for v in all_recent) > self._min_ferror * 0.8:
                warn = True

        if warn:
            painter.fillRect(x, y, w, h, self.COLOR_WARN_BG)
        else:
            painter.fillRect(x, y, w, h, self.COLOR_BG)

        # Border
        painter.setPen(QPen(QColor(COLORS['border']), 1))
        painter.drawRect(x, y, w, h)

    def _draw_grid(self, painter, x, y, w, h, y_range):
        """Draw horizontal grid lines."""
        painter.setPen(QPen(self.COLOR_GRID, 1, Qt.DotLine))

        # Draw 4 grid lines above and below zero
        for i in range(1, 5):
            frac = i / 5.0
            y_pos_upper = y + h * (0.5 - frac * 0.5)
            y_pos_lower = y + h * (0.5 + frac * 0.5)
            painter.drawLine(x, int(y_pos_upper), x + w, int(y_pos_upper))
            painter.drawLine(x, int(y_pos_lower), x + w, int(y_pos_lower))

    def _draw_zero_line(self, painter, x, y, w, h, y_range):
        """Draw the zero reference line."""
        painter.setPen(QPen(self.COLOR_ZERO, 1, Qt.SolidLine))
        y_zero = y + h // 2
        painter.drawLine(x, y_zero, x + w, y_zero)

    def _draw_limits(self, painter, x, y, w, h, y_range):
        """Draw FERROR and MIN_FERROR limit lines."""
        if y_range <= 0:
            return

        # MIN_FERROR (orange, dashed)
        min_frac = self._min_ferror / y_range
        if min_frac <= 1.0:
            pen = QPen(self.COLOR_MIN_LIMIT, 1, Qt.DashLine)
            painter.setPen(pen)
            y_upper = int(y + h * (0.5 - min_frac * 0.5))
            y_lower = int(y + h * (0.5 + min_frac * 0.5))
            painter.drawLine(x, y_upper, x + w, y_upper)
            painter.drawLine(x, y_lower, x + w, y_lower)

        # FERROR (red, solid)
        ferr_frac = self._ferror / y_range
        if ferr_frac <= 1.0:
            pen = QPen(self.COLOR_LIMIT, 2, Qt.SolidLine)
            painter.setPen(pen)
            y_upper = int(y + h * (0.5 - ferr_frac * 0.5))
            y_lower = int(y + h * (0.5 + ferr_frac * 0.5))
            painter.drawLine(x, y_upper, x + w, y_upper)
            painter.drawLine(x, y_lower, x + w, y_lower)

    def _draw_trace(self, painter, data, color, x, y, w, h, y_range):
        """Draw a data trace as a connected line."""
        if len(data) < 2 or y_range <= 0:
            return

        pen = QPen(color, 1.5, Qt.SolidLine)
        painter.setPen(pen)

        n = len(data)
        points = []
        for i, val in enumerate(data):
            px = x + (i / max(1, self._max_points - 1)) * w
            # Map value to Y: 0 is center, +y_range is top, -y_range is bottom
            normalized = val / y_range  # -1 to +1
            py = y + h * (0.5 - normalized * 0.5)
            # Clamp to plot area
            py = max(y, min(y + h, py))
            points.append((int(px), int(py)))

        # Draw connected line segments
        for i in range(len(points) - 1):
            painter.drawLine(points[i][0], points[i][1],
                             points[i + 1][0], points[i + 1][1])

    def _draw_y_labels(self, painter, plot_left, plot_top, plot_h, y_range):
        """Draw Y-axis value labels."""
        painter.setPen(QPen(QColor(COLORS['text_dim']), 1))
        painter.setFont(mono_font(8))

        # Top label (+y_range)
        painter.drawText(2, plot_top + 10, f"+{y_range:.5f}")
        # Center label (0)
        painter.drawText(2, plot_top + plot_h // 2 + 4, " 0.00000")
        # Bottom label (-y_range)
        painter.drawText(2, plot_top + plot_h - 2, f"-{y_range:.5f}")

        # FERROR label
        if self._ferror / y_range <= 1.0:
            ferr_y = int(plot_top + plot_h * (0.5 - (self._ferror / y_range) * 0.5))
            painter.setPen(QPen(self.COLOR_LIMIT, 1))
            painter.drawText(2, ferr_y - 2, f"FERR")

    def _draw_legend(self, painter, plot_left, plot_top):
        """Draw a small legend in the top-right corner."""
        painter.setFont(mono_font(9))

        # X axis legend
        if self._show_x:
            painter.setPen(QPen(self.COLOR_X, 2))
            lx = plot_left + 10
            ly = plot_top + 12
            painter.drawLine(lx, ly, lx + 15, ly)
            painter.setPen(QPen(QColor(COLORS['text']), 1))
            painter.drawText(lx + 18, ly + 4, f"X: {self._x_peak:.6f}")

        # Z axis legend
        if self._show_z:
            painter.setPen(QPen(self.COLOR_Z, 2))
            lx = plot_left + 10
            ly = plot_top + 26
            painter.drawLine(lx, ly, lx + 15, ly)
            painter.setPen(QPen(QColor(COLORS['text']), 1))
            painter.drawText(lx + 18, ly + 4, f"Z: {self._z_peak:.6f}")


class FollowingErrorPanel(QWidget):
    """Complete panel with graph + controls for the tuning tab.

    Wraps FollowingErrorGraph with axis toggle buttons and peak readouts.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(0, 0, 0, 0)

        # Header row
        header = QHBoxLayout()
        title = QLabel("Following Error")
        title.setFont(ui_font(11, QFont.Bold))
        title.setStyleSheet(f"color: {COLORS['accent_blue_lt']};")
        header.addWidget(title)
        header.addStretch()

        # Peak readouts
        self._peak_x_label = QLabel("X pk: 0.000000")
        self._peak_x_label.setFont(mono_font(9))
        self._peak_x_label.setStyleSheet(f"color: {COLORS['accent_blue_lt']};")
        header.addWidget(self._peak_x_label)

        self._peak_z_label = QLabel("Z pk: 0.000000")
        self._peak_z_label.setFont(mono_font(9))
        self._peak_z_label.setStyleSheet(f"color: {COLORS['accent_green']};")
        header.addWidget(self._peak_z_label)

        layout.addLayout(header)

        # Graph
        self.graph = FollowingErrorGraph()
        layout.addWidget(self.graph, stretch=1)

    def add_sample(self, x_error, z_error):
        """Add sample and update peak labels."""
        self.graph.add_sample(x_error, z_error)
        x_pk, z_pk = self.graph.get_peaks()
        self._peak_x_label.setText(f"X pk: {x_pk:.6f}")
        self._peak_z_label.setText(f"Z pk: {z_pk:.6f}")

    def set_ferror_limits(self, ferror=None, min_ferror=None):
        """Pass through to graph."""
        self.graph.set_ferror_limits(ferror, min_ferror)

    def clear(self):
        """Clear graph and reset peaks."""
        self.graph.clear()
        self._peak_x_label.setText("X pk: 0.000000")
        self._peak_z_label.setText("Z pk: 0.000000")
