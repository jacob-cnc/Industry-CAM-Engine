# Claude status

- Updated: 2026-11-09 10:50 UTC
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
- State: idle.
