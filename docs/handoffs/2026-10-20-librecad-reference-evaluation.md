# Session: 2026-10-20 - Evaluate LibreCAD as Reference for 2D Geometry and DXF I/O

## Workstream

Branch: `docs/librecad-reference-evaluation`
Commit: See the commit containing this handoff
Environment: Kiro IDE repository checkout (Windows), local clone
Change classification: Software-only documentation. No motion-affecting or
machine-control change in this commit.

## Starting State

- **Observed:** `AGENTS.md` directs the next agent to read
  `docs/handoffs/ACTIVE.md` for owner-requested work before substantial work.
- **Observed:** An existing owner request already covers the DXF boundary and
  arc representation: `2026-09-13-explicit-xz-contours-and-dxf.md`. That handoff
  recommends a canonical contour document with DXF kept strictly at the boundary
  (reusable DXF parse/write module outside Qt), and flags arc identity as a
  known problem area (`R-008`).
- **Observed:** Current geometry handling lives under `geometry/` (e.g.
  `arc_helpers.py`, `contour_intersect.py`, `zone_builder.py`), and DXF export
  lives in `outputs/dxf_exporter.py`. There is no DXF importer yet.
- **Observed:** This LibreCAD evaluation is a research lead that supports the
  2026-09-13 DXF work; it is not a new, separate feature request.

## Owner Request - Verbatim

The following text is preserved exactly as supplied by Jacob Honick. Do not
silently rewrite it when converting this proposal into a specification.

```text
I'd like you to inspect LibreCAD's windows instance for any potential malware
or otherwise harmful code before I download it onto this computer
https://github.com/LibreCAD/LibreCAD/

Can you add a note in my industry cam engine project to evaluate libreCAD's
potential as code inspiration for how we handle representing 2d geometry,
importing and exporting dxf's from our builder?
```

## Goal and Acceptance Criteria

- Goal: Record, for the next agent, that LibreCAD should be evaluated as design
  reference (not a code-copy source) for how this engine represents 2D geometry
  and imports/exports DXF from the builder.
- Acceptance criteria for the evaluation task itself (future work):
  - A written comparison of LibreCAD's 2D entity model (lines, arcs, circles,
    polylines, splines) against our `geometry/` model and the canonical contour
    document proposed in the 2026-09-13 handoff.
  - A written assessment of LibreCAD's DXF read/write path (via `libdxfrw`) and
    which import/normalization behaviors are worth adopting as patterns.
  - An explicit license determination recorded before any code is reused.

## Reference Material

- LibreCAD source: https://github.com/LibreCAD/LibreCAD
- DXF read/write in LibreCAD is provided by the `libdxfrw` library; that
  library boundary is the most directly relevant part for our DXF round-trip
  (read -> internal model -> write).

## Suggested Evaluation Focus

1. **2D geometry representation.** How LibreCAD models entities internally and
   how it handles arc direction, bulge conversion, and polyline closure.
   Compare against `geometry/arc_helpers.py` and the proposed canonical contour
   document. This is relevant to the unresolved arc-identity problem (`R-008`)
   called out in the 2026-09-13 handoff.
2. **DXF import normalization.** How `libdxfrw` + LibreCAD handle units
   (`$INSUNITS`), entity chaining, unsupported entities (SPLINE, ELLIPSE,
   INSERT, HATCH), and cleanup of messy CAD exports. This maps directly to the
   "visible normalization workflow" recommended for our DXF importer.
3. **DXF export.** How a geometry-only export is structured, to inform our
   geometry-only export mode distinct from the current toolpath/diagnostic
   export in `outputs/dxf_exporter.py`.

## License Caveat (important)

- LibreCAD is GPLv2; `libdxfrw` is GPLv2+.
- Treat LibreCAD as reference for *approach and structure only*. Reading it to
  understand technique is fine. Copying source into this engine is a licensing
  decision with GPL obligations, not an implementation detail. If reuse is ever
  proposed, confirm license compatibility first and record it as an ADR before
  writing any derived code.

## Malware / Safety Review (context for the request)

- The owner first asked whether LibreCAD is safe to download on Windows. LibreCAD
  is a long-established, legitimate open-source 2D CAD project with no credible
  history of malware in its official builds. Its known CVEs are memory-safety
  bugs in file parsers (crafted DWG/JWW/DXF/DBF files), not backdoors.
- A static/dynamic scan of the actual Windows binary was NOT performed; that is
  outside this repo's scope. Download only from official channels (librecad.org
  -> GitHub Releases or SourceForge) and verify the published checksum before
  running. This is **Assumed** safe based on reputation and provenance, not
  **Verified** by binary analysis.

## Evidence and Measurements

- **Verified:** The owner's wording is recorded verbatim above and is reachable
  from the agent start-up path via `AGENTS.md` -> `ACTIVE.md`.
- **Observed:** The evaluation directly supports the existing 2026-09-13 DXF and
  contour handoff rather than introducing an unrelated workstream.
- **Inferred:** LibreCAD's `libdxfrw`-based DXF boundary is a useful reference
  for the boundary module the 2026-09-13 handoff already recommends.
- **Assumed:** LibreCAD official Windows builds are safe to install; not
  confirmed by binary analysis.

## Verification Performed

| Check | Result | Notes |
|---|---|---|
| Documentation diff review | Pass | Verbatim request plus advice reviewed |
| Whitespace/error check | Pending | Run `git diff --check` before commit |
| Focused tests | N/A | Documentation-only change |
| Full tests | N/A | Documentation-only change |
| Architecture checks | N/A | No Python/import changes |
| Ground-truth comparison | N/A | No geometry or G-code changed |
| G-code round-trip | N/A | No geometry or G-code changed |
| Offline LinuxCNC/mock | N/A | No runtime change |
| Physical machine | N/A | No runtime change |

## Safety Impact

None. This commit changes documentation only and cannot alter motion or machine
state. Any future code reuse from LibreCAD would be motion-affecting and must
follow the normal verification and commissioning path, plus a license review.

## Deployment and Rollback

Deployment commit: See the commit containing this handoff
Preserved machine-state files: No machine-state files touched
Rollback location/commit: Parent of the commit containing this handoff

## Decisions

No decision is made here. This is a research lead. If LibreCAD technique or code
is adopted, record it as an ADR (and a license determination) at that time.

## Known Problems and Risks

- License contamination risk if GPL code is copied without a deliberate
  decision. Mitigated by the caveat above.
- `R-008` (Program-tab arc preview) remains the relevant open arc-representation
  risk the geometry evaluation should keep in mind.

## Exact Next Step

When picking up the 2026-09-13 DXF/contour work, review LibreCAD's `libdxfrw`
DXF boundary and its arc/polyline entity model, then write a short comparison
against our proposed canonical contour document. Do not copy code; record any
reuse proposal as an ADR with a license determination first.
