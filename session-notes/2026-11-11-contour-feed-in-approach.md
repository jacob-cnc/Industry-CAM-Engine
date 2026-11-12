# Cleanup/finish entry: rapid, then feed the last .020 dia of X (2026-11-11)

Class: **motion-affecting** (generated G-code). Software-verified only; NOT machine-verified.

## Why

X bench tests 2026-11-11 (air, halsampler captures, see project notes / commit 3389dfb, 97149b5):

- X backlash .0156 dia (calibration sweep fit; .014 by reversal tests).
- Every move start winds the drive train ~.0005 dia before the carriage follows; inward it
  springs back, outward ~.0002–.0003 stays (permanent slip, grows with acceleration).
- Owner measured the X motor mount moving ~±.0008 when jogging.

Owner approved (2026-11-11): rapid to .020 short of the finish X, feed the last .020 before
engaging, approach from the same side every time; apply to the finish passes and the
cleanup pass.

## What changed

`CONTOUR_FEED_IN_DIA = 0.020` (diameter, `models/constants.py`).

1. `GCodeWriter._emit_contour_pass` (cleanup pass, finish pass 1): the "above entry point"
   rapid now stops at entry X + .020 (OD, outside) / − .020 (ID, inside) at the clearance Z,
   then `G01` to the entry X at the pass feed. Always from that feed start, so every entry is
   identical, even if the tool was already inside the band. Skipped only when the previous
   X motion was already the planned feed-in to this X.
2. `TransitionPlanner._retract_traverse_plunge` (planned links into finish pass 2+ and the
   spring pass; also the validated, not-emitted links into cleanup / finish 1): step 3 is now
   a rapid to target ± .020 then a FEED to the target at the next pass's feed.

Approach direction was already consistent per mode (OD from outside, ID from inside); this
makes the last .020 a feed. All feed-in moves are in air at the clearance / approach Z,
comp off. Offset-contour roughing's own passes are not touched.

Example (OD, test fixture bore part, 2 finish + spring):

    G00 X3.1600 Z0.0520   ; Contour approach: rise to clearance Z (comp off)
    G00 X3.1390 Z0.0520   ; Contour approach: above entry point, feed-in start (comp off)
    G01 X3.1190 Z0.0520   ; Contour approach: feed in to entry X (comp off)
    G42 ...
    ...
    G00 X4.0100 Z0.0500   ; Finish retract/approach
    G00 X3.1370 Z0.0500   ; Finish retract/approach
    G01 X3.1170 Z0.0500   ; Finish retract/approach      <- feed-in
    G00 X3.1170 Z0.0760   ; Contour approach: rise to clearance Z (Z only)

Cycle-time cost: .010 radius at the finish feed per entry, e.g. .002 ipr at 1000 rpm = 0.3 s,
at 80 rpm = 3.75 s.

## Software verification

- `tests/integration/test_contour_feed_in_approach.py` (9): every cleanup/finish/spring entry's
  last X motion is a G01 of exactly .020 from the approach side, preceded by the rapid that
  ends at the feed start (OD/ID × 1 pass / 2 passes + spring); planned links end with the
  feed-in; feed-in longer than the measured backlash; LinuxCNC rs274 runs the OD and ID
  programs to PROGRAM_END.
- Full suite on the lathe runtime and architecture check: see the commit message.

## Commissioning plan (owner at the machine)

1. Regenerate a known program (previous programs are unchanged until regenerated).
2. Air run first, spindle off, single block over the cleanup and finish entries: confirm the
   rapid stops ~.010 radius short of the finish X, then a slow feed to the finish X, then
   comp on and the Z move. OD: tool moves toward centre during the feed; ID: away.
3. Cut a test part with the usual wear workflow; compare finish diameter scatter with
   recent parts. Record the result here as machine evidence, separately from the tests.

Rollback: revert the commit (no INI/HAL change involved).
