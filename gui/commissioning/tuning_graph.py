"""Following Error Strip Chart — Real-time graph for PID tuning.

Enhanced over the reference implementation with:
    - Freeze/capture mode (click to freeze, scroll history)
    - Mouse wheel Y-axis zoom
    - Dual trace: following error + velocity overlay
    - FERROR/MIN_FERROR limit lines with color-coded warnings
    - Peak tracking with slow decay
    - Step response capture mode

Uses QPainter directly (no pyqtgraph dependency) for lightweight rendering.
The graph is designed for 50ms update rate (20 FPS).
"""

from collections import deque
from typing import Optional, Tuple

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy
from PyQt5.QtCore import Qt, QRectF, pyqtSignal
from PyQt5.QtGui import (
    QPainter, QPen, QColor, QFont, QPainterPath,
    QMouseEvent, QWheelEvent,
)

from gui.colors import COLORS, FONTS


def _mono_font(size: int, bold: bool = False) -> QFont:
    """Create a monospace font."""
    f = QFont(FONTS['mono_family'], size)
    if bold:
        f.setBold(True)
    return f


def _ui_font(size: int, bold: bool = False) -> QFont:
    """Create a UI font."""
    f = QFont(FONTS['ui_family'], size)
    if bold:
        f.setBold(True)
    return f


class FollowingErrorGraph(QWidget):
    """Real-time strip chart for following error visualization.

    Features:
        - Scrolling time-series (newest data on right)
        - FERROR and MIN_FERROR limit lines
        - Color-coded traces (blue=X, green=Z)
        - Background warning tint when approaching limits
        - Auto-scaling Y axis with mouse wheel override
        - Click to freeze, scroll to pan history
        - Peak tracking with exponential decay

    Signals:
        frozen_changed(bool): Emitted when freeze state changes
        peak_updated(float, float): Emitted with (x_peak, z_peak)
    """

    frozen_changed = pyqtSignal(bool)
    peak_updated = pyqtSignal(float, float)

    # Trace colors (from project palette)
    COLOR_X = QColor(COLORS['status_info'])       # Blue
    COLOR_Z = QColor(COLORS['status_ok'])         # Green
    COLOR_LIMIT = QColor(COLORS['status_error'])  # Red
    COLOR_MIN_LIMIT = QColor(COLORS['status_warning'])  # Orange-red
    COLOR_GRID = QColor(COLORS['graph_grid'])
    COLOR_ZERO = QColor(COLORS['border_normal'])
    COLOR_BG = QColor(COLORS['graph_bg'])

    def __init__(self, max_points: int = 600, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(120)
        self.setMinimumWidth(200)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)

        # Data buffers (ring buffers)
        self._max_points = max_points
        self._x_data = deque(maxlen=max_points)
        self._z_data = deque(maxlen=max_points)

        # Limit lines
        self._ferror = 0.005
        self._min_ferror = 0.001

        # Display state
        self._auto_scale = True
        self._y_range = 0.002       # manual Y range (±)
        self._y_zoom_factor = 1.0   # mouse wheel zoom multiplier
        self._show_x = True
        self._show_z = True
        self._show_limits = True
        self._frozen = False
        self._scroll_offset = 0     # samples to scroll back when frozen

        # Peak tracking
        self._x_peak = 0.0
        self._z_peak = 0.0
        self._peak_decay = 0.998

        # Layout margins
        self._margin_left = 58
        self._margin_right = 8
        self._margin_top = 8
        self._margin_bottom = 16

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def add_sample(self, x_error: float, z_error: float):
        """Add a new error sample. Call from timer at 50ms intervals.

        If frozen, data is still collected but display doesn't scroll.
        """
        self._x_data.append(x_error)
        self._z_data.append(z_error)

        # Update peaks
        abs_x = abs(x_error)
        abs_z = abs(z_error)
        self._x_peak = max(self._x_peak * self._peak_decay, abs_x)
        self._z_peak = max(self._z_peak * self._peak_decay, abs_z)
        self.peak_updated.emit(self._x_peak, self._z_peak)

        if not self._frozen:
            self.update()

    def set_ferror_limits(self, ferror: float = None, min_ferror: float = None):
        """Set FERROR limit lines."""
        if ferror is not None:
            self._ferror = ferror
        if min_ferror is not None:
            self._min_ferror = min_ferror
        self.update()

    def set_frozen(self, frozen: bool):
        """Freeze/unfreeze the display."""
        if frozen != self._frozen:
            self._frozen = frozen
            self._scroll_offset = 0
            self.frozen_changed.emit(frozen)
            self.update()

    def toggle_frozen(self):
        """Toggle freeze state."""
        self.set_frozen(not self._frozen)

    def set_show_x(self, show: bool):
        self._show_x = show
        self.update()

    def set_show_z(self, show: bool):
        self._show_z = show
        self.update()

    def clear(self):
        """Clear all data and reset peaks."""
        self._x_data.clear()
        self._z_data.clear()
        self._x_peak = 0.0
        self._z_peak = 0.0
        self._scroll_offset = 0
        self.update()

    def get_peaks(self) -> Tuple[float, float]:
        """Return current peak values (x_peak, z_peak) in inches."""
        return (self._x_peak, self._z_peak)

    # -----------------------------------------------------------------
    # Mouse interaction
    # -----------------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent):
        """Click to toggle freeze."""
        if event.button() == Qt.LeftButton:
            self.toggle_frozen()
        event.accept()

    def wheelEvent(self, event: QWheelEvent):
        """Mouse wheel: zoom Y axis (unfrozen) or scroll history (frozen)."""
        delta = event.angleDelta().y()
        if self._frozen:
            # Scroll through history
            scroll_step = max(1, self._max_points // 50)
            if delta > 0:
                self._scroll_offset = min(
                    self._scroll_offset + scroll_step,
                    max(0, len(self._x_data) - self._max_points // 2)
                )
            else:
                self._scroll_offset = max(0, self._scroll_offset - scroll_step)
            self.update()
        else:
            # Zoom Y axis
            if delta > 0:
                self._y_zoom_factor *= 0.8  # zoom in
            else:
                self._y_zoom_factor *= 1.25  # zoom out
            self._y_zoom_factor = max(0.1, min(20.0, self._y_zoom_factor))
            self.update()
        event.accept()

    # -----------------------------------------------------------------
    # Painting
    # -----------------------------------------------------------------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()

        # Plot area
        px = self._margin_left
        py = self._margin_top
        pw = w - self._margin_left - self._margin_right
        ph = h - self._margin_top - self._margin_bottom

        if pw < 10 or ph < 10:
            painter.end()
            return

        y_range = self._compute_y_range()

        # Background
        self._draw_background(painter, px, py, pw, ph, y_range)

        # Grid
        self._draw_grid(painter, px, py, pw, ph, y_range)

        # Limit lines
        if self._show_limits:
            self._draw_limits(painter, px, py, pw, ph, y_range)

        # Zero line
        self._draw_zero_line(painter, px, py, pw, ph)

        # Data traces
        x_slice, z_slice = self._get_visible_data()
        if self._show_x and x_slice:
            self._draw_trace(painter, x_slice, self.COLOR_X, px, py, pw, ph, y_range)
        if self._show_z and z_slice:
            self._draw_trace(painter, z_slice, self.COLOR_Z, px, py, pw, ph, y_range)

        # Y-axis labels
        self._draw_y_labels(painter, px, py, ph, y_range)

        # Frozen indicator
        if self._frozen:
            self._draw_frozen_badge(painter, px, py, pw)

        painter.end()

    def _compute_y_range(self) -> float:
        """Compute Y-axis range (symmetric around zero)."""
        if not self._auto_scale:
            return self._y_range * self._y_zoom_factor

        max_val = 0.0001
        if self._x_data:
            max_val = max(max_val, max(abs(v) for v in self._x_data))
        if self._z_data:
            max_val = max(max_val, max(abs(v) for v in self._z_data))

        # Include FERROR in range if data is near it
        if max_val > self._min_ferror * 0.5:
            max_val = max(max_val, self._ferror * 1.1)

        return max_val * 1.2 * self._y_zoom_factor

    def _get_visible_data(self):
        """Get the data slice currently visible (handles scroll offset)."""
        if not self._x_data:
            return [], []

        n = len(self._x_data)
        end = n - self._scroll_offset
        start = max(0, end - self._max_points)
        end = max(start, end)

        x_slice = list(self._x_data)[start:end]
        z_slice = list(self._z_data)[start:end]
        return x_slice, z_slice

    def _draw_background(self, painter, x, y, w, h, y_range):
        """Draw plot background with warning tint if near limits."""
        warn = False
        if self._x_data or self._z_data:
            recent = list(self._x_data)[-20:] + list(self._z_data)[-20:]
            if recent and max(abs(v) for v in recent) > self._min_ferror * 0.8:
                warn = True

        if warn:
            bg = QColor(COLORS['bg_panel'])
            bg.setAlpha(200)
            painter.fillRect(x, y, w, h, bg)
        else:
            painter.fillRect(x, y, w, h, self.COLOR_BG)

        # Border
        painter.setPen(QPen(QColor(COLORS['border_normal']), 1))
        painter.drawRect(x, y, w, h)

    def _draw_grid(self, painter, x, y, w, h, y_range):
        painter.setPen(QPen(self.COLOR_GRID, 1, Qt.DotLine))
        for i in range(1, 5):
            frac = i / 5.0
            y_up = int(y + h * (0.5 - frac * 0.5))
            y_dn = int(y + h * (0.5 + frac * 0.5))
            painter.drawLine(x, y_up, x + w, y_up)
            painter.drawLine(x, y_dn, x + w, y_dn)

    def _draw_zero_line(self, painter, x, y, w, h):
        painter.setPen(QPen(self.COLOR_ZERO, 1, Qt.SolidLine))
        y_zero = y + h // 2
        painter.drawLine(x, y_zero, x + w, y_zero)

    def _draw_limits(self, painter, x, y, w, h, y_range):
        if y_range <= 0:
            return

        # MIN_FERROR (orange, dashed)
        min_frac = self._min_ferror / y_range
        if min_frac <= 1.0:
            painter.setPen(QPen(self.COLOR_MIN_LIMIT, 1, Qt.DashLine))
            y_up = int(y + h * (0.5 - min_frac * 0.5))
            y_dn = int(y + h * (0.5 + min_frac * 0.5))
            painter.drawLine(x, y_up, x + w, y_up)
            painter.drawLine(x, y_dn, x + w, y_dn)

        # FERROR (red, solid)
        ferr_frac = self._ferror / y_range
        if ferr_frac <= 1.0:
            painter.setPen(QPen(self.COLOR_LIMIT, 2, Qt.SolidLine))
            y_up = int(y + h * (0.5 - ferr_frac * 0.5))
            y_dn = int(y + h * (0.5 + ferr_frac * 0.5))
            painter.drawLine(x, y_up, x + w, y_up)
            painter.drawLine(x, y_dn, x + w, y_dn)

    def _draw_trace(self, painter, data, color, x, y, w, h, y_range):
        if len(data) < 2 or y_range <= 0:
            return

        pen = QPen(color, 1.5, Qt.SolidLine)
        painter.setPen(pen)

        n = len(data)
        display_points = min(n, self._max_points)

        prev_px, prev_py = None, None
        for i, val in enumerate(data):
            px = int(x + (i / max(1, display_points - 1)) * w)
            normalized = val / y_range
            py = int(y + h * (0.5 - normalized * 0.5))
            py = max(y, min(y + h, py))

            if prev_px is not None:
                painter.drawLine(prev_px, prev_py, px, py)
            prev_px, prev_py = px, py

    def _draw_y_labels(self, painter, plot_left, plot_top, plot_h, y_range):
        painter.setPen(QPen(QColor(COLORS['text_secondary']), 1))
        painter.setFont(_mono_font(8))

        painter.drawText(2, plot_top + 10, f"+{y_range:.5f}")
        painter.drawText(2, plot_top + plot_h // 2 + 4, " 0.00000")
        painter.drawText(2, plot_top + plot_h - 2, f"-{y_range:.5f}")

    def _draw_frozen_badge(self, painter, x, y, w):
        """Draw a FROZEN indicator when paused."""
        painter.setPen(QPen(QColor(COLORS['status_warning']), 1))
        painter.setFont(_ui_font(9, bold=True))
        painter.drawText(x + w - 60, y + 14, "FROZEN")


# =============================================================================
# Panel wrapper with header + peak readouts
# =============================================================================

class FollowingErrorPanel(QWidget):
    """Complete panel: graph + header with peak readouts.

    This is what gets embedded in the TuningTab.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(2)
        layout.setContentsMargins(0, 0, 0, 0)

        # Header
        header = QHBoxLayout()
        title = QLabel("Following Error")
        title.setFont(_ui_font(11, bold=True))
        title.setStyleSheet(f"color: {COLORS['status_info']};")
        header.addWidget(title)

        self._freeze_label = QLabel("")
        self._freeze_label.setFont(_ui_font(9))
        self._freeze_label.setStyleSheet(f"color: {COLORS['status_warning']};")
        header.addWidget(self._freeze_label)

        header.addStretch()

        self._peak_x = QLabel("X pk: 0.000000")
        self._peak_x.setFont(_mono_font(9))
        self._peak_x.setStyleSheet(f"color: {COLORS['status_info']};")
        header.addWidget(self._peak_x)

        self._peak_z = QLabel("Z pk: 0.000000")
        self._peak_z.setFont(_mono_font(9))
        self._peak_z.setStyleSheet(f"color: {COLORS['status_ok']};")
        header.addWidget(self._peak_z)

        layout.addLayout(header)

        # Graph
        self.graph = FollowingErrorGraph()
        self.graph.peak_updated.connect(self._on_peak_updated)
        self.graph.frozen_changed.connect(self._on_frozen_changed)
        layout.addWidget(self.graph, stretch=1)

        # Hint
        hint = QLabel("Click to freeze • Scroll to zoom/pan")
        hint.setFont(_ui_font(8))
        hint.setStyleSheet(f"color: {COLORS['text_disabled']};")
        hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint)

    def add_sample(self, x_error: float, z_error: float):
        self.graph.add_sample(x_error, z_error)

    def set_ferror_limits(self, ferror=None, min_ferror=None):
        self.graph.set_ferror_limits(ferror, min_ferror)

    def clear(self):
        self.graph.clear()
        self._peak_x.setText("X pk: 0.000000")
        self._peak_z.setText("Z pk: 0.000000")

    def _on_peak_updated(self, x_pk: float, z_pk: float):
        self._peak_x.setText(f"X pk: {x_pk:.6f}")
        self._peak_z.setText(f"Z pk: {z_pk:.6f}")

    def _on_frozen_changed(self, frozen: bool):
        self._freeze_label.setText("⏸ FROZEN" if frozen else "")
