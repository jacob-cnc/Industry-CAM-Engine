#!/usr/bin/env python3
"""Regenerate saved programs exactly as the GUI's Generate button does, headless.

For every program (.json saved by the Program tab) this loads it into a real
ProgramTab (Qt offscreen), resolves tools from a tool table, runs
`_on_generate_clicked()` and records what came out:

    OUT/<name>.ngc            the combined G-code, byte for byte what the GUI shows
    OUT/<name>.result.json    status line, notes, and the cut sections that the
                              GUI shades (face / rough / cleanup / finish / finished /
                              uncut / gouge / not_removed) as rings in (z, r), plus areas

The cut sections come from LinuxCNC's own interpreter (rs274) through
outputs/cut_regions.py: the nose circle and insert wedge swept along the path
LinuxCNC will really run. That is the machinist-level record compare.py uses.

Nothing here talks to the machine. Refuses to run while LinuxCNC is up (the
test-suite rule: heavy work next to the realtime thread froze the PC).

usage: regen.py [--repo DIR] --tool-table TBL --out DIR prog.json [prog.json ...]
       --repo: the checkout whose code generates (default: this one), e.g. a
               detached worktree of main for the baseline.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _refuse_if_linuxcnc_up() -> None:
    for name in ("milltask", "rtapi_app", "linuxcncsvr"):
        if subprocess.run(["pgrep", "-x", name], capture_output=True).returncode == 0:
            sys.exit(f"LinuxCNC is running ({name}): shut it down first.")


def _tool_resolver(table_path: str):
    from pipeline.tool_card_data import tool_card_to_tool_def
    from pipeline.tool_table_io import load_tool_table
    cards = {c.tool_number: c for c in load_tool_table(table_path)}
    return lambda n: tool_card_to_tool_def(cards[n]) if n in cards else None


SECTION_KEYS = ("face", "rough", "cleanup", "finish", "finished", "uncut", "gouge", "not_removed")


def _sections(section_inputs) -> dict:
    """Union per section over all profile blocks, exactly as the GUI shades them,
    from outputs/cut_regions.compute_sections. Geometry in radius space (r, z)."""
    from outputs.cut_regions import compute_sections, CutRegionsUnavailable
    from shapely.ops import unary_union
    parts = {k: [] for k in SECTION_KEYS}
    notes = []
    for gcode_text, plan_result, outlines in section_inputs:
        try:
            sec = compute_sections(gcode_text, plan_result, outlines)
        except CutRegionsUnavailable as exc:
            notes.append(f"sections unavailable: {exc}")
            continue
        for k in SECTION_KEYS:
            parts[k].append(getattr(sec, k))
    return {k: unary_union(v) if v else None for k, v in parts.items()}, notes


_DIALOGS: list = []


def _record_dialogs() -> None:
    """Headless runs can't click: every QMessageBox the GUI would show is recorded
    (title + text go into the program's notes) and answered with the dialog's own
    default button (No/Cancel-style for questions), never a choice the GUI
    wouldn't make by default. Any other modal dialog is rejected and recorded."""
    from PyQt5.QtWidgets import QMessageBox, QDialog

    def make(kind, fallback):
        def fake(parent, title, text, buttons=None, default=None, *a, **k):
            default = k.get("defaultButton", default)
            _DIALOGS.append(f"[{kind}] {title}: {text}")
            return default if default not in (None, QMessageBox.NoButton) else fallback
        return staticmethod(fake)
    QMessageBox.information = make("information", QMessageBox.Ok)
    QMessageBox.warning = make("warning", QMessageBox.Ok)
    QMessageBox.critical = make("critical", QMessageBox.Ok)
    QMessageBox.question = make("question", QMessageBox.No)

    def reject(self, *a, **k):
        from PyQt5.QtWidgets import QLabel, QTextEdit, QPlainTextEdit
        texts = [w.text() for w in self.findChildren(QLabel) if w.text().strip()]
        texts += [w.toPlainText() for w in self.findChildren((QTextEdit, QPlainTextEdit))
                  if w.toPlainText().strip()]
        body = " | ".join(t.strip().replace("\n", " ") for t in texts)[:1500]
        _DIALOGS.append(f"[dialog] {type(self).__name__} {self.windowTitle()}: {body} (rejected, headless)")
        return QDialog.Rejected
    QDialog.exec_ = reject
    QDialog.exec = reject


def regenerate(program_path: str, resolver, out_dir: str) -> dict:
    from gui.program_tab import ProgramTab, ProgramState
    name = os.path.splitext(os.path.basename(program_path))[0]
    tab = ProgramTab()
    _DIALOGS.clear()
    try:
        tab.set_tool_resolver(resolver)
        with open(program_path) as f:
            tab._load_program_data(json.load(f))
        tab.set_state(ProgramState.READY)
        t0 = time.time()
        tab._on_generate_clicked()
        dt = time.time() - t0
        code = getattr(tab, "_last_gcode_text", None) or ""
        sections, sec_notes = _sections(getattr(tab, "_section_inputs", []))
        result = {
            "program": program_path,
            "status": tab._status_label.text(),
            "notes": list(getattr(tab, "_generate_notes", [])) + sec_notes,
            "dialogs": list(_DIALOGS),
            "generated": bool(code),
            "seconds": round(dt, 2),
            "areas": {k: (g.area if g is not None else None) for k, g in sections.items()},
            "wkt": {k: (g.wkt if g is not None else None) for k, g in sections.items()},
        }
    finally:
        tab.close()
        tab.deleteLater()
    with open(os.path.join(out_dir, name + ".ngc"), "w") as f:
        f.write(code)
    with open(os.path.join(out_dir, name + ".result.json"), "w") as f:
        json.dump(result, f, indent=1, default=lambda o: list(o) if isinstance(o, tuple) else str(o))
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=REPO, help="checkout whose code generates")
    ap.add_argument("--tool-table", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("programs", nargs="+")
    a = ap.parse_args()
    _refuse_if_linuxcnc_up()
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("QT_FONT_DPI", "96")
    repo = os.path.abspath(a.repo)
    programs = [os.path.abspath(p) for p in a.programs]
    out = os.path.abspath(a.out)
    table = os.path.abspath(a.tool_table)
    sys.path.insert(0, repo)
    os.chdir(repo)
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])          # noqa: F841 (keeps Qt alive)
    _record_dialogs()
    os.makedirs(out, exist_ok=True)
    resolver = _tool_resolver(table)
    import gui.program_tab as _pt
    print(f"generating with {os.path.dirname(os.path.dirname(_pt.__file__))}")
    bad = 0
    for p in programs:
        r = regenerate(p, resolver, out)
        flag = "OK " if r["generated"] else "BAD"
        bad += not r["generated"]
        a_ = {k: (v or 0.0) for k, v in r["areas"].items()}
        print(f"{flag} {os.path.basename(p)}: {r['seconds']}s  gouge={a_.get('gouge', 0):.2e} "
              f"not_removed={a_.get('not_removed', 0):.2e}  notes={len(r['notes'])} dialogs={len(r['dialogs'])}  | {r['status'][:90]}", flush=True)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
