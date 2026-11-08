# ADR-003: Finish cutting passes and an independent spring pass

Status: accepted for implementation by owner, 2026-11-08. Motion-affecting;
software verification and separate lathe commissioning required.

The architecture was reviewed before engine changes: models/params/results,
geometry zone construction and query, cleanup/finish planning, transition
planning, all three validation gates, pipeline assembly, writer, and GUI storage.
Existing code ignores finish DOC/count and the spring checkbox. Cleanup leaves
the configured finish allowance. The writer currently approaches only the first
finish pass, so simply multiplying existing contours would create return cuts.

The user sets a positive integer N cutting passes. Diameter DOC is finish
allowance / N and is read-only in the GUI, recalculated on load and in the
pipeline for API callers. No independent DOC controls the engine. For pass i
(1..N), the remaining normal allowance is allowance * (N-i)/N; the geometry
layer produces that contour with an OCCT open-wire offset on the stock side.
No arithmetic translation of X/Z, contour closure cuts, or planner-local offset
implementation is permitted. Multiple/disconnected/failed offsets raise.

The last cutting contour is the existing exact final profile. An optional spring
pass copies its cutting moves exactly, changing only identity/index metadata.
It is explicitly marked in TurningPass and excluded from the requested cutting
count and calculated DOC. With zero allowance, multiple cutting passes are
rejected; one final trace with an optional spring repeat remains allowed.

Each contour has an explicit retract/approach. The pipeline's existing transition
planner supplies finish-to-finish links, and the writer consumes those planned
links from PlanResult rather than concatenating cutting moves. Every pass and
link participates in validation; no validator tolerance is weakened. The existing
single-cut/no-spring case retains its final contour and approach behavior.

The current broader writer/pipeline duplication and validator phase-boundary
reset are known existing limitations, not justification to introduce another
offset algorithm or relax safety checks. Focused tests must compare planned and
emitted finish links and use the parser to verify final/spring paths. Unsupported
offset geometry is blocked instead of falling back to a different path.

No HAL, INI, tool offsets, or machine deployment belongs to this change. Existing
quadrant-arc failures remain distinct from readiness of the new finish cases.
