# Active Handoffs

Agents must review the entries below before scoping related work. This file is
an index, not the full specification; follow the linked handoff and preserve
the distinction between the owner's verbatim request and later design advice.

## Proposed

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
