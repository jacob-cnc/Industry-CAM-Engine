"""Run-from-line resume program: modal restore and refusals."""

import pytest

from outputs.run_from_line import (
    RunFromError, build_resume_program, find_n_line, has_n_numbers)

PROG = """%
; header comment
N10 G20 G7 G18 G40 G49 G80  ; Safety line
N20 G90 G95  ; abs, feed/rev
N30 S64 M3  ; spindle
N40 G00 X4.0000 Z2.0000  ; park
N50 T1 M6  ; tool
N60 G43  ; TLO
; --- tool check: program generated for T1 D0.031400 Q3 ---
o9001 if [[#5400 NE 1] OR [#5413 NE 3]]
  (DEBUG, TOOL MISMATCH)
  M0
o9001 endif
N70 G40  ; comp off
N80 G00 X3.1000 Z0.1000
N90 G01 X3.1000 Z-0.5000 F0.0080
N100 X3.0500  ; modal G1, no motion word
N110 G00 X2.9000 Z0.1000
N120 G41  ; comp on
N130 G01 X3.0960 Z0.0015
N140 G01 X3.0960 Z-0.5585
N150 G40
N160 G00 X2.9400 Z0.0015
N170 M5
N180 M2
%
"""


def _plan(n, **kw):
    return build_resume_program(PROG, find_n_line(PROG, n), **kw)


def test_n_lookup_beyond_line_count():
    # N180 is far past the file's line count - the case the old box rejected.
    assert has_n_numbers(PROG)
    idx = find_n_line(PROG, 180)
    assert idx is not None and 180 > len(PROG.splitlines())
    assert find_n_line(PROG, 175) is None


def test_preamble_restores_modal_state_and_tool():
    plan = _plan(110, tool_in_spindle=0)
    pre = [l.split("(")[0].strip() for l in plan.preamble]
    assert pre[0].split() == ["G20", "G7", "G18", "G90", "G91.1", "G95",
                              "G40", "G80", "G98"]
    assert "G54" in pre and "T1 M6" in pre and "G43" in pre
    assert "G97 S64 M3" in pre and "M9" in pre and "F0.008" in pre
    # tool check repeated verbatim, including its DEBUG message
    assert any("o9001 if" in l for l in plan.preamble)
    assert any("DEBUG, TOOL MISMATCH" in l for l in plan.preamble)
    assert plan.preamble.index("T1 M6  (load tool used at this line)") < \
        next(i for i, l in enumerate(plan.preamble) if "o9001 if" in l)
    assert (plan.state.x, plan.state.z) == (3.05, -0.5)


def test_program_text_and_line_mapping():
    plan = _plan(110, tool_in_spindle=0)
    out = plan.program_text.splitlines()
    assert out[0] == "%" and out[-1] == "%"
    assert out[plan.resume_start_index].startswith("N110 G00")
    # nothing before the start line is copied
    assert not any(l.startswith(("N50", "N90")) for l in out)
    src = PROG.splitlines()
    assert plan.source_line(plan.resume_start_index + 1) == find_n_line(PROG, 110) + 1
    assert src[plan.source_line(plan.resume_start_index + 2) - 1].startswith("N120")
    assert plan.source_line(1) == 0


def test_no_tool_change_when_tool_already_loaded():
    plan = _plan(110, tool_in_spindle=1)
    assert not any("M6" in l for l in plan.preamble)
    assert any(l.startswith("G43") for l in plan.preamble)


def test_modal_motion_added_to_start_line():
    plan = _plan(100, tool_in_spindle=1)
    assert plan.first_line.startswith("N100 G1 X3.0500")


def test_refuses_inside_cutter_comp():
    with pytest.raises(RunFromError, match="Cutter comp"):
        _plan(130)
    _plan(150)              # starting on the G40 line: nothing to restore
    _plan(120)              # the comp-on line itself is allowed
    _plan(160)              # after G40


def test_refuses_unrestorable_constructs():
    base = "N10 G20 G7 G18\nN20 G90 G94\n"
    with pytest.raises(RunFromError, match="O-word"):
        build_resume_program(base + "o100 sub\no100 endsub\nN30 G0 X1 Z1\n", 4)
    with pytest.raises(RunFromError, match="G91"):
        build_resume_program(base + "N30 G91\nN40 G0 X1 Z1\n", 3)
    with pytest.raises(RunFromError, match="G92"):
        build_resume_program(base + "N30 G92 X0\nN40 G0 X1 Z1\n", 3)
    with pytest.raises(RunFromError, match="parameters"):
        build_resume_program(base + "N30 #1=2\nN40 G0 X1 Z1\n", 3)
    with pytest.raises(RunFromError, match="G76"):
        build_resume_program(base + "N30 G0 X1 Z.1\nN40 G76 P.05 Z-1 I-.02 J.01 K.03\n", 3)


def test_css_coolant_and_defaults():
    prog = ("N10 G21\nN20 G96 D1500 S120 M4\nN30 M8\nN35 M7\nN40 M9\nN45 M8\n"
            "N50 G0 X10 Z5\nN60 G1 Z-5 F0.2\n")
    plan = build_resume_program(prog, 7)
    pre = [l.split("(")[0].strip() for l in plan.preamble]
    # units from program; G7/G18 from the machine startup code (INI)
    assert pre[0].split()[:3] == ["G21", "G7", "G18"]
    assert "G96 D1500 S120 M4" in pre
    assert "M8" in pre
    assert "G49" in pre and not any("M6" in l for l in pre)
    assert not plan.program_text.startswith("%")


# --- Run tab integration (mock backend) -----------------------------------

def test_run_tab_types_n_number_and_runs_resume_program(monkeypatch, tmp_path):
    import os
    from PyQt5.QtCore import Qt
    from PyQt5.QtTest import QTest
    from PyQt5.QtWidgets import QApplication, QMessageBox
    from hal.factory import get_backend
    from hal.interface import InterpState, TaskMode
    app = QApplication.instance() or QApplication([])  # noqa: F841
    b = get_backend(force_mock=True)
    b.estop_reset(); b.machine_on(); b._interp_state = InterpState.IDLE
    b._task_mode = TaskMode.MANUAL
    from gui.run_tab import RunTab
    tab = RunTab()
    opened, runs = [], []
    monkeypatch.setattr(b, "program_open", lambda p: opened.append(p) or True)
    monkeypatch.setattr(b, "program_run", lambda start_line=0: runs.append(start_line) or True)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    src = tmp_path / "job.ngc"
    src.write_text(PROG)
    tab._load_gcode_file(str(src))
    assert tab._lbl_from.text() == "From N:"

    # Typing a 3-digit N number larger than the file's line count is accepted.
    spin = tab._line_spin
    spin.lineEdit().selectAll()
    QTest.keyClicks(spin, "110")
    QTest.keyClick(spin, Qt.Key_Return)
    assert spin.value() == 110

    tab._on_run_from_line()
    resume = opened[-1]
    assert resume != str(src) and runs == [0]
    text = open(resume).read()
    assert "T1 M6" in text and "N110 G00" in text and "N50 T1 M6" not in text
    # LinuxCNC line numbers are mapped back to source lines for highlighting
    assert tab._resume_plan.source_line(tab._resume_plan.resume_start_index + 1) \
        == find_n_line(PROG, 110) + 1

    # When the run ends the source program is reopened in LinuxCNC.
    tab._set_idle_state()
    assert opened[-1] == str(src) and tab._resume_plan is None
    os.unlink(resume)
