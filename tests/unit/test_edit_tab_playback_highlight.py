"""The Edit tab's playback highlight must not fight the operator (lathe 2026-11-18).

The GUI segfaulted inside Qt's own text layout - QTextLine::textStart() with a
null QTextEngine, i.e. Qt asked for a text line that does not exist - while the
owner was working in the Edit tab. Sim playback drives
EditTab._highlight_editor_line from a QTimer, and it used to call
setTextCursor() + centerCursor() on the very editor the operator may be typing
in. These tests pin the new contract: the caret is never moved, the highlight
stands down while the editor has focus, and the line-number gutter never
measures a block past the end of the document.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PyQt5.QtGui import QPixmap  # noqa: E402
from PyQt5.QtWidgets import QApplication, QPlainTextEdit  # noqa: E402

_app = QApplication.instance() or QApplication([])

from gui.edit_tab import EditTab  # noqa: E402

PROGRAM = "\n".join(f"N{10 * (i + 1)} G01 X{i / 10:.4f} Z-{i / 10:.4f} F0.003"
                    for i in range(40))
LINES = len(PROGRAM.splitlines())


@pytest.fixture
def tab():
    t = EditTab()
    t.receive_gcode(PROGRAM)
    yield t
    t.close()
    t.deleteLater()


def test_highlight_does_not_move_the_caret(tab):
    editor = tab._editor
    cursor = editor.textCursor()
    cursor.setPosition(0)
    editor.setTextCursor(cursor)

    tab._highlight_editor_line(25)

    assert editor.textCursor().position() == 0, "playback moved the operator's caret"
    assert len(editor.extraSelections()) == 1, "the line should still be highlighted"


def test_highlight_scrolls_towards_the_line(tab):
    editor = tab._editor
    editor.resize(320, 120)
    editor.show()
    _app.processEvents()
    bar = editor.verticalScrollBar()
    bar.setValue(0)

    tab._highlight_editor_line(LINES - 5)

    assert bar.value() <= bar.maximum()
    if bar.maximum() > 0:
        assert bar.value() > 0


def test_highlight_stands_down_while_the_editor_has_focus(tab, monkeypatch):
    editor = tab._editor
    editor.setExtraSelections([])
    monkeypatch.setattr(type(editor), "hasFocus", lambda self: True)

    tab._highlight_editor_line(10)

    assert editor.extraSelections() == [], "playback highlighted while the user was typing"


@pytest.mark.parametrize("idx", [-1, LINES, LINES + 1, 10_000])
def test_line_outside_the_document_clears_and_never_raises(tab, idx):
    tab._highlight_editor_line(idx)
    assert tab._editor.extraSelections() == []


def test_editor_does_not_wrap(tab):
    """One block == one visual row; the gutter and the playback scroll rely on it."""
    assert tab._editor.lineWrapMode() == QPlainTextEdit.NoWrap


def test_gutter_paints_past_the_last_block(tab):
    """The paint loop measured block.next() before checking it was valid."""
    editor = tab._editor
    editor.resize(320, 900)          # viewport taller than the whole program
    editor.show()
    _app.processEvents()
    gutter = editor._line_number_area
    pm = QPixmap(max(1, gutter.width()), max(1, gutter.height()))
    gutter.render(pm)                # drives paintEvent across the document end
