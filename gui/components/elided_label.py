"""ElidedLabel — a QLabel that never forces its parent wider than a set minimum.

A plain QLabel reports its full text width as its minimum size, so a long
dynamic string (e.g. LinuxCNC's full active G-code list or an hm2 error
message) silently widens the whole main window past the screen edge.

ElidedLabel prefers its full text width when space is available, but can
shrink down to ``min_width``; any text that doesn't fit is drawn with a
trailing "…" and the full text is always available as a tooltip.
"""

from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QPainter
from PyQt5.QtWidgets import QLabel, QSizePolicy, QStyle, QStyleOption


class ElidedLabel(QLabel):
    """Single-line QLabel that elides overflowing text instead of growing."""

    def __init__(self, text: str = "", min_width: int = 60, parent=None):
        super().__init__(text, parent)
        self._min_width = min_width
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self.setToolTip(text)

    def setText(self, text: str) -> None:  # noqa: N802 (Qt naming)
        super().setText(text)
        self.setToolTip(text)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        hint = super().minimumSizeHint()
        return QSize(min(hint.width(), self._min_width), hint.height())

    def paintEvent(self, event) -> None:  # noqa: N802
        # Draw the stylesheet background/border, then the elided text inside
        # the contents rect (which already accounts for stylesheet padding).
        painter = QPainter(self)
        opt = QStyleOption()
        opt.initFrom(self)
        self.style().drawPrimitive(QStyle.PE_Widget, opt, painter, self)
        rect = self.contentsRect()
        elided = self.fontMetrics().elidedText(self.text(), Qt.ElideRight, rect.width())
        painter.setPen(self.palette().color(self.foregroundRole()))
        painter.drawText(rect, int(self.alignment()) | Qt.TextSingleLine, elided)
