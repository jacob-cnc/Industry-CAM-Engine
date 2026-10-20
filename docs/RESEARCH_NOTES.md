# Research Notes

Short, standing notes on external projects and techniques worth evaluating.
These are not decisions (see `docs/decisions/` for ADRs) and not commitments
(see `docs/ROADMAP.md`). They are leads to investigate.

For owner-requested work the next agent must act on, the authoritative location
is `docs/handoffs/ACTIVE.md` and the dated handoff it links. This file is only a
quick index.

## LibreCAD as reference for 2D geometry + DXF I/O

Source read: LibreCAD `master` (full clone), 2026-10-20. Lead supporting the
2026-09-13 DXF-boundary + arc-representation work (see
`docs/handoffs/2026-10-20-librecad-reference-evaluation.md`). Findings below are
verified against source unless marked inferred.

**DXF I/O boundary.** LibreCAD keeps the file format strictly separate from the
model: `libraries/libdxfrw/` (a maintained dxflib fork) parses/writes DXF and
calls back through an abstract interface (`drw_interface.h`, `addLine/addArc/
addCircle/addSpline/addLWPolyline`). `rs_filterdxfrw.cpp` maps each callback to
an internal `RS_*` entity; export runs the reverse. This is the same
"DXF-at-the-boundary, reusable parse/write module outside the GUI" shape the
2026-09-13 handoff recommends — external validation of that direction.

**Entity model.** `RS_Entity` base splits into `RS_AtomicEntity` (line/arc/
circle) and `RS_EntityContainer`. A polyline — and a spline — is a *container*
of its decomposed primitive children. Arcs store center/radius/angle1/angle2 +
a reversed (CW/CCW) flag.

**Arc identity (relevant to R-008).** LibreCAD does NOT re-fit curves to arcs
for its model: `RS_Spline::update()` (rs_spline.cpp:699) flattens a spline into
a chain of `RS_Line` segments. So "preserve true arcs through the pipeline" is
an identity LibreCAD does not itself maintain for splines — it line-approximates
with error control instead.

**Spline flattening is curvature-adaptive (the notable technique).**
`fillDisplayPoints()` subdivides span-by-span, adding more segments where the
curve bends, governed by a chord-error tolerance (~h^2/8*|C''|) scaled to the
spline's bbox, bounded min 32 / max 4096 segments, with 5-point Gauss-Legendre
arc-length tabulation per knot span. This is the principled alternative to a
fixed-density flatten and is the single highest-value idea to borrow.

**Intersection + split.** `RS_Information::getIntersection(e1,e2,onEntities)`
dispatches to typed line/arc/circle solvers returning `RS_VectorSolutions`;
`onEntities` filters to crossings within both entities' bounds. `LC_Division`
(lc_division.h) is the break-at-intersections engine (`SegmentDisposition`:
INSIDE/TO_START/TO_END/ENTIRE). `LC_LineMath` has reusable primitives:
`areLinesOnSameRay()` (angle-based collinearity), `isNonZeroLineLength()`
(squared-length vs tolerance).

**No collinear/overlap cleanup.** Verified absent: "overlap" is only bbox
overlap, "duplicate" is a copy action, "collinear" only a degeneracy note. A
"merge overlapping duplicate collinear lines" pass would be net-new.

**Tolerances.** `RS_TOLERANCE = 1e-10`, `RS_TOLERANCE15 = 1.5e-15` (rs.h:35-40);
squared-length comparisons and angle-based collinearity throughout. Note: 1e-10
is tuned for clean model geometry — looser tolerances are safer for messy
CAD-exported DXFs.

**Leads worth acting on:** (1) adopt curvature-adaptive spline sampling for the
DXF import path; (2) borrow the angle-based collinearity test and squared-length
comparisons as robust primitives; (3) treat flatten-to-lines as the accepted
norm rather than blocking on spline->arc refit.
**Added:** 2026-10-20 — **Status:** To investigate

Evaluate LibreCAD (https://github.com/LibreCAD/LibreCAD, GPLv2) as design
inspiration for 2D geometry representation and DXF import/export in the builder.
DXF read/write there is built on `libdxfrw` (GPLv2+). Reference only — reading
for technique is fine, copying code is a license decision (record an ADR first).

Full context and evaluation plan:
`docs/handoffs/2026-10-20-librecad-reference-evaluation.md`
