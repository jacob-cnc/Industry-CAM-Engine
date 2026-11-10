"""Manual tab coord toggle: 50 px, centred between the tab row and the X
DRO, text styled like ribbon bar 2 (state label)."""

from PyQt5.QtCore import QPoint
from PyQt5.QtGui import QFontInfo
from PyQt5.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])


def test_coord_toggle_size_position_and_text():
    from gui.main_window import MainWindow
    from gui.colors import STYLESHEET
    _app.setStyleSheet(STYLESHEET)            # the app-wide rule it must beat
    w = MainWindow()
    w.resize(1918, 1034)
    w.show()
    w.tab_widget.setCurrentWidget(w._manual_tab)
    _app.processEvents()
    try:
        btn = w._manual_tab._coord_toggle
        dro = w._manual_tab._dro_x
        tb = w.tab_widget.tabBar()
        tabs_bottom = tb.mapTo(w, QPoint(0, tb.height())).y()
        top = btn.mapTo(w, QPoint(0, 0)).y()
        bottom = top + btn.height()
        dro_top = dro.mapTo(w, QPoint(0, 0)).y()

        assert btn.height() == 50
        assert abs((top - tabs_bottom) - (dro_top - bottom)) <= 1   # centred
        for state in (False, True):            # G54 and G53 labels alike
            btn.setChecked(state)
            _app.processEvents()
            assert btn.height() == 50

        lab = w.status_bar._state_label
        fb, fl = QFontInfo(btn.font()), QFontInfo(lab.font())
        assert (fb.family(), fb.pixelSize(), btn.font().bold()) == \
            (fl.family(), fl.pixelSize(), lab.font().bold())
        btn.setChecked(False)
        assert btn.palette().color(btn.foregroundRole()) == \
            lab.palette().color(lab.foregroundRole())
    finally:
        w._status_timer.stop()
        w._cycle_btn_timer.stop()
        w.close()
        w.deleteLater()
        _app.setStyleSheet("")
        _app.processEvents()
