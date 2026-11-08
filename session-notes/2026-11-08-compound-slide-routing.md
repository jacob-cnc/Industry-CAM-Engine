# 2026-11-08 — Compound-slide MPG routing (machine-control)

Branch `claude/compound-slide-routing`. Owner decision: no homing requirement.

## Findings on the previous design

1. `postgui.hal` is never loaded (no `POSTGUI_HALFILE`), and its `mux2` is
   float-only — `net` of s32 jog-counts into it fails. It never ran.
2. Motion applies `jog-counts` **deltas** each servo cycle
   (`reference/linuxcnc-2.9.6-source/src/emc/motion/control.c:1063-1066`).
   Switching a mux between raw MPG (e.g. 12000) and a compound total starting at
   0 is a -12000-count step = ~1.5" X jog. The old design had no protection.
3. The GUI converted with one scale for both axes; X (radius, 0.000125/count)
   and Z (0.00025/count) differ, so 45 deg ran at ~27 deg and 4-8x per-click travel.
4. Compound soft limits used `hal/constants.py` values that disagree with the
   INI (Z -3..3 in INI vs 0..23.5), and required homing.
5. Python loop ran at 10 Hz.

## Design implemented

- `industry-cam.hal`: `mux_generic config="ss2,ss2"` per joint; in0 = encoder
  count (default), in1 = `compound-x/z-jog` (writer attached by GUI);
  `compound-enable` selects. jog-enable = `halui.machine.is-on` AND NOT
  `compound-jog-inhibit`. Motion copies the new count into its old-count while
  jog-enable is FALSE (control.c 1066 precedes the enable check at 1088; same
  pattern for axis jogwheels), so a switch made while inhibited causes no motion.
  Routing functions run between `hm2 read` and `motion-command-handler`.
- `hal/live_backend.py`: verifies the routing signals exist (halcmd would
  otherwise silently create them), nets compound-slide pins with inhibit held,
  `set_compound_routing()` = inhibit -> zero outputs -> flip mux -> 20 ms -> release.
- `hal/compound_router.py` `CompoundJogEngine`: machine-frame, per-joint scales,
  fractional accumulators, virtual position tracks emitted counts, real joint limits.
- `gui/manual/manual_tab.py`: interlocks = not E-stop, machine on, MANUAL, interp
  idle; forces position MPG increment; 20 ms loop; velocity selection exits compound.
- One input count travels the Z jog-scale (0.001"/click at index 1) along the path.

## Software verification

- 20 new unit tests (`tests/unit/test_compound_routing.py`), 64 existing compound
  tests pass. Full suite: 316 passed, 6 failed (pre-existing quadrant-arc
  failures, same as Codex baseline at 1f490eb), 2 skipped, 2 xfailed, 2 xpassed.
- Mock end-to-end (offscreen ManualTab): 30 deg request -> 29.97 deg, 400 counts
  -> 0.0998" path; velocity mode forced to 0.001; interlocks refuse.

## Commissioning plan (NOT yet run)

Rollback: `git checkout lathe-tested-2026-11-08 -- industry-cam.hal` restores the
direct MPG nets; GUI then logs "Compound-slide routing unavailable" and normal
jogging is unaffected.

1. LinuxCNC closed: `scripts/check_compound_hal_routing.sh` -> ALL CHECKS PASSED.
2. Start LinuxCNC. Log shows compound nets established, no "unavailable" error.
   `halcmd show sig compound-enable` / `x-jog-final` / `mpg-jog-enable` wired as designed.
3. Machine ON, compound OFF: normal MPG jog both axes at .0002 — must feel identical.
4. Motors-on, tool clear, compound ACTIVATE/DEACTIVATE 5x without turning MPGs
   while watching DRO X/Z: **zero motion** at each switch (the jump test).
5. Turn MPGs before/between switches to build large raw counts, repeat step 4.
6. Linear 45 deg, .0002 increment, X MPG: small rotations; X and Z DRO change by
   equal radius amounts (X DRO shows the G8/G7 issue — compare raw joint
   positions via `halcmd getp joint.0.pos-cmd` / `joint.1.pos-cmd`). Reverse returns.
7. 29.5 deg and -45 deg direction check; E-stop while active deactivates.
8. Arc mode, small radius, clear air.

## Machine evidence

(pending)
