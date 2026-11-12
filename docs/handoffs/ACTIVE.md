# Active Handoffs

Agents must review the entries below before scoping related work. This file is
an index, not the full specification; follow the linked handoff and preserve
the distinction between the owner's verbatim request and later design advice.

## Proposed

- [Hand-math inquiry: findings, walls, next steps](2026-11-12-hand-math-inquiry.md)
  - Status: branch `claude/hand-math-kernel` (from `claude/structure-cleanup`) pushed, NOT merged.
    Fixed: "wires not planar" for contours ending on the back face (F1); finish contour from the
    kernel's open profile wire, hand-math fallback with centre swapping removed (F2); zone boundary
    polylines up to .118 off their arcs (F5). Removed dead/duplicate math (F3, F6). Wall: OCCT
    sharp-join offsets of concave features (F4, owner decision). Corpus 18 SAME, 1 newly generating.
  - Next (owner): merge both branches; F4 policy; corner breaks (C1) on kernel fillet/chamfer vs the NX STEP fixtures.

- [Structure cleanup: work log + result](2026-11-12-structure-cleanup-log.md)
  - Status: branch `claude/structure-cleanup` pushed, NOT merged (owner review). Behaviour-
    neutral reorganisation verified step by step (suite + regenerated 21-program corpus through
    the GUI's own Generate, machinist compare: 16 SAME, 5 identical refusals). Dependency
    errors 62 → 4 (planners 0); geometry/kernel.py facade (owner rule (a)); architecture
    ratchet test. Open owner decisions listed at the end of the log.
  - Next: `claude/hand-math-kernel` (hand-math inquiry, from this branch).

- Architecture check debt from the 2026-11-11 work (merged to main as-is, owner OK)
  - Status: `python -m validation.architecture_check` failed on main before the
    merge (62 errors) and fails after it (88). The 26 new ones come from the
    2026-11-11 work. They are layering rules (Shapely only in validation/, OCP
    only in geometry/, outputs/ may import only models/, planners/ may not import
    validation/ or geometry/) plus the "atan2 + cos/sin = manual arc math"
    heuristic. They are not behaviour bugs: the full suite passes (1301) on the
    lathe runtime.
  - First action: move outputs/cut_regions.py under validation/ (it is a
    validation of the G-code). Give the staircase planner its nose-aware keep
    region from the pipeline instead of importing validation.polygon_builder.
    Move contour roughing's OCP translate into geometry/. Have tool_reach take
    the insert table as an argument. Decide whether the arc helpers' trig is
    legitimate (canonical arc maths, like geometry/arc_math) or should use the
    kernel.
  - New errors (file | rule):
    - geometry/arc_entry.py | Function 'arc_candidates' uses atan2 + cos/sin — likely manual arc center computation. Use Build123d kernel operations instead.
    - geometry/arc_entry.py | Function 'quadrant_points' uses atan2 + cos/sin — likely manual arc center computation. Use Build123d kernel operations instead.
    - geometry/arc_entry.py | Function 'radius_arc_x_extreme' uses atan2 + cos/sin — likely manual arc center computation. Use Build123d kernel operations instead.
    - geometry/tool_reach.py | Function '_densify' uses atan2 + cos/sin — likely manual arc center computation. Use Build123d kernel operations instead.
    - geometry/tool_reach.py | Function '_piece_geom' uses atan2 + cos/sin — likely manual arc center computation. Use Build123d kernel operations instead.
    - geometry/tool_reach.py | Function '_piece_to' uses atan2 + cos/sin — likely manual arc center computation. Use Build123d kernel operations instead.
    - geometry/tool_reach.py | Function '_shadow_pass' uses atan2 + cos/sin — likely manual arc center computation. Use Build123d kernel operations instead.
    - geometry/tool_reach.py | Function '_tangents_of' uses atan2 + cos/sin — likely manual arc center computation. Use Build123d kernel operations instead.
    - geometry/tool_reach.py | Module 'geometry' imports 'pipeline.insert_geometry_lookup' but is only allowed to import from: ['models', 'tools']
    - gui/program_tab.py | Package 'shapely' may only be imported by ['validation'], but found in 'gui'
    - gui/program_tab.py | try/except ImportError with alternative implementation — violates 'no silent fallbacks' principle (P3)
    - outputs/cut_regions.py | Module 'outputs' imports 'geometry.tool_reach' but is only allowed to import from: ['models']
    - outputs/cut_regions.py | Module 'outputs' imports 'geometry.zone_builder' but is only allowed to import from: ['models']
    - outputs/cut_regions.py | Package 'shapely' may only be imported by ['validation'], but found in 'outputs'
    - outputs/gcode_writer.py | Module 'outputs' imports 'geometry.arc_math' but is only allowed to import from: ['models']
    - planners/cleanup_planner.py | Module 'planners' imports 'geometry.arc_math' but is only allowed to import from: ['intervals', 'models', 'tools']
    - planners/contour_roughing_planner.py | Package 'OCP' may only be imported by ['geometry'], but found in 'planners'
    - planners/staircase_planner.py | Module 'planners' imports 'validation.polygon_builder' but is only allowed to import from: ['intervals', 'models', 'tools']
    - planners/staircase_planner.py | Package 'shapely' may only be imported by ['validation'], but found in 'planners'

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

- [X Vernier: Commissioning Runbook](2026-11-10-x-vernier-commissioning.md)
  - Status: Built and bench-proven 2026-11-10 on branch `claude/x-vernier`;
    not yet on the machine. Owner-present tuning session required.
  - Sub-count X position from scale edges + step feedback (`rtcomp/xvernier.comp`).
    Bench, with calibration fitted from a simulated sweep: ±.00005-.0001 dia
    parking vs ±.0009 today. No new hardware; wear workflow unchanged.
  - First action: merge (inert), `sudo halcompile --install rtcomp/xvernier.comp`,
    then the runbook steps 1-6 (shadow → baseline → sweep/fit → indicator check
    → close → cut). The bench-day card at the top of the runbook has the commands;
    fill in its session log.

- [Z Vernier: Plan](2026-11-11-z-vernier-plan.md)
  - Status: Plan only (2026-11-11). Starts after X is closed and cutting parts.
  - Same estimator, own twin component; Z differences: 5.3 steps/count, 10" travel
    (maybe a pitch table), cutting thrust on the nut, deadband already 1 count.
  - First data: optional X runbook step 7 (raw Z sweep, ~5 min, Z vernier not needed).
  - Owner: acme/tight nut, same scale, Z tolerance ±.0005–.001 → Z is likely already in
    band; measure it first (offline replay of raw captures), build only if needed.

- [X Axis: Hold a .0004" Diameter Band](2026-11-10-x-axis-tolerance.md)
  - Status: Plan written 2026-11-10 after an evening of chasing X wear by hand
    (11 corrections, .001" window). Owner-present session required.
  - Finding: X scale = 1 count per .0004" dia (the whole band); deadband
    .0005 r = +/-.0010 dia parking window. Tuning alone cannot reach the band.
  - Superseded by the X vernier (above), chosen by the owner 2026-11-10 over a
    1 um scale. Deadband step-down kept as the fallback.

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
