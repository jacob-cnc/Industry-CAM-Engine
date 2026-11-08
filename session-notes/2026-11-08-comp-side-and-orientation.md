# 2026-11-08 — Cutter comp side (G41/G42) and boring-bar orientation (Q)

Owner expanded Claude's scope to CAM for this (Codex inactive).

## Bench evidence
GCH air run, live read-only sample: executing `N200 G01 X3.0700 Z-0.5665`, control
point at X3.1339 dia (+0.0639 = 2 x TNR on diameter). Active G42, T1 D0.032 Q8.

## Simulator proof (headless LinuxCNC 2.9.6 sim lathe, scratchpad)
Straight Z pass, 0.032 nose diameter, sampled mid-pass:

| Case | Programmed | Control point | Error |
|---|---|---|---|
| ID Q3 G41 | X3.070 | X3.0700 | 0.0000 |
| ID Q3 G42 | X3.070 | X3.1340 | +0.0640 (lathe: 3.1339) |
| ID Q8 G41 / G42 | X3.070 | 3.0700 / 3.1340 | 0 / +0.064 |
| OD Q2 G42 | X1.000 | X1.0000 | 0.0000 |
| OD Q2 G41 | X1.000 | X0.9360 | -0.0640 |

Rule (front-tool lathe, RH tool toward chuck): OD G42, ID G41; LH reverses.

## Changes
- outputs/gcode_writer.py `_get_comp_code(direction, is_id)` at all four call sites
  (was hand-only: RH -> G42 always). Regenerated GCH now emits N70 G41.
- Tool orientation per LinuxCNC manual Fig 2.16 (front-tool lathe, X+ down): corner
  1 -X+Z, 2 -X-Z (RH OD), 3 +X-Z (conventional boring bar), 4 +X+Z, 5 +Z, 6 -X,
  7 -Z, 8 +X. Tools-tab graphic had Q1<->Q2, Q3<->Q4 swapped and Q5-8 as copies of
  Q1-4; now matches the manual (Q3 shows the picture formerly labelled Q8).
- Boring Bar options [8, 6, 5, 7] -> [3, 4, 8] (Q3 default). models/tool.py enum
  docstring warns the member names are legacy. CAM toolpaths do not use Q.
- Q does not change X on a straight Z pass (sim) but sets the control point at
  corners/shoulders — T1 must be set to Q3 in the Tools tab (machine-local tool.tbl
  still has Q8; not edited by Claude).

## Not changed (owner to decide)
Other tool types' Q lists (e.g. Threading External [2,1], Threading Internal [6,5],
Grooving [2,6,1,5]) predate this mapping and should be reviewed against Fig 2.16.

## Verification
Unit tests (8 new) + full suite 461 passed / same 6 quadrant-arc failures.
Machine verification pending: re-touch with Q3, regenerate, air run, read X.
