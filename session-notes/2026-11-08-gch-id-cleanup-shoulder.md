# GCH ID cleanup: preserve terminal shoulder

Owner approved the open-contour solution for the immediate GCH job, with explicit
follow-up on more complete pocket/removal-region modeling. Classification:
motion-affecting; software verification only. Base: fddfe74.

## Reproduction and cause

Stock OD4.000, pilot2.995, physical backZ-1.000, operation endZ-.568,
X Start3.117, Z clearance.050, finish allowance.002 diameter. Profile:
(3.117,0)->(3.117,-.568)->(2.995,-.568).

The duplicate ID cleanup face builder closed the last point toward stock OD
along Z-.568, retracing the real shoulder. OCCT offset raised ValueError
"Null TopoDS_Shape object"; an exception handler returned[] and the pipeline
reported success without cleanup. A valid-face-only probe still lost the
terminal shoulder through bottom face clipping/filtering. Neither is a stock
setting error, and changing final dimensions is not a valid workaround.

## Approved correction

ID cleanup now uses the same geometry-layer open-profile offset as intermediate
finish contours. The query is renamed profile_offset_edges and explicitly
supports zero allowance. It offsets toward the stock side and clips the WIRE
against the stock/depth window, retaining real edges on the boundary. It does
not reconstruct or filter a closed face's artificial edges. The obsolete ID
face/offset/clip implementation is removed. OD geometry method is unchanged
(AST comparison verified); finish uses the renamed query without depth clipping.

Cleanup's lower depth bound remains operation end + allowance/2, so wall-only
boring retains its previous bottom allowance. A genuine terminal shoulder at
that plane is retained by wire clipping, not discarded as a clipping boundary.
Kernel errors, empty/disconnected results, or unsupported noncircular curve
types raise instead of silently omitting a requested cleanup. No validator
tolerance is relaxed and no hand-calculated offset geometry is added.

For the example, cleanup feeds along X3.115 to Z-.567, then inward to X2.995
at Z-.567, and retracts toward the pilot hole. Final finish remains X3.117
to Z-.568, then X2.995 at Z-.568. Cutting/spring count and DOC behavior remain
as approved in ADR-003. No HAL, INI, tool offsets or physical stock values change.

## Explicit follow-up / scope limit

The owner's concern is preserved in the active handoff
docs/handoffs/2026-11-08-id-pocket-removal-model.md, including their verbatim
request. Open-contour generation is accepted for the immediate case; it does
not establish a complete model of complex interior pockets, tool access, or
sequential remaining stock. That investigation is proposed, not completed.
R-001 remains open. Do not infer complex-pocket readiness from the GCH fix.

## Verification and commissioning

Regression cases cover the exact GCH shoulder with both roughing strategies,
one cut and three cuts+spring, parsed emitted shoulder/retract, unchanged final
finish dimensions, wall-only bottom allowance, zero allowance, steps, arcs,
authored face segments, and explicit failure instead of missing cleanup.

Claude should review the exact commit on the latest bench branch and regenerate
the GCH program. Preserve machine-local table/offsets. Confirm nominal cleanup
X3.115/Z-.567 then X2.995/Z-.567, followed by appropriate retract, and final
finish X3.117/Z-.568 then X2.995/Z-.568. Check actual tool/bar geometry, pilot
depth, corner capability, compensation, active G7 and all clearances with the
owner before single-block powered testing. Use agreed conservative speeds and
feeds with physical E-stop available; abort unexpected motion, clearance,
following error or dimensional result. Record exact commit/program and measured
outcome before calling it machine-verified. Roll back to the prior software and
regenerate its program without overwriting machine-local offsets.

Final software results: 397 passed, the same six existing quadrant-arc failures,
2 skipped, 2 xfailed, 2 xpassed. All 14 new cleanup cases pass. Architecture
analysis reports 58 errors and 172 warnings (down from 69/178 after removing
obsolete ID geometry); it remains a failing check on existing source findings.
git diff --check passes. No machine verification or deployment is claimed.
