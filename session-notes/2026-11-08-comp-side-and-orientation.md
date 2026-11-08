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

## Follow-up: all tool types reviewed (owner-approved)
TYPE_ORIENTATIONS now: Turning RH [2, 6], Turning LH [1, 6], Boring Bar [3, 4, 8],
Threading External [6], Threading Internal [8], Grooving/Parting [2, 1, 6],
Knurling [9], Custom all. (Before: RH [2,1,3,4], LH [4,3,1,2], ext thread [2,1],
int thread [6,5], grooving [2,6,1,5].)
Safeguard: a saved Q not in its type's list is now kept and shown as
"Qn (non-standard)" instead of silently falling back to the first option (which the
next autosave would have written). Lathe tool.tbl today: T1 boring Q8 (-> Q3),
T2 ext thread Q2 (-> Q6), T4 turning RH Q1 (-> Q2) — owner to change in the Tools tab.
scripts/preview_tool_orientations.py prints the options as ASCII art.

## Compensated contours only; G40 roughing; tool checks (owner decisions)

Trigger: LinuxCNC "Straight feed in concave corner cannot be reached by the tool
without gouging" on the GCH program. Source (interp_queue.cc): at an inside corner
comp shortens the incoming move; it errors when the move is shorter than the cut-back
(tool would reverse). G41 through the roughing zigzag treated each X step-out as an
inside corner; pass-2 step 0.0125 r < TNR 0.0157.

Writer changes:
- Roughing G40 (owner OK): exact on straight X/Z; angled surfaces leave
  R(|sin|+|cos|-1) <= 0.414 R extra (never less).
- Cleanup/finish: G40 -> rapid above contour start -> G41/G42 -> entry G01 down
  the contour's line in air (> 2R) -> contour -> [lead-out] -> G40 -> exit.
  ID face-lead moves (pilot -> wall along Z0+fin) dropped (air, wrong side).
- Lead-out: comp ends with the nose centre on the last endpoint (overhang R). If
  the overhang point is material (finished part, or stock beyond the profile's
  Z span), a compensated lead-out toward the air side makes LinuxCNC stop the
  nose at the endpoint. Into air (pilot hole, past bar end) no lead-out.
- Tool check after every T M6/G43: #5400/#5410/#5413 vs generated T/D/Q; on
  mismatch (DEBUG, values) + M0 pause (owner: pause with message).
- Program tab: tool missing from the table is a generation error (no default
  ToolDef / active-tool substitution). Run tab: compares the program's tool
  checks with LinuxCNC's loaded table at load (warning) and at Cycle Start /
  Run From Line (Run anyway? default No).

Simulator (headless 2.9.6, scratchpad simlathe/run3):
- old GCH program: reproduces the concave-corner error (line 64), no motion.
- new GCH (T1 D0.0314 Q3): runs to completion; walls 3.1150/3.1160/3.1170,
  final shoulder Z -0.5680.
- new GCH with table T1 D0.032 Q8: pauses at the tool check with message.
- OD sample: runs; face Z0.0000, walls 0.5000/0.8000, shoulder -0.3000.
- OD wall ending into material: no lead-out Z -0.6156, with lead-out Z -0.6000.

Known, not changed: an OD profile ending mid-stock (bar continuing past the
profile) is blocked earlier by the validator ("CLEANUP ... CROSSES the Finish
Allowance zone") — separate CAM limitation.
