"""Arc picker: the operator clicks the arc they mean; the GUI never guesses.

Arc strategy Phase 1, Principle C (docs/handoffs/2026-11-10-arc-segment-strategy.md).
For an end point + radius there are two arcs, one bulging to each side of the
chord. Both are drawn in the operator's orientation - Z+ to the right, larger
diameter DOWN (the graph's invertY, like gui/components/quadrant_graphic.py) -
with the start green and the end red. The selected one is solid blue; clicking the
other picks it and emits picked(sign), which the segment list writes as the sign of
R. The maths is geometry/arc_entry.arc_candidates; the stored identity stays end
point + signed R.
"""

from __future__ import annotations

import math
from typing import Optional, Tuple

from PyQt5.QtCore import QPointF, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPainter, QPen
from PyQt5.QtWidgets import QWidget

from gui.colors import COLORS


class ArcPicker(QWidget):
    picked = pyqtSignal(int)            # +1 / -1: the sign of R the operator clicked

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(130)
        self.setMinimumWidth(160)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("The two arcs this radius can make between the points. "
                        "Click the one you want (green = start, red = end).")
        self._cands = []
        self._sign = 1
        self._prev_dir = None
        self._p0 = self._p1 = None
        self._tangent_sign = 0
        self._screen = []                # per candidate: list of QPointF (last paint)
        self.mode_od = lambda: True      # set by the owner: OD (material inside) or ID

    # ------------------------------------------------------------------
    def set_arc(self, p0: Tuple[float, float], p1: Tuple[float, float], radius: float,
                prev_dir: Optional[Tuple[float, float]] = None) -> bool:
        """Show the candidates for start p0, end p1 (radius space (r, z)) and the
        signed radius currently in the row. Returns False (and clears) when there
        is nothing to pick."""
        from geometry.arc_entry import arc_candidates, tangent_arc
        self._cands = arc_candidates(p0, p1, abs(radius)) if abs(radius) > 1e-9 else []
        self._sign = 1 if radius > 0 else -1
        self._p0, self._p1, self._prev_dir = p0, p1, prev_dir
        self._tangent_sign = 0
        if prev_dir is not None and self._cands:
            t, _ = tangent_arc(p0, p1, prev_dir)
            if t is not None and abs(abs(t) - abs(radius)) <= 1e-4:
                self._tangent_sign = 1 if t > 0 else -1
        self.update()
        return len(self._cands) == 2

    def selected_sign(self) -> int:
        return self._sign

    def candidate_count(self) -> int:
        return len(self._cands)

    # ------------------------------------------------------------------
    def _transform(self):
        """(r, z) -> widget point: z to the right, r DOWN, uniform scale."""
        pts = [p for c in self._cands for p in c["points"]]
        if self._prev_dir is not None and self._p0 is not None:
            pts.append(self._p0)
        rs = [p[0] for p in pts]
        zs = [p[1] for p in pts]
        span = max(max(rs) - min(rs), max(zs) - min(zs), 1e-6)
        m = 18.0
        w, h = self.width() - 2 * m, self.height() - 2 * m - 14
        s = min(w / span, h / span)
        zc, rc = (max(zs) + min(zs)) / 2.0, (max(rs) + min(rs)) / 2.0
        cx, cy = self.width() / 2.0, m + h / 2.0

        def f(p):
            return QPointF(cx + (p[1] - zc) * s, cy + (p[0] - rc) * s)
        return f, s

    def paintEvent(self, event):  # noqa: N802 (Qt naming)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(COLORS["graph_bg"]))
        self._screen = []
        if not self._cands:
            return
        f, s = self._transform()
        blue = QColor(COLORS["status_info"])
        dim = QColor(COLORS["text_disabled"])
        # incoming direction (what "tangent" means), grey
        if self._prev_dir is not None:
            L = math.hypot(*self._prev_dir) or 1.0
            back = 30.0 / s
            q0 = (self._p0[0] - self._prev_dir[0] / L * back, self._p0[1] - self._prev_dir[1] / L * back)
            p.setPen(QPen(dim, 1, Qt.SolidLine))
            p.drawLine(f(q0), f(self._p0))
        order = sorted(range(len(self._cands)),
                       key=lambda i: self._cands[i]["radius"] * self._sign > 0)   # selected last
        self._screen = [[f(q) for q in c["points"]] for c in self._cands]
        for i in order:
            c = self._cands[i]
            sel = (c["radius"] > 0) == (self._sign > 0)
            pen = QPen(blue if sel else dim, 3 if sel else 1.5, Qt.SolidLine if sel else Qt.DashLine)
            p.setPen(pen)
            pts = self._screen[i]
            for a, b in zip(pts, pts[1:]):
                p.drawLine(a, b)
        for pt, col in ((self._p0, "#3cb371"), (self._p1, "#e05050")):
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(col))
            p.drawEllipse(f(pt), 4.5, 4.5)
        # caption
        sel = next(c for c in self._cands if (c["radius"] > 0) == (self._sign > 0))
        mid = sel["points"][len(sel["points"]) // 2]
        chord_r = (self._p0[0] + self._p1[0]) / 2.0
        # Convex / concave: OD material is at smaller diameters, ID at larger.
        # An arc bulging toward the material is concave (inside corner).
        chord_z = (self._p0[1] + self._p1[1]) / 2.0
        if abs(mid[0] - chord_r) > 1e-9:
            try:
                od = bool(self.mode_od())
            except Exception:             # owner being torn down: assume OD
                od = True
            toward_material = (mid[0] < chord_r) == od
            way = "concave (inside corner)" if toward_material else "convex (outside corner)"
        else:                                           # radial chord: bulges in Z
            way = "bulges toward the chuck" if mid[1] < chord_z else "bulges toward the tailstock"
        smooth = "  smooth with previous" if self._tangent_sign == self._sign else ""
        font = QFont(self.font())
        font.setPointSizeF(max(7.0, font.pointSizeF() - 1))
        p.setFont(font)
        p.setPen(QColor(COLORS["text_secondary"]))
        p.drawText(6, self.height() - 6,
                   f"R{abs(sel['radius']):.4f} {'+' if self._sign > 0 else '−'}  {way}{smooth}")

    def mousePressEvent(self, event):  # noqa: N802 (Qt naming)
        if len(self._cands) != 2 or not self._screen:
            return
        pos = event.pos()

        def dist(pts):
            return min((q.x() - pos.x()) ** 2 + (q.y() - pos.y()) ** 2 for q in pts)
        best = min(range(2), key=lambda i: dist(self._screen[i]))
        sign = 1 if self._cands[best]["radius"] > 0 else -1
        if sign != self._sign:
            self._sign = sign
            self.update()
            self.picked.emit(sign)
