"""Generate checks the program as LinuxCNC will run it (owner 2026-11-12).

A gouge into the finished part (incl. an arc LinuxCNC would run as a full
circle) or a rapid more than .003 into material that is still there stops the
program from being handed to Edit / Run; shallow brushes (nose scallops at a
free bar end, <= .0024) are one note.
"""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt5.QtWidgets import QApplication   # noqa: E402

_app = QApplication.instance() or QApplication([])   # kept alive for the module

from validation.rapid_collision import HIT_ERROR, RapidReport, operator_findings


def _r(depth, section="rough"):
    return RapidReport(0, section, (1.0, -0.5), (1.2, -0.5), 1e-5, depth, 0.0,
                       (1.0, 1.1, -0.51, -0.49))


def test_deep_rapid_hit_is_an_error_shallow_ones_one_note():
    errors, notes = operator_findings([_r(HIT_ERROR + 0.001), _r(0.002), _r(0.0023), _r(0.0)])
    assert len(errors) == 1 and "runs 0.0040 into material" in errors[0]
    assert len(notes) == 1 and notes[0].startswith("2 rapid(s) brush material up to 0.0023")


def test_no_hits_no_findings():
    assert operator_findings([_r(0.0), _r(0.0001)]) == ([], [])


def test_generate_refuses_to_hand_on_a_program_with_a_deep_rapid_hit(monkeypatch):
    """Through the GUI's own Generate: the program is shown, not emitted."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "regen", os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "regression", "regen.py"))
    regen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(regen)
    regen._record_dialogs()
    import validation.rapid_collision as rc
    real = rc.check_rapids

    def deep(gcode, plan):
        out = real(gcode, plan)
        return out + [_r(0.010)]
    monkeypatch.setattr(rc, "check_rapids", deep)
    prog = os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "regression", "corpus",
                        "Test Cut (T4 derived).json")      # T4: has the geometry the checks need
    if not os.path.exists(prog):
        pytest.skip("reference programs not present")
    table = os.path.expanduser("~/linuxcnc/configs/industry-cam/tool.tbl")
    if not os.path.exists(table):
        pytest.skip("lathe tool table not present")
    import tempfile
    r = regen.regenerate(os.path.abspath(prog), regen._tool_resolver(table), tempfile.mkdtemp())
    assert not r["generated"]
    assert "NOT sent to Edit/Run" in r["status"]
    assert any("Program not sent to Edit/Run" in d for d in r["dialogs"])
