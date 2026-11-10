"""Collapsible accordion section widget for Industry CAM Engine.

A header bar that expands/collapses its content on click.
Used in the Program tab to keep all sections visible without scrolling.
"""

from PyQt5.QtCore import Qt, pyqtSignal, QPropertyAnimation, QEasingCurve
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFrame, QSizePolicy,
)

from gui.colors import COLORS, FONTS


class CollapsibleSection(QWidget):
    """A section with a clickable header that expands/collapses content.

    Args:
        title: Section header text.
        expanded: Whether to start expanded (default True).
    """

    toggled = pyqtSignal(bool)  # Emitted with new expanded state

    HEADER_HEIGHT = 53  # px, total header bar height

    def __init__(self, title: str, expanded: bool = True, parent=None):
        super().__init__(parent)
        self._expanded = expanded
        self._title = title
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header button
        self._header = QPushButton(self._make_header_text())
        self._header.setFlat(True)
        self._header.setCursor(Qt.PointingHandCursor)
        # 53 px, the height it has always drawn at. The old setFixedHeight(32)
        # lost to the app-wide QPushButton min-height (44 + padding + border),
        # so the layout reserved 32 px, the header drew 53 px and hung 10 px
        # into the next section. QSS heights are the content box:
        # 44 + 2 x 4 px padding + 1 px bottom border = 53 px.
        self._header.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {COLORS['bg_surface']};"
            f"  color: {COLORS['text_primary']};"
            f"  border: none;"
            f"  border-bottom: 1px solid {COLORS['border_normal']};"
            f"  text-align: left;"
            f"  min-height: {self.HEADER_HEIGHT - 9}px;"
            f"  max-height: {self.HEADER_HEIGHT - 9}px;"
            f"  padding: 4px 8px;"
            f"  font-weight: bold;"
            f"  font-size: {FONTS['ui_size']}pt;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background-color: {COLORS['btn_primary_hover']};"
            f"}}"
        )
        self._header.clicked.connect(self.toggle)
        layout.addWidget(self._header)

        # Content container
        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(4, 4, 4, 4)
        self._content_layout.setSpacing(2)
        layout.addWidget(self._content, stretch=1)

        # Apply initial state
        self._expanded_min_height = 0
        self._expanded_v_policy = self.sizePolicy().verticalPolicy()
        self._content.setVisible(self._expanded)
        self._apply_size_mode()

    def _apply_size_mode(self):
        """Collapsed = exactly header-height and never grows, so collapsed
        sections pack together and leave the free height to expanded ones.

        Without this a collapsed section kept any minimum height set on it
        (Blocks: 240 px) and any layout stretch (Profile Segments), and its
        lone header floated in the middle of that dead space. Expanding
        restores the minimum height and vertical policy it had before.
        """
        policy = QSizePolicy(self.sizePolicy())
        if self._expanded:
            policy.setVerticalPolicy(self._expanded_v_policy)
            QWidget.setSizePolicy(self, policy)
            QWidget.setMinimumHeight(self, self._expanded_min_height)
        else:
            policy.setVerticalPolicy(QSizePolicy.Fixed)
            QWidget.setSizePolicy(self, policy)
            QWidget.setMinimumHeight(self, 0)

    def _ready(self) -> bool:
        return hasattr(self, "_expanded_min_height")

    def setMinimumHeight(self, h: int):  # noqa: N802 (Qt naming)
        """Remembered as the expanded-state minimum; a collapsed section
        stays header-height until it is expanded again."""
        if self._ready():
            self._expanded_min_height = h
            if not self._expanded:
                return
        QWidget.setMinimumHeight(self, h)

    def setSizePolicy(self, *args):  # noqa: N802
        """The vertical policy is remembered for the expanded state; while
        collapsed the section stays vertically Fixed."""
        policy = QSizePolicy(args[0]) if len(args) == 1 else QSizePolicy(*args)
        if self._ready():
            self._expanded_v_policy = policy.verticalPolicy()
            if not self._expanded:
                policy.setVerticalPolicy(QSizePolicy.Fixed)
        QWidget.setSizePolicy(self, policy)

    def content_layout(self) -> QVBoxLayout:
        """Return the layout to add widgets into."""
        return self._content_layout

    def add_widget(self, widget: QWidget):
        """Add a widget to the content area."""
        self._content_layout.addWidget(widget)

    def add_layout(self, layout):
        """Add a layout to the content area."""
        self._content_layout.addLayout(layout)

    def toggle(self):
        """Toggle expanded/collapsed state."""
        self._expanded = not self._expanded
        self._content.setVisible(self._expanded)
        self._apply_size_mode()
        self._header.setText(self._make_header_text())
        self.toggled.emit(self._expanded)

    def set_expanded(self, expanded: bool):
        """Set expanded state directly."""
        if expanded != self._expanded:
            self.toggle()

    @property
    def is_expanded(self) -> bool:
        return self._expanded

    def _make_header_text(self) -> str:
        arrow = "▼" if self._expanded else "▶"
        return f"  {arrow}  {self._title}"
