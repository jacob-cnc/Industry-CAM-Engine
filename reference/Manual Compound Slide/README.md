# Manual Compound Slide — Feature Documentation

## Purpose and Concept

The compound slide feature emulates a manual lathe's compound rest using software. On a manual lathe, the compound slide is a small carriage mounted on the cross-slide that can be set to an angle — the operator turns its handwheel to move the tool along that angle (commonly used for threading infeed at 29.5°, or taper turning).

This GUI feature lets the operator use a **single physical MPG handwheel** to drive **coordinated X and Z axis motion** along a user-defined angle (Linear mode) or along a circular arc (Arc mode). The machine has two MPG handwheels (one for X, one for Z), and the operator selects which one to use as the input source.

---

## Widget Location and Visual Layout

The `CompoundSlideWidget` is a `QGroupBox` titled **"Compound Jog"** placed in the **right sidebar** of the main GUI window. It sits below the DRO/position grid and above the E-Stop button. It's wrapped in a `QScrollArea` (with hidden scrollbars and touch-scroll enabled) to prevent it from squishing other sidebar elements.

The widget layout is a vertical stack:

1. **Activation toggle button** — A checkable `QPushButton` showing "OFF" (default) or "ACTIVE" (green background when engaged). Fixed height 22px.

2. **Mode selector row** — A `QLabel` "Mode:" + `QComboBox` with options ["Linear", "Arc"]. Default is Linear.

3. **Linear mode parameters** (visible when mode = Linear):
   - `QLabel` "Angle:" + `QLineEdit` (right-aligned, monospace font, default "45.0") + `QLabel` "°"
   - Accepts values 0.0 to 90.0 degrees. Invalid input flashes the border red for 500ms and reverts.

4. **Arc mode parameters** (visible when mode = Arc, hidden by default):
   - Left side: A 60×60px `QuadrantGraphic` widget showing a circle divided into 4 arcs with the selected quadrant highlighted in accent color and dotted crosshair lines.
   - Right side (stacked vertically):
     - Radius input: `QLabel` "R:" + `QLineEdit` (default "0.250") + `QLabel` `"` (inch symbol). Must be > 0.
     - Quadrant selector: `QComboBox` ["NE", "NW", "SW", "SE"], default "SE".
     - Start type selector: `QComboBox` ["Arc Top", "Arc Bottom"], default "Arc Top".

5. **MPG selector row** — `QLabel` "MPG:" + `QComboBox` ["X MPG", "Z MPG"]. Default is X MPG. Selects which physical handwheel drives the compound motion.

6. **Cumulative distance display** — `QLabel` "Dist:" + `QLabel` showing "0.0000\"" in monospace bold with DRO-style background (dark bg, light text, border, rounded corners). Shows total distance traveled along the compound path since activation.

7. **Stretch** at bottom to keep everything compact at the top.

---

## User Interaction Flow

### Activation

1. User sets desired mode (Linear or Arc) and parameters (angle, or radius/quadrant/start-type).
2. User clicks the "OFF" button to activate.
3. The widget checks **interlocks** before allowing activation:
   - E-Stop must NOT be active
   - All axes must be homed
   - Machine must be in MANUAL mode
   - No program running (interpreter idle)
   - Machine must be enabled (power on)
4. If interlocks pass: button turns green "ACTIVE", mode/quadrant/start-type selectors are **locked** (disabled), cumulative distance resets to 0, and the `compound_activated(True)` signal fires.
5. If interlocks fail: button stays unchecked, nothing happens (no error message from the widget itself, but the status bar shows the reason via the main GUI).

### While Active

- The operator turns the selected MPG handwheel. Each encoder pulse is decomposed into X and Z components based on the angle (Linear) or arc tangent (Arc), and the machine moves both axes simultaneously.
- The "Dist:" display updates in real-time showing cumulative distance traveled.
- The angle input remains editable in Linear mode. The radius input remains editable in Arc mode.
- Mode selector, quadrant, and start-type are **locked** while active.
- If any interlock is violated (E-Stop pressed, mode changed to AUTO, program started, machine disabled), the widget is **force-deactivated** and a warning appears in the status bar.
- **Cycle Start is blocked** while compound mode is active — the main GUI refuses to run a program and shows "Cannot start program while compound slide is active".

### Deactivation

- User clicks the "ACTIVE" button again, or an interlock triggers force-deactivation.
- Button reverts to "OFF" (default style), all selectors unlock, distance resets to "0.0000\"", accumulators reset, `compound_activated(False)` signal fires.

---

## Computation Architecture (Two-Layer Design)

The feature uses a **thin UI wrapper + pure logic** pattern:

### Layer 1: `CompoundSlideWidget` (compound_slide_widget.py)

- PyQt5 `QGroupBox` subclass — handles all UI, signals, and state management.
- Delegates math to the logic classes.
- Manages fractional jog count accumulators (`_x_accum`, `_z_accum`) to avoid losing sub-count motion over time.

### Layer 2a: `CompoundSlideLogic` (compound_slide_logic.py) — Linear Mode

Pure computation class (no GUI, no HAL, no side effects):

- **`validate_angle(value)`** — Static method. Accepts string or numeric, returns `(is_valid, parsed_float)`. Valid range: 0.0–90.0.
- **`decompose_pulse(count_delta, jog_scale, angle_deg)`** — Trigonometric decomposition:
  - `x_distance = count_delta × jog_scale × sin(angle_rad)`
  - `z_distance = count_delta × jog_scale × cos(angle_rad)`
  - (Angle is measured from the Z axis, so 0° = pure Z motion, 90° = pure X motion)
- **`check_soft_limits(current_x, current_z, x_delta, z_delta)`** — If either axis would exceed soft limits, BOTH are suppressed (no partial motion). Returns `(x_delta, z_delta, suppressed)`.
- **`accumulate_distance(x_delta, z_delta)`** — Adds `sqrt(x² + z²)` to cumulative distance.
- **`reset()`** — Zeros cumulative distance.

### Layer 2b: `ArcJogLogic` (arc_jog_logic.py) — Arc Mode

Pure computation class for circular arc traversal:

- **`validate_radius(value)`** — Must be > 0.
- **`compute_arc_center(current_x, current_z, radius, quadrant, start_type)`** — Computes the arc center point based on tool position and parameters. "Pole" (Arc Top) means tool starts at the tangent-horizontal point; "Midpoint" (Arc Bottom) means tool starts at the tangent-vertical point.
- **`get_quadrant_angle_range(quadrant)`** — Returns angular boundaries for the selected 90° arc segment.
- **`activate(current_x, current_z, radius, quadrant, start_type)`** — Sets up arc state: computes center, initial angle, and boundaries.
- **`compute_tangent(angle)`** — Returns unit tangent vector at the current angular position (perpendicular to radius, in direction of increasing angle).
- **`decompose_arc_pulse(count_delta, jog_scale)`** — Projects MPG pulse along the tangent direction.
- **`reproject_onto_arc(position_x, position_z)`** — After tangent motion, normalizes position back onto the ideal circle to prevent drift.
- **`clamp_angle(angle)`** — Prevents motion past the 90° quadrant boundaries.
- **`process_pulse(count_delta, jog_scale, current_x, current_z)`** — Full pipeline: tangent decomposition → soft limit check → re-projection → angle update → angular clamping. Returns `(x_delta, z_delta, suppressed, clamped)`.
- **`accumulate_distance(x_delta, z_delta)`** — Same as linear.

### Supporting: `QuadrantGraphic` (quadrant_graphic.py)

A 60×60px `QWidget` that paints a circle divided into 4 arcs using `QPainter.drawArc()`. The selected quadrant is drawn with a thicker accent-colored pen; others are dim. Dotted crosshair lines through center provide visual reference.

---

## Data Flow During Periodic Update (Every ~100ms)

The main GUI's `periodic_update()` method (called by a QTimer) does the following when compound mode is active:

```
1. Poll LinuxCNC status (position, mode, estop, etc.)
2. Update interlock state on the widget:
   compound_widget.set_interlock_state(estop, homed, manual_mode, program_idle, machine_enabled)
3. If active and interlocks violated → force_deactivate(reason)
4. If active:
   a. Read current position: pos[0] (X radius), pos[2] (Z)
   b. Read HAL pins: mpg-x-in, mpg-z-in, jog-scale
   c. Call compound_widget.update_compound(current_x, current_z, mpg_x, mpg_z, jog_scale)
   d. Write returned (x_out, z_out) to HAL pins: x-jog-counts, z-jog-counts
5. Always: sync HAL pins compound-enable and compound-angle from widget state
```

Inside `update_compound()`:

```
1. Select encoder counts based on MPG selection (X or Z handwheel)
2. Compute count_delta = selected_counts - last_counts
3. If delta == 0: return (0, 0)
4. If arc mode: call arc_logic.process_pulse() pipeline
   If linear mode: call logic.decompose_pulse() + check_soft_limits()
5. If suppressed: emit limit_warning signal, return (0, 0)
6. Accumulate distance, update display label
7. Convert distance deltas back to integer jog counts using fractional accumulators:
   _x_accum += x_delta / jog_scale
   _z_accum += z_delta / jog_scale
   x_out = int(_x_accum)  # truncate to integer
   z_out = int(_z_accum)
   _x_accum -= x_out  # keep fractional remainder
   _z_accum -= z_out
8. Return (x_out, z_out)
```

---

## HAL Wiring (Machine Integration)

The GUI creates a userspace HAL component named `"compound-slide"` with these pins:

| Pin | Type | Direction | Purpose |
|-----|------|-----------|---------|
| `compound-enable` | bit | IN | Activation state from GUI |
| `compound-angle` | float | IN | Angle in degrees from GUI |
| `mpg-x-in` | s32 | IN | Raw X MPG encoder count |
| `mpg-z-in` | s32 | IN | Raw Z MPG encoder count |
| `jog-scale` | float | IN | Current jog increment (from mux4) |
| `x-jog-counts` | s32 | OUT | Decomposed X jog counts |
| `z-jog-counts` | s32 | OUT | Decomposed Z jog counts |

**postgui.hal wiring:**

```hal
# Feed MPG encoder counts to compound-slide GUI component
net mpg-x-counts => compound-slide.mpg-x-in
net mpg-z-counts => compound-slide.mpg-z-in

# Feed jog scale to compound-slide
net mpg-x-scale => compound-slide.jog-scale

# Route compound-slide outputs to jog-counts
net x-jog-final  compound-slide.x-jog-counts => joint.0.jog-counts axis.x.jog-counts
net z-jog-final  compound-slide.z-jog-counts => joint.1.jog-counts axis.z.jog-counts
```

The key insight: the MPG encoder raw counts are fed INTO the GUI component, and the GUI outputs the final jog counts to the motion controller joints/axes. When compound mode is disabled, the GUI outputs zero counts (the MPG counts pass through a different path in normal jog mode — this routing is handled by the HAL net topology). When enabled, the GUI decomposes the single-handwheel input into coordinated two-axis output.

---

## Safety Interlocks Summary

| Condition | Required State | Violation Action |
|-----------|---------------|-----------------|
| E-Stop | NOT active | Force deactivate |
| Homed | All axes homed | Block activation |
| Mode | MANUAL | Force deactivate |
| Interpreter | IDLE | Force deactivate |
| Machine | Enabled | Force deactivate |
| Soft limits | Within bounds | Suppress pulse (both axes) |
| Program run | N/A | Blocked while active |

---

## Offline/Development Mode

When `HAS_LINUXCNC = False` (Windows development), the compound slide still works in the GUI:

- No HAL component is created (`compound_hal = None`)
- The periodic update uses simulated MPG counts from `_sim_mpg_counts()`
- Position values come from the DRO simulation
- All UI interactions, validation, and distance display work identically

---

## Styling

- **Button:** Default theme style when OFF; green background (`COLORS['accent_green']`) with white bold text and darker green border when ACTIVE.
- **Labels:** `ui_font(11)`, `text_secondary` color.
- **Inputs:** `mono_font(12)`, right-aligned.
- **Distance display:** `mono_font(12, Bold)`, DRO-style (dark background `COLORS['dro_bg']`, light text `COLORS['dro_text']`, 1px border, 4px border-radius).
- **Invalid input flash:** 2px solid accent (red/crimson) border for 500ms, then reverts.
- **Quadrant graphic:** accent color for selected arc, `text_dim` for others, dotted `border` color crosshairs.

---

## Signals Emitted

| Signal | Payload | Purpose |
|--------|---------|---------|
| `compound_activated` | `bool` | Notifies main GUI of activation/deactivation |
| `limit_warning` | `str` | Sends warning message for status bar display |

---

## Key Design Decisions

- **X is always radius internally** — user-facing fields show diameter, but all computation uses radius.
- **Both axes suppressed on any limit violation** — no partial motion allowed (prevents tool from drifting off-angle).
- **Fractional accumulator pattern** — since jog counts are integers but trig decomposition produces fractional values, accumulators carry the remainder between cycles to prevent cumulative position error.
- **Arc re-projection** — after tangent-based motion, position is normalized back onto the ideal circle to prevent drift from the arc path over many pulses.
- **Angular clamping** — arc motion is confined to exactly 90° of arc (one quadrant), preventing the tool from overshooting.
- **Mode/parameter locking while active** — prevents the operator from changing arc parameters mid-motion which would invalidate the computed arc center.

---

## File Inventory

| File | Description |
|------|-------------|
| `compound_slide_widget.py` | Main UI widget (PyQt5 QGroupBox) |
| `compound_slide_logic.py` | Pure computation for linear mode |
| `arc_jog_logic.py` | Pure computation for arc mode |
| `quadrant_graphic.py` | Visual quadrant selector widget |
| `postgui.hal` | HAL wiring connecting component to motion |
| `tests/test_compound_slide_widget.py` | Widget activation/interlock tests |
| `tests/test_compound_slide_logic.py` | Logic class verification tests |
| `tests/test_update_compound.py` | update_compound() method tests |
