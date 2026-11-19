# Session Notes — 2026-11-18 — two GUI failures on the lathe

Branch `claude/run-from-open-race`, base main 78a3d50. Diagnosis from the
owner's two failures on the machine that evening. **Software only — no HAL,
INI, offsets or tool-table changes, and nothing here is machine-tested.**

## The two failures were unrelated

| # | When | What the owner was doing | Evidence |
|---|---|---|---|
| 1 | 18:16:49 PST | working in the **Edit tab** | kernel: `python3[1941]: segfault at 0 ... in libQt5Gui.so.5.15.8` |
| 2 | 17:20 / 17:41 / 18:25 PST | **Run From** a line, with no normal run first in that session | `Linear move on line 53 would exceed X's negative limit`, `invalid params in linear command`, `USRMOT: ERROR: invalid command` |

LinuxCNC's own report for the 16:33–18:16 session is `/tmp/linuxcnc.report`
(tmpfs — gone at reboot); the GUI log is `/tmp/lcnc_gui.log`.

## 1. Edit-tab segfault — Qt asked for a text line that does not exist

The faulting address resolves exactly. Mapping base `0x7fcecfef2000` is the
library's executable segment (`readelf -l`: vaddr `0xe2000`), so the file
address is `0xe2000 + 0x15caa4 = 0x23eaa4`:

```
000000000023eaa0 <QTextLine::textStart() const>:
  23eaa0:  mov 0x8(%rdi),%rax      # rax = this->eng  (QTextEngine*)
  23eaa4:  mov (%rax),%rdx         # <-- faulted, rax == 0
```

A `QTextLine` with a null engine is an invalid line — Qt was asked to position
text for a line its layout does not have. There is no `QTextLayout` or
`QTextLine` anywhere in this repo, so this happened inside Qt, reached from
ordinary widget use.

The one path that reaches into the editor's layout from outside a keystroke is
sim playback: `edit_tab.py` wires `sim_viewer.sim_line_changed` →
`_highlight_editor_line`, which ran on a **QTimer tick** and called
`setExtraSelections`, `setTextCursor` and `centerCursor` on the editor the
operator may be typing in, while `setPlainText` can re-enter from
`textChanged` → `gcode_modified`. That is a known shape for this class of Qt
crash. **Not proven** — the Python frames were never captured, because nothing
enabled `faulthandler`.

Changes:
- `gui/main_window.py`: `faulthandler.enable()` at the top of `main()`. The
  next segfault prints a Python stack to stderr, which `display_gui.sh`
  appends to `/tmp/lcnc_gui.log`. This is the only thing that will *prove* the
  cause.
- `gui/edit_tab.py` `_highlight_editor_line`: returns immediately while the
  editor has focus; validates the block; and scrolls with the vertical scroll
  bar instead of `setTextCursor()` + `centerCursor()`. Moving the caret under
  a typist was a functional bug in its own right.
- `gui/edit_tab.py` `GCodeEditor.__init__`: `setLineWrapMode(NoWrap)` — one
  block is now one visual row, which both the line-number gutter and the new
  block-numbered playback scroll rely on (and wrapped G-code is unreadable).
- `gui/edit_tab.py` `line_number_area_paint_event`: `break` after
  `block.next()` turns up invalid, instead of measuring it with
  `blockBoundingRect()`. Qt happens to guard that, but the loop should not
  depend on it.

## 2. Run From — the GUI aborted its own file open

Owner's decisive observation: Run From works **if the program is first loaded,
run normally from the top, and stopped**; it fails in a session where it was
never run. The code reproduces that asymmetry exactly.

- **Normal start** (`run_tab._start_from_line` → `_ensure_source_loaded`)
  returns at once because `_backend_file == _gcode_path` — the file was opened
  back at *load* time. Cycle start issues no `program_open`, the interpreter
  has been idle for minutes, and `program_run` only switches mode.
- **Run From** (`run_tab._on_run_from_line`) called `program_open(resume)` and
  `program_run(start_line=0)` in consecutive statements. `program_open` never
  `wait_complete()`d after `_cmd.program_open(path)`, so the interpreter was
  still `INTERP_READING` when `program_run` → `_ensure_mode(AUTO)` ran — and
  `_ensure_mode` issued `_cmd.abort()` on *any* non-idle interp state. The
  abort threw the open away, and `auto(AUTO_RUN, 0)` then ran the file task
  still had open: **the source program, from line 1.**
- Warm works because `task_mode` is still `AUTO` after a normal run + Stop, so
  `_ensure_mode` returns `True` at its first check and never aborts.
- `_program_busy()` could not guard this: it starts with
  `if s.task_mode != MODE_AUTO: return False`, so it never reports busy in
  MANUAL.

This matches the one hard clue: LinuxCNC named **line 53**, which exists only
in the 107-line source — not in either resume file (30 and 45 lines).

Changes in `hal/live_backend.py`:
- `program_open`: `wait_complete()` after `_cmd.program_open(path)`, then
  confirm via new `_opened_file_is()` (bounded ~1 s poll of `stat.file`,
  realpath compare) and return `False` if LinuxCNC has a different file open.
  The run tab already treats `False` as "refused" and never runs.
- `_ensure_mode`: waits up to `_INTERP_SETTLE_S` (1 s) for the interpreter to
  go idle, and only aborts when `task_mode == MODE_MDI` — the stuck-MDI case
  the abort was added for. Otherwise it logs and returns `False` instead of
  aborting. Stock AXIS's `ensure_mode` never aborts at all.
- `program_run` / `program_step`: one `_log_run_state()` INFO line with the
  open file, tool in spindle, G54 X/Z, tool offset X/Z and whether G7/G18 are
  active. The wrong-file run was only identifiable from LinuxCNC's own line
  numbers; now it is in the GUI log.

### What is NOT established
- **Which move** tripped the soft limit. The error comes from motmod's
  `inRange()` (strings are in `motmod.so`, not `milltask`), so a move's
  machine-coordinate target was below joint 0's `MIN_LIMIT = -0.05`. The
  source program was regenerated at **17:55**, *after* the failures, so its
  line 53 at the time is gone, and no offsets/open-file were logged. With the
  G54 X origin now at +0.9305 (`industry-cam.var` #5221) and T3's offsets all
  zero, no move in either surviving file can violate that limit.
- Whether the Edit-tab crash is the playback path (see above).

### Also seen, not changed
In the 18:25 incident every state command logged
`estop_reset: command accepted (5.00 s)` — `_state_async` logs "accepted"
after `linuxcnc.command().state()` returns, and that call returns on its own
5 s timeout, so a task that has stopped answering reads as success. The
`STATE_ACK_WARN_S` warning does fire, but the log line is actively
misleading for estop/machine-on. Left alone deliberately: it is a separate
change to a safety-adjacent path, and the comment above it records the same
symptom from 2026-11-10.

## Verification (LinuxCNC down, lathe runtime)
- `scripts/run_tests.sh` — see the branch commit message for counts.
- `python -m validation.architecture_check`: 15 errors / 130 warnings, byte
  for byte the same as main 78a3d50 in the live checkout. No new violations.
- `git diff --check` clean.
- New tests: `tests/unit/test_run_from_open_guard.py` (a refused open never
  reaches `program_run`; a confirmed open runs the resume file from line 0) and
  `tests/unit/test_edit_tab_playback_highlight.py` (caret untouched, stands
  down on focus, out-of-range lines, gutter paints past the last block,
  NoWrap). `LiveBackend` itself cannot be unit-tested — `tests/conftest.py`
  makes the `linuxcnc` binding unimportable on purpose.

## Machine verification still owed
1. Cold session, no normal run: load a program, **Run From** a mid-program
   line. It must either run the resume file or refuse with an error — never
   run the source from the top. Check the new `program_run:` log line names
   the `- from line N.ngc` file.
2. Confirm Run From still works warm (run from top, Stop, Run From).
3. Tool change via MDI, then a mode switch, to confirm the narrowed abort
   still clears a stuck MDI interpreter.
4. Edit tab: run sim playback while typing. The caret must stay put, and if it
   ever dies again `/tmp/lcnc_gui.log` should now carry a Python traceback.

Rollback: `lathe-2026-11-16-working` (71ce670) remains the owner-proven point;
this branch is not merged.
