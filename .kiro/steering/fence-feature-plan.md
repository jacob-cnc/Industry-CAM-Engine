---
inclusion: auto
---

# Fence Feature — Manual Tab Soft Limit for Jogging

## Overview

The fence is a one-directional soft limit for manual jogging. It lets the operator jog toward a target position and automatically prevents overshooting. Motion away from the fence is unrestricted. Think of it as a wall that blocks you from crossing a coordinate.

## Architecture (3 pieces)

### 1. Widget — `gui/manual/widgets_fence.py` → `GoToFenceWidget`

- A QGroupBox titled "Go To" placed as a collapsible section in the Manual tab.
- Two rows: X checkbox + input, Z checkbox + input.
- X input is in **diameter** (user-facing), stored internally as **radius** (matching LinuxCNC's internal coordinate convention).
- Z input is stored directly.
- Emits `fence_changed(axis: str, enabled: bool, value: float)` whenever a checkbox toggles or the value changes.
- Has `check_fence(current_x, current_z, target_x, target_z)` → returns `(clamped_x, clamped_z, was_clamped)`.

### 2. Manual Tab Wiring — `gui/manual/manual_tab.py`

- Instantiate `GoToFenceWidget` and add as a collapsible section (or build via `sections.py`).
- Connect `fence_changed` signal to update the position graph overlay.
- Call `check_fence()` before issuing jog commands in `_jog_start()` and `_update_compound()`.

### 3. Visual Overlay — `gui/components/position_graph.py`

- `set_fence(axis, enabled, value)` stores the fence state.
- When a fence is enabled, draw a dashed-dot line across the graph in the fence color.
- X fence draws a horizontal line; Z fence draws a vertical line.
- Label shows the coordinate value.
- Fence color: `#E056A0` (pink/magenta) — add to `COLORS` dict as `"fence"`.

## Clamping Logic (`check_fence`)

Directional clamping:

```python
if current_pos < fence:
    # approaching from below → block motion past fence (target > fence → clamp)
elif current_pos > fence:
    # approaching from above → block motion past fence (target < fence → clamp)
else:
    # sitting exactly on fence → block all motion toward fence
```

The fence only blocks you from **crossing** it. You can always jog **away** from it.

## Key Design Decisions

- X is always diameter in the UI, radius internally. Any code consuming `fence_x_value` gets radius.
- `check_fence` should be called before issuing any jog or MDI move — in `_jog_start()`, `_update_compound()`, and any future go-to MDI logic.
- Metric conversion is display-only — internal storage is always inches.
- The fence is per-axis and independently toggleable (X only, Z only, or both).

## Integration Points

When implementing, call `check_fence()` in these locations:
1. `ManualTab._jog_start()` — before `backend.jog_continuous()`
2. `ManualTab._update_compound()` — before issuing jog increments
3. Any future MDI-based "go to position" command

## Color

Add to `gui/colors.py` COLORS dict:
```python
"fence": "#E056A0",
```
