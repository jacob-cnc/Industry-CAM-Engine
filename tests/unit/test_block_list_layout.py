"""Blocks list layout: '+ Add' stays inside its header row (no overlap with
the list), and Dup/Up/Dn/Vis/Del are one size, fully inside their row and
vertically centred together - under the app-wide stylesheet that used to
override their heights."""

from PyQt5.QtCore import QPoint
from PyQt5.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])


def _g(w, root):
    p = w.mapTo(root, QPoint(0, 0))
    return p.x(), p.y(), w.width(), w.height()


def test_block_list_buttons_fit_and_align():
    from gui.colors import STYLESHEET
    from gui.components.block_list import BlockListWidget, BTN_W, BTN_H
    _app.setStyleSheet(STYLESHEET)
    bl = BlockListWidget()
    bl.resize(400, 300)
    bl.show()
    _app.processEvents()
    try:
        _, ay, _, ah = _g(bl._add_btn, bl)
        _, hy, _, hh = _g(bl._add_btn.parentWidget(), bl)
        _, ly, _, _ = _g(bl._list, bl)
        assert hy <= ay and ay + ah <= hy + hh          # inside its header
        assert ay + ah <= ly                            # no overlap with list

        btns = [bl._dup_btn, bl._up_btn, bl._down_btn, bl._vis_btn, bl._del_btn]
        _, ry, _, rh = _g(btns[0].parentWidget(), bl)
        geo = [_g(b, bl) for b in btns]
        assert {(w, h) for _, _, w, h in geo} == {(BTN_W, BTN_H)}   # same size
        assert len({y for _, y, _, _ in geo}) == 1                  # centred together
        for _, y, _, h in geo:
            assert ry <= y and y + h <= ry + rh                     # not cut off
        top, bottom = geo[0][1] - ry, (ry + rh) - (geo[0][1] + geo[0][3])
        assert abs(top - bottom) <= 1                   # centred in the row
        assert [b.text() for b in btns] == ["Dup", "Up", "Dn", "Vis", "Del"]
        # Row style must not leak onto the buttons (stray top border).
        assert "#blockBtnRow" in btns[0].parentWidget().styleSheet()
    finally:
        bl.close()
        bl.deleteLater()
        _app.setStyleSheet("")
        _app.processEvents()
