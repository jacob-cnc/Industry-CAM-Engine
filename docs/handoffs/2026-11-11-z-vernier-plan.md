# Z vernier: plan (written 2026-11-11, not started)

**X comes first.** None of this starts until X has been closed and cut parts at the
bench (X runbook: docs/handoffs/2026-11-10-x-vernier-commissioning.md). Z's
requirements are looser, but any gain there is real. The only Z work done so far is the
optional data grab (X runbook step 7) plus the two small script additions that support it.

## Z today (from industry-cam.ini / industry-cam.hal)

| | X (joint 0) | Z (joint 1) |
|---|---|---|
| scale | encoder.01, 5080/in → .000197 r = **.0004 dia** per count | encoder.00, 5080/in → **.000197** per count (length, 1:1) |
| motor | stepgen.01, 54186.667 steps/in → .0000185/step | stepgen.00, 27093.333 steps/in → **.0000369/step** |
| steps per scale count | 10.7 | **5.3** |
| pid | P 125, D .002, deadband .0005 (2.5 counts) | P 60, D .005, deadband **.0002 (1 count)** |
| travel | 6.0 | **10.0** |
| parking error today | ±.0009 dia measured on the bench and seen at the machine | **not measured.** Estimate ±.0002–.0003 length: a count of quantization plus a one-count deadband |

Z's deadband is already tight, so Z isn't as badly off as X was. What the vernier would
add is roughly a 3–5× gain: shoulder lengths and face positions parking within about
±.00005–.0001 of command, with Z wear changes of a tenth or two showing up exactly
in the part. The bench will give the real number before any machine time.

## What carries over unchanged

- The estimator: edges anchor the step count to the scale, and the screw model is slope +
  harmonic + backlash, with the ±½-count clamp and the fault latch. Z needs nothing new.
- Capture, fit and analysis scripts. `fit_calibration.py` already has `--units length`
  and `--steps-per-unit`; `capture.sh … z` records raw Z.
- The procedure: shadow → baseline → sweep/fit → indicator → close → cut, with the
  same rollback (comment out a `HALFILE` line).

## What is different about Z (and how each is handled)

1. **Coarser step interpolation.** At 5.3 steps per count, the step quantum is
   .000037. That is still 5× finer than a count, and the floor sits around ±.00004.
   The bench gets a Z plant to measure it.
2. **Longer travel (10").** A slope plus one harmonic may not describe the whole screw.
   The step-7 sweep only covers 1"; run a second region to check. If the fit
   residual grows with travel, add a **pitch-error table** (e.g. a node every 0.5",
   linear between, fitted from one full-travel slow sweep) as an optional extra
   screw term. X doesn't need it, so X keeps its model.
3. **Cutting thrust on the carriage.** During turning, feed force pushes the carriage
   against the nut in one direction, whichever way the last move went. The
   calibration is done in air, so its backlash model can pick the wrong side of the
   play right after a reversal under load. The error is bounded: at most H (small if
   the nut is tight), and never more than the ±½-count clamp, so it can't do worse than
   today. A cut test checks it: shoulders approached from both sides.
4. **Holding still under load.** While X faces, Z sits still and takes the thrust. With
   no Z motion there are no edges. If the carriage creeps without steps changing, the
   estimate sees it only when the scale count moves, and then it clamps or re-anchors.
   That is the same visibility as today; it doesn't get worse.
5. **Feeds.** Edges are used only below `SPAN_MAX` per servo period. At .0001 that
   is 3 in/min of Z. Typical Z finish feeds (around .003–.005 ipr at the usual rpm)
   can run above that, which is fine: the estimate coasts on steps plus the last
   anchor, and decelerating into each stop crosses slow edges. Set Z's
   `SPAN_MAX` from your real finish feeds.
6. **Thermal.** The Z screw is longer and grows more, but the scale is the reference.
   Screw growth only shifts the step-to-scale offset (b0), and the estimator tracks
   that continuously with `ALPHA`. Growth of the scale itself is the same as today.

## Implementation plan

**Z0: gate.** X closed, cut parts, stable for a few days of real work.

**Z1: component (desk).** Recommendation: generate a **twin component `zvernier.comp`
from `xvernier.comp`**, with a test asserting that the estimator core is byte-identical.
The X module that was commissioned then stays exactly the binary that passed. The
alternative, converting to one multi-instance component, is cleaner. But it
would mean reinstalling X and re-verifying it, for no gain at the machine. If a
pitch table is needed, it goes into the shared core behind a zero-length default, and
X re-runs its bench tests.

**Z2: bench (desk).**
- Add a Z plant to `tests/xvernier/bench.c`: 5.3 steps/count, P 60, deadband .0002,
  10" travel, optional pitch-error map, and an axial-load term (an offset step in the
  nut while "cutting").
- Scenarios:
  - shoulder approached from +Z,
  - shoulder approached from −Z,
  - hold under load while X faces,
  - Z wear steps of .0002.
- Tests mirror X. Once the real Z sweep exists, the plant is set from that data.
- Pass target: ±.0001 length or better, no faults in normal scenarios.

**Z3: scripts (desk).**
- `z-vernier-observe.hal` and `z-vernier-close.hal`: same shape as X, but on pid.z,
  joint.1, encoder.00 and stepgen.00, with a `[ZVERNIER]` INI section.
- `capture.sh … z` grows pos-est/residual columns once zvernier exists.
- `analyze_holds.py --units length`.
- `z_positioning_test.ngc` and `z_step_staircase.ngc`.
- Everything dry-runs in rs274.

**Z4: machine (owner present, about 1–1.5 h).**
1. Z shadow alongside closed X. This is zero risk and gives the first real Z baseline.
2. Sweep/fit in two regions.
3. Indicator on the carriage, MPG single clicks.
4. Close Z.
5. Air positioning and staircase.
6. Cut: shoulder lengths from both directions, and a Z wear change.

## Questions for the owner (no rush, answer whenever)

1. Z screw: ballscrew or acme? Nut adjustable or preloaded?
2. Which Z dimensions are tight on your parts (shoulder lengths, face-to-face, groove
   positions)? Roughly what tolerance?
3. Typical Z finish feed and rpm, which set `SPAN_MAX`.
4. Is the Z scale the same model as X's (5 µm)?
