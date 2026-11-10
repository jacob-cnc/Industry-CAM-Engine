"""Shared test setup.

GUI tests must lay out like the app: on Windows, gui/main_window.main()
pins Qt's font DPI to 96 (the lathe's) before the QApplication exists.
Without the same pin here, whichever test module creates the QApplication
first decides the DPI for the whole run (e.g. 144 on a 150 % desktop), and
pixel-budget layout tests then depend on test order.
"""

import os
import sys

if sys.platform == "win32":
    os.environ.setdefault("QT_FONT_DPI", "96")
