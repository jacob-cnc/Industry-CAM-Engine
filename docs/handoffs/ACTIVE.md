# Active Handoffs

Agents must review the entries below before scoping related work. This file is
an index, not the full specification; follow the linked handoff and preserve
the distinction between the owner's verbatim request and later design advice.

## Proposed

- [Corner-Break Tool, OD Engine, GUI Tuning - lathe integration](2026-11-10-corner-break-tool-and-gui.md)
  - Status: Software done on `work/2026-11-10` (not on main); lathe test pending.
  - Motion-affecting: OD corner-break G-code, offset fallback, stock-size refusal.
  - Path overlap: `gui/manual/manual_tab.py`, `gui/manual/sections.py` (layout only).
  - First action: Claude checks out `origin/work/2026-11-10` on a lathe branch,
    preserves tool.tbl/var/ini, runs the suite, then the no-motion GUI checks.

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
