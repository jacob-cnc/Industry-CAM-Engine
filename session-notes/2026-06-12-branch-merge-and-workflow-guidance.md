# Session: 2026-06-12 - Branch Merge, Threading UX, and Sim Visualization

## Workstream

Branch: main
Environment: Windows offline development
Change classification: Software-only (GUI, planner visualization, file format)

## Starting State

Repository had two diverged branches:
- `main` — stale, missing 6+ commits of feature work
- `fix/contour-roughing-and-ui-improvements` — active, had all features (corner
  breaks, multi-block, threading, grooving, arc improvements)

An initial attempt to reimplement threading from scratch broke existing
functionality. All those changes were reverted.

## Goal and Acceptance Criteria

- Merge feature branch into main (single authoritative branch)
- Update threading panel UX: standard size list with tolerance bands, fit class
- Add G76 visualization to the sim viewer
- Fix block list sizing and file load issues
- Create a valid conv test program for 1/4-20 cap screw

## Changes Made

### 1. Branch Merge
Merged `fix/contour-roughing-and-ui-improvements` into main (38,898 lines, 96
files). All features restored: corner breaks, multi-block programs, threading
planner, grooving planner, quadrant arcs, metric/inch toggle.

### 2. Threading Panel Rewrite (`gui/components/threading_panel.py`)
- Standard size dropdown: UNC/UNF interleaved by diameter, Metric coarse+fine,
  NPT, ACME, plus "Custom" option
- Fit selector: Mid / MMC / LMC (tolerance position within class band)
- Class selector: 2A / 3A / 1A (separate field)
- Direction: External / Internal
- Custom fields (TPI, Major Ø, Form) hidden unless "Custom" selected
- All fields 44px minimum height for touch
- Live computed info display: target major, pitch, minor diameters, depth, max
  RPM, pitch diameter band
- ASME B1.1 tolerance computation for UN, ISO 965 for metric, B1.5 for ACME
- Tool default changed to T2 (matches tool table)

### 3. G76 Sim Visualization (`gui/components/sim_viewer.py`)
- `_expand_g76_for_sim()` added to the sim parser
- Recognizes G76 lines and expands into rapid/feed SimMoves showing actual tool
  motion: approach at pass depth → feed along thread → chamfer lead-out → retract
- Constant-area (sqrt) depth progression computed from J and K words
- All expanded moves stamped with G76's line_idx (code panel highlights G76
  during playback)
- Works for any .ngc file with G76, not just our generated programs

### 4. Threading Color (`gui/colors.py`, `gui/components/graph_widget.py`)
- `graph_threading: #E5B84C` (gold) added to palette
- `_get_segment_color` uses it for `PassType.THREADING` feed moves
- Distinct from green (profile feed), red (rapid), blue (arc)

### 5. Block List Fixes (`gui/components/block_list.py`)
- Removed `setMaximumHeight(150)` cap on list widget
- Added `QSizePolicy.Expanding` for vertical growth
- Section minimum height set to 240px (room for header + items + buttons)
- Removed parenthetical tool number from block labels

### 6. File Load Fix (`gui/program_tab.py`)
- Disconnected `block_selected` signal during `set_blocks()` in load path to
  prevent `_save_active_block_data()` from overwriting freshly loaded params
  with default field values

### 7. Conv Test Program
`reference/CAD Reference/Engine Output/Conv Tests/Quarter-20 Cap Screw Op1.json`
- Block 1: OD Profile — turn 0.2448" thread OD, 0.190" undercut, 0.500" head
- Block 2: Threading — 1/4-20 UNC, class 2A mid, 6 passes + 2 spring, 400 RPM
- Validated through pipeline: 7 roughing passes, 56 moves, no errors

## Evidence and Measurements

- **Verified:** Threading panel resolves 1/2-13 UNC class 2A mid to major
  0.4931", pitch 0.4461" — matches ASME B1.1 computed values
- **Verified:** G76 expansion produces correct pass depths (constant-area)
  and X positions matching the K word full depth
- **Verified:** Pipeline succeeds on cap screw program (both blocks)
- **Verified:** 296 tests pass (6 pre-existing quadrant arc failures unrelated)

## Verification Performed

| Check | Result | Notes |
|---|---|---|
| Compile check | All files pass | py_compile on all modified files |
| Full tests | 296 passed, 6 pre-existing fail | Quadrant arc cleanup gouge |
| Pipeline validation | Success | Cap screw OD + threading |
| G76 expansion | 31 moves for 5+2 pass cycle | Correct depth progression |

## Safety Impact

Threading visualization only — no changes to G-code output or planner logic.
The threading planner and G-code writer are unchanged from the merged branch.

## Deployment and Rollback

Deployment: Push to origin/main after commit.
Rollback: `git revert HEAD` (merge commit + this session's work)

## Known Problems and Risks

- 6 pre-existing test failures in `test_quadrant_arc_pipeline` (cleanup gouge)
- File load signal timing was fragile — fixed with disconnect/reconnect pattern
- Threading panel tolerance computation uses simplified ISO 965 formula (not
  full table lookup) — adequate for workshop use but not for certification

## Exact Next Step

1. Test the GUI end-to-end: open cap screw program, verify segments display,
   generate both blocks, confirm threading passes render in gold on the graph
2. Add threading documentation to Help tab
3. Address the 6 quadrant arc test failures (cleanup planner gouge at Q arcs)
