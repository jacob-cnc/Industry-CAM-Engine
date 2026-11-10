"""Jog section 'Clear Trail' button: real 50 px height that its section
reserves (no spill-over), centred between the Mode combo and the next
section's header."""

from PyQt5.QtCore import QPoint
from PyQt5.QtWidgets import QApplication, QComboBox, QPushButton

_app = QApplication.instance() or QApplication([])


def _y(w, win):
    return w.mapTo(win, QPoint(0, 0)).y()


def test_clear_trail_centred_and_inside_section():
    from gui.main_window import MainWindow
    from gui.colors import STYLESHEET
    from gui.components.collapsible_section import CollapsibleSection
    _app.setStyleSheet(STYLESHEET)            # the app-wide rule it must beat
    w = MainWindow()
    w.resize(1918, 1034)
    w.show()
    w.tab_widget.setCurrentWidget(w._manual_tab)
    _app.processEvents()
    try:
        secs = w._manual_tab.findChildren(CollapsibleSection)
        jog = next(s for s in secs if "Jog" in s._header.text())
        nxt = next(s for s in secs if "Compound" in s._header.text())
        jog.set_expanded(True)
        _app.processEvents()
        _app.processEvents()
        combo = jog._content.findChildren(QComboBox)[0]
        btn = next(b for b in jog._content.findChildren(QPushButton)
                   if b.text() == "Clear Trail")
        top, bottom = _y(btn, w), _y(btn, w) + btn.height()
        above = top - (_y(combo, w) + combo.height())
        below = _y(nxt._header, w) - bottom
        assert btn.height() == 50
        assert abs(above - below) <= 1, (above, below)
        assert bottom <= _y(jog._content, w) + jog._content.height()  # no spill
    finally:
        w._status_timer.stop()
        w._cycle_btn_timer.stop()
        w.close()
        w.deleteLater()
        _app.setStyleSheet("")
        _app.processEvents()
