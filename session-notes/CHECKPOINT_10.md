# Checkpoint 10 — WCS Commissioning, GUI Fixes, Cycle Buttons, Rapid Speed

## Date: 2026-05-27

## Summary
First live commissioning session. Established WCS/tool offset workflow (G54 + per-tool
offsets via G10 L20). Fixed multiple GUI bugs discovered during commissioning. Activated
cycle start/stop pushbuttons. Diagnosed and reduced G0 rapid speed to prevent motor stall
and Z joint following error.

---

## WCS and Tool Offset Workflow Established

**Coordinate hierarchy:** G53 (machine absolute) → G54 (work offset, set per workpiece)
→ tool offset (set per tool) → displayed position.

**T99 — QCTP Master Reference Tool:**
- Added to tool.tbl: T99 P99 X+0 Z+0 D0 I0 J0 Q9, described as "QCTP Master Tool"
- Purpose: establishes G54 Z datum at chuck jaw face with the QCTP post face as reference
- X offset = 0 (no cutting geometry — only used for Z datum setup)
- Q9 chosen (nearest neutral orientation for a non-cutting reference tool)

**Per-workpiece procedure:**
1. Load T99, jog QCTP face to chuck jaw face
2. Touch off Z=0 → sets G54 Z datum
3. For each cutting tool: jog tip to same jaw face → touch off Z=0; turn test diameter → measure → touch off X=<measured diameter>

---

## GUI Fixes

### Tool Number Now Editable
- Replaced read-only `QLabel` (`_tool_label`) with `QSpinBox` (range 1–99999, prefix "T")
- `editingFinished` → `_on_tool_number_changed()` updates internal state and emits `field_changed`
- `set_data()` / `set_tool_number()` use `blockSignals(True/False)` + `setValue()`
- **File:** `gui/components/tool_geometry_row.py`

### Custom Insert Available for All Tool Types
- "Custom" insert added to all `TYPE_INSERTS` entries in `pipeline/tool_card_data.py`
- When insert_code == "Custom", orientation combo shows all Q1–Q9 (not just tool-type valid)
- New helper `_set_orientation_options(tool_type, insert_code, preserve)` consolidates logic
- **Files:** `pipeline/tool_card_data.py`, `gui/components/tool_geometry_row.py`

### G10 L20 Touch-Off (was L1)
- `tools_tab.py` `_on_set_x_clicked` / `_on_set_z_clicked` changed from `G10 L1` to `G10 L20`
- L1 sets offset directly; L20 computes offset so current position reads the given value
- L20 is correct for touch-off — it's what the operator intends: "where I am now is zero"
- **File:** `gui/tools_tab.py`

### DRO Shows G54 Work Coordinates (was G53)
- `live_backend.py` `poll()` now subtracts `g5x_offset + g92_offset + tool_offset` from
  `actual_position` (which is always raw G53)
- Without this, DRO showed machine absolute and ignored WCS/tool offsets entirely
- **File:** `hal/live_backend.py`

### Delete No Longer Auto-Renumbers
- Removed the post-delete loop that renumbered all tools T1, T2, T3…
- Custom numbers (e.g., T99) were being destroyed on every delete
- "Add tool" now finds the first unused number (not len+1)
- Delete confirmation dialog updated to remove "Remaining tools will be renumbered."
- **File:** `gui/tools_tab.py`

### MDI Mode Restores to MANUAL After Tool Change / Touch-Off / MDI
- `live_backend.py`: added `_ensure_mode(MODE_MANUAL)` at end of `tool_change()`,
  `mdi_command()`, and `touch_off()`
- Root cause: LinuxCNC stays in MDI mode after MDI commands complete; HAL motion
  component enforces task_mode==MANUAL before accepting jog inputs, so MPG was disabled
  after every tool change until operator manually switched modes
- `_ensure_mode` safety guard: if `task_mode==MODE_AUTO` and interp is non-idle,
  returns False immediately (never aborts a running program). Only aborts if stuck
  in MDI non-idle (e.g. after tool change M0).
- **File:** `hal/live_backend.py`

---

## Cycle Start/Stop Pushbuttons Activated

**Wiring:** 24V+ → NO pushbutton → TB3 P10 (Cycle Start) or P11 (Cycle Stop)
**HAL:** Changed `.in_not` → `.in` (NO button = HIGH when pressed = `.in` asserts)

The commented-out version in the original HAL used `.in_not`, which would have asserted
`halui.program.run` continuously whenever the button was NOT pressed — dangerous.

```hal
net cycle-go-raw     hm2_7i96s.0.gpio.009.in => debounce.0.8.in
net cycle-stop-raw   hm2_7i96s.0.gpio.010.in => debounce.0.9.in
net cycle-go-btn     debounce.0.8.out => halui.program.run halui.program.resume
net cycle-stop       debounce.0.9.out => halui.program.stop
```
**File:** `industry-cam.hal`

---

## Rapid Speed Reduction and Z Following Error Fix

### Symptom 1: G0 Motor Stall
- Default `[TRAJ] MAX_LINEAR_VELOCITY = 2.0 in/s` caused the Z stepper to stall on G0
- Reduced to `0.5 in/s` (30 IPM) as safe starting point for commissioning

### Symptom 2: Z Joint Following Error at 0.5 in/s
- Even at 0.5 in/s, Z axis tripped following error during G0 ramp
- Root cause: `[TRAJ] MAX_LINEAR_ACCELERATION = 10.0 in/s²` — 5× the AXIS_Z limit of 2 in/s²
  The trajectory planner was demanding acceleration the Z motor couldn't track, and with
  `FF2 = 0` (no acceleration feedforward) the PID had no means to anticipate it
- Fix: reduced TRAJ acceleration from 10.0 → 2.0 in/s²; AXIS_Z MAX_ACCELERATION 5 → 2 in/s²

**Current conservative commissioning values (increase as tuning improves):**
```ini
[TRAJ]
MAX_LINEAR_VELOCITY = 0.5        ; was 2.0
DEFAULT_LINEAR_VELOCITY = 0.5    ; was 1.0
MAX_LINEAR_ACCELERATION = 2.0    ; was 10.0
DEFAULT_LINEAR_ACCELERATION = 2.0 ; was 10.0

[AXIS_Z]
MAX_ACCELERATION = 2             ; was 5
```

**File:** `industry-cam.ini`

---

## Pending / Next Session

- [ ] Verify Z joint error is resolved at 0.5 in/s with 2 in/s² acceleration
- [ ] Run actual WCS commissioning procedure (T99 → Z datum, then per-tool offsets)
- [ ] Add FF2 to Z PID to improve acceleration tracking, then raise velocity ceiling
- [ ] Tune rapid speed upward in 0.25 in/s steps toward AXIS_Z MAX_VELOCITY = 0.75 in/s
- [ ] Wire and activate home switches when ready
- [ ] Wire jog buttons (TB3 P6–P9) when ready

---

## Files Changed This Session

| File | Change |
|------|--------|
| `gui/components/tool_geometry_row.py` | Editable tool number (QSpinBox); _set_orientation_options helper; Custom insert Q1-Q9 |
| `gui/tools_tab.py` | G10 L1→L20; no auto-renumber on delete; first-unused add logic; dialog text |
| `hal/live_backend.py` | DRO G53→G54; _ensure_mode safety guard; return to MANUAL after MDI/tool-change/touch-off |
| `pipeline/tool_card_data.py` | "Custom" added to all TYPE_INSERTS entries |
| `industry-cam.hal` | Cycle start/stop buttons activated (.in_not → .in, uncommented) |
| `industry-cam.ini` | Rapid velocity 2.0→0.5; acceleration 10.0→2.0; AXIS_Z accel 5→2 |
| `tool.tbl` | T99 QCTP master reference tool added |
