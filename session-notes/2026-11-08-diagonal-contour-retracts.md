# Coordinated X/Z retracts after cleanup and finish

Owner requested diagonal cleanup/finish exits mirroring roughing retract style.
Base: 0049570. Classification: motion-affecting. Software-verified only; not
deployed or machine-verified.

## Behavior

Cleanup and each finishing/spring contour exit with one G0 to safe-side X and
that pass's own approach Z. ID uses pilot diameter minus existing 0.010 diameter
clearance (clamped at zero); OD uses stock OD plus 0.010. This changes both axes
when both differ. It is a return to pass clearance, not an arbitrary diagonal
directly to park. The subsequent material-aware park route is unchanged.

For the GCH shoulder with Z clearance+.050:

- Cleanup ends at X2.995 Z-.567, then G0 X2.985 Z+.050.
- Finish ends at X2.995 Z-.568, then G0 X2.985 Z+.050.
- Subsequent finish/spring entry occurs after the prior diagonal exit.

The transition planner generates the exits and links. TurningPass carries
retract_moves; pipeline includes the final contour exit in tool_moves so it is
validated too. Writer emits the planned cleanup/final exits and existing planned
finish-to-finish links, including before cleanup tool-change travel. A missing
terminal exit plan is an error; an explicitly planned empty exit is distinguishable
from missing metadata. No roughing retract or park-helper logic is modified.

## Validation correction

The validator formerly reset its previous position whenever pass type changed.
That could skip the cutting-endpoint-to-TRANSITION segment. It now preserves
position specifically for CLEANUP/FINISH -> TRANSITION, so the actual diagonal
is checked against the finished part. Other legacy phase resets and tolerances
are unchanged. The previously documented remaining-stock/pocket-model limitations
remain open; this does not establish general pocket access or bar clearance.

Not every contour admits this diagonal: an OD shoulder ending inward of its outer
wall can make an upward/outward diagonal cross the finished part. A regression
confirms such a program is blocked rather than emitted or silently reverted to
another route. The GCH ID case passes. Broader retract policy may need revisiting
alongside the queued pocket/removal-region model.

## Verification

Twelve new cases cover OD/ID, both strategies, single/multiple finish plus spring,
matching planned/emitted X/Z exit endpoints, final exit in the validated path,
cleanup exit before tool-change travel, missing terminal metadata, a crossing
diagonal across the phase boundary, and an unsafe real OD shoulder. Existing
cleanup/retract and writer fixtures were updated for the new explicit plan contract.

Full suite: 409 passed, the same six existing quadrant-arc failures, 2 skipped,
2 xfailed, 2 xpassed. Architecture remains at 58 errors / 172 warnings on existing
findings. git diff --check passes. No HAL/INI, tool offsets, cutter geometry,
finish dimensions, feeds or spindle behavior is changed.

## Claude / owner commissioning

Review the exact commit on the latest bench branch and regenerate the GCH program.
Preview both axes moving together at each cleanup/finish/spring exit. Verify
actual tool/bar clearance, pilot depth, active G7 and cutter compensation before
single-block powered testing with owner-agreed conservative limits and physical
E-stop available. Confirm the cut ends at its specified dimensions before the
diagonal begins; compare endpoint to the expected X2.985 Z+.050 clearance point.
Stop on unexpected direction, clearance, following error or dimensional result.
Record commit, program and observations separately from software results.
Rollback to the preceding software and regenerate its program; preserve table
and work offsets. No powered-machine test is claimed here.
