"""The suite runs on the lathe's runtime, version for version (owner 2026-11-11:
"they should match all versions of lathe runtime deps").

requirements-lathe.txt is the lathe's exact set (pip freeze --user of the system
Python, ~/.local). The interpreter is Debian's Python 3.11 (LinuxCNC 2.9.6's
bindings are built for it) and PyQt5 is Debian's 5.15.9. If this fails, the tests
are running on something else - use scripts/run_tests.sh - or the lathe's packages
changed and requirements-lathe.txt must be updated with them.
"""
import os
import re
import sys
from importlib import metadata

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCK = os.path.join(REPO, "requirements-lathe.txt")

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="lathe runtime is Linux only")


def _pins():
    out = {}
    for line in open(LOCK):
        line = line.split("#", 1)[0].strip()
        m = re.match(r"^([A-Za-z0-9_.\-]+)==([^\s;]+)$", line)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def test_lock_file_lists_the_runtime_set():
    pins = {k.lower().replace("_", "-"): v for k, v in _pins().items()}
    for name in ("shapely", "pyqtgraph", "numpy", "scipy", "build123d", "cadquery-ocp",
                 "ocp-gordon", "ezdxf", "matplotlib", "pytest", "hypothesis"):
        assert name in pins, f"{name} missing from requirements-lathe.txt"


def test_interpreter_is_the_lathes():
    assert sys.version_info[:2] == (3, 11), (
        f"tests run on Python {sys.version.split()[0]}; the lathe GUI runs Debian's 3.11 "
        f"(scripts/run_tests.sh)")


@pytest.mark.parametrize("name,version", sorted(_pins().items()))
def test_installed_version_matches_lathe(name, version):
    try:
        got = metadata.version(name)
    except metadata.PackageNotFoundError:
        pytest.fail(f"{name}=={version} (requirements-lathe.txt) is not installed")
    assert got == version, f"{name}: {got} installed, lathe runs {version}"


def test_pyqt5_is_debians():
    from PyQt5.QtCore import PYQT_VERSION_STR
    assert PYQT_VERSION_STR == "5.15.9", f"PyQt5 {PYQT_VERSION_STR}; the lathe runs Debian's 5.15.9"


def test_fonts_are_the_lathes():
    """Pixel-budget layout tests (e.g. the Program column) depend on the fonts.
    The style guide asks for JetBrains Mono / Inter; neither is installed on the
    lathe, so Qt uses DejaVu (Debian fonts-dejavu-core 2.37-6). Installing other
    fonts changes the layouts: do it deliberately, re-check the layout tests,
    and update this pin."""
    import subprocess
    from PyQt5.QtGui import QFont, QFontInfo
    from PyQt5.QtWidgets import QApplication
    from gui.colors import FONTS
    _app = QApplication.instance() or QApplication([])  # noqa: F841
    from gui.components.segment_list import SEG_MONO_FAMILIES
    seg_font = QFont()
    seg_font.setFamilies(SEG_MONO_FAMILIES)              # as the segment list sets it
    assert QFontInfo(seg_font).family() == "DejaVu Sans Mono"
    # Asked for alone (numeric fields, some panels' stylesheets), the style
    # guide's mono family falls back to the PROPORTIONAL DejaVu Sans on the lathe.
    assert QFontInfo(QFont(FONTS["mono_family"])).family() == "DejaVu Sans"
    assert QFontInfo(QFont(FONTS["ui_family"])).family() == "DejaVu Sans"
    ver = subprocess.run(["dpkg-query", "-W", "-f=${Version}", "fonts-dejavu-core"],
                         capture_output=True, text=True).stdout
    assert ver == "2.37-6", f"fonts-dejavu-core {ver!r}; the lathe has 2.37-6"


def test_display_dpi_is_the_lathes():
    """The lathe's display is 1920x1080 at 96 DPI; layouts are measured at it."""
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    assert round(app.primaryScreen().logicalDotsPerInch()) == 96


def test_machine_bindings_are_blocked_in_tests():
    with pytest.raises(ImportError):
        import linuxcnc  # noqa: F401
    from hal.factory import get_backend, reset_backend
    reset_backend()
    try:
        assert type(get_backend()).__name__ == "MockBackend"
    finally:
        reset_backend()
