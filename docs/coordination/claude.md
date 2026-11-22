# Claude status

## 2026-11-22 REVIEW-READY (lathe PC session): on-screen X/Z jog buttons removed; claims released
- Owner request: delete the four on-screen pushbutton-jog buttons from the Manual
  tab's Jog Controls section. The Speed spin box, MPG Mode combo and Clear Trail
  stay. Arrow-key velocity jog (keyPressEvent/keyReleaseEvent -> _jog_start/
  _jog_end) is unaffected and stays.
- Application branch: claude/remove-onscreen-jog-buttons, base main 28fb225.
- Claimed paths (GUI manual lane; no CAM/planner/writer/HAL/INI/tool-table):
  gui/manual/sections.py (build_jog_section), gui/manual/manual_tab.py
  (_connect_signals jog-button wiring only).
- No overlap expected with the three open side-session PRs (#7 jog-speed preset
  touches hal/constants.py + industry-cam.hal + help_tab.py, #8 tests/conftest.py,
  #9 .kiro/steering/dev-tooling.md). None of those touch gui/manual/.
- Codex: shout if you hold uncommitted work in gui/manual/ (none expected).
- Result: commit 3b857ae on origin/claude/remove-onscreen-jog-buttons, base
  main cd2f3a3. Two files: gui/manual/sections.py (jog button grid + the four
  QPushButtons + their widget-dict keys deleted; header "Pushbutton Jog (hold to
  move)" -> "Pushbutton Jog", now labelling the Speed row only; QGridLayout
  import dropped) and gui/manual/manual_tab.py (the eight pressed/released
  connects deleted). No other section, no HAL, no INI, no tool table.
- _jog_start/_jog_end are NOT removed: the arrow-key handlers still call them,
  so arrow-key velocity jog is unchanged. Speed spin box, MPG Mode combo and
  Clear Trail all unchanged.
- NOT VERIFIED: py_compile passes on both files, but the pytest suite was not
  run - LinuxCNC is up on the lathe PC and scripts/run_tests.sh refuses in that
  state. The GUI has not been restarted, so the change is not seen on screen yet.
  Needs a run_tests.sh pass with LinuxCNC down plus a GUI launch before merge.
- State: review-ready; claims on gui/manual/sections.py and
  gui/manual/manual_tab.py released.

## 2026-11-22 — REVIEW-READY (side session): three PRs, claims released
- **PR #7** `feat/jog-speed-extra-slow-preset` (commit 6a9c8a2, base main cd2f3a3):
  adds the "Extra Slow" MPG velocity jog preset → Extra Slow / Slow / Medium /
  Fast. hal/constants.py, industry-cam.hal (mux8 in4/in5), hal/live_backend.py,
  gui/help_tab.py. Software-only, NOT machine-run — needs a lathe verify of the
  mux8 scales. Claude HAL/manual lane; no Codex overlap.
- **PR #8** `fix/qsettings-test-isolation` (base main cd2f3a3): redirects
  QSettings to a temp INI in tests/conftest.py so the suite never writes the real
  store (Windows registry / ~/.config) and GUI-toggle state can't leak between
  tests. Fixes 3 Windows run-from failures caused by a leaked single_block=true.
  Claimed path: **tests/conftest.py** only. Codex: no overlap with your CAM test
  files; shout if you hold uncommitted conftest work (none expected).
- **PR #9** `docs/dev-tooling-real-env` (base main cd2f3a3): rewrites
  .kiro/steering/dev-tooling.md, which described a fictional Python 3.15 system /
  3.12 uv venv, to the real Python 3.11.9 .venv (requirements-lathe.txt + PyQt5
  5.15.9) with the Windows run notes. Docs-only. Claimed path:
  **.kiro/steering/dev-tooling.md** only.
- Built a parity test env on the Windows authoring box (was Python-less): Python
  3.11.9 + requirements-lathe.txt versions (incl. cadquery-ocp 7.8.1.1.post1, vtk
  9.3.1, build123d 0.10.0) + PyQt5 5.15.9. Full suite with PR #8: 1400 passed / 1
  failed / 138 skipped. The lone failure is a pyqtgraph overlay under pip's Qt
  5.15.2 vs the lathe's Qt 5.15.9 (binding matches; C++ runtime can't on native
  Windows) — not an isolation or dependency issue.
- NOTE for whoever runs on the lathe: neither PR is Linux-verified. Please run
  scripts/run_tests.sh (LinuxCNC down) on both branches to confirm green.
- State: review-ready; both branches pushed, claims released. No merge/deploy.

## 2026-11-22 05:10 UTC — (superseded by the entry above) ACTIVE (claim): add "Extra Slow" jog-speed preset (side session)
- Side session spun off main for an owner-requested jog-speed preset change.
  Application branch: feat/jog-speed-extra-slow-preset, base main cd2f3a3.
  Software-only; NO machine deployment, NO machine verification (no Python on the
  Windows authoring box — the change is unexecuted and needs a run on the lathe PC).
- Task: the velocity MPG jog presets become Extra Slow, Slow, Medium, Fast (were
  Slow, Medium, Fast). Extra Slow = old Slow value, Slow = old Medium value, new
  Medium = geometric midpoint of old Medium and old Fast, Fast unchanged. The two
  position presets (.0002 / .001) and DEFAULT_JOG_MODE_INDEX are untouched.
- Claimed paths (Claude HAL/manual lane; no overlap with Codex CAM claims):
  hal/constants.py (JOG_MODES), industry-cam.hal (mux8.jogscale-x/z in4/in5 +
  comments), postgui.hal (unloaded-stub comments), gui/help_tab.py (MPG Modes
  table), hal/live_backend.py (set_mpg_scale_index docstring). mux8 select logic
  is unchanged; index 5 was already reachable (in5 held the Fast fallback value).
- Codex: no CAM/planner/writer/INI/tool-table files touched. Shout if you hold
  uncommitted work in any of the above (none expected — this is the jog GUI/HAL).
- State: active. Will update to review-ready with the PR link when done.

## 2026-11-19 UTC — SUITE RUN, REVIEW-READY: 28fb225 on claude/zero-finish-allowance
- Owner shut LinuxCNC down, so the suite gate opened. FULL SUITE: 1556 passed / 2 failed.
  Arithmetic: 1539 baseline + 19 new - 2 now-failing = 1556. Architecture still 15 errors /
  130 warnings, findings identical to cd2f3a3. 76-case allowance>0 motion diff still identical.
- THE 2 FAILURES ARE PRE-EXISTING, NOT FROM THIS BRANCH:
    test_arc_gcode_linuxcnc.py::test_linuxcnc_runs_concave_fillet_around_nose_radius[0.03]
    test_cut_regions.py::test_owner_reference_programs_check_clean[Hemisphere Test.json]
  Cause: the owner's UNCOMMITTED tool.tbl. T4 went from a CNMG nose O.032 (R.016) to a VNMG
  nose O.064 (R.032); T4 is the OD turning tool both tests use. rs274 refuses "Tool radius not
  less than arc radius with comp" on G02 X0.5600 Z-0.4950 I0.0250 (Cleanup move 4) - an R.032
  nose cannot cut an R.025 concave arc under comp.
  Proven twice: (1) the emitted G-code for the failing fillet case is BYTE-IDENTICAL between
  cd2f3a3 and this branch; (2) both tests FAIL on a clean `git archive` of cd2f3a3 as soon as
  the owner's current tool.tbl is dropped in. Codex: do not chase these as a CAM regression.
  REAL MACHINING FINDING for the owner, not just a test artefact: with the new VNMG insert on
  T4, the saved "Hemisphere Test" program and any R.03 concave fillet no longer post under
  cutter comp. Needs a smaller-nose tool, a larger fillet, or comp off. Owner's call; nothing
  changed here and tool.tbl was left exactly as the owner has it.
- Follow-up commit 28fb225 corrects 68b1b3d: ZoneQueryAPI.contains() is back to FIRST-FACE-ONLY.
  Widening it was only needed for the new duplicate check, and it also feeds the comp lead-out
  via part_contains/stock_contains - not worth changing a shared primitive with no test asking.
  The any-region behaviour is now a separate contains_any_region(), used only by the one-pass
  code. THE BEHAVIOUR NOTE IN MY PREVIOUS ENTRY IS WITHDRAWN: contains() is unchanged from
  cd2f3a3, so nothing that depends on it moves.
- Also fixed in 28fb225: the new test helper defaulted stock to O1.5 on an OD, leaving material
  outside the cut so no allowance could cover the whole removal (1 self-inflicted test failure).
- tests/integration/test_one_pass_program.py: 19 cases, all passing.
- State: review-ready, claims released. Not merged; main untouched; live checkout on its own
  commit with the owner's M tool.tbl intact.

## 2026-11-19 UTC — REVIEW-READY (claims released): 68b1b3d on claude/zero-finish-allowance
- One-pass programs. Owner: a finish allowance of 0 must be a valid input; his case is a bore
  opening .193 -> .194, .001" on the diameter, one cut. Owner chose BOTH ends valid:
    allowance 0                -> the roughing CONTOUR (cleanup) pass cuts the profile itself,
                                  at roughing feed. No finish pass.
    allowance >= whole removal -> the finish pass alone, at finish feed. No roughing, no cleanup.
- Base cd2f3a3. Single commit 68b1b3d. No HAL/INI/offsets/tool-table changes. NOT machine-tested.
- Three defects fixed:
    * allowance >= removal CRASHED (RuntimeError): the material-to-rough boolean leaves an empty
      face and pipeline._extract_zone_boundary read "no edges" as kernel failure.
    * allowance 0 cut final size TWICE - three times on an OD, where 1.000 - 5 x .020 puts a
      roughing level on the profile too - and the approach to that duplicate was flagged a gouge,
      so the OD returned BLOCKED_BY_ERROR. Which side it hit was floating point; the matching ID
      bore missed the level, which is why ID "worked" and OD did not.
    * owner's .194 bore refused at EVERY allowance by comp planning: the .0011" lead across the
      bore mouth is shorter than the .0019" comp needs before the corner at the wall.
- Changed: geometry/zone_query.py (new zone_is_empty; contains() now classifies EVERY face of a
  zone - a boolean-op zone is a compound the classifier rejected outright, so
  contains("material_to_rough", ...) could not be called at all), pipeline/pipeline.py (new
  _pass_schedule + _without_contour_duplicates), planners/comp_contour.py (air-lead recognition),
  new tests/integration/test_one_pass_program.py (20 cases), session note.
- BEHAVIOUR NOTE for Codex: ZoneQueryAPI.contains() answers differently for a multi-region zone -
  a point in the second region used to return False. It feeds the comp lead-out via
  part_contains/stock_contains. The 76-case motion diff below shows no existing program moved,
  but if you depend on the old single-face behaviour, say so.
- Verification (lathe runtime, LinuxCNC UP, so engine probes not pytest):
    * architecture 15 errors / 130 warnings, findings byte-identical to cd2f3a3 (diffed against a
      git archive of the base; only set-iteration order differs inside two function lists).
    * NO allowance>0 program changed: 76 cases - staircase and offset_contour x allowance
      .002/.005/.010/.030 x 1/2/3 finish passes and spring pass, plus stepped_id, stepped_od and
      arc_od ground-truth fixtures - generated on both trees and compared on emitted MOTION
      (comments stripped; the header carries a timestamp). Byte-identical, same pass/move counts.
    * one-pass cases pass end to end: ID and OD, both strategies, allowance 0 and >= removal, and
      the owner's .194 bore at a .008 nose.
- VERIFICATION GAP: the pytest suite has NOT been run on this branch. scripts/run_tests.sh refuses
  while LinuxCNC is up (milltask/rtapi_app/linuxcncsvr all running) and that guard was NOT
  bypassed - pytest alongside the RT stack has frozen this machine before. The 20 new cases have
  therefore never executed. Suite must be run with LinuxCNC down before any merge; expect
  1539 + 20 passing.
- Claims RELEASED: pipeline/pipeline.py, geometry/zone_query.py, planners/comp_contour.py,
  planners/cleanup_planner.py, models/params.py, pipeline/model_builder.py, gui/program_tab.py.
  models/params.py, model_builder.py, cleanup_planner.py and program_tab.py ended up UNCHANGED.
- State: review-ready. Not merged; main untouched; live checkout still on its own commit with the
  owner's M tool.tbl intact.

## 2026-11-19 UTC — (superseded by the entry above) ACTIVE: one-pass programs / finish allowance 0
- Task: the CAM engine must accept a one-pass program. Owner's case: a bore removing .001" dia
  total, one cut, no rough-then-finish. Owner chose BOTH inputs valid:
    * fin_allowance == 0        -> roughing/contour makes the finished surface; NO cleanup, NO finish.
    * fin_allowance >= removal  -> finish pass alone makes it; NO roughing, NO cleanup.
  Owner also authorized fixing the cutter-comp concave-corner guard in the same branch.
- Application branch: claude/zero-finish-allowance, base cd2f3a3 (current main, fast-forwarded).
- Reproduced on cd2f3a3, read-only probes, LinuxCNC down, no machine run:
    * allowance 0, roomy ID bore: CLEANUP and FINISH emit the IDENTICAL path -> double cut.
    * allowance 0, OD: BLOCKED_BY_ERROR, transition feed flagged crossing the Finished Part zone.
    * allowance == whole removal: RuntimeError in pipeline._extract_zone_boundary, the
      material_to_rough zone is empty.
    * owner's .193->.194 bore: refuses at every allowance; also trips comp_contour
      check_concave_corners (.0011" entry move vs .0019" comp need).
- CLAIMED source paths (CAM — Codex please avoid these until released):
    pipeline/pipeline.py, geometry/zone_builder.py, planners/cleanup_planner.py,
    planners/comp_contour.py, models/params.py, pipeline/model_builder.py,
    gui/program_tab.py (finish fields only), new tests/integration/test_one_pass_program.py,
    and a dedicated session note.
- Acceptance: allowance 0 and allowance>=removal both produce exactly ONE surface-making pass with
  no duplicate path and no gouge/BLOCKED; multi-pass behaviour at allowance>0 byte-unchanged;
  owner's .194 bore posts. Software only — no HAL/INI/offsets/tool-table changes, no machine run.
- Codex: main moved to cd2f3a3. models/params.py and pipeline/model_builder.py are in my claim and
  were also touched by cd2f3a3's error-message pass; rebase before touching them.
- State: active.

## 2026-11-19 UTC — MERGED (owner-directed): claude/run-from-open-race -> main cd2f3a3
- Owner said "merge it into main". Merge commit cd2f3a3, --no-ff, brings in 1254c9b (Run From
  open/abort race + Edit-tab crash hardening) and a749104 (error-message quality pass).
- Merged tree is BYTE-IDENTICAL to the tested branch tip (tree 4d67778). Suite re-run on the merge
  commit itself, LinuxCNC down: 1539 passed / 0 failed. Architecture 15 errors / 130 warnings,
  unchanged from the pre-merge main. Clean merge, no conflicts.
- Tags: rollback `lathe-pre-merge-2026-11-19` = 78a3d50 (the last main the owner actually ran on the
  machine); `lathe-2026-11-19-merged` = cd2f3a3.
- LIVE CHECKOUT NOT PULLED. /home/jacob/linuxcnc/configs/industry-cam is still on 78a3d50 with the
  owner's own `M tool.tbl`. The machine is unchanged until the owner pulls.
- STILL NOT MACHINE-TESTED. main now carries a Run From path and a program_open/_ensure_mode change
  that have only ever run against the mock backend. The four owner checks are in
  session-notes/2026-11-18-run-from-open-race-and-edit-tab-crash.md; the one that matters is a cold
  session Run From (no normal run first), which must run the resume file or refuse, never the source
  from the top. The new `program_run:` log line names the file it actually starts.
- One behaviour change beyond messages: a refused Cycle Start and a refused Run From now show on
  screen instead of only writing logger.warning("program_run failed").
- Codex: main moved 78a3d50 -> cd2f3a3. Rebase or merge before further work. gui/program_tab.py error
  strings in _load_program_data/_open_conversational_file changed (your aec99f0 restore logic is
  otherwise untouched); tests asserting old wording in tool_table_io, run_from_line, model_builder,
  zone_builder, gcode_writer or params will need the new text.
- Carried forward, deliberately not done: hal/factory.py still falls back to MockBackend with only a
  log line, so a fallback caused by NML being down rather than Mesa is never announced on screen; and
  _state_async still logs a 5 s timeout as "command accepted". Both behaviour changes, owner's call.
- State: idle. No claims held.

## 2026-11-19 UTC — REVIEW-READY (claims released): a749104 on origin/claude/run-from-open-race
- Error-message quality pass, owner-directed, on top of 1254c9b. Message TEXT plus the context carried
  in it. No motion, geometry, offsets, HAL, INI or tool-table semantics changed.
- ONE behaviour change, deliberate: gui/run_tab.py refused Cycle Start and refused Run From used to end
  with only logger.warning("program_run failed") - the owner pressed the button and saw nothing at all.
  Both now show_error() and log task_mode/interp_state. Same failure shape as the 2026-11-18 incident.
- tools/tool_table_io.py: load_tool_table re-raised a row error with NO row indication, so a hand-edited
  tool.tbl produced only "Duplicate or non-finite tool table field." Now names the file, the line number
  as a text editor counts it, the reason, and the row verbatim; every field check names the tool and the
  value. LegacyToolTableError still propagates as itself. Also fixed: corrupt wear metadata escaped as a
  bare float() message because float() ran before the isfinite check.
- outputs/run_from_line.py: "Start line is outside the program" covered both line 1 and past-the-end and
  was false for line 1. Split; canned-cycle and unclosed-o refusals name the cycle/o-number and its line
  (new ModalState.motion_line, o_stack carries the line); new describe_missing_n() gives the N range and
  nearest blocks. gui/program_tab.py: JSONDecodeError line/column/reason reported instead of discarded;
  schema checks name the block and value. Plus pipeline/model_builder.py, geometry/zone_builder.py
  ("Do NOT create a fallback" moved from owner-facing text to a code comment with its reason),
  outputs/gcode_writer.py, models/params.py, hal/factory.py.
- Checks: 1539 passed / 0 failed on the lathe runtime, LinuxCNC down. Architecture 15 errors / 130
  warnings, warning list byte-identical to the pre-change tree. diff --check clean. Every reworded path
  fired once and read (34 engine/IO + 14 GUI); that caught two defects in these edits the suite missed.
- New tests/unit/test_error_message_context.py (17) pins the facts into the text; +2 cases for the
  formerly silent refusals. Eight existing raises(match=) regexes retargeted. test_run_from_open_guard's
  fixture was order-dependent on the shared mock singleton (machine_on() only works from ESTOP_RESET and
  state is built by poll()); fixed.
- Codex: NOTE if you touch these files. gui/program_tab.py error strings in _load_program_data and
  _open_conversational_file changed; your conversational-restore logic (aec99f0) is untouched otherwise.
  If you have tests asserting on old wording in tool_table_io, run_from_line, model_builder, zone_builder,
  gcode_writer or params, they will need the new text. Claims released.
- NOT done, deliberately: hal/factory.py still falls back to MockBackend with only a log line, so a
  fallback caused by NML being down rather than Mesa is not announced on screen; and _state_async still
  logs a 5 s timeout as "command accepted". Both are behaviour changes and safety-adjacent - owner's call.
- No machine verification. Nothing here changes motion. Session note:
  session-notes/2026-11-19-error-message-quality-pass.md.
- State: idle. Branch claude/run-from-open-race now holds 1254c9b + a749104, base main 78a3d50.

## 2026-11-19 04:52 UTC — REVIEW-READY (claims released): 1254c9b on origin/claude/run-from-open-race
- Base main 78a3d50. NOT merged, NOT machine-tested; owner wants it off main while cutting. Rollback point
  remains lathe-2026-11-16-working (71ce670).
- Run From root cause fixed: live_backend.program_open now wait_complete()s and confirms stat.file is the file
  it asked for (bounded 1 s, realpath) or returns False; _ensure_mode waits up to 1 s for an idle interpreter
  and aborts only when task_mode == MODE_MDI, instead of aborting any non-idle interp state and so discarding
  the just-issued open; program_run/program_step log open file + tool + G54 X/Z + tool offset + G7/G18.
- Edit-tab segfault hardening: faulthandler.enable() in main_window.main() (next segfault leaves a Python
  stack in /tmp/lcnc_gui.log); _highlight_editor_line no longer touches the caret and stands down while the
  editor has focus; GCodeEditor is NoWrap; the gutter paint loop no longer measures an invalid block. The Qt
  frame (QTextLine::textStart, null engine) is confirmed from the faulting address; the Python path that
  reached it is NOT proven - faulthandler is what will prove it.
- Verification, LinuxCNC down, lathe runtime: suite 1520 passed / 0 failed (main was 1509 + 11 new cases);
  architecture check 15 errors / 130 warnings, identical to main 78a3d50 in the live checkout; git diff
  --check clean. LiveBackend itself is untestable under the suite (conftest makes the linuxcnc binding
  unimportable), so the new tests pin the run_tab half: tests/unit/test_run_from_open_guard.py and
  tests/unit/test_edit_tab_playback_highlight.py.
- Deliberately NOT changed: _state_async logs "estop_reset: command accepted (5.00 s)" after
  linuxcnc.command().state() returns on its own 5 s timeout, so an unresponsive task reads as success (seen
  again in the 18:25 incident). Safety-adjacent; separate change, owner's call.
- Not established: which move tripped joint 0's -0.05 soft limit. The source program was regenerated at 17:55
  PST, after the failures, so its line 53 at the time is gone, and nothing logged offsets or the open file.
- Details, including the machine checks still owed:
  session-notes/2026-11-18-run-from-open-race-and-edit-tab-crash.md.
- Claimed paths released: hal/live_backend.py, gui/run_tab.py (untouched in the end), gui/main_window.py,
  gui/edit_tab.py.
- To Codex: no CAM, writer, HAL, INI, offset or tool-table changes in this branch.

## 2026-11-19 04:41 UTC — ACTIVE (claim): cold-session Run-From failure + two GUI crash fixes
- State: active. Application branch: claude/run-from-open-race, base main 78a3d50. No HAL/INI/offsets/tool-table changes.
- Owner symptoms (2026-11-18, lathe): (1) GUI segfault while working in the Edit tab (18:16:49 PST, kernel:
  python3 segfault at 0 in libQt5Gui.so.5.15.8; address resolves to QTextLine::textStart() with a null
  QTextEngine, i.e. Qt asked for a text line that does not exist). (2) Run From a line fails unless the
  program was first run normally from the top in the same session; LinuxCNC reported "Linear move on line 53
  would exceed X's negative limit" + "invalid params in linear command" (motmod inRange()), and line 53 exists
  only in the 107-line source, not in either 30/45-line resume file.
- Root cause (2) found in code: run_tab._on_run_from_line calls backend.program_open(resume) and then
  program_run() immediately; live_backend.program_open never wait_complete()s after _cmd.program_open(), so the
  interpreter is still INTERP_READING when program_run -> _ensure_mode(AUTO) runs, and _ensure_mode issues
  _cmd.abort() on any non-idle interp state. The abort kills the open; AUTO_RUN then runs the file task still
  has open - the source program, from line 1. Warm works because task_mode is still AUTO after a normal run +
  Stop, so _ensure_mode returns at its first check and never aborts. Normal start never hits it either: the
  source was opened at load time, so _ensure_source_loaded short-circuits. Also note _program_busy() returns
  False whenever task_mode != AUTO, so it cannot guard this.
- Claimed paths: hal/live_backend.py (program_open, _ensure_mode only), gui/run_tab.py (_on_run_from_line /
  run-start logging only), gui/main_window.py (faulthandler enable only), gui/edit_tab.py (_highlight_editor_line
  + line_number_area_paint_event only), plus new tests under tests/unit/.
- Acceptance: full suite on the lathe runtime (scripts/run_tests.sh, LinuxCNC down) with no new failures;
  architecture check with no new violations; run-from refuses to start when stat.file is not the resume file.
- NOT machine-tested, no merge to main, no deployment. Owner wants this off main while cutting.
- To Codex: no overlap with your released claims; these four files are GUI/runtime, not CAM. Shout if you have
  uncommitted work in gui/run_tab.py or hal/live_backend.py.

## 2026-11-16 — MACHINE-VERIFIED (owner): threading and tool graphic T1-T5 both work on the lathe
- Owner ran them on the machine and reported both good. lathe-2026-11-16-working (71ce670) is therefore a
  PROVEN rollback point, not an assumed one.
- Still NOT machine-tested: the run-overrides merge (main 78a3d50) - feed/rapid MPG re-routing during a run,
  green-button-while-paused single step, M1 optional stop. It changes industry-cam.hal, so a failed start is
  the first thing to watch; roll back to lathe-2026-11-16-working.

## 2026-11-16 — MAIN at 78a3d50 (run-overrides merged, owner-approved); no active claims
- ROLLBACK POINT: lathe-2026-11-16-working = 71ce670, owner-confirmed good on the machine
  (tool-graphic T1-T5 + threading + Tools-tab label fix). Post-merge tag lathe-2026-11-16-run-overrides.
- Merged claude/run-overrides via claude/run-overrides-integration (cb5d6d1 merged main in first).
  One conflict, outputs/gcode_writer.py: the branch predated the threading/G76 rework and carried the
  old threading header. Took main's header, kept only _optional_stop("before threading"), placed after
  the header comments and before G7 / S M3 (tool at park).
- Verified LinuxCNC down: suite 1509 pass on the lathe runtime; architecture check 15 errors, same as
  main before the merge. HAL re-checked after the merge: main never touched industry-cam.hal since the
  fork, all six new components loaded + addf'd, and the two override nets are extra READERS on the
  existing mpg-x-counts / mpg-z-counts signals (drivers unchanged: encoder.03 / encoder.02).
- NOT MACHINE-TESTED: feed/rapid MPG re-routing during a run, green-button-while-paused single step,
  M1 optional stop. Also still unverified on the machine: tool graphic T1-T5, threading.

## 2026-11-16 — MAIN at 71ce670 (Tools-tab spindle-tool label merged, owner-approved); no active claims
- Rollback tag lathe-pre-merge-2026-11-16 = 9c255f9; post-merge tag lathe-2026-11-16-merged.
- Verified with LinuxCNC down: full suite 1502 pass on the lathe runtime (was 1496 + 6 new);
  architecture check 15 errors on the branch AND on main before the merge - no new violations.
- Live checkout IS at 71ce670 (the merge was made in it); the fix is on disk and takes effect at the next GUI start. Tool graphic T1-T5 and
  threading remain NOT machine-tested. claude/run-overrides still awaits a live test.

## 2026-11-16 — REVIEW-READY (claim released): Tools-tab spindle-tool label, branch claude/tools-tab-current-tool 6a60861 (from main 9c255f9)
- The TopButtonBar label is built as QLabel("Offline") and ToolsTab.refresh_current_tool_display() had no caller
  anywhere in the repo, so it read "Offline" all session with a live controller. Now called on showEvent and after
  _accept_table. Paths: gui/tools_tab.py, tests/unit/test_tools_tab_current_tool_label.py (new, 6 cases).
- NOT RUN YET: owner deferred the suite until LinuxCNC is down (scripts/run_tests.sh refuses while it is up).
  Compile-checked only. Live checkout left on main 9c255f9; branch pushed, not merged.
- Also 2026-11-16: live checkout PULLED to main 9c255f9 (tool graphic T1-T5 + threading now on the machine,
  neither machine-tested). Owner hit a TOOL MISMATCH pause from the generated o9001 tool check - correct
  behaviour, the controller's table was stale (T3 D0.032 vs file D0.000000); resolved by Tools tab -> Load Table.
- Owner decision: the .194 bore / .1875 pilot retract will be hand-edited in G-code. Per-block retract stays
  bookmarked, NOT scheduled. Noted for anyone scoping transitions/transition_planner.py::_get_safe_x.

## 2026-11-13 — REVIEW-READY (claim released): tool-graphic T1-T5 complete on claude/tool-graphic-build (not merged)
- T5: validation/material_sweep.py, outputs/program_header.py (new); outputs/gcode_writer.py adds header line
  "; Stock Face Z:"; hal MachineState.motion_type + motion_sample(); sim_viewer/graph_widget/run_tab. Suite 1496 pass.

## 2026-11-13 — REVIEW-READY (claim released): tool-graphic T1-T4 on claude/tool-graphic-build; T5 not started
- T4: validation/sim_path.py (new), validation/cycle_time.py (error text), geometry/tool_outline.py (speed/cache),
  gui/components/{sim_viewer,graph_widget,tool_graphic_item}.py, gui/{run_tab,edit_tab,program_tab}.py. Suite 1485 pass.

## 2026-11-13 — REVIEW-READY (claim released): tool-graphic T1-T3 on claude/tool-graphic-build (from main f6f29d8); T4/T5 not started
- Also touched: hal/interface.py + hal/live_backend.py (work_position), gui/components/{tool_graphic_item,position_graph,graph_widget,sim_viewer}.py, gui/manual/manual_tab.py, gui/run_tab.py, gui/main_window.py
- Plan merged to main f6f29d8 (docs only). Claimed paths: geometry/tool_outline.py (new), tools/tool_card_data.py,
  tools/tool_table_io.py, tools/insert_geometry_lookup.py, models/tool.py, gui/components/orientation_graphic.py,
  gui/components/tool_geometry_row.py, gui/tools_tab.py (IC field), tests/unit/test_tool_outline*.py.

## 2026-11-13 — REVIEW-READY (claim released): tool-graphic plan, docs only, claude/tool-graphic-plan
- Path: docs/handoffs/2026-11-13-tool-graphic-plan.md. No source edits (owner: plan first).

## 2026-11-12 — MAIN at a9a4bb6 (threading build merged, owner-approved); rollback tag lathe-pre-merge-threading (85d3230)
- No active claims. claude/run-overrides still awaits live test. Live checkout pulled (ff) to a9a4bb6 2026-11-13.

## 2026-11-12 — REVIEW-READY (claim released): threading follow-up 2f1b132 (NPT pilot -> ASME B1.20.1 K0); tests pending (LinuxCNC was up)
- Owner: tap drills must come from Machinery's Handbook / ASME, not web charts. Paths: models/thread_data.py (NPT),
  gui/components/threading_panel.py (NPT hint), tests/unit/test_thread*.py, threading plan doc section 10.

## 2026-11-12 — REVIEW-READY (claim released): threading build, branch claude/threading-build 62e0835 (from main 85d3230)

- Owner-approved: implement docs/handoffs/2026-11-12-threading-workflow-plan.md (T1 data, T2 panel, T3 motion).
- Claimed paths: models/thread_data.py (new) + data, models/program.py (ThreadingParams), gui/components/threading_panel.py,
  planners/threading_planner.py, outputs/gcode_writer.py (threading block only), pipeline threading wiring,
  validation (thread checks), tests/unit/test_thread*.py, tests/unit/test_g76_threading.py.

## 2026-11-12 — MAIN at 85d3230 (threading plan merged, docs only); no active claims; claude/run-overrides awaits live test

- Merged docs only: docs/handoffs/2026-11-12-part-model-and-import-plan.md and
  2026-11-12-threading-workflow-plan.md. PLAN ONLY - owner: no implementation yet.
- Upcoming threading rework will touch threading_panel / threading_planner / gcode_writer threading block
  (not started; will claim first).

## 2026-11-12 — MAIN at G76 merge (tag lathe-2026-11-12-g76); claude/run-overrides awaits live test; no active claims

## 2026-11-12 — MAIN at ee4331b (cycle time merged); REVIEW-READY: claude/g76-fix, claude/run-overrides (live test)

- claude/g76-fix: G76 per LinuxCNC semantics (drive line .020 outside crest, diameter J/K, lead, safe ID approach/retract).
  Threading blocks could not run before (I0) and would have cut half depth / crashed internally. Touched
  planners/threading_planner.py, outputs/gcode_writer.py (threading block), validation/cycle_time.py, tests.
- claude/run-overrides: awaiting live test. No active claims.

## 2026-11-12 — MAIN at 28665c6 (last-retract hotfix + Generate checks merged); REVIEW-READY: cycle time, run controls

- claude/cycle-time cd8bd7f: cycle-time estimate (validation/cycle_time.py; Program tab + Run tab). Merges cleanly with run-overrides.
- claude/run-overrides ff65ea5: still awaiting the owner's LIVE test (HAL change).
- FOUND: threading blocks emit G76 with I0 -> LinuxCNC rejects ('In G76, I must not be 0'). Not fixed (owner input on drive-line clearance).
- No active claims.

## 2026-11-12 — REVIEW-READY (claims released): HOTFIX last retract, run controls, Generate checks

- claude/hotfix-last-retract f3bc794 (from main 1be0bd5): last roughing pass exits fully - the cleanup approach rapided
  .0225 into material on a neck part since today's retract-rule merge. URGENT, owner approval to merge.
- claude/run-overrides ff65ea5: feed/rapid override sliders, MPG overrides during a run (industry-cam.hal), single block,
  optional stop + M1 emission. Needs a LIVE test on the lathe (HAL change).
- claude/generate-checks 98c9a30 (includes the hotfix): rapid-collision + gouge checks at Generate; refuses to hand on.
- Next (owner-approved): cycle-time estimate.

## 2026-11-12 — ACTIVE: run controls (branch claude/run-overrides), then Generate checks, cycle time

- Owner-approved: feed (1-200%) / rapid (1-100%) override sliders on the Run tab; X MPG = feed override, Z MPG = rapid
  override while a program runs or is paused (HAL, jog disabled meanwhile); single block + optional stop (M1 per block).
  Claimed: gui/run_tab.py, industry-cam.hal (MPG section only), hal/live_backend.py + interface + mock (program step /
  optional stop), outputs/gcode_writer.py + gui/program_tab.py (M1 emission only), tests. No merge without owner.

## 2026-11-12 — MAIN at hand-math close-out (tag lathe-2026-11-12-handmath-done); no claims, discussing GUI features (read-only)

## 2026-11-12 — MAIN at 37104cb (C2 merged); REVIEW-READY: C4-C6 leftovers, branch claude/c456-leftovers dea35eb

- Curve-fitting path removed (unreachable; non-circular edges now refused), canon arc sampling on arc_math.Arc, dead
  arc helper removed. hand_math 15 -> 9. Corpus SAME. Touched planners/finish_planner.py, geometry/face_ops.py,
  geometry/kernel.py, geometry/arc_helpers.py, validation/cut_regions.py, tests. NOT merged (owner review).

## 2026-11-12 — MAIN at d83862f (full-circle HOTFIX merged); REVIEW-READY: C2 tool reach, branch claude/c2-tool-reach-v2

- HOTFIX on main: arcs whose ends coincide at output precision (LinuxCNC full circles) can no longer be emitted
  (pipeline converts slivers, writer refuses, cut_regions reads them as full circles). Regenerate any offset-contour program.
- claude/c2-tool-reach-v2 (b277396, from d83862f): tool reach from kernel edges (find_tangent, intersections). Touched
  geometry/tool_reach.py, corner_breaks_od.py, face_ops.py, arc_math.py, architecture baseline. NOT merged (owner review).
  (claude/c2-tool-reach is the stale pre-rebase WIP; ignore.)

## 2026-11-12 — MAIN at 517fe43 (C3 merged); REVIEW-READY: roughing retract rule, branch claude/rough-retract

- main 517fe43 = lathe-2026-11-12-c3. Live checkout pulled.
- claude/rough-retract: owner retract rule (OD prev max +.005, ID prev min -.005, pass 1 stock OD +.005 / pilot -.001,
  45 deg pull-off at walls, pocket exit to the mouth) planned in planners/rough_links.py; writer emits; pipeline validates
  the same moves. New validation/rapid_collision.py (rapids vs remaining material). Touched: outputs/gcode_writer.py
  (roughing section), pipeline/pipeline.py, geometry/arc_math.py + kernel.py, scripts/regression/regen.py, tests. NOT merged.

## 2026-11-12 — REVIEW-READY (claims released): C3 writer geometry, branch claude/c3-writer-geometry 59f6365

- From main d9c7d36. Cutter-comp entry/contour/lead-out planned in planners/comp_contour.py (pipeline; TurningPass.comp_contour),
  writer emits only. Kernel point-in-face + line intersection. Corpus TEXT-IDENTICAL to main; suite passed. dependency 4 -> 2.
- Codex: outputs/gcode_writer._emit_contour_pass signature changed (takes the pass); PlanResult passes now carry comp_contour.
  NOT merged (owner review). Owner decision pending: roughing retract X rule (_compute_pass_max_x over-states, safe side).

## 2026-11-12 — MAIN at d9c7d36 (C1 merged, owner-approved); ACTIVE: C3 writer geometry -> planners

- main d9c7d36 = lathe-2026-11-12-c1. Live checkout pulled.
- ACTIVE: branch claude/c3-writer-geometry. Cutter-comp entry/contour/lead-out decisions move from outputs/gcode_writer.py
  to planners/comp_contour.py (pipeline plans them; TurningPass.comp_contour). Behaviour-neutral: corpus text-identical.
  Claimed: outputs/gcode_writer.py, planners/comp_contour.py, models/results.py, pipeline/pipeline.py, geometry/zone_query.py,
  geometry/kernel.py, tests touching the writer. No merge without owner.

## 2026-11-12 — REVIEW-READY (claims released): C1 corner breaks via kernel, branch claude/c1-corner-breaks a4256d3

- From main edff211. Corner breaks built by OCCT 2D fillet/chamfer (NX part reproduced; NX trim rules kept for line-line);
  arc-adjacent breaks fixed (old chord method moved the operator's arc .008-.073 in). Program-tab preview now draws the
  engine's own outline. Writer never prints -0.0000. Suite 1328 passed; corpus text-identical to main except -0.0000.
- Docs: docs/handoffs/2026-11-12-hand-math-inquiry.md (C1 section). NOT merged (owner review).
- Codex: gui/program_tab.py preview code changed substantially (_engine_outline / _outline_rows); rebase GUI work onto it after merge.

## 2026-11-12 — MAIN at edff211 (F4 merged, owner-approved); ACTIVE: C1 corner breaks via kernel

- main edff211 = lathe-2026-11-12-f4 (contour roughing rounded joins). Live checkout pulled.
- ACTIVE: branch claude/c1-corner-breaks. Corner-break solver kernel-first (OCCT 2D fillet/chamfer); NX trim rules kept
  for line-line; arc-adjacent breaks were built off the arc (moved the operator's arc centre .008-.034 in) -> kernel.
  Then the Program-tab preview draws the engine's break geometry. Claimed: geometry/corner_breaks_od.py,
  geometry/zone_builder.py, gui/program_tab.py (profile preview + corner-break status only), tests/unit/test_corner_breaks_*,
  scripts/hand_math/. No merge without owner.

## 2026-11-12 — MAIN MOVED to 72eeab4 (owner-approved merge of structure-cleanup + hand-math-kernel); ACTIVE: F4

- main 72eeab4 = lathe-2026-11-12-merged (rollback tag lathe-pre-merge-2026-11-12 = 01f6cf3). Suite 1310 passed. Live checkout pulled.
- Codex: planners import geometry only via geometry/kernel.py; tool data pipeline/ -> tools/; cut_regions outputs/ -> validation/.
- ACTIVE: branch claude/f4-rounded-joins (owner approved F4 policy): contour roughing uses rounded offset joins; sharp->rounded
  fallbacks elsewhere become a Generate WARNING. Claimed: geometry/kernel_offset.py, planners/contour_roughing_planner.py,
  pipeline/pipeline.py (execute wrapper only), tests/unit/test_offset_join_policy.py. Next: C1 corner breaks via kernel (claim to follow).

## 2026-11-12 16:35 UTC — REVIEW-READY (claims released): structure cleanup + hand-math inquiry

- origin/claude/structure-cleanup 9962c59 (from main 01f6cf3): behaviour-neutral reorganisation. Dependency errors 62 -> 4,
  geometry/kernel.py facade (planners' only geometry import), architecture ratchet test, regression tooling (scripts/regression).
- origin/claude/hand-math-kernel dd23a97 (from 9962c59): F1 back-face "wires not planar" fixed; F2 finish contour from the kernel
  open profile wire (hand-math fallback removed); F5 zone boundary polylines on the kernel's arcs; F3/F6 dead & duplicate math
  removed; F4 OCCT sharp-join wall documented. Suite 1310 passed. Corpus: 18 SAME, 1 newly generating (machinist-checked).
- Docs: docs/handoffs/2026-11-12-structure-cleanup-log.md, 2026-11-12-hand-math-inquiry.md. NOTHING merged to main (owner review).
- Codex: rebase any CAM work onto these only after the owner merges them; note planners now import geometry only via geometry/kernel.py,
  tool data moved pipeline/ -> tools/, cut_regions moved outputs/ -> validation/.

## 2026-11-12 07:55 UTC — MAIN MOVED to 01f6cf3 (cleanup/finish .020 dia feed-in), claim released

- main 01f6cf3 = 7698982 + contour feed-in (fast-forward). Tags: lathe-2026-11-11-feed-in; rollback lathe-pre-feed-in-2026-11-11 (7698982).
- Suite 1310 passed / 0 failed on the lathe runtime; arch unchanged. Motion-affecting: NOT machine-verified yet
  (commissioning: session-notes/2026-11-11-contour-feed-in-approach.md). Live checkout on 01f6cf3.
- Kiro / Codex: rebase onto 01f6cf3. Note planned links into finish/spring passes now end with a FEED move.

## 2026-11-12 07:40 UTC — REVIEW-READY (claim released): feed-in final approach for cleanup + finish passes (owner-approved)

- Owner request: for cleanup and every finish/spring pass, rapid to .020 dia short of the entry X
  (outside for OD, inside for ID), then FEED the last .020 at the pass feed, same direction every time.
  Reason: X backlash .0156 dia, start-of-move windup ~.0005 dia, accel-dependent outward slip (bench 2026-11-11).
- Claimed (motion-affecting): outputs/gcode_writer.py (_emit_contour_pass approach only),
  transitions/transition_planner.py (_retract_traverse_plunge final X step for FINISH/CLEANUP targets),
  models/constants.py (one new constant), new tests/integration/test_contour_feed_in_approach.py.
- Branch claude/contour-feed-in from main 7698982, developed in a separate worktree (live checkout stays on main).
- DONE: 01f6cf3 on origin/claude/contour-feed-in (parent main 7698982). Also touched: tests/integration/test_finish_pass_schedule.py,
  tests/unit/test_comp_entry_and_tool_checks.py (links now end with a feed), session-notes/2026-11-11-contour-feed-in-approach.md.
  Suite 1310 passed (main 1301/0 failed); arch unchanged. NOT merged: awaiting owner OK; motion-affecting, not machine-verified. Claims released.

## 2026-11-12 06:50 UTC — MAIN MOVED to 7698982 (X tuning + replay tool), claim released

- main 7698982 = 8e44e8a + 3389dfb (X DEADBAND .00025) + 97149b5 (X MAX_ACCELERATION 3, joint+axis) + merge of 78ba45f (scripts/xvernier/replay.c, build_replay.sh).
- Tags: lathe-2026-11-11-x-tuned (new main), rollback lathe-pre-x-tuning-merge-2026-11-11 (8e44e8a).
- INI-only machine change; G-code interpreter tests unaffected (they use the INI for RS274 startup only). Suite not rerun: LinuxCNC was up.
- Live checkout on 7698982; vernier shadow HALFILE commented again (vernier parked until the X motor mount is stiffened).
- Kiro / Codex: rebase onto 7698982.

## 2026-11-12 06:30 UTC — REVIEW-READY (claim released): offline vernier replay tool (owner-requested)

- Scope (claimed, new files only): scripts/xvernier/replay.c, scripts/xvernier/build_replay.sh. No changes to rtcomp/ or tests/.
- Branch claude/xvernier-replay from main 8e44e8a. Feeds a capture.sh file through the shipped CORE-BEGIN..END estimator.
- Vernier decision (owner): NOT closing the loop for now; replay of the 2026-11-11 sweep shows ~2x parking gain at best, clamps of .0005-.0009 dia at reversals. Revisit after the X motor mount is stiffened.
- DONE: 78ba45f on origin/claude/xvernier-replay (parent main 8e44e8a, 2 new files). Not merged. Claim released.

## 2026-11-12 06:10 UTC — REVIEW-READY (claim released): X MAX_ACCELERATION 10 -> 3 (owner-requested)

- Scope (claimed): industry-cam.ini [JOINT_0] MAX_ACCELERATION and [AXIS_X] MAX_ACCELERATION only. STEPGEN_MAXACCEL unchanged (12.5).
- Second commit on claude/x-deadband-00025 (on top of 3389dfb). Live machine already at 3 via halcmd.
- Evidence: outward slip per +.020 dia F10 move: accel 10 +.0010, 5 +.00065, 3 +.0003, 2 +.0002 dia. Owner measured the X motor mount moving ~+-.0008 when jogging.
- DONE: 97149b5 on origin/claude/x-deadband-00025 (on 3389dfb). Not merged to main; the live checkout has the same lines uncommitted. Claim released.

## 2026-11-12 05:56 UTC — REVIEW-READY (claim released): X PID deadband .0005 -> .00025 (owner-authorized, bench-measured)

- Scope (claimed): industry-cam.ini [JOINT_0] DEADBAND only. No other INI/HAL/source edits.
- Branch claude/x-deadband-00025 from main 8e44e8a; one-line INI commit. Live machine already running .00025 via halcmd.
- Evidence (air, 12 x +.020 dia F10 moves per run, halsampler captures): deadband .0005 parks +.0002..+.0008 dia short every move;
  .0003 parks -.0003..+.0003; .00025 parks on the nearest scale count (-.0004..+.0001, pattern = scale quantization), no hunting
  (1 correction step in 82 s parked). Scale count = .000197 radius; .00025 sits between 1 count and the 2-count acceptance edge.
- Also found (no change made): outward-only slip ~+.0002..+.0010 dia per move, grows with accel; inward ~0; not the coupling.
- Codex: no overlap expected (your claims released since 2026-11-08).
- DONE: 3389dfb on origin/claude/x-deadband-00025 (parent main 8e44e8a, INI only). Not merged to main; live checkout has the same line uncommitted on main and runs it live. INI claim released.

## 2026-11-11 05:27 UTC — MAIN MOVED to 9e904b4 (owner: merge what passes)

- Merged after full suites (baseline failures only; merged main: 1105 pass / 5 known):
  hotfix/contour-roughing-arcs (SAFETY: offset_contour arcs no longer run the long way round),
  claude/id-corner-breaks (ID breaks validated vs NX), claude/housekeeping-2026-11-10
  (reference programs, CLAUDE.md axis table, test hygiene - complete suite now runs in one
  pass, X-axis tolerance handoff + read-only logger), claude/gui-nonblocking-state (Reset/On/
  Off off the GUI thread; no plan_synch in AUTO; owner to verify live at next start),
  plus peck dwell 5 -> 2.5 rev (owner request).
- NOT merged: claude/arc-phase0 (2 new test failures, in progress), claude/arc-proto (strategy).
- Kiro / Codex: rebase onto 9e904b4.

## 2026-11-11 01:56 UTC — SAFETY: offset_contour roughing arcs run the long way round on main

- main 61fb77d: ContourRoughingPlanner labels arcs mirrored (and builds a mirrored face). Since
  the arc dialect fix LinuxCNC ACCEPTS these and runs e.g. -359 deg instead of +1 deg
  (GUI Conv Test: 27 arcs). Staircase (GUI default) unaffected. Owner told: do not use
  Offset Contour until fixed.
- Fix ready: branch hotfix/contour-roughing-arcs 88666ae (from main; staircase output byte-
  identical; audited with scripts/arc_testbed/sweep_audit.py). Awaiting owner OK to merge.
- Phase 0 (claude/arc-phase0, in progress) includes the same fix plus kernel sweep + quadrant
  split at edge extraction, explicit densify direction everywhere, writer re-merge.

## 2026-11-11 01:19 UTC — arc-segment strategy + prototype (branch claude/arc-proto, NOT for merge)

- docs/handoffs/2026-11-10-arc-segment-strategy.md: test bed from the NX parts (fillets
  re-entered as arc segments) + synthetic two-quadrant OD/ID cases; root cause = arcs carry
  no sweep, every consumer re-guesses direction/centre; plan = one arc identity end to end,
  canonical <=90 deg pieces split at kernel edge extraction, operator-picked arcs (compound
  quadrant-graphic pattern), OD/ID policy modules; phases 0-3; dependency list.
- SAFETY (main): ID bead (arcs forming a bump into the bore) can produce a rapid through the
  part that the validator misses; avoid 180 deg arc pairs until Phase 0.
- Prototype touches only geometry/zone_query.py; scripts/arc_testbed added.
- Please don't start arc work without reading the strategy doc; owner decides direction.

## 2026-11-11 00:48 UTC — ID corner breaks validated + housekeeping (branches pushed, NOT on main)

- claude/id-corner-breaks f6d3737: ID breaks now use the vertex solver; owner's NX ID part
  (id_sharp/id_broken.stp) matches element by element (tests/unit/test_corner_breaks_id_nx.py).
  Legacy ID method was wrong at V1 (bore-mouth chamfer cut INTO the bore -> lip) and clamped
  V4/V6/V7 to 40 %. GCH NEW G-code byte-identical. Claimed: geometry/corner_breaks_od.py,
  geometry/zone_builder.py, gui/program_tab.py, gui/components/corner_break_panel.py.
  Full NX ID part still blocked by retract-routing gouge (undercuts) - pre-existing.
- claude/housekeeping-2026-11-10 14a2aad: arc reference programs regenerated (T1->T4),
  README flags May Arc OD exports as old arc format; CLAUDE.md axis table from real INI
  (signs, PID, limits); requirements lathe note. Pending: tests/conftest.py offscreen
  hygiene (flush DeferredDelete, auto-answer modal dialogs) - to verify with full suite.
- Owner running parts on main 61fb77d tonight. Warned: on main, an ID V1 chamfer as a corner
  break is built backwards - draw it as a segment until id-corner-breaks is merged.

## 2026-11-10 23:55 UTC — MAIN MOVED: 2026-11-10 integration merged (owner: best working version)

- origin/main = 61fb77d (merge of lathe/test-2026-11-10; tree identical to what was tested).
  Tag lathe-2026-11-10-working. Previous known-good: tag + branch lathe-2026-11-09-working (9e98a36).
- Includes Kiro's work/2026-11-10 plus the lathe fixes (arc G-code dialect, software +
  hardware E-stop with estop_latch, concave fillet <= TNR as sharp corner, RT CPU tuning).
- Kiro / Codex: rebase or merge onto 61fb77d before further work. Any arc/G-code work must
  go through outputs/gcode_dialect.py. Regenerate every .ngc with G02/G03 made before it.
  Record: session-notes/2026-11-10-lathe-integration.md; handoff ACTIVE.md entry closed.
- Lathe checkout is on main 61fb77d; live tool.tbl (machine-local) uncommitted as usual.
- Claims released: all paths claimed today. State: idle.

## 2026-11-10 23:52 UTC — hardware E-stop wired (lathe/test-2026-11-10, local)

- Claimed + changed: industry-cam.hal (E-stop section, loadrt/addf), CLAUDE.md note,
  gui/commissioning/pin_providers.py (mock labels).
- NC button on TB3 P5 = gpio.004 (.in TRUE released, FALSE pressed/broken wire), verified
  live by owner presses. 2470663 (plain and2) FAILED live: release cleared ESTOP by itself.
  675afcb: LinuxCNC estop_latch (ok-in=user-enable-out, fault-in=gpio.004.in_not,
  reset=user-request-enable, ok-out=emc-enable-in). Live: press -> ESTOP + machine off;
  release -> stays ESTOP; Reset (released) -> clears; On works.
- HAL rule for everyone: never add the button to the old estop-loop net (one driver per
  net) and never use a plain and2 for it.

## 2026-11-10 23:43 UTC — concave fillet <= TNR handling (owner decision) on lathe/test-2026-11-10

- Owner air-cut the regenerated GCH bore with the ID fillet on the arc-dialect fix:
  performed as expected.
- c3da369: under comp, a concave arc with R <= TNR (+.0001) between two lines is cut as the
  sharp inside corner (tool leaves R=TNR); writer.notes + '; NOTE:' comment; amber notes
  status after Generate; corner-break tool marks the vertex 'tool radius'. Between arcs:
  generation fails with a clear message. Files: outputs/gcode_writer.py, gui/program_tab.py,
  gui/components/corner_break_panel.py, tests/integration/test_arc_gcode_linuxcnc.py.
- Corner Break Test now runs to PROGRAM_END in rs274; all other regression programs
  byte-identical. Suite 1074 pass / same 4 quadrant-arc fails.
- Branch is local only (not pushed). Merge to main = owner decision.

## 2026-11-10 23:25 UTC — arc dialect + software E-STOP fixed on lathe/test-2026-11-10 (local, not pushed)

- Commits: 5e7d561 (outputs/gcode_dialect.py; writer + both parsers), 8b09211 (tests,
  incl. rs274 integration), 4e04c5e (software E-STOP -> STATE_ESTOP; ribbon OFF state).
- Evidence: regenerated GCH ID fillet, 4 NX OD candidates, GUI Conv Test (29 arcs) all run
  to PROGRAM_END in rs274; preview geometry old vs new identical (arc types/endpoints;
  points within 0.0001 from I rounding). Suite: 1069 pass / same 4 quadrant-arc fails;
  Kiro GUI files run separately: 15 pass / 1 fail (423 != 420 px, known).
- For Kiro/Codex: every .ngc with G02/G03 written before 5e7d561 is in the old dialect
  and wrong for LinuxCNC - regenerate. main still has the old writer; this fix must go to
  main with (or before) any arc/corner-break work. Internal convention unchanged
  (center_i = diameter offset; MoveType.ARC_CW draws CCW on the Z-right/X-up graph).
- Still open: Corner Break Test.ngc concave fillet smaller than TNR is refused only by
  LinuxCNC ("Tool radius not less than arc radius with comp") - engine should refuse it.
- Next: owner restarts LinuxCNC (hm2 read error 15:15), regenerates GCH NEW in the GUI,
  air cut.

## 2026-11-10 23:17 UTC — owner-approved fixes on lathe/test-2026-11-10 (in progress)

- Air-cut found: every G02/G03 the engine writes is wrong for LinuxCNC (pre-existing,
  identical on main): I emitted as a DIAMETER offset (LinuxCNC G7 reads I as radius) and
  G02/G03 swapped. Proven with rs274 on the lathe: as generated, the GCH ID fillet and all
  NX OD candidates fail; with I/2 + swapped direction all run to PROGRAM_END.
- Fix (claiming): new outputs/gcode_dialect.py is the single internal<->G-code arc map;
  used by outputs/gcode_writer.py, outputs/gcode_parser.py, gui/components/sim_viewer.py
  (parser only). Internal convention + preview drawing unchanged. Tests updated + rs274
  round-trip test (skips without rs274).
- Also claiming: software E-STOP button sent STATE_OFF (machine off) instead of
  STATE_ESTOP, and the ribbon showed machine-off as green IDLE. Files: hal/live_backend.py,
  hal/interface.py, hal/mock_backend.py, gui/main_window.py, gui/components/status_bar.py.
- Reserved pre-integration state unchanged (tag lathe-pre-integration-2026-11-10 + snapshot).

## 2026-11-10 22:53 UTC — integration test of Kiro's work/2026-11-10 (owner-directed)

- State: active — lathe test branch ready; owner runs no-motion GUI checks, air cut, scrap part.
- Reserved pre-integration state (owner: do not change until test passes):
  tag `lathe-pre-integration-2026-11-10` -> 9e98a36 (= claude/rt-cpu-tuning, now pushed),
  plus a read-only full-directory snapshot on the lathe PC
  (~/linuxcnc/configs/industry-cam.pre-integration-2026-11-10, incl. live tool.tbl/var).
- Test branch (local only, no upstream): `lathe/test-2026-11-10` = 50ec0df =
  origin/work/2026-11-10 (dfb1c1a) + merge of claude/rt-cpu-tuning (keeps boot-time
  set-cpu-performance.sh). Live tool.tbl untouched. Not merged to main.
- Verification (software, LinuxCNC down):
  - G-code regression: 9 saved programs generate byte-identical on main vs branch
    (only the generation-time comment differs).
  - Suite (miniforge 3.13): 1058 pass / 4 fail (same 4 axis-aligned Q tests as main) /
    2 skip / 1 xfail / 3 xpass, with test_jog_clear_trail.py and
    test_segment_builder_layout.py run separately (see findings).
  - NX ref part (inch, V1 sharp): V9 cut-short centre Ø14 Z-21.866mm and V10 tangent R3
    match the handoff values in the finish G-code.
- Findings for Kiro:
  1. offset_contour roughing gouges large concave fillets (NX V10 R3; R2 ok; staircase ok).
     Pre-existing on main (synthetic R0.12 concave fails there too); now hit more often
     because the 40% clamp is gone. Pre-output validator blocks it.
  2. V1 chamfer at the front face is refused (cleanup comp entry 0.0015" < 0.0066").
     Pre-existing on main. => the NX ref part as drawn cannot be generated on either branch.
  3. On Linux full-suite runs, test_jog_clear_trail segfaults and
     test_segment_builder_layout hangs (order-dependent; both pass in isolation).
     test_program_column_420_widens_for_arc_and_returns: 423 != 420 (font metrics).
  4. requirements pin ocp_gordon<0.2 but the lathe runs 0.2.0 fine with build123d 0.10.0;
     nothing installed or changed on the lathe.
- Claimed paths: none new; no code edits on the branch so far.

## Earlier status (2026-11-10 02:50 UTC)

- Updated: 2026-11-10 02:50 UTC
- State: active — compound routing implemented, awaiting machine commissioning
- Agent: Claude Code (Opus 5.5) on the lathe Linux PC (live LinuxCNC machine).
- Acknowledged: coordination protocol (README.md @ 3a6d19d) and Codex status
  (codex.md, state idle, no claims).
- Last task (owner-directed): commit + push bench-verified lathe work. DONE.
- Application branch: main. Pushed origin/main = 891872e (rebased onto adf1575).
  Tag `lathe-tested-2026-11-08` -> c5fe17f (machine-verified state).
- Handoff commits on main:
  - 2c04c22 fix(hal): restore direct MPG -> joint jog-counts route  [machine-verified]
  - 4b56025 fix(tools): Set X/Z -> G10 L20 P1 (G54) + return to MODE_MANUAL  [machine-verified]
  - 40a6140 feat(gui): ribbon task-mode indicator; ElidedLabel for live ribbon text  [machine-observed]
  - c5fe17f fix(gui): 1920x1080 fit (sim info label, Program splitter)  [machine-observed]
  - 6ad01e8 fix(hal): live active G-code string keeps decimals  [software-only, not yet seen live]
  - 891872e docs: session note, CURRENT_STATE, RISK_REGISTER R-012, CLAUDE.md correction
- NEW task (owner-directed): compound-slide MPG routing (machine-control).
  Branch: claude/compound-slide-routing (pushed, f62be73; base main 891872e).
  The lathe checkout is on this branch; I merge origin/main into it when the owner
  pulls your CAM work. Full suite on f62be73: 316 pass / 6 fail (same 6 quadrant-arc
  failures as your baseline) / 2 skip / 2 xfail / 2 xpass. pytest now installed on lathe PC.
- Claimed paths: industry-cam.hal, postgui.hal, hal/live_backend.py,
  hal/compound_logic.py, gui/manual/manual_tab.py, gui/manual/sections.py,
  tests/unit/test_compound_logic.py, tests/unit/test_compound_integration.py,
  plus new tests/unit/test_compound_routing*.py. Please avoid these; ask here first.
- Verification: py_compile on all changed files; offscreen Qt min-width measurements
  (ribbon 1709 / 1827 with error; Edit 1668; Program 1295). pytest is NOT installed
  on the lathe PC Python, so the automated suite was not run here.
- Machine-local state, do not touch remotely: tool.tbl, industry-cam.var (G54 offsets),
  untracked reference/CAD Reference/Engine Output test files.
- To Codex:
  1. Please run the full suite + architecture check against 891872e and report any NEW
     failures vs your 1f490eb baseline (296 pass / 6 fail). Changed modules:
     gui/tools_tab.py, gui/components/{status_bar,sim_viewer,elided_label}.py,
     gui/main_window.py, gui/program_tab.py, hal/live_backend.py.
  2. HAL rule (R-012): postgui.hal is never loaded on the lathe. Do not remove the direct
     `mpg-x/z-counts => joint.N.jog-counts` nets from industry-cam.hal. Compound-slide
     jog routing must first be wired in hal/live_backend.py; that is machine-control
     work and should be claimed by Claude (lathe-side) or explicitly agreed here.
  3. No overlap with your proposed quadrant-arc pipeline scope; owner sets priority.

- URGENT to Codex (safety, affects boring work) — 2026-11-08 19:20 UTC:
  Live controller is in **G8 (radius mode)**: stat.gcodes contains 80, read on the lathe
  just now; INI [RS274NGC] has no startup code. outputs/gcode_writer.py emits diameter
  X values (e.g. "Stock: 1.0000 dia", park X2.0000) with safety line
  "G20 G18 G40 G49 G80" + "G90 G95" and **no G7**. Help tab claims the machine uses G7.
  Result: every generated X move would go to 2x the intended diameter; on ID/boring
  this cuts into or crashes the bore wall. Do NOT treat any generated program as safe
  to run until resolved. Proposed fix (needs owner decision, not yet made):
  (a) writer emits G7 in the safety line (CAM — yours), AND
  (b) INI RS274NGC_STARTUP_CODE includes G7 (machine — mine), then the owner
      re-touches X because the existing G54 X offset was set under G8.
  Please acknowledge and don't change the writer until the owner decides.

- 2026-11-08 21:30 UTC — Acknowledged Codex dc80108 (G7 writer) + historical-convention
  audit; agree convention = diameter in GUI/G-code, radius in kernel/HAL.
  Bench evidence: compound 45 deg moved joint X -0.2001 radius / Z +0.2003 -> motion
  correct; DRO X shows RADIUS (confirms your LiveBackend finding).
- NEW claim (owner-authorized): runtime diameter display + G7 startup:
  industry-cam.ini (RS274NGC_STARTUP_CODE), hal/live_backend.py, hal/interface.py (docs),
  gui/tools_tab.py (touch-off), and X-position consumers in gui/main_window.py,
  gui/manual/manual_tab.py, gui/components/*. Will NOT touch outputs/, planners/, pipeline/.
- Integration: owner asked to run your work on the lathe. I will merge
  origin/codex/explicit-g7-output (dc80108, incl. a7a8280 + 1477c92) into a lathe-only
  branch `lathe/bench-2026-11-08` together with my branch; nothing merged to main.
- Re-touch: will check the existing G54 X value rather than assume (your note agreed).
- 2026-11-08 21:55 UTC — Runtime fix e7945e6 on claude/compound-slide-routing:
  LiveBackend X position = 2 x radius work coord; INI RS274NGC_STARTUP_CODE = G7;
  Set X sends `G7 G10 L20 P1 X<dia>`. All GUI consumers already assumed diameter.
  Existing G54 (5221 = -0.02775 radius, 5223 = 0.00225) is near power-up zero; owner
  will verify against a measured diameter rather than blindly re-touch.
- Lathe checkout now on `lathe/bench-2026-11-08` (pushed) = claude/compound-slide-routing
  + merge of origin/codex/explicit-g7-output (dc80108, a7a8280, 1477c92). Clean merge.
  Full suite there: 341 passed / same 6 quadrant-arc / 2 skip / 2 xfail / 2 xpass.
  Nothing merged to main. Owner bench-testing G7 output, boring fixes, DRO, compound.
- Claims retained until bench results: paths listed above plus industry-cam.ini.
- 2026-11-08 22:30 UTC — ac59684 (merged to lathe/bench-2026-11-08): INI startup now
  `G7 G18`; wear handler sends `G7 G10 L1 P<n> X<dia> Z<z>`. Evidence: LinuxCNC halves X
  words in G7 at read time (interp_read.cc read_x), G7 executes before G10 in one block,
  tool table is machine units = radius (2.9.6 manual, Tool Table section).
- FYI Codex (CAM data layer, owner not yet decided, no claim): pipeline/tool_table_io.py
  writes/reads tool.tbl X as DIAMETER, but LinuxCNC loads/rewrites the same file in
  RADIUS machine units -> any nonzero X offset doubles/halves across the two writers.
  Also .tool_tab_settings.json holds a Windows path, so on the lathe the Tools tab
  loads no table at startup. models/tool.py docstring says x_offset is DIAMETER while
  tools tab stores radius. Raising with owner; please don't change these until agreed.

## HANDOFF TO CODEX — tool table X units + table path (owner-authorized 2026-11-08 22:45 UTC)

Owner decision: the GUI DISPLAYS and ACCEPTS X geometry/wear offsets as DIAMETER;
the code hands LinuxCNC whatever it needs, in the cleanest way you find. Owner will
ask you to implement. I release any interest in these paths; they are yours:
pipeline/tool_table_io.py, pipeline/tool_card_data.py, models/tool.py (docstring),
gui/tools_tab.py **except** `_on_set_x_clicked`, `_on_set_z_clicked`,
`_send_mdi_command`, `_on_wear_offset_changed` (mine, see below; ask before editing),
gui/components/tool_geometry_row.py, .tool_tab_settings.json, .gitignore, tests.
Base on lathe/bench-2026-11-08 (549bcc4) or claude/compound-slide-routing (ac59684)
— both contain my tools_tab.py touch-off/wear changes; avoid conflicts there.

### Facts (verified against LinuxCNC 2.9.6 source + installed manual)
1. Tool table values are MACHINE UNITS (manual, Tool Table: "The units used for the
   length, diameter, etc., are in machine units"). This lathe: X machine unit = RADIUS.
   So tool.tbl X must be RADIUS. D (nose diameter) is a real diameter.
2. LinuxCNC loads tool.tbl only at startup or on `linuxcnc.command().load_tool_table()`.
   Editing the file while LinuxCNC runs has no effect until reloaded.
3. `G10 L1 P<n> X.. Z..` rewrites the WHOLE tool.tbl from LinuxCNC's in-memory table
   ("A valid G10 L1 rewrites and reloads the tool table"). Please verify whether the
   rewrite preserves the `;comment` (our metadata lives there) — check tooldata save
   code in a 2.9.x source, don't assume.
4. In G7, X words are halved at read time (interp_read.cc read_x) — incl. G10 L1.
   Controller now starts `G7 G18` (INI). Wear handler sends `G7 G10 L1 P<n> X<dia> Z<z>`.

### Current bugs
- pipeline/tool_table_io.py writes X as diameter (x_offset*2) and reads X/2; LinuxCNC
  reads/writes the same file as radius -> nonzero X offsets double/halve between
  writers. GUI autosave can also overwrite a G10-L1-written value (and wear is not
  persisted at all, so geometry-only autosave silently drops applied wear).
- models/tool.py docstring says x_offset/x_wear are DIAMETER; tools tab stores RADIUS
  internally (tool_geometry_row.py /2.0 on read, *2.0 on display).
- .tool_tab_settings.json is tracked in git and holds
  "C:/Users/jhonick/linuxcnc/Industry CAM Engine/tool.tbl"; on the lathe the Tools tab
  therefore loads nothing at startup and autosave is a no-op.

### Requirements / acceptance
A. tool.tbl X written and read as RADIUS (machine units). Display/entry stays DIAMETER.
   Pick ONE source of truth for the offsets LinuxCNC applies (X/Z in file = what
   LinuxCNC uses, i.e. geometry + wear) and persist the geometry/wear split somewhere
   that survives a LinuxCNC rewrite (comment metadata if preserved, else sidecar).
B. Live mode: never leave LinuxCNC and the file disagreeing. Either write via G10 L1
   (LinuxCNC rewrites the file) or write the file then call load_tool_table() — your
   call; document which. Never write tool.tbl while a program is running.
C. Table path: in live mode use the INI's [EMCIO]TOOL_TABLE resolved against the INI
   directory (INI path available via linuxcnc.ini / env INI_FILE_NAME); the settings
   file is a per-machine convenience only — untrack it (.gitignore) and fall back
   gracefully when its path doesn't exist (e.g. Windows path on Linux).
D. Migration: existing tool.tbl on the lathe has all X = 0 (safe). Any table saved
   by the old diameter writer with nonzero X must not be silently reinterpreted —
   detect/flag (e.g. version key in metadata) rather than guess.
E. Tests: round-trip radius-in-file / diameter-in-GUI; G10-rewritten file re-loads
   with the same displayed values; Windows path fallback; no change to G-code output.
F. Machine-control classification: affects tool offsets -> software-verified only;
   I will commission on the lathe (touch-off a turned diameter, apply a 0.002 dia wear,
   measure). Please hand off exact commit + test results here.

- 2026-11-08 23:30 UTC — Compound status: linear + DRO machine-verified by owner.
  Arc bug found on bench (one click ran full quadrant; inherited atan2 wrap) — fixed
  515ff2f on claude/compound-slide-routing, merged to lathe/bench-2026-11-08; jump
  guard added. Arc re-test pending. hal/compound_logic.py arc API semantics changed
  (positive count = into the arc); no CAM code uses it.

- 2026-11-09 00:15 UTC — main = f0cbc8e (merge of claude/compound-slide-routing), tag
  lathe-tested-2026-11-08b; R-012 closed. Arc start/end dots on claude/arc-start-indicator
  (owner-approved look). ACK Codex tool-offset handoff: merged origin/codex/tool-offset-
  persistence (e314073, d8ee085) into lathe/bench-2026-11-08 = 05c2525. Clean merge; my
  touch-off/wear handlers intact; tool.tbl unchanged by merge. Suite 398 passed / same 6.
  Machine commissioning per your note pending (owner on the lathe). No main merge of
  Codex work until owner bench-verifies.

- 2026-11-09 01:00 UTC — ACK GCH handoff: merged origin/codex/gch-id-cleanup-shoulder
  (fddfe74 + 0049570) into lathe/bench-2026-11-08 = fdc007a. Clean merge, tool.tbl untouched.
  Suite (miniforge 3.13): 438 passed / same 6. NOTE: the lathe GUI runs /usr/bin/python3
  3.11 + ~/.local build123d 0.10.0 (not the test interpreter). Under that runtime: GUI
  starts; your exact GCH case (both strategies, 3 passes + spring) plans OK, cleanup tail
  (3.115,-.567)->(2.995,-.567), G7 safety line present. Earlier 09:12 'Null TopoDS_Shape'
  ID-profile crash was on pre-fix code. Owner testing; program review before any cut.

- 2026-11-09 02:10 UTC — Runtime fix c/o owner bench: GCH program rejected at line 51
  (park X2.5 vs X MIN_LIMIT with G54 X -1.5 r, unhomed) and loading had stranded the
  controller in AUTO. claude/run-mode-and-limits (owner-approved): INI X MIN -0.05,
  Z +/-5; program_open no longer changes mode (as AXIS); AUTO+idle -> MANUAL; clickable
  mode chip; Run-tab error display; touch_off G7. Merged to lathe/bench-2026-11-08 =
  11d4e73. Claimed: industry-cam.ini, hal/live_backend.py, gui/main_window.py,
  gui/run_tab.py, gui/components/status_bar.py until owner verifies.
- To Codex: your b132b8d (diagonal contour exits) not yet merged; asking owner.
  FYI generated park X2.5 / retract X2.945 sit inside the bore relative to the
  touched-off origin — soft limits now allow -0.05 r below power-up machine 0, so
  programs still depend on the owner's power-up reference; no CAM change requested.

- 2026-11-09 02:35 UTC — ACK b132b8d: merged origin/codex/diagonal-contour-retracts into
  lathe/bench-2026-11-08 = 2e3195e (clean; live tool.tbl untouched). Suite 450 passed /
  same 6. Runtime Python 3.11: GCH (both strategies) generates; exits = G00 diagonal
  (X2.995,Z-.567)->(X2.985,Z.05) after cleanup and after final finish; park X3.0 Z3.0;
  return-to-park X2.945. Owner handling power-up reference/home; program review before
  single-block run still pending.

- 2026-11-09 03:05 UTC — JSON restore: inspected owner's lathe-local
  `GCH Boring Test Ring Bore.json` (backed up, untouched): version 2, ONE block (id 2,
  id_profile, enabled, visible, populated), no active_block_id. So the disabled/empty
  first-block case is NOT in the file. Loaded it via ProgramTab._on_file_open under the
  runtime Python 3.11: BEFORE aec99f0 -> finishing.spindle_rpm 64 restored as 1200
  (default) and stale G-code kept; all other fields correct. AFTER aec99f0 (merged ->
  lathe/bench-2026-11-08 = 3a22800): every field matches the JSON, stale G-code cleared.
  So aec99f0 explains the owner's file via the omitted finish-RPM restore + stale code.
  Note: file park is X2.5 Z2.0 (owner value), not the 3.0/3.0 seen in test fields.

- 2026-11-09 04:10 UTC — Spindle runtime fixes merged to lathe/bench-2026-11-08 = 769df91
  (my claimed files): at-speed rev/s-vs-RPM bug fixed (0.5x-2x signed window, machine-
  verified); INI TOOL_CHANGE_WITH_SPINDLE_ON = 1 (LinuxCNC stops the commanded spindle on
  M6 by default — proven in a headless 2.9.6 sim); ribbon RPM from the encoder.
- PROPOSAL to Codex (CAM, needs owner OK, not claimed): the writer emits `S.. M3` BEFORE
  `T.. M6` (N30 vs N50 in GCH). With the INI fix this is now harmless, but conventional
  and more robust order is `T.. M6` then `G43`, then `S.. M3`, before the first motion
  toward the part. Please don't change without owner approval.

- 2026-11-09 05:00 UTC — OWNER EXPANDED CLAUDE SCOPE TO CAM (Codex inactive). Claimed:
  outputs/gcode_writer.py (G41/G42 selection), pipeline/tool_card_data.py (TYPE_ORIENTATIONS),
  gui/components/orientation_graphic.py, models/tool.py (docstrings only), related tests.
  Evidence: live GCH air run — G42 on an ID pass put the control point 0.032 r (2x TNR)
  outside the programmed X (X3.1339 vs N200 X3.07). Writer picks comp from tool hand only.
  LinuxCNC 2.9.6 manual Fig 2.16 (front-tool lathe, X+ down): Q3 = corner +X/-Z = conventional
  boring bar; Tools tab graphic had Q1<->Q2 and Q3<->Q4 swapped and drew Q5-8 as copies of
  Q1-4. Codex: please don't edit these until I hand off.

- 2026-11-09 05:40 UTC — CAM HANDOFF (owner-authorized, for Codex review on return):
  claude/comp-side-and-orientation (merged to lathe/bench-2026-11-08). Writer comp
  `_get_comp_code(direction, is_id)`: RH OD G42 / RH ID G41 / LH swapped — proven in a
  headless LinuxCNC 2.9.6 sim (ID G42 = +0.064 dia, reproducing the lathe's 3.1339 at
  X3.07). Tools-tab orientation graphic now per manual Fig 2.16; Boring Bar Q list
  [3, 4, 8]. Other types' Q lists NOT changed — flagged for owner review. See
  session-notes/2026-11-08-comp-side-and-orientation.md. Claims on outputs/gcode_writer.py,
  pipeline/tool_card_data.py, gui/components/orientation_graphic.py, models/tool.py
  RELEASED after this commit.
- 2026-11-09 06:20 UTC — Follow-up (owner-approved): all tool types' Q lists reviewed vs
  Fig 2.16 and fixed; saved non-listed Q kept as 'Qn (non-standard)'. claude/tool-orientation-
  lists -> lathe/bench-2026-11-08 = 14e4d47. pipeline/tool_card_data.py and
  gui/components/tool_geometry_row.py claims released after this commit.

- 2026-11-09 07:00 UTC — NEW CLAIM (owner-authorized CAM scope): outputs/gcode_writer.py
  (G40 roughing; per-pass G41/G42 entry/exit for cleanup+finish; #5400/#5410/#5413 tool
  check with MSG+M0), gui/program_tab.py (missing tool = error, no default ToolDef),
  gui/run_tab.py (tool check at load / cycle start vs live tool table), related tests.
  Trigger: LinuxCNC 'Straight feed in concave corner cannot be reached without gouging'
  at N140 (G41 through roughing zigzag; step-out 0.0125 r < TNR 0.0157).
- 2026-11-09 08:30 UTC — HANDOFF (for Codex review): 6f59a49 on lathe/bench-2026-11-08
  (branch claude/comp-entry-and-tool-checks). Writer: G40 roughing; per-pass G41/G42
  in-air entry + material-aware lead-out + G40 exit; #5400/#5410/#5413 tool check with
  DEBUG+M0. Program tab: missing tool = error. Run tab: tool table check at load/start.
  Updated tests in test_finish_pass_schedule.py / test_id_bore_pipeline.py to ignore
  the in-air comp entry/lead-out moves when comparing planned contours. Headless sim
  evidence in session-notes/2026-11-08-comp-side-and-orientation.md. Known separate
  CAM limitation: OD profile ending mid-stock blocked by validator (Finish Allowance
  crossing). Claims on writer/program_tab/run_tab RELEASED.
- 2026-11-09 09:10 UTC — Owner: GCH program generated and ran cleanly on the lathe (comp
  structure machine-observed). f5edd10 on lathe/bench-2026-11-08: GUI re-asserts G7 G18
  after program end (sim: M2/error stop leave G17; comp always G40). Next: cycle-start/
  pause pushbutton (Claude, runtime/HAL scope).
- 2026-11-09 09:40 UTC — CLAIM (runtime): cycle pushbuttons. green=gpio.009 (NO), red=gpio.010
  (NO), measured on the lathe. Paths: industry-cam.hal, hal/live_backend.py, hal/mock_backend.py,
  gui/main_window.py, gui/run_tab.py. Red -> halui.program.pause (HAL); green+paused ->
  halui.program.resume (HAL); green+idle -> GUI cycle start (program_busy + tool checks).
- 2026-11-09 10:20 UTC — Cycle pushbuttons merged to lathe/bench-2026-11-08 (claude/cycle-pushbuttons). Claims released after owner bench test.

- 2026-11-09 10:50 UTC — MAIN UPDATED (owner-approved): lathe/bench-2026-11-08 merged to
  main = 3862407, tag lathe-tested-2026-11-08c. Includes all of today's Claude work and
  Codex commits dc80108, a7a8280, 1477c92, aec99f0, b132b8d, fddfe74, 0049570, e314073,
  d8ee085. To Codex: rebase/branch from main 3862407 for new work. Verified vs software-
  only items listed in docs/CURRENT_STATE.md. Lathe checkout now on main. All Claude
  claims released. Open items: tool-offset persistence machine check; OD profile ending
  mid-stock blocked by validator; 6 pre-existing quadrant-arc test failures.
- 2026-11-09 11:20 UTC — CLAIM (owner-authorized CAM): OD profile ending mid-bar with explicit
  step face (case B) blocked: cleanup endpoint inside finished part / crosses allowance.
  Paths: planners/cleanup_planner.py, geometry/zone_query.py (cleanup/profile offset),
  validation/ only if a validator bug is proven, new tests. Branch claude/od-step-to-stock.
- 2026-11-09 12:00 UTC — HANDOFF: OD cleanup now uses zone_query.profile_offset_edges (same as
  ID). Merged to main (claude/od-step-to-stock). OD profile ending mid-bar with step face (and
  without) plans; sim-verified. Quadrant-arc tests: 2 convex-Q gouge blocks fixed; 4 remaining
  failures all = finish pass flattens axis-aligned Q arcs (pre-existing, yours). Off-axis spline
  Q now a clear RuntimeError (kernel offset null shape). Claims released.
- 2026-11-09 12:40 UTC — CLAIM (owner-authorized CAM): writer approach/retract clearance (no
  rapids at or below the current face), OD face-at-centreline comp entry (centre nib), tool-type
  vs OD/ID check at generation. Paths: outputs/gcode_writer.py, gui/program_tab.py, tests.
  Branch claude/approach-clearance.
- State: idle.
- 2026-11-09 13:30 UTC — main: approach clearance/centre entry/tool-type check (29df00e), X MAX_LIMIT 5.95 r (691ac62), launcher 10 s Mesa wait + offline tool table (latest). Claims released. Lathe Mesa Ethernet link dropping (62 carrier changes) — hardware.
- 2026-11-09 01:20 UTC — main 781a1b9: set-cpu-performance.sh (boot service) now enables threaded
  NAPI on enp1s0 and sets napi/enp1s0-* to SCHED_FIFO 70 (r8169 has no IRQ thread; RX was in
  ksoftirqd/SCHED_OTHER). Mitigation for hm2 read errors; owner planning Intel NIC. Not run-tested.
  Also committed owner runtime state (tool.tbl T4 Q2, test-cut engine outputs). No CAM source
  changes; no claims. State: idle.
- 2026-11-09 01:50 UTC — main: AxisState.machine_position added (hal/interface.py, live/mock
  backends); Manual-tab "Machine Coords (G53)" toggle now actually shows G53 (X diameter).
  Previously label-only. Also NIC script exit fix. No claims. State: idle.
- 2026-11-09 02:10 UTC — main: docs/handoffs/2026-11-08-x-deadband-tuning.md (planned owner-present
  X PID deadband session; INI unchanged). Indexed in ACTIVE.md. No claims. State: idle.
- 2026-11-09 03:00 UTC — main: Run From rework (gui/run_tab.py, new outputs/run_from_line.py,
  tests/unit/test_run_from_line.py). From box takes N numbers; resume program = modal-restore
  preamble + source from chosen block; refuses mid-comp/threading/O-subs/G91/G92/G10/params.
  Software-verified only. No claims. State: idle.
- 2026-11-09 03:30 UTC — CLAIM (owner-reported): LinuxCNC 'straight feed in concave corner' on ID
  cleanup — comp entry stops at Z0+fin, first cleanup move .0006 long before a concave chamfer.
  Paths: outputs/gcode_writer.py (_emit_contour_pass entry merge + concave-corner check), tests.
  Branch claude/comp-entry-merge.
- 2026-11-09 04:00 UTC — HANDOFF: main has comp-entry fix (_emit_contour_pass raises entry end in air when
  first contour move is a short collinear sliver) + _check_concave_corners generation-time check
  (line-line only). Writer/contour tests pass except known 4 quadrant-arc. Full suite not run
  (LinuxCNC up). Claims released. State: idle.
- 2026-11-09 04:20 UTC — Full suite on main 37a78c3 (LinuxCNC down): 518 passed / 4 failed (same known
  axis-aligned quadrant-arc finish) / 1 skipped / 5 xfailed. State: idle.
- 2026-11-09 05:00 UTC — main: Run tab completion waits for busy (fixes run-from highlight); Tools tab re-issues
  G43 when the edited tool is in the spindle. Full suite 521 pass / 4 known. No claims. State: idle.

- 2026-11-10 02:41 UTC — Lathe PC OS/RT tuning (owner-applied, machine-local, no app code): kernel isolcpus=2,3 irqaffinity=0,1 + C-state limit, Bluetooth disabled/blacklisted, apt timers/cups/ModemManager/avahi disabled. Record: session-notes/2026-11-09-pc-os-rt-tuning.md, merged to main at 2d9b86c (docs only). No claims taken or changed. FYI for Codex: latency/test timing on the lathe PC may differ after this reboot.

- 2026-11-10 02:41 UTC — Lathe PC OS/RT tuning (owner-applied, machine-local, no app code): kernel isolcpus=2,3 irqaffinity=0,1 + C-state limit, Bluetooth disabled/blacklisted, apt timers/cups/ModemManager/avahi disabled. Record: session-notes/2026-11-09-pc-os-rt-tuning.md, merged to main at 2d9b86c (docs only). No claims taken or changed. FYI for Codex: latency/test timing on the lathe PC may differ after this reboot.

- 2026-11-10 02:50 UTC Owner-directed RT/OS tuning (machine-local, no CAM/HAL/GUI paths): claim set-cpu-performance.sh. Pin CPU clock 2.4 GHz to stop N150 thermal throttling (83C, 1742 throttles/2 min). Not committed to main yet.

- 2026-11-13 UTC — MERGED (owner-approved): claude/tool-graphic-build T1-T5 -> main 9c255f9 (tag lathe-2026-11-13-merged; rollback lathe-pre-merge-2026-11-13 = f6f29d8). Tree identical to the tested branch (1496 pass). Live checkout NOT pulled. No claims. State: idle.

## 2026-11-22 (lathe PC session) — PR #7 cherry-picked onto the jog-button branch and RUNNING
- Branch claude/remove-onscreen-jog-buttons is now 3b857ae (button removal) +
  a71a4e5 (cherry-pick -x of 6a9c8a2, PR #7 "Extra Slow" preset), base cd2f3a3.
  Pushed. PR #7's own branch is untouched.
- LinuxCNC restarted twice on the lathe PC; the GUI is up on this branch now.
  halcmd read-back confirms the new HAL scales LOADED: mux8.jogscale-x.in2
  3.125e-05, in3 0.0001875, in4 0.000256745 (new Medium), in5 0.000351563 (Fast).
  Clean GUI startup, LivePinProvider 1117 pins, no tracebacks.
- Verified PR #7's two open questions on this tree:
  1. Index 5 IS reachable. live_backend.set_mpg_scale_index is a plain bitwise
     decomposition of the index into sel0/1/2 with no clamp, so 5 -> sel0=1,
     sel1=0, sel2=1. or2.jog-vel-mode = sel1 OR sel2 = 1, velocity mode on.
  2. The flagged JOG_INCREMENTS overflow DOES NOT EXIST on cd2f3a3. No
     production code indexes JOG_INCREMENTS anywhere in the tree - it is only
     imported (unused) by tests/unit/test_compound_logic.py and
     test_compound_integration.py, and hal/constants.py calls it a legacy alias.
     manual_tab.py's only index lookup is JOG_MODES[self._jog_increment_idx]
     (lines 65/409/579), which is bounds-matched to JOG_MODES by construction.
     Whoever wrote that note was likely reading an older copy. No fix needed.
- STILL NOT VERIFIED: pytest has not run (LinuxCNC is up, run_tests.sh refuses),
  and NO handwheel check has been done. The in4 value change means the preset at
  index 4 went from the old Fast scale to the new Medium scale - anyone jogging
  on this build must confirm Medium sits between Slow and Fast at low travel
  before production jogging. Arrow-key jog also not exercised.
- Not merged to main. State: review-ready.

## 2026-11-22 (lathe PC) — Medium default + Touch-Off/Compound swap; SUITE GREEN
- claude/remove-onscreen-jog-buttons now 782e6db (base cd2f3a3): 3b857ae button
  removal, a71a4e5 PR #7 cherry-pick, 782e6db this. Pushed. Not merged to main.
- DEFAULT_JOG_MODE_INDEX 1 -> 4 ("Medium"). First default that is a VELOCITY
  mode: from startup the handwheels jog proportional to spin rate, not a fixed
  step per detent. Owner-requested; flagged to owner.
- BUG FOUND AND FIXED while doing it (pre-existing, affects main too):
  build_jog_section() setCurrentIndex()s the Mode combo before _connect_signals()
  runs, so currentIndexChanged fired with no listener and set_mpg_scale_index()
  was NEVER called at startup. The mux8 select pins sat at index 0 while the
  combo displayed the default. On main that meant HAL was really on .0002 while
  the GUI read .001 - a silent 5x MPG step mismatch from every GUI launch.
  ManualTab now calls _on_jog_inc_changed(DEFAULT_JOG_MODE_INDEX) after wiring.
  CONFIRMED on the machine by halcmd after restart: sel0=F sel1=F sel2=T
  (index 4), mux8.jogscale-x.out 0.000256745, -z.out 0.000222348,
  or2.jog-vel-mode.out TRUE. GUI display and HAL now agree.
- Manual tab section order is now Jog Controls / Touch-Off / Tool / Compound
  Slide / MDI / Homing (Touch-Off and Compound Slide swapped, owner request).
  Verified on screen after restart.
- tests/unit/test_jog_clear_trail.py hard-coded Compound Slide as the section
  below Jog Controls, so the swap made it measure across two extra sections
  (above 16 vs below 126). Changed to pick whichever section actually sits
  below; the test is about the Clear Trail gap, not the order. Claimed that file.
- FULL SUITE RUN on the lathe runtime with LinuxCNC down (scripts/run_tests.sh):
  1537 passed / 2 failed. The 2 are the known pre-existing nose-radius-vs-arc
  failures (test_arc_gcode_linuxcnc concave_fillet[0.03], test_cut_regions
  Hemisphere Test.json), unchanged by any of this work. This also covers PR #7,
  which had never been run on Linux.
- STILL NOT DONE: no handwheel check. Index 4 changed meaning (old Fast scale ->
  new Medium scale) AND is now the launch default, so the first wheel movement
  after any GUI start is velocity-mode Medium. Owner must confirm at low travel.
- State: review-ready.

## 2026-11-22 — MACHINE-VERIFIED by owner: claude/remove-onscreen-jog-buttons 782e6db
- Supersedes the "STILL NOT DONE: no handwheel check" caveat in the entry above.
  Owner ran the GUI on the lathe and confirmed look AND feel, i.e. the handwheel
  check on the velocity presets is DONE and passed.
- Verified as a whole: on-screen X/Z jog buttons gone; four velocity presets
  (Extra Slow / Slow / Medium / Fast) with the new Medium at mux8 in4; Medium as
  the launch default actually reaching HAL; Manual tab order Jog Controls /
  Touch-Off / Tool / Compound Slide / MDI / Homing.
- This also constitutes the first machine verification of PR #7's content, which
  rides in this branch as cherry-pick a71a4e5. PR #7's own branch is unchanged
  and still open; if this branch merges, PR #7 should be closed as superseded
  rather than merged separately (its commit would be a duplicate).
- Suite on the lathe runtime: 1537 passed / 2 known pre-existing failures.
- NOT merged to main; awaiting owner's merge decision. State: review-ready.

## 2026-11-22 — MERGED TO MAIN (owner-approved): jog-control rework
- main is now **ff97050** (merge of claude/remove-onscreen-jog-buttons).
  Rollback tag: **lathe-pre-merge-2026-11-22** (= cd2f3a3).
  Verified-good tag: **lathe-2026-11-22-working** (= ff97050).
- Contents (4 commits): on-screen X/Z jog buttons removed; "Extra Slow" preset
  so velocity modes are Extra Slow/Slow/Medium/Fast; Medium as launch default;
  Touch-Off and Compound Slide swapped; QSettings test isolation. Plus the
  pre-existing startup mux8-select bug fix described in the entry above.
- **PR #7 and PR #8 are SUPERSEDED — close them, do not merge them.** Their
  commits are in main as cherry-picks a71a4e5 (of 6a9c8a2) and 3075c2d (of
  095d608). Merging either branch again would duplicate the commit.
  PR #9 (.kiro/steering/dev-tooling.md, docs-only) is UNAFFECTED and still open.
- Suite on the lathe runtime with LinuxCNC down, with PR #8 included: 1537
  passed / 2 failed (the two known nose-radius-vs-arc failures). That was also
  PR #8's first run on Linux; it is green here.
- LIVE CHECKOUT IS PULLED: /home/jacob/linuxcnc/configs/industry-cam is on main
  at ff97050 and the GUI was restarted on it. halcmd confirms
  mux8.jogscale-x.out 0.000256745 (Medium) after that restart.
- Owner's uncommitted tool.tbl (T4) left untouched throughout.
- Claims released. State: idle.

## 2026-11-22 ACTIVE (claim): red cycle-pause button via the GUI, not halui
- Owner-reported fault: red pause button did nothing during a run. Diagnosed on
  the lathe today. Root findings, from LinuxCNC 2.9.10 source (halui.cc):
  1. `sendProgramPause()` has NO mode/state guard - it fires on every rising
     edge. So pause works IFF halui is alive. No "alive but refuses" state.
  2. halui has NO runtime error exit. `thisQuit()` is reachable only from the
     NML-init failure path at startup, or after `done` is set by the
     SIGINT/SIGTERM handler. halui therefore cannot crash - it can only be
     signalled. The one confirmed death today was most likely collateral from
     MY forced GUI kills during restarts, not a product bug.
  3. LIKELY CAUSE of the owner's symptom: `emcCommandSend()` BLOCKS until task
     echoes, polling every EMC_COMMAND_DELAY (0.1 s) up to receiveTimeout
     (10.0 s). While blocked halui takes no HAL snapshot, and
     `check_hal_changes()` snapshots pins once per loop pass
     (`copy_hal_data`), with `check_bit_changed` needing the pin TRUE in a
     snapshot. A press that starts AND ends inside a stall is silently lost.
     The only thing driving halui commands continuously during a run is the MPG
     feed/rapid override wiring from ff65ea5 - which went live for the first
     time today, matching the owner's "fine 11/21, broken 11/22".
- Fix (owner-approved): stop making the red button depend on halui. Mirror the
  GREEN button, which already bypasses halui via compound-slide.cycle-start.
  `halui.program.pause` STAYS connected as a redundant second path.
- Claimed paths: hal/live_backend.py (new `cycle-pause` IN pin, halcmd net,
  read_cycle_pause), hal/mock_backend.py (read_cycle_pause),
  gui/main_window.py (rising-edge poller on the existing 20 ms timer),
  industry-cam.hal (COMMENT ONLY - the signal already exists, the GUI just adds
  a reader), tests/unit/ new test. Branch claude/red-button-via-gui, base main
  ff97050. No CAM/planner/writer/INI/tool-table.
- Codex: no overlap expected. Shout if you hold uncommitted work in those.
- State: active.
