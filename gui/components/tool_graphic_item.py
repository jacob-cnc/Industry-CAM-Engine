"""The tool on the Manual / Run / sim graphs (tool-graphic plan 2026-11-13).

One object per graph. With a drawable tool loaded it shows the true-scale
insert (geometry/tool_outline.py) with a cross at the controlled point - the
point the DRO reports. Otherwise it shows the old dot, with a short reason
when there is one (tool not in the table, G43 not active, angles unknown).

Plot space: x = Z, y = radius (the graphs are 1:1 aspect-locked, so the
insert is drawn at its true shape at every zoom; their inverted Y is the
plot's business, not this item's). Moving the tool is one setPos per item: no
path is rebuilt during motion.
"""

from __future__ import annotations

from typing import Optional, Tuple

import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets

from gui.colors import COLORS

_BODY_FILL = "#5B7A99AA"
_BODY_LINE = "#C8D3DE"
_EDGE = "#E56E72"
_Z = 20


def _path(points) -> QtGui.QPainterPath:
    path = QtGui.QPainterPath()
    if points:
        path.moveTo(points[0][1], points[0][0])            # (r, z) -> (x = z, y = r)
        for r, z in points[1:]:
            path.lineTo(z, r)
    return path


def graphic_for(card, tool_in_spindle: int, tool_offset: Optional[Tuple[float, float]] = None,
                tol: float = 1e-6):
    """(outline or None, note) for the tool in the spindle.

    card: the ToolCardData for tool_in_spindle (None when it isn't in the table);
    tool_offset: LinuxCNC's active (x radius, z) tool offset, checked against
    the card's geometry + wear: if they differ the work position is NOT this
    tool's controlled point (G43 not applied), so the dot is shown, not a
    misplaced insert. tol: 1e-6 for LinuxCNC's live offset; the interpreter's
    printed offset (sim) has 4 decimals.
    """
    from geometry.tool_outline import tool_outline
    from tools.tool_card_data import insert_spec
    if tool_in_spindle <= 0:
        return None, ""
    if card is None:
        return None, f"T{tool_in_spindle} is not in the tool table"
    if tool_offset is not None:
        want = (card.x_offset + card.x_wear, card.z_offset + card.z_wear)
        if abs(tool_offset[0] - want[0]) > tol or abs(tool_offset[1] - want[1]) > tol:
            return None, f"T{tool_in_spindle} offset not active (G43) - showing the spindle point"
    try:
        outline = tool_outline(insert_spec(card))
    except ValueError as exc:
        return None, f"T{tool_in_spindle}: {exc}"
    # drawn at a nominal size until an ISO code or IC is entered - say so
    return outline, ("" if outline.size_known else f"T{tool_in_spindle} size not set (ISO code / IC)")


class ToolGraphic:
    """The tool (or the dot) on one pyqtgraph PlotWidget / PlotItem."""

    def __init__(self, plot, dot_size: int = 14):
        self._plot = plot
        self._outline = None
        self._pos = (0.0, 0.0)                         # (r, z) of the controlled point

        body_pen = pg.mkPen(_BODY_LINE, width=1)
        body_pen.setCosmetic(True)
        self._body = QtWidgets.QGraphicsPathItem()
        self._body.setPen(body_pen)
        self._body.setBrush(pg.mkBrush(_BODY_FILL))
        self._body.setZValue(_Z)
        edge_pen = pg.mkPen(_EDGE, width=2.5)
        edge_pen.setCosmetic(True)
        self._edges = QtWidgets.QGraphicsPathItem()
        self._edges.setPen(edge_pen)
        self._edges.setZValue(_Z + 1)
        self._cross = pg.ScatterPlotItem(size=13, symbol="+", pen=pg.mkPen("#F0F4F8", width=1.5),
                                         brush=pg.mkBrush("#F0F4F8"))
        self._cross.setZValue(_Z + 2)
        self._dot = pg.ScatterPlotItem(size=dot_size, brush=pg.mkBrush(COLORS["graph_tool_dot"]),
                                       pen=pg.mkPen("#000000", width=1))
        self._dot.setZValue(_Z)
        self._note = pg.TextItem("", color=COLORS.get("status_warning", "#E0A030"), anchor=(0, 1))
        self._note.setZValue(_Z + 3)
        for item in (self._body, self._edges, self._cross, self._dot, self._note):
            plot.addItem(item, ignoreBounds=True)
        self.set_outline(None)

    # -- public ------------------------------------------------------------
    @property
    def outline(self):
        return self._outline

    def set_outline(self, outline, note: str = "") -> None:
        """Show this outline (controlled point at (0, 0)); None = the dot."""
        self._outline = outline
        drawn = outline is not None
        if drawn:
            self._body.setPath(_path(outline.outline))
            edges = QtGui.QPainterPath()
            for e in outline.cutting_edges:
                edges.addPath(_path(e))
            self._edges.setPath(edges)
        for item in (self._body, self._edges, self._cross):
            item.setVisible(drawn)
        self._dot.setVisible(not drawn)
        self._note.setText(note)
        self._note.setVisible(bool(note))
        self.set_position(*self._pos)

    def set_position(self, x_radius: float, z: float) -> None:
        """Put the controlled point at (x radius, z)."""
        self._pos = (x_radius, z)
        if self._outline is not None:
            self._body.setPos(z, x_radius)
            self._edges.setPos(z, x_radius)
            self._cross.setData([z], [x_radius])
        else:
            self._dot.setData([z], [x_radius])
        self._note.setPos(z, x_radius)

    def position(self) -> Tuple[float, float]:
        return self._pos
