# Claude status

- Updated: 2026-11-08 22:30 UTC
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
