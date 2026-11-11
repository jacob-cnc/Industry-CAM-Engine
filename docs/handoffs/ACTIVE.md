# Active Handoffs

Agents must review the entries below before scoping related work. This file is
an index, not the full specification; follow the linked handoff and preserve
the distinction between the owner's verbatim request and later design advice.

## Proposed

- [Zone Shading on the Graph: Plan + Status](2026-11-11-zone-shading-plan.md)
  - Status: S0-S2 BUILT 2026-11-11 (sections from G-code via rs274, legend,
    pixel-probe tests). Found 3 real defects; 1 (roughing gouge beside falling
    flanks) and 2 (ID mouth chamfer left proud) FIXED same day (§7); 3 (face
    left at the face allowance) to discuss with the owner.
  - Original: Owner wants the discrete sections shaded
    (finished part, roughing, cleanup/finish, face stock, uncut) and the graph
    100% trustworthy as a validation tool.
  - Why earlier tries failed (rasterised zones, fillLevel fills, kernel-tolerance
    gaps, G-code-to-planner move matching, clutter) and the fix: sections from
    the G-code via rs274, same numbers as the lines, real polygon items,
    invariants checked on every Generate, toggles.
  - Open: owner picks sections / colours / preview behaviour (§5).

- [Arc Segments: Strategy + Phase 0/1 Status](2026-11-10-arc-segment-strategy.md)
  - Status: branch `claude/arc-phase0`, pushed, NOT merged (needs owner OK).
    Phase 0 done; Phase 1 part 1 done 2026-11-11: true circular Q / -Q (ellipses
    retired), same-X arcs auto-split into two quadrants, R arcs past their X
    extreme split instead of refused (geometry/arc_entry.py). Section 7 of the doc.
  - Known limit until Phase 2: a part ending behind a bead is blocked (closing
    rapid would cross it), never cut.
  - Phase 1 part 2 done: arc picker (click the arc; sets the sign of R), "T" =
    tangent radius. Stored identity stays end point + signed R (§7).
  - Phase 1 part 3 done: tool reach, OD + ID (geometry/tool_reach.py). Per owner:
    what the insert can't reach is LEFT UNCUT (bridged at its limit angle), the
    rest generates; each uncut X/Z range is reported with why + suggested inserts.
    Next: Phase 2 (rapid routing around beads; two-tool blocks for necks).

- [Corner-Break Tool, OD Engine, GUI Tuning - lathe integration](2026-11-10-corner-break-tool-and-gui.md)
  - Status: INTEGRATED 2026-11-10, merged to main, owner-verified on the lathe
    (tag `lathe-2026-11-10-working`). Outcome and the fixes found during the
    air cut (arc G-code dialect, E-stop): `session-notes/2026-11-10-lathe-integration.md`.
  - Still open from this handoff: ID corner breaks unvalidated; offset_contour
    gouge on large concave fillets; V1 front-face chamfer; Kiro GUI tests on Linux.

- [X Axis: Hold a .0004" Diameter Band](2026-11-10-x-axis-tolerance.md)
  - Status: Plan written 2026-11-10 after an evening of chasing X wear by hand
    (11 corrections, .001" window). Owner-present session required.
  - Finding: X scale = 1 count per .0004" dia (the whole band); deadband
    .0005 r = +/-.0010 dia parking window. Tuning alone cannot reach the band.
  - First action: deadband step-down (2026-11-08 handoff below), then a
    read-only error log; decide on a 1 um X scale (recommended).

- [X Position-Loop Deadband Tuning](2026-11-08-x-deadband-tuning.md)
  - Status: Planned; owner-present bench session required. Nothing changed yet.
  - X `DEADBAND = .0005` r lets X park up to .0007 dia off command (observed).
  - First action: baseline standstill error, then step deadband .0004 → .00025
    live from the Tuning tab; stop at the first sign of hunting.

- [Define the ID Pocket/Removal Region Explicitly](2026-11-08-id-pocket-removal-model.md)
  - Status: Owner request captured; investigation not started.
  - Priority: Follow-up after the immediate GCH bore-and-shoulder cleanup fix.
  - Open-contour cleanup is accepted for that case; it does not settle complex
    interior pocket modeling or remaining-stock safety.
  - First action: define keep/removal/air regions and boundary provenance, then
    compare kernel-based pocket and open-contour approaches in an ADR.

- [Explicit X-Z Contours, Arc Choice, and DXF Interchange](2026-09-13-explicit-xz-contours-and-dxf.md)
  - Status: Owner request captured; design and implementation not started.
  - Applies to: conversational geometry entry, Program-tab visualization,
    operation selection, corner breaks, arc disambiguation, threading, cutoff,
    grooving, and DXF import/export.
  - First action: write an ADR for the canonical contour model, arc
    representation, and DXF boundary before modifying motion-affecting code.

- [Evaluate LibreCAD as Reference for 2D Geometry and DXF I/O](2026-10-20-librecad-reference-evaluation.md)
  - Status: Owner request captured; evaluation not started.
  - Applies to: 2D geometry representation, DXF import/export in the builder.
    Directly supports the 2026-09-13 explicit X-Z contour and DXF handoff.
  - First action: review LibreCAD's `libdxfrw` DXF boundary and arc/polyline
    entity model, then compare against the proposed canonical contour document.
    Reference only (GPLv2) - no code copy without a license decision recorded
    as an ADR.

Move an entry out of this index only after its request is implemented,
superseded by a newer owner decision, or explicitly declined. Link the outcome
from the dated handoff so the reasoning remains discoverable.
