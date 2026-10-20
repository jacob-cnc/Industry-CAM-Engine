# Research Notes

Short, standing notes on external projects and techniques worth evaluating.
These are not decisions (see `docs/decisions/` for ADRs) and not commitments
(see `docs/ROADMAP.md`). They are leads to investigate.

For owner-requested work the next agent must act on, the authoritative location
is `docs/handoffs/ACTIVE.md` and the dated handoff it links. This file is only a
quick index.

## LibreCAD as reference for 2D geometry + DXF I/O

**Added:** 2026-10-20 — **Status:** To investigate

Evaluate LibreCAD (https://github.com/LibreCAD/LibreCAD, GPLv2) as design
inspiration for 2D geometry representation and DXF import/export in the builder.
DXF read/write there is built on `libdxfrw` (GPLv2+). Reference only — reading
for technique is fine, copying code is a license decision (record an ADR first).

Full context and evaluation plan:
`docs/handoffs/2026-10-20-librecad-reference-evaluation.md`
