# GUI Buildout, MPG Velocity Mode, and Bug Fixes — 2026-05-26

## Summary

Major session covering: MPG velocity mode HAL upgrade, Run tab implementation,
Help tab with exhaustive G-code reference, multiple GUI fixes, and several
bug corrections in the tools/display system.

---

## Changes Made

### 1. MPG Velocity Mode Upgrade (HAL)

Replaced mux4 with mux8 to support 5 jog modes (2 position + 3 velocity).
Added or2 gate for jog-vel-mode signal.

**Files:** `industry-cam.hal`, `postgui.hal`, `hal/live_backend.py`, `hal/constants.py`,
`hal/mock_backend.py`, `gui/manual/sections.py`, `gui/manual/manual_tab.py`

**Mode table:**
| Index | Label | Type | Behavior |
|-------|-------|------|----------|
| 0 | .0002 | Position | 0.0002" per MPG click |
| 1 | .001 | Position | 0.001" per MPG click (default) |
| 2 | Slow | Velocity | ~0.1 in/s at moderate spin |
| 3 | Medium | Velocity | ~0.3 in/s at moderate spin |
| 4 | Fast | Velocity | ~0.6 in/s (capped by MAX_VEL) |

**Key change:** In velocity mode, stopping the MPG wheel stops the axis within
the deceleration ramp. No more position backlog coasting.

### 2. Setup Tab Fixes (HAL Monitor + Tuning)

**Problem:** Following error graph and HAL monitor showed no data in online mode.

**Root cause:** `LivePinProvider.get_pin_value()` silently swallowed exceptions
when `hal.get_info_pins()` returned data in unexpected formats. The tuning graph
fed 0.0 on every poll cycle.

**Fixes:**
- `tuning_tab.py`: Added fallback to `backend.state.following_error` when pin reads fail
- `pin_providers.py`: Relaxed type parsing (accepts string or int type/direction),
  added `halcmd getp` fallback for individual pin reads, added `halcmd show pin`
  fallback for full pin enumeration
- `hal_utils.py`: Updated MPG filter preset from mux4 to mux8

### 3. Run Tab (New)

**File:** `gui/run_tab.py`

Complete program execution tab:
- Open .ngc files
- Preview toolpath via SimViewerWidget (same proven architecture as Edit tab)
- Cycle Start / Pause / Resume / Stop controls
- Run From Line with line number input
- Live line highlighting during execution (polls MachineState.motion_line)
- Live tool position dot tracking

### 4. Program Tab — Save G-code Companion

**Problem:** Programs saved from the Program tab only saved .json (conversational
parameters). The Run tab couldn't open them.

**Fix:** `_write_program_file()` now saves a companion `.ngc` file alongside the
`.json` whenever G-code has been generated. Run tab can open the .ngc directly.

### 5. Program Tab — Tool Number Fields

Added tool number (T1–T99) spinbox to both Roughing and Finishing sections.
Saved/loaded with program files.

### 6. Program Tab — Spring Pass Option

Added "Spring pass" checkbox to Finishing section. When checked, signals the
pipeline to repeat the final finish pass at zero DOC.

### 7. Help Tab (New)

**Files:** `gui/help_tab.py`, `gui/gcode_reference.py`

Two sub-tabs:
- **Documentation** — searchable topic tree (Quick Start, tab guides, machine info, troubleshooting)
- **G-code Reference** — exhaustive searchable table of all 153 LinuxCNC codes
  (G-codes, M-codes, O-codes, word letters) with examples for each

### 8. Manual Tab — Section Reorder + Machine State to Status Bar

**Reordered** right-side sections: Jog Controls, Compound Slide, Tool, Touch-Off, MDI, Homing.

**Moved** Machine State buttons (Reset, ON, OFF) to the top status bar ribbon,
always visible regardless of active tab. Removed the Machine State collapsible section.

### 9. Status Bar — Tool Number + Live Polling

Added tool number display (`T 0`) to the status bar between feed rate and E-Stop.
Added a 5 Hz poll timer in MainWindow that keeps the status bar live with position,
state, RPM, feed, tool, and G-codes from the backend.

### 10. Insert Geometry Fixes

**Bug:** `_tip_angle_from_angles()` formula was wrong (`360 - front - back` instead
of `back - front`). Produced incorrect tip angles for all inserts (e.g., CNMG
computed as 90° instead of 80°).

**Fix:** Corrected formula to `back_angle - front_angle`.

**Threading inserts:** Were using symmetric angles `(30, 30)` giving 0° tip angle.
Fixed to proper asymmetric values (e.g., 60° UN/Metric → front=60°, back=120° → tip=60°).

### 11. Tool Orientation Defaults

Reordered `TYPE_ORIENTATIONS` so the conventionally correct orientation is first
(auto-selected on tool type change):
- Turning RH → Q2, Turning LH → Q4, Boring Bar → Q8
- Threading External → Q2, Threading Internal → Q6, Grooving → Q2

### 12. Orientation Graphic — Threading Insert Shape

**Problem:** Threading inserts rendered as a wide diamond (same as turning inserts).

**Fix:** Inserts with ≤65° included angle now render as a pointed V-shape with
triangular body, matching the physical appearance of threading/V-profile inserts.

### 13. Graph Widget — Aspect Lock + Coordinate Overlay

**Problem:** Toolpath appeared to not reach X=0 — visible gap between data and
axis gridlines. Missing gridlines at top/bottom of view.

**Root cause:** `setAspectLocked(True, ratio=1)` forced equal pixel-per-unit scaling
on both axes. For lathe parts (long Z, short X), this compressed the X axis and
introduced a visual offset between the data and the grid tick positions. The grid
also couldn't fill the full view area.

**Fix:** Removed aspect lock. Both axes now scale independently to fit the data.
Grid fills the entire view. The "gap" was an artifact of the locked aspect ratio
misaligning grid positions with data coordinates.

**Added:** Cursor coordinate overlay — hold the crosshair still for 1.5 seconds
and a tooltip appears showing `X (diameter) / Z` at 6 decimal places. Useful for
verifying exact positions during debugging.

---

## What We Learned

- **Aspect lock on pyqtgraph causes grid misalignment** when the data ranges on
  X and Y are very different. The grid tick positions are computed for the locked
  view, but the visual rendering can place them at slightly wrong pixel positions
  due to rounding in the aspect-lock transform. Removing the lock fixes both the
  grid coverage and the alignment.

- **LinuxCNC's `hal.get_info_pins()` Python API** returns data in different formats
  depending on the LinuxCNC version. The type/direction fields can be integers OR
  strings. Robust code must handle both.

- **Threading insert rendering** needs special handling — the standard parallelogram
  shape (used for 80°+ inserts) looks wrong for narrow-angle inserts. A V-shape
  with triangular body is more accurate for ≤65° included angles.

---

## Test Results

All 157 tests pass after all changes. No regressions.
