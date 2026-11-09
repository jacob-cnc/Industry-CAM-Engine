# 2026-11-09 — OD profile ending mid-bar (turned stub with step face)

Owner chose case B (step face drawn to the bar OD) as the representation.

## Problem
Bar 1.0 dia, Stock Back Face -1.0; profile 0.5 dia to Z-0.3, 0.8 dia to Z-0.6.
- A (profile ends at (0.8,-0.6)): BLOCKED — cleanup wall ran to Z-0.600 into the
  finish-allowance band in front of the step face.
- B (+ step face (0.8,-0.6)->(1.0,-0.6)): BLOCKED — cleanup endpoint (0.79,-0.600)
  inside the finished part; corner arc and step move crossed part/allowance.
- C (Stock Back Face = profile end) worked, but models no bar beyond the profile.
Operation Z End is derived from the contour (1477c92); Stock Back Face is still
user-entered (physical bar extent).

## Cause and fix
OD cleanup used the legacy face-offset route (_compute_offset_profile); ID was
moved to the shared open-contour kernel offset in 0049570. OD now uses the same
zone_query.profile_offset_edges with the operation-depth + allowance clip.
Case B cleanup: (0.51,0)->(0.51,-0.295)->(0.81,-0.295)->(0.81,-0.595)->(1.0,-0.595).
Finished-part model includes the bar beyond the step (protected by validation).
Case A also plans now (cleanup stops at -0.595; the writer adds the comp
lead-out so the finish nose stops at -0.6). Kernel offset failures now raise a
clear message instead of "Null TopoDS_Shape".

## Test outcomes vs main
- Fixed: TestAxisAlignedConvexQ pipeline success / arc I-K / Q-string (the old
  OD cleanup gouged the part).
- Still failing (pre-existing root cause, Codex's quadrant-arc item): axis-aligned
  Q arcs are flattened in the FINISH pass; with OD cleanup now consistent with
  finish, TestAxisAlignedConcaveQ::test_gcode_contains_g2_or_g3 joins the failing
  "arc expected" tests (the old cleanup alone emitted an arc there).
- Off-axis spline Q (xfail) went XPASS -> XFAIL: the kernel offset rejects the
  spline contour; now a clear RuntimeError.
- 4 new integration tests (test_od_step_to_stock.py). Full suite: 498 passed,
  4 failed (all "arc expected" Q tests), 5 xfailed.
Simulator verification of the case A/B G-code pending (LinuxCNC was running).

## Simulator (headless 2.9.6, T2 D0.032 Q2) — both programs ran, no errors
Case B: finish walls X0.5000 / X0.8000, shoulder Z-0.3000, step face Z-0.6000
(running out to the bar OD); cleanup X0.5100 / X0.8100, Z-0.2950 / -0.5950;
roughing passes at the step stop at about Z-0.594 (allowance kept).
Case A: same walls; finish wall ends in the comp lead-out (nose stop verified
earlier at exactly Z-0.6000 vs -0.6156 without it).

## Follow-up: contour approach clearance, OD centre entry, tool-type check
Owner review of a generated OD program (face from centre, step to bar OD):
(1) boring bar T1 selected for an OD block — now a generation error; (2) finish
approach rapided at Z0.0010 across a face standing at Z0.0025 and cleanup rapided
along the face surface — contours now rise to clearance (Stock Z start), traverse,
feed down in air; (3) comp entry at X0 left a centre nib up to TNR — OD face
contours now enter one nose radius before the face start.
Sim (T4 D0.032 Q2): face Z0.0000 with control point X-0.0320 (nose centre on the
centreline); walls 0.5000/0.8000; step Z-0.6000; no errors. GCH bore unchanged
(3.1150/3.1160/3.1170, Z-0.5680). Roughing rapids at Z0+fin are over already-cut
X only (reviewed, unchanged).
