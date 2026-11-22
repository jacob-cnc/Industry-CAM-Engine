# 2026-11-22 — Add "Extra Slow" MPG velocity jog preset

## Goal
Owner request: the velocity MPG jog presets should go from three names
(Slow, Medium, Fast) to four, slowest→fastest: **Extra Slow, Slow, Medium, Fast**.

Value mapping (preserve existing feel, add one in-between step):
- **Extra Slow** = old **Slow** scale (unchanged value)
- **Slow** = old **Medium** scale (unchanged value)
- **Medium** = NEW, geometric midpoint of old Medium and old Fast scales
- **Fast** = old **Fast** scale (unchanged value)

The two position presets (`.0002`, `.001`) and the default selection
(`DEFAULT_JOG_MODE_INDEX = 1`, i.e. `.001` position mode) are untouched.

## Why this is a clean, low-risk change in this architecture
The MPG jog mode is one list whose **index maps directly to the mux8 select
encoding** (`sel0/1/2` bits). `hal/constants.py:JOG_MODES` holds only the labels;
the actual per-axis velocity *values* live in `industry-cam.hal` as
`mux8.jogscale-x/z.inN`, keyed by that same index. `or2.jog-vel-mode` turns on
velocity mode when `sel1 OR sel2` is HIGH.

Old indices: 0=.0002, 1=.001, 2=Slow, 3=Medium, 4=Fast, with in5–in7 already set
to the Fast value as a "fallback (unused but safe)".

New indices: 0=.0002, 1=.001, 2=Extra Slow, 3=Slow, 4=Medium(new), 5=Fast.
- Index 5 = `0b101` → sel0=1, sel1=0, sel2=1 → or2 = 1 → velocity mode ON. Correct.
- mux8 `in5` already held the Fast value (the old fallback), so index 5 = Fast
  needs **no numeric change** — only the comment now names it Fast explicitly.
- The only numeric edits are `in4` (was Fast, now the new Medium midpoint).

### New Medium values (geometric midpoint = sqrt(old_Medium × old_Fast))
- X: sqrt(0.0001875 × 0.000351563) = **0.000256745** (`mux8.jogscale-x.in4`)
- Z: sqrt(0.0001875 × 0.000263672) = **0.000222348** (`mux8.jogscale-z.in4`)

## Files changed
- `hal/constants.py` — `JOG_MODES` now 6 entries (relabeled + new Medium);
  added the index-5 select-encoding comment.
- `industry-cam.hal` — mux8 comment block (6 modes); `jogscale-x.in4` and
  `jogscale-z.in4` set to the new Medium midpoints; in5 comment now names Fast.
- `hal/live_backend.py` — `set_mpg_scale_index` docstring index map (0–5).
- `gui/help_tab.py` — Manual-tab "MPG Modes" help table lists the four velocity
  presets with Medium at ~0.45 in/s.

`postgui.hal` is now an unloaded stub (no mux8 block) — nothing to change there.
`industry-cam-commissioning.hal` uses a separate **mux4, position-only** jog
scheme with no Slow/Medium/Fast names — correctly untouched.

## NOT executed — needs a run on the lathe PC
This Windows authoring box has no Python / no LinuxCNC, so nothing here was run:
no pytest, no `halcmd`, no GUI launch. Verify on the LinuxCNC PC (LinuxCNC down
for the pytest gate):
1. GUI Manual tab: the MPG mode combo shows, in order,
   `.0002 / .001 / Extra Slow / Slow / Medium / Fast`; default is `.001`.
2. Selecting each velocity preset drives the expected mux8 scale
   (`halcmd show pin mux8.jogscale-x.out` / `-z.out`): Extra Slow 0.00003125,
   Slow 0.0001875, Medium 0.000256745 (X) / 0.000222348 (Z), Fast 0.000351563 (X)
   / 0.000263672 (Z); `or2.jog-vel-mode.out` HIGH for all four.
3. A conservative, low-travel handwheel check per velocity preset that Medium
   sits sensibly between Slow and Fast before any production jogging.

## Pre-existing observation (NOT fixed here — out of scope)
`gui/manual/manual_tab.py` reads `JOG_INCREMENTS[self._jog_increment_idx]` in the
compound-slide pulse path, but `JOG_INCREMENTS` has only 4 entries while the
combo index can reach the velocity modes. This already overflowed for the Fast
index before this change (Fast was index 4); the rename shifts which velocity
indices overflow (now 4 and 5). This is a latent compound-slide + velocity-mode
interaction issue, independent of the preset rename — flag for a separate,
runtime-verified fix.
