# Explicit G7 for generated diameter programs

Owner authorized a targeted generator fix after confirming that inputs,
preview/simulation geometry, and diameter X output must remain unchanged.
Classification: motion-affecting; software verification only, not deployed.

## Change

The main writer now emits `G20 G7 G18 G40 G49 G80` in inch mode, or the G21
equivalent in metric mode, before the first park move. G7 explicitly selects
LinuxCNC diameter interpretation rather than inheriting G8 from the controller.
Threading, grooving/parting, and tool-change block entry points also emit G7
before their motion, so block-only generation has the same diameter contract.

No input, graph/simulation scaling, generated coordinate/feed values, tool
offsets, HAL, MPG calibration, or INI startup settings are changed. This follows
the existing `.kiro/steering/linuxcnc-gcode-reference.md` requirement to emit G7.

## Software verification

Seven new regression cases check G7 before any coordinate-bearing motion,
including OD/ID inch/metric main programs and all three block entry points.
All 32 focused writer and boring tests pass. Full suite: 318 passed, the same
six existing quadrant-arc failures, 2 skipped, 2 xfailed, and 2 xpassed. A comparison against the previous writer
confirms every emitted X/Z/I/K/R/F motion word is unchanged for straight and arc
fixtures in both units. The modal declaration is the targeted change.

## Claude handoff and commissioning

Regenerate old programs; already-saved G-code does not acquire this fix. Review
the first executable line and ensure G7 precedes every initial move. This commit
does not establish that live touch-off, DRO conversions, tool offsets, or arc
compensation are correct. Claude owns the live runtime audit. Do not automatically
re-touch or alter offsets merely from the previously observed G8 mode: reconcile
them against actual known diameters and measured machine position first.

Before powered verification, Claude and the owner must agree exact commit,
program, clearances, conservative limits, physical E-stop access, and single-block
test. Confirm a known diameter corresponds to the intended radial position,
then review the actual boring approach/cut/retract. Abort on unexpected movement,
clearance, or following error. Preserve tool.tbl and machine-local offsets; retain
the prior machine-tested commit for rollback. No machine test is claimed here.

This change is separate from the previous ID finish-contour and derived-depth
commits; it can be reviewed/cherry-picked by its own commit without deploying
those earlier software-only changes.
