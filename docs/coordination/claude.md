# Claude status

- Updated: 2026-11-08 18:00 UTC
- State: idle
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
- Claimed paths: none (all released).
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
