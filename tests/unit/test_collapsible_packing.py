"""CollapsibleSection packing: collapsed sections are exactly header-height
and pack together; expanded sections get the free height."""

import pytest
from PyQt5.QtCore import QPoint
from PyQt5.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from gui.components.collapsible_section import CollapsibleSection

_app = QApplication.instance() or QApplication([])


def _y(w, root):
    return w.mapTo(root, QPoint(0, 0)).y()


def test_collapsed_is_header_height_and_min_restored():
    s = CollapsibleSection("S", expanded=True)
    s.add_widget(QLabel("content"))
    s.setMinimumHeight(240)
    s.show()
    s.set_expanded(False)
    _app.processEvents()
    assert s.minimumHeight() == 0
    assert s.sizeHint().height() == CollapsibleSection.HEADER_HEIGHT
    s.setMinimumHeight(300)              # set while collapsed: remembered
    assert s.minimumHeight() == 0
    s.set_expanded(True)
    assert s.minimumHeight() == 300
    s.close()


def test_header_drawn_inside_its_section():
    """In a parent layout (as in the app), the header fills the section
    exactly: no 10 px overhang into the next section."""
    from gui.colors import STYLESHEET
    _app.setStyleSheet(STYLESHEET)       # the app-wide rule that caused it
    root = QWidget()
    lay = QVBoxLayout(root)
    a = CollapsibleSection("A", expanded=False)
    b = CollapsibleSection("B", expanded=False)
    lay.addWidget(a)
    lay.addWidget(b)
    lay.addStretch()
    root.resize(300, 400)
    root.show()
    _app.processEvents()
    try:
        for s in (a, b):
            assert s._header.y() == 0
            assert s._header.height() == s.height() == CollapsibleSection.HEADER_HEIGHT
        assert _y(a._header, root) + a._header.height() <= _y(b, root)
    finally:
        root.close()
        _app.setStyleSheet("")


@pytest.mark.parametrize("open_profile", [False, True])
def test_program_tab_sections_pack(open_profile):
    from gui.main_window import MainWindow
    w = MainWindow()
    w.resize(1918, 1034)
    w.show()
    w.tab_widget.setCurrentWidget(w.program_tab)
    _app.processEvents()
    try:
        pt = w.program_tab
        inner = [pt._section_blocks, pt._section_stock, pt._section_roughing,
                 pt._section_finishing]                  # inside Parameters
        params = pt._section_parameters
        for s in inner + [pt._section_profile]:
            s.set_expanded(False)
        params.set_expanded(True)
        pt._section_profile.set_expanded(open_profile)
        _app.processEvents()
        _app.processEvents()
        tops = [_y(s, w) for s in inner]
        heights = [s.height() for s in inner]
        for i in range(len(inner) - 1):
            gap = tops[i + 1] - (tops[i] + heights[i])
            assert 0 <= gap <= 4, (i, tops, heights)    # packed, no dead space
        for s in inner:
            assert s.height() == CollapsibleSection.HEADER_HEIGHT
        # Parameters ends right after its last section; Profile right after it.
        params_bottom = _y(params, w) + params.height()
        assert 0 <= params_bottom - (tops[-1] + heights[-1]) <= 4
        assert 0 <= _y(pt._section_profile, w) - params_bottom <= 4
        prof = pt._section_profile
        gen_top = _y(pt._generate_btn, w)
        if open_profile:           # takes the free height down to Generate
            assert gen_top - (_y(prof, w) + prof.height()) <= 8
        else:
            assert prof.height() == CollapsibleSection.HEADER_HEIGHT
    finally:
        w._status_timer.stop()
        w._cycle_btn_timer.stop()
        w.close()
        w.deleteLater()
        _app.processEvents()
