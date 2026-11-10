"""UI debug overlay: a shared vocabulary for layout and spacing work.

Off unless the environment variable INDUSTRY_CAM_DEBUG_UI=1 is set. It draws
on a transparent layer above the main window and never changes the real UI.
Only F9-F12 and Ctrl+Shift+mouse are used, so arrow-key jogging is untouched.

Keys (from any tab):
    F12              ID tags: off -> depth 1 -> 2 -> 3 -> 4 -> all -> off
    F11              Outlines: widget borders + hatched empty space
                     (margins, spacing, stretch); follows the tag depth
    F10              Inspector: ID, size, position, margins and size policy
                     of the widget under the mouse
    F9               Snapshot: tagged + clean PNG, layout tree (.txt, .json)
    Ctrl+Shift+drag  Add a ruler (R1, R2, ...) between two points
    F8               Undo: remove the most recent ruler
    Shift+F8         Remove all rulers

IDs are hierarchical and in reading order (top-to-bottom, left-to-right):
    BAR   the top status ribbon        BAR3, BAR3.1, ...
    TABS  the tab bar
    P     the current tab's page, named by its first letter (Program = P,
          Manual = M, Tools = T, Run = R, Edit = E, Debug = D, Setup = S,
          Help = H)                    P1, P1.2, P1.2.3, ...
IDs are stable while the layout code is unchanged; a restructure renumbers.

Snapshots go to %LOCALAPPDATA%/IndustryCAMEngine/ui_snapshots (Windows) or
~/.local/share/IndustryCAMEngine/ui_snapshots, or INDUSTRY_CAM_SNAPSHOT_DIR.
All coordinates are window pixels, origin at the window's top-left.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import sys
import time
from dataclasses import dataclass, field

from PyQt5.QtCore import QEvent, QObject, QPoint, QRect, Qt, QTimer
from PyQt5.QtGui import (
    QBrush, QColor, QCursor, QFont, QFontInfo, QFontMetrics, QPainter, QPen,
    QRegion,
)
from PyQt5.QtWidgets import (
    QAbstractButton, QAbstractItemView, QAbstractScrollArea, QAbstractSlider,
    QAbstractSpinBox, QApplication, QComboBox, QGraphicsView, QGroupBox,
    QLabel, QLineEdit, QPlainTextEdit, QProgressBar, QScrollArea, QSizePolicy,
    QSplitterHandle, QStackedWidget, QTabBar, QTextEdit, QWidget,
)

logger = logging.getLogger(__name__)

ENV_FLAG = "INDUSTRY_CAM_DEBUG_UI"
ENV_SNAPSHOT_DIR = "INDUSTRY_CAM_SNAPSHOT_DIR"

# Widgets drawn as one box: their internals are not useful layout handles.
LEAF_TYPES = (
    QAbstractButton, QLabel, QLineEdit, QAbstractSpinBox, QComboBox,
    QAbstractSlider, QAbstractItemView, QTextEdit, QPlainTextEdit,
    QGraphicsView, QTabBar, QProgressBar, QSplitterHandle,
)

DEPTH_STEPS = (None, 1, 2, 3, 4, 99)   # F12 cycle; None = off, 99 = all
DEPTH_COLORS = ("#FFFFFF", "#FF6B6B", "#4ECDC4", "#FFD93D", "#A78BFA",
                "#60A5FA", "#F472B6")
MAX_QT = 16777215                     # QWIDGETSIZE_MAX

_POLICY_NAMES = {
    QSizePolicy.Fixed: "Fixed", QSizePolicy.Minimum: "Minimum",
    QSizePolicy.Maximum: "Maximum", QSizePolicy.Preferred: "Preferred",
    QSizePolicy.Expanding: "Expanding",
    QSizePolicy.MinimumExpanding: "MinExpanding",
    QSizePolicy.Ignored: "Ignored",
}


def debug_ui_enabled() -> bool:
    """True when the user asked for the overlay (INDUSTRY_CAM_DEBUG_UI=1)."""
    return os.environ.get(ENV_FLAG, "").strip() == "1"


def snapshot_dir() -> str:
    """Folder snapshots are written to (created on first snapshot)."""
    override = os.environ.get(ENV_SNAPSHOT_DIR)
    if override:
        return override
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    else:
        base = os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "IndustryCAMEngine", "ui_snapshots")


# ----------------------------------------------------------------------
# Widget tree
# ----------------------------------------------------------------------

@dataclass
class Node:
    """One tagged widget."""
    id: str
    widget: QWidget
    depth: int
    rect: QRect                 # full widget rect, window coords
    visible: QRect              # rect clipped by every ancestor
    children: list = field(default_factory=list)


def _window_rect(w: QWidget, win: QWidget) -> QRect:
    return QRect(w.mapTo(win, QPoint(0, 0)), w.size())


def _clipped_rect(w: QWidget, win: QWidget) -> QRect:
    """Widget rect intersected with every ancestor up to the window."""
    clip = _window_rect(w, win)
    p = w.parentWidget()
    while p is not None and p is not win:
        clip = clip.intersected(_window_rect(p, win))
        p = p.parentWidget()
    return clip.intersected(win.rect())


def _child_candidates(w: QWidget, skip: QWidget) -> list:
    """Visible child widgets of w that get their own node.

    Qt-internal containers (objectName 'qt_*', QStackedWidget) are see-through:
    their children are promoted. A QScrollArea contributes only its content.
    """
    if isinstance(w, QScrollArea):
        inner = w.widget()
        return [inner] if inner is not None and inner.isVisible() else []
    out = []
    for c in w.children():
        if not c.isWidgetType() or c is skip or c.isWindow() or not c.isVisible():
            continue
        if isinstance(c, QSplitterHandle):
            out.append(c)
        elif c.objectName().startswith("qt_") or isinstance(c, QStackedWidget):
            out.extend(_child_candidates(c, skip))
        else:
            out.append(c)
    return out


def _is_leaf(w: QWidget) -> bool:
    if isinstance(w, QScrollArea):
        return False
    return isinstance(w, LEAF_TYPES) or isinstance(w, QAbstractScrollArea)


def _reading_order(widgets: list, win: QWidget) -> list:
    """Sort into rows (top to bottom), each row left to right.

    A widget joins the current row when its vertical centre falls inside the
    row's first (topmost) widget's band, so a row of differently sized
    widgets - a tall button beside short labels - stays one row.
    """
    items = sorted(((_window_rect(w, win), w) for w in widgets),
                   key=lambda t: (t[0].y(), t[0].x()))
    rows = []
    for r, w in items:
        if rows:
            band = rows[-1][0][0]
            if band.top() <= r.center().y() <= band.bottom():
                rows[-1].append((r, w))
                continue
        rows.append([(r, w)])
    return [w for row in rows for _, w in sorted(row, key=lambda t: t[0].x())]


def build_tree(win: QWidget, roots, skip: QWidget = None) -> list:
    """Build Node trees for [(prefix, widget), ...] roots.

    Nodes whose visible area is empty (hidden, scrolled away) are dropped
    with their subtree. A wrapper with a single child of identical geometry
    collapses into that child so IDs land on meaningful widgets.
    """

    def make(w: QWidget, node_id: str, depth: int):
        visible = _clipped_rect(w, win)
        if visible.isEmpty():
            return None
        node = Node(node_id, w, depth, _window_rect(w, win), visible)
        if _is_leaf(w):
            return node
        kids = [c for c in _child_candidates(w, skip)
                if not _clipped_rect(c, win).isEmpty()]
        # Collapse pass-through wrappers (same rect as their only child).
        # Below the root the node takes the inner widget; a root keeps its
        # page widget and adopts the wrapper's children.
        while len(kids) == 1 and _window_rect(kids[0], win) == node.rect:
            inner = kids[0]
            if _is_leaf(inner):
                if depth > 0:            # a wrapper around one control IS it
                    node.widget = inner
                    return node
                break                    # a root keeps its single control
            if depth > 0:
                node.widget = inner
            kids = [c for c in _child_candidates(inner, skip)
                    if not _clipped_rect(c, win).isEmpty()]
        kids = _reading_order(kids, win)
        n = 0
        for c in kids:
            child_id = f"{node_id}{n + 1}" if depth == 0 else f"{node_id}.{n + 1}"
            child = make(c, child_id, depth + 1)
            if child is not None:
                node.children.append(child)
                n += 1
        return node

    trees = []
    for prefix, w in roots:
        if w is None or not w.isVisible():
            continue
        t = make(w, prefix, 0)
        if t is not None:
            trees.append(t)
    return trees


def iter_nodes(trees):
    """Depth-first pre-order over every node."""
    stack = list(reversed(trees))
    while stack:
        n = stack.pop()
        yield n
        stack.extend(reversed(n.children))


# ----------------------------------------------------------------------
# Widget description helpers (inspector + snapshot)
# ----------------------------------------------------------------------

def attr_name(w: QWidget, win: QWidget) -> str:
    """'OwnerClass._attr' for the Python attribute holding w, if any."""
    p = w.parentWidget()
    hops = 0
    while p is not None and hops < 8:
        try:
            items = vars(p).items()
        except TypeError:
            items = ()
        for k, v in items:
            if v is w:
                return f"{type(p).__name__}.{k}"
        if p is win:
            break
        p = p.parentWidget()
        hops += 1
    return ""


def widget_text(w: QWidget) -> str:
    """Short visible text that helps a human recognise the widget."""
    text = ""
    try:
        if isinstance(w, QAbstractButton):
            text = w.text()
        elif isinstance(w, QLabel):
            text = w.text()
        elif isinstance(w, QGroupBox):
            text = w.title()
        elif isinstance(w, QLineEdit):
            text = w.text() or w.placeholderText()
        elif isinstance(w, QComboBox):
            text = w.currentText()
        elif isinstance(w, QTabBar):
            text = " | ".join(w.tabText(i) for i in range(w.count()))
        else:
            title = getattr(w, "title", None)
            if callable(title):
                title = title()
            if isinstance(title, str):
                text = title
    except Exception:
        text = ""
    text = re.sub(r"<[^>]+>", "", text or "").replace("\n", " ").strip()
    return text if len(text) <= 40 else text[:37] + "..."


def _size_txt(w: int, h: int) -> str:
    """'120x32'; an unlimited side reads 'any' ('anyx32'); both = 'none'."""
    if w >= MAX_QT and h >= MAX_QT:
        return "none"
    fw = "any" if w >= MAX_QT else str(w)
    fh = "any" if h >= MAX_QT else str(h)
    return f"{fw}x{fh}"


def describe(node: Node, win: QWidget) -> dict:
    """Everything worth knowing about a node's size and spacing."""
    w = node.widget
    info = {
        "id": node.id,
        "depth": node.depth,
        "class": type(w).__name__,
        "attr": attr_name(w, win),
        "text": widget_text(w),
        "x": node.rect.x(), "y": node.rect.y(),
        "w": node.rect.width(), "h": node.rect.height(),
        "clipped": node.visible != node.rect,
        "min": _size_txt(w.minimumWidth(), w.minimumHeight()),
        "max": _size_txt(w.maximumWidth(), w.maximumHeight()),
        "hint": f"{w.sizeHint().width()}x{w.sizeHint().height()}",
        "policy": (f"{_POLICY_NAMES.get(w.sizePolicy().horizontalPolicy(), '?')}/"
                   f"{_POLICY_NAMES.get(w.sizePolicy().verticalPolicy(), '?')}"),
    }
    fi = QFontInfo(w.font())
    info["font"] = f"{fi.family()} {fi.pointSizeF():g}pt/{fi.pixelSize()}px"
    lay = w.layout()
    if lay is not None:
        m = lay.contentsMargins()
        info["layout"] = type(lay).__name__
        info["margins"] = [m.left(), m.top(), m.right(), m.bottom()]
        spacing = lay.spacing()
        if spacing < 0 and hasattr(lay, "horizontalSpacing"):
            spacing = f"{lay.horizontalSpacing()}h/{lay.verticalSpacing()}v"
        info["spacing"] = spacing
    return info


# ----------------------------------------------------------------------
# Overlay
# ----------------------------------------------------------------------

class DebugOverlay(QWidget):
    """Transparent drawing layer + key/mouse handling for one main window."""

    def __init__(self, window: QWidget):
        super().__init__(window)
        self._win = window
        self.setObjectName("ui_debug_overlay")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self.setStyleSheet("background: transparent;")
        self.setFocusPolicy(Qt.NoFocus)

        self.tag_depth = None        # None = tags off
        self.outlines = False
        self.inspect = False
        self.rulers = []             # [(QPoint, QPoint)] window coords
        self._drag = None            # ruler being dragged: (start, end)
        self._toast = ("", 0.0)
        self._hide_hud = False
        self._hover = None           # Node under the mouse (inspector)

        self._tag_font = QFont("Consolas, DejaVu Sans Mono, monospace")
        self._tag_font.setStyleHint(QFont.Monospace)
        self._tag_font.setPixelSize(11)
        self._tag_font.setBold(True)
        self._info_font = QFont(self._tag_font)
        self._info_font.setBold(False)
        self._info_font.setPixelSize(12)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(120)

        window.installEventFilter(self)
        QApplication.instance().installEventFilter(self)
        self._fit()
        self.show()

    # -- state ----------------------------------------------------------

    @property
    def any_mode(self) -> bool:
        return (self.tag_depth is not None or self.outlines or self.inspect
                or bool(self.rulers) or self._drag is not None)

    def undo_ruler(self):
        """Remove the most recently added ruler."""
        if self.rulers:
            self.rulers.pop()
        self.update()

    def clear_rulers(self):
        """Remove every ruler."""
        self.rulers.clear()
        self.update()

    def cycle_tags(self):
        i = DEPTH_STEPS.index(self.tag_depth)
        self.tag_depth = DEPTH_STEPS[(i + 1) % len(DEPTH_STEPS)]
        self.update()

    def roots(self):
        """(prefix, widget) roots: ribbon, tab bar and the current page."""
        win = self._win
        tabs = getattr(win, "tab_widget", None)
        bar = getattr(win, "status_bar", None)
        if tabs is None:
            return [("W", win.centralWidget() if hasattr(win, "centralWidget")
                     and win.centralWidget() is not None else win)]
        roots = []
        if bar is not None:
            roots.append(("BAR", bar))
        roots.append(("TABS", tabs.tabBar()))
        idx = tabs.currentIndex()
        if idx >= 0:
            roots.append((self._page_prefix(tabs, idx), tabs.widget(idx)))
        return roots

    @staticmethod
    def _page_prefix(tabs, idx) -> str:
        letters = [(tabs.tabText(i).strip()[:1] or "X").upper()
                   for i in range(tabs.count())]
        letter = letters[idx]
        return letter if letters.count(letter) == 1 else f"{letter}{idx}"

    def tree(self):
        return build_tree(self._win, self.roots(), skip=self)

    # -- events ---------------------------------------------------------

    def _fit(self):
        self.setGeometry(self._win.rect())
        self.raise_()

    def _tick(self):
        if self.any_mode or self._toast[1] > time.time():
            self.raise_()
            self.update()

    def eventFilter(self, obj, event):
        et = event.type()
        if obj is self._win and et in (QEvent.Resize, QEvent.Show):
            self._fit()
            return False
        if et == QEvent.KeyPress and not event.isAutoRepeat():
            if self._belongs(obj) and self._on_key(event.key(), event.modifiers()):
                return True
        elif et == QEvent.ShortcutOverride:
            if self._belongs(obj) and event.key() in (
                    Qt.Key_F8, Qt.Key_F9, Qt.Key_F10, Qt.Key_F11, Qt.Key_F12):
                event.accept()
                return True
        elif et in (QEvent.MouseButtonPress, QEvent.MouseMove,
                    QEvent.MouseButtonRelease):
            if self._belongs(obj) and self._on_mouse(et, event):
                return True
        return False

    def _belongs(self, obj) -> bool:
        return isinstance(obj, QWidget) and obj.window() is self._win

    def _on_key(self, key, modifiers=Qt.NoModifier) -> bool:
        if key == Qt.Key_F8:
            if modifiers & Qt.ShiftModifier:
                self.clear_rulers()
            else:
                self.undo_ruler()
        elif key == Qt.Key_F12:
            self.cycle_tags()
        elif key == Qt.Key_F11:
            self.outlines = not self.outlines
        elif key == Qt.Key_F10:
            self.inspect = not self.inspect
        elif key == Qt.Key_F9:
            self.take_snapshot()
        else:
            return False
        self.update()
        return True

    def _on_mouse(self, et, event) -> bool:
        both = Qt.ControlModifier | Qt.ShiftModifier
        pos = self._win.mapFromGlobal(event.globalPos())
        if et == QEvent.MouseButtonPress:
            if event.button() == Qt.LeftButton and \
                    (event.modifiers() & both) == both:
                self._drag = (pos, pos)
                self.update()
                return True
            return False
        if self._drag is None:
            return False
        self._drag = (self._drag[0], pos)
        if et == QEvent.MouseButtonRelease:
            start, end = self._drag
            self._drag = None
            # A click or a jittery sub-4 px drag is not a measurement.
            if (end - start).manhattanLength() >= 4:
                self.rulers.append((start, end))
        self.update()
        return True

    # -- snapshot -------------------------------------------------------

    def take_snapshot(self) -> dict:
        """Write tagged PNG, clean PNG, .txt and .json; return their paths."""
        folder = snapshot_dir()
        os.makedirs(folder, exist_ok=True)
        nums = [int(m.group(1)) for f in os.listdir(folder)
                if (m := re.match(r"snap_(\d+)_", f))]
        num = max(nums, default=0) + 1
        trees = self.tree()
        page = trees[-1].id if trees else "W"
        tab_name = page
        tabs = getattr(self._win, "tab_widget", None)
        if tabs is not None and tabs.currentIndex() >= 0:
            tab_name = re.sub(r"\W+", "", tabs.tabText(tabs.currentIndex())) or page
        stem = os.path.join(folder, f"snap_{num:03d}_{tab_name}")

        # Clean image: overlay hidden.
        self.hide()
        clean = self._win.grab()
        self.show()
        # Tagged image: current modes, tags forced on (depth 3) if off.
        saved_depth = self.tag_depth
        if self.tag_depth is None:
            self.tag_depth = 3
        self._hide_hud = True
        self.update()
        tagged = self._win.grab()
        self._hide_hud = False
        self.tag_depth = saved_depth

        paths = {"tagged": stem + ".png", "clean": stem + "_clean.png",
                 "txt": stem + ".txt", "json": stem + ".json"}
        tagged.save(paths["tagged"])
        clean.save(paths["clean"])

        nodes = [describe(n, self._win) for n in iter_nodes(trees)]
        screen = self._win.screen() if hasattr(self._win, "screen") else None
        meta = {
            "snapshot": num,
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "tab": tab_name,
            "window": [self._win.width(), self._win.height()],
            "screen": ([screen.availableGeometry().width(),
                        screen.availableGeometry().height()] if screen else None),
            "logical_dpi": round(screen.logicalDotsPerInch()) if screen else None,
            "rulers": [{"id": f"R{i + 1}", "x1": a.x(), "y1": a.y(),
                        "x2": b.x(), "y2": b.y()}
                       for i, (a, b) in enumerate(self.rulers)],
        }
        with open(paths["json"], "w", encoding="utf-8") as fh:
            json.dump({"meta": meta, "nodes": nodes}, fh, indent=1)
        with open(paths["txt"], "w", encoding="utf-8") as fh:
            fh.write(self._tree_text(meta, nodes))

        self._toast = (f"Snapshot {num} saved", time.time() + 3.0)
        self.update()
        logger.info("UI snapshot %d saved: %s", num, paths["tagged"])
        return paths

    @staticmethod
    def _tree_text(meta, nodes) -> str:
        lines = [
            f"Industry CAM Engine UI snapshot {meta['snapshot']} - {meta['time']}",
            f"Tab: {meta['tab']}   window {meta['window'][0]} x {meta['window'][1]}"
            f"   logical DPI {meta['logical_dpi']}   screen {meta['screen']}",
            "Coordinates are window pixels from the top-left. size = w x h.",
            "layout = margins L,T,R,B / spacing.  * = partly scrolled/clipped.",
        ]
        for r in meta.get("rulers", []):
            dx, dy = r["x2"] - r["x1"], r["y2"] - r["y1"]
            lines.append(f"Ruler {r['id']}: ({r['x1']},{r['y1']}) -> "
                         f"({r['x2']},{r['y2']})  dx {dx}  dy {dy}  "
                         f"len {math.hypot(dx, dy):.1f}")
        lines.append("")
        for n in nodes:
            ident = "  " * n["depth"] + n["id"]
            label = n["class"]
            if n["attr"]:
                label += f" {n['attr']}"
            if n["text"]:
                label += f' "{n["text"]}"'
            geo = f"{n['x']:>5},{n['y']:>5}  {n['w']:>4} x {n['h']:<4}"
            extra = ""
            if "margins" in n:
                extra = f"  layout {','.join(map(str, n['margins']))}/{n['spacing']}"
            lines.append(f"{ident:<22} {geo}{'*' if n['clipped'] else ' '} "
                         f"{label}{extra}")
        return "\n".join(lines) + "\n"

    # -- painting -------------------------------------------------------

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        trees = self.tree() if (self.tag_depth is not None or self.outlines
                                or self.inspect) else []
        limit = self.tag_depth if self.tag_depth is not None else 99
        nodes = [n for n in iter_nodes(trees) if n.depth <= limit]
        if self.outlines:
            self._paint_outlines(p, nodes)
        if self.tag_depth is not None:
            self._paint_tags(p, nodes)
        if self.inspect:
            self._paint_inspector(p, trees)
        for i, (a, b) in enumerate(self.rulers):
            self._paint_ruler(p, a, b, f"R{i + 1}")
        if self._drag is not None:
            self._paint_ruler(p, *self._drag, f"R{len(self.rulers) + 1}")
        if not self._hide_hud:
            self._paint_hud(p)
        p.end()

    @staticmethod
    def _color(depth: int) -> QColor:
        return QColor(DEPTH_COLORS[min(depth, len(DEPTH_COLORS) - 1)])

    def _paint_outlines(self, p, nodes):
        # Empty space inside each container = its area minus its children.
        hatch = QColor("#FF9F43")
        hatch.setAlpha(110)
        for n in nodes:
            if not n.children:
                continue
            region = QRegion(n.visible)
            for c in n.children:
                region = region.subtracted(QRegion(c.visible))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(hatch, Qt.BDiagPattern))
            for r in region.rects():
                p.drawRect(r)
        p.setBrush(Qt.NoBrush)
        for n in nodes:
            p.setPen(QPen(self._color(n.depth), 1))
            r = n.visible
            p.drawRect(r.adjusted(0, 0, -1, -1))

    def _paint_tags(self, p, nodes):
        p.setFont(self._tag_font)
        fm = QFontMetrics(self._tag_font)
        placed = []
        bounds = self.rect()
        for n in nodes:
            tw, th = fm.horizontalAdvance(n.id) + 6, fm.height() + 2
            x, y = n.visible.x() + 1, n.visible.y() + 1
            box = QRect(x, y, tw, th)
            for _ in range(8):          # nudge right past tags already drawn
                hit = next((b for b in placed if b.intersects(box)), None)
                if hit is None:
                    break
                box.moveLeft(hit.right() + 2)
            if box.right() > bounds.right():
                box.moveRight(bounds.right())
            placed.append(box)
            col = self._color(n.depth)
            p.setPen(Qt.NoPen)
            p.setBrush(col)
            p.drawRect(box)
            p.setPen(QColor("#000000"))
            p.drawText(box, Qt.AlignCenter, n.id)
            if not self.outlines:
                p.setBrush(Qt.NoBrush)
                pen = QPen(col, 1, Qt.DotLine)
                p.setPen(pen)
                p.drawRect(n.visible.adjusted(0, 0, -1, -1))

    def _hover_node(self, trees):
        w = QApplication.widgetAt(QCursor.pos())
        if w is None or w.window() is not self._win:
            return None
        by_widget = {id(n.widget): n for n in iter_nodes(trees)}
        while w is not None:
            if id(w) in by_widget:
                return by_widget[id(w)]
            w = w.parentWidget()
        return None

    def _paint_inspector(self, p, trees):
        node = self._hover_node(trees)
        self._hover = node
        if node is None:
            return
        fill = QColor("#22D3EE")
        fill.setAlpha(45)
        p.setPen(QPen(QColor("#22D3EE"), 2))
        p.setBrush(fill)
        p.drawRect(node.visible.adjusted(1, 1, -1, -1))
        # Layout margins of the hovered widget, shaded darker.
        info = describe(node, self._win)
        if "margins" in info:
            l, t, r, b = info["margins"]
            inner = node.rect.adjusted(l, t, -r, -b)
            margin_region = QRegion(node.rect).subtracted(QRegion(inner))
            shade = QColor("#22D3EE")
            shade.setAlpha(90)
            p.setPen(Qt.NoPen)
            p.setBrush(shade)
            for rr in margin_region.intersected(QRegion(node.visible)).rects():
                p.drawRect(rr)

        lines = [f"{info['id']}  {info['class']}"]
        if info["attr"]:
            lines.append(info["attr"])
        if info["text"]:
            lines.append(f'"{info["text"]}"')
        lines.append(f"size {info['w']} x {info['h']}   at x {info['x']}, y {info['y']}"
                     + ("  (clipped)" if info["clipped"] else ""))
        lines.append(f"min {info['min']}  max {info['max']}  hint {info['hint']}")
        lines.append(f"policy {info['policy']}")
        if "margins" in info:
            lines.append(f"{info['layout']}  margins {','.join(map(str, info['margins']))}"
                         f"  spacing {info['spacing']}")
        lines.append(f"font {info['font']}")
        self._paint_box(p, lines, self.mapFromGlobal(QCursor.pos()) + QPoint(18, 18))

    def _paint_box(self, p, lines, at: QPoint, color="#22D3EE"):
        p.setFont(self._info_font)
        fm = QFontMetrics(self._info_font)
        w = max(fm.horizontalAdvance(s) for s in lines) + 16
        h = fm.height() * len(lines) + 10
        box = QRect(at.x(), at.y(), w, h)
        b = self.rect()
        if box.right() > b.right():
            box.moveRight(min(b.right(), at.x() - 36))
        if box.bottom() > b.bottom():
            box.moveBottom(min(b.bottom(), at.y() - 36))
        box.moveLeft(max(box.left(), 0))
        box.moveTop(max(box.top(), 0))
        bg = QColor("#0B1220")
        bg.setAlpha(235)
        p.setPen(QPen(QColor(color), 1))
        p.setBrush(bg)
        p.drawRect(box)
        p.setPen(QColor("#E5E7EB"))
        y = box.top() + 5 + fm.ascent()
        for s in lines:
            p.drawText(box.left() + 8, y, s)
            y += fm.height()

    def _paint_ruler(self, p, a: QPoint, b: QPoint, name: str):
        col = QColor("#FACC15")
        p.setPen(QPen(col, 1, Qt.DashLine))
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRect(a, b).normalized())
        p.setPen(QPen(col, 2))
        p.drawLine(a, b)
        for pt in (a, b):
            p.drawLine(pt.x() - 6, pt.y(), pt.x() + 6, pt.y())
            p.drawLine(pt.x(), pt.y() - 6, pt.x(), pt.y() + 6)
        dx, dy = b.x() - a.x(), b.y() - a.y()
        lines = [f"{name}  dx {dx}  dy {dy}  len {math.hypot(dx, dy):.1f} px",
                 f"from ({a.x()},{a.y()}) to ({b.x()},{b.y()})"]
        self._paint_box(p, lines, b + QPoint(14, 14), color="#FACC15")

    def _paint_hud(self, p):
        if self.any_mode:
            depth = ("off" if self.tag_depth is None else
                     "all" if self.tag_depth == 99 else str(self.tag_depth))
            text = (f"UI DEBUG  F12 tags:{depth}  F11 outlines:"
                    f"{'on' if self.outlines else 'off'}  F10 inspect:"
                    f"{'on' if self.inspect else 'off'}  F9 snapshot  "
                    f"Ctrl+Shift+drag ruler  F8 undo ruler  "
                    f"Shift+F8 clear rulers")
            if self.rulers:
                text += (f"  [{len(self.rulers)} ruler"
                         f"{'s' if len(self.rulers) != 1 else ''}]")
        else:
            text = ("UI debug: F12 tags | F11 outlines | F10 inspect | "
                    "F9 snapshot | Ctrl+Shift+drag ruler | F8 undo ruler | "
                    "Shift+F8 clear rulers")
        msg, until = self._toast
        if msg and until > time.time():
            text = f"{msg}   |   {text}"
        p.setFont(self._info_font)
        fm = QFontMetrics(self._info_font)
        w, h = fm.horizontalAdvance(text) + 14, fm.height() + 6
        box = QRect(self.width() - w - 4, self.height() - h - 4, w, h)
        bg = QColor("#0B1220")
        bg.setAlpha(200)
        p.setPen(Qt.NoPen)
        p.setBrush(bg)
        p.drawRect(box)
        p.setPen(QColor("#FACC15") if msg and until > time.time()
                 else QColor("#9CA3AF"))
        p.drawText(box, Qt.AlignCenter, text)


def install_debug_overlay(window: QWidget) -> DebugOverlay:
    """Attach the overlay to a top-level window and return it."""
    overlay = DebugOverlay(window)
    logger.info("UI debug overlay on (F9 snapshot, F10 inspect, F11 outlines, "
                "F12 tags); snapshots -> %s", snapshot_dir())
    return overlay
