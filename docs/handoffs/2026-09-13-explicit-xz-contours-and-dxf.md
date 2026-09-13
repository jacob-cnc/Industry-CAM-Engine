# Session: 2026-09-13 - Explicit X-Z Contours, Arc Choice, and DXF Interchange

## Workstream

Branch: `main`
Commit: See the commit containing this handoff
Environment: ChatGPT Work repository checkout
Change classification: Software-only documentation; the proposed feature will
be motion-affecting

## Starting State

- **Observed:** `SegmentListWidget` currently stores an ordered list of LINE or
  ARC endpoints plus corner-break rows. It describes an open OD or ID profile;
  `geometry/zone_builder.py` adds closure geometry from stock parameters.
- **Observed:** `ClosedProfile` therefore does not yet represent the owner's
  requested explicit, independently closed stock, part, and bore contours.
- **Observed:** Chamfer and fillet corner-break data and Build123d construction
  already exist, so they should be evolved rather than independently
  reimplemented.
- **Observed:** Arc terminology is inconsistent in current documentation and
  code comments: some locations describe radius sign as CW/CCW, while others
  describe it as minor/major. Program-tab arc preview is also a registered known
  defect (`R-008`). This must be resolved before extending arc authoring.
- **Observed:** Multi-block profile, threading, and grooving support now exists,
  satisfying the major prerequisite identified in
  `2026-06-11-csv-import-export-and-dxf-architecture.md`.
- **Observed:** `outputs/dxf_exporter.py` currently exports PlanResult and
  G-code-derived geometry. There is no editable part-definition DXF importer,
  and the export is not a lossless conversational-project format.

## Owner Request - Verbatim

The following text is preserved exactly as supplied by Jacob Honick. Do not
silently rewrite it when converting this proposal into a specification.

```text
I want to add a note into my LinuxCNC repo https://github.com/jacob-cnc/Industry-CAM-Engine  about a new conversational style I’d like to try.

I want to have an X|Z table where a user makes explicitly closed polygons to describe the geometry of the stock, part, and bores/holes by inputting vertex coordinates. This will be a standalone table which will generate a displayed/simulated graphic similar or the same as the style I have now. When the user inputs a valid closed polygon it will generate a tool path choice for each line segment. I want to have corner break features so a user can easily program a chamfer or radius between vertices. I believe most of my arc choice code is cleaned up, but I’d like to plan in an explicit way for the user to choose which arc as part of a circle they are intending when programming corner breaks, in addition to radii that are part of the described part itself. A prompt or selector akin to the compound slide arc selector might work well.

I’d like to handle threading and cutoff events with a more structured, text based option, but the line selector system described above should work well for grooves.

It would be ideal if a user could create and export DXF’s from this conv feature, and it may be wise to have the tool path generation engine pull directly from the DXF instead of the vertex info and rad choices logic. It would also let users import DXFs from their own cad softwares into the conv tab, that way users can program from CAD geometry. Sometimes DXFs are not clean from cad programs though, so the X|Z table should populate from the imported DXF, that way a user can still utilize the conv tab functionality to change, add, or remove vertices as needed.

Create a note in my repo that will flag whatever agent accesses the repo next, there should be a handoff note location, and record my exact wording there. You can also add in comments about your suggested ideas, integration advice, modes of action, etc of this feature
```

## Goal and Acceptance Criteria

- Goal: Design a standalone X|Z contour editor that can author and repair
  explicit stock, finished-part, and bore contours; attach machining intent;
  disambiguate arcs visually; and exchange geometry with CAD through DXF.
- Eventual acceptance criteria:
  - Invalid or ambiguous contours cannot generate G-code.
  - Each contour is visibly and explicitly closed, with no hidden closure edge.
  - Table, preview, saved project, DXF adapter, geometry kernel, toolpath, and
    G-code visualization agree on coordinates and arc solutions.
  - A user can select an eligible edge and see only operations valid for that
    edge and contour role.
  - Corner chamfers/fillets and profile arcs can be selected from unambiguous
    visual candidates and survive save/load without changing solution.
  - DXF import populates the editable table and reports every repair,
    assumption, ignored entity, and unsupported entity.
  - DXF export can recreate the authored geometric contours.
  - Threading and cutoff remain structured operations rather than being
    inferred only from drawn geometry; groove operations can reference selected
    contour edges.
  - Existing version-1/version-2 conversational files remain loadable or are
    migrated explicitly.

## Recommended Architecture

### 1. Use one canonical contour document, not DXF, as the runtime source

Introduce a pure-data model in `models/` representing a collection of typed,
closed contours and stable edge IDs. Suggested roles are `STOCK`,
`FINISHED_PART`, and `BORE`; clarify whether multiple nested bores are supported
and whether “hole” means only an axisymmetric 2-axis lathe feature.

Both entry paths should converge immediately:

- X|Z table -> canonical contour document
- DXF import -> normalize, chain, and validate -> canonical contour document

The preview, Build123d geometry construction, operation bindings, project save,
and DXF export should all consume that same normalized document. Do not export a
temporary DXF and then reparse it inside the CAM pipeline. DXF is valuable as an
interchange format, but it is a poor internal contract because units, layer
meaning, entity order, topology, and custom machining intent may be absent or
altered by another CAD system. Keeping it at the boundary also complies with
the repository's “one path, one implementation” rule.

Use the existing `.cam`/JSON project format for lossless persistence of contour
roles, stable IDs, arc choices, corner breaks, operation assignments, tool data,
and threading/cutoff parameters. DXF should round-trip geometry; a companion CAM
file may be required to round-trip all machining intent.

### 2. Make closure and topology explicit

The new model cannot be a GUI-only variation of the current `ClosedProfile`,
because that model intentionally appends closure from stock. Define the contour
contract first, then provide an adapter to the existing pipeline for shapes it
can safely support during migration.

Recommended table behavior:

- One row per vertex, with a stable vertex ID and an edge from that vertex to
  the next; the final row owns the visible closing edge back to the first row.
- Show contour role, closure state, winding, and validation state.
- Provide an explicit `Close contour` action. Normalize away a duplicate final
  point internally, but never silently bridge a gap outside tolerance.
- Preserve a user-visible repair log for snapping, duplicate removal, entity
  chaining, or direction reversal; require confirmation when geometry changes.
- Validate at least: three unique vertices, nonzero edges, closure, no
  self-intersection, no branching, no overlapping duplicates, X >= 0, supported
  containment between stock/part/bores, and valid line/arc continuity.

An arbitrary stock polygon is a larger planner change than the current
`StockDef`. In the first increment, either derive a supported `StockDef` from a
validated cylindrical-stock contour or reject unsupported stock shapes with a
clear message. Do not approximate them silently.

### 3. Separate geometry from machining intent

A selected geometric edge should expose applicable operations, but selecting an
edge must not directly become a literal machine move. Store operation blocks
that reference stable contour/edge IDs; planners still decide offsets, roughing
passes, ordering, approaches, and safe transitions.

Candidate edge intents include OD/ID contour region, face, groove, and
reference/ignore. Threading should remain a typed `ThreadingParams` operation.
Cutoff/parting should become its own structured operation block, even if it
shares implementation with grooving, because its terminal sequencing and safety
meaning differ. A groove block can naturally reference a selected radial or
groove-defining edge. If an edit deletes or splits a referenced edge, mark the
operation unresolved and block generation instead of guessing a replacement.

### 4. Replace overloaded signed-radius meaning with explicit arc identity

Do not encode every arc choice in the sign of one radius value. A durable arc
record should separate radius magnitude from the selected geometric solution,
using a canonical combination such as center/side plus traversal direction (or
an equivalent kernel-derived solution ID). Minor/major sweep and CW/CCW are
related but not interchangeable concepts.

For an endpoint-and-radius arc, ask the geometry kernel for every valid
candidate, display the candidates in a small selector like the compound-slide
arc selector, highlight each candidate in the main preview, and persist the
selected canonical solution. Use canonical X-Z geometry terms in stored data;
translate to screen-relative CW/CCW labels only in the GUI, because the graph's
inverted axis can reverse what the operator sees.

Use the same selector pattern for ambiguous profile arcs and for corner-break
fillets where more than one material-side/tangent solution is valid. Resolve
`R-008` and add arc-contract tests before treating the preview as authoritative.

### 5. Treat DXF import as a visible normalization workflow

Implement DXF parsing outside Qt in a reusable boundary module, as proposed by
the 2026-06-11 handoff. A safe first entity subset is `LINE`, `ARC`, and
`LWPOLYLINE`/`POLYLINE` with bulges. Explicitly report or reject `SPLINE`,
`ELLIPSE`, `INSERT`, `HATCH`, 3D entities, and nonplanar geometry until supported.

Import should:

1. Read `$INSUNITS`; prompt when absent or conflicting.
2. Confirm axis mapping, Z sign, and whether the source X dimension is radius or
   diameter before conversion to the UI's X-diameter convention.
3. Map recognized layers to contour roles, building on `STOCK`, `PROFILE_OD`,
   and `PROFILE_ID` from the earlier handoff, with a user mapping dialog for
   unfamiliar layers.
4. Match endpoints within a documented import tolerance, chain unordered
   entities, and detect disconnected components, branches, gaps, duplicates,
   overlaps, and self-intersections.
5. Present each proposed contour and all cleanup actions before acceptance.
6. Populate the same X|Z table used for manual entry, where the user can add,
   remove, reorder, or change vertices and arc choices.

DXF export should have a geometry-only mode for CAD use and may retain the
existing diagnostic/toolpath mode separately. Do not conflate an editable part
definition with a G-code-round-trip toolpath drawing.

### 6. Keep preview and execution on one traceable path

The editable preview may render candidate/invalid geometry before generation,
but after validation the displayed part and generated path should be derived
from the same normalized model and kernel results. Keep the existing chain of
trust for actual motion: normalized input -> Build123d/OCCT -> planners ->
validation -> G-code -> parsed execution preview. Clearly style stock, finished
part, bores, selected edges, unresolved edges, feeds, and rapids differently.

## Suggested Modes of Action

1. **Write an ADR before implementation.** Decide the canonical contour schema,
   explicit closure representation, arc identity, coordinate/unit contract, DXF
   boundary, operation-to-edge references, and migration strategy.
2. **Build and test the model/compiler first.** Add the contour document,
   topology validation, stable IDs, JSON migration, and a narrow adapter to
   current `ClosedProfile`/`StockDef`. No G-code behavior should change yet.
3. **Add the standalone editor and preview.** Support manual LINE contours,
   explicit closure, editing, selection, and clear error states before arcs or
   operations are enabled.
4. **Add kernel-derived arcs and corner breaks.** Reuse current corner-break
   geometry where valid, introduce the visual arc selector, and verify every
   candidate against saved/loaded and generated geometry.
5. **Bind operations to stable edges.** Reuse the multi-block system and current
   planners. Add groove edge selection and typed cutoff; retain structured
   threading.
6. **Add DXF adapters and repair UI.** Start with the strict entity subset and
   layer mapping, then expand only with fixtures from real CAD exporters.
7. **Verify as motion-affecting work.** Add property, import-order, unit,
   radius/diameter, topology, arc-candidate, save/load, DXF round-trip, G-code
   round-trip, and safety-validation tests. Compare representative results to NX
   ground truth before controlled machine commissioning.

## Evidence and Measurements

- **Verified:** The owner's wording is recorded verbatim above and is linked
  from the agent start-up path through `AGENTS.md` and `ACTIVE.md`.
- **Observed:** Existing corner-break, multi-block, threading, grooving, preview,
  Build123d, validation, and DXF-export components provide reusable foundations.
- **Inferred:** A canonical contour model with boundary adapters is the lowest
  risk way to support both table and CAD entry without duplicate geometry paths.
- **Assumed:** The first implementation remains limited to axisymmetric 2-axis
  lathe geometry; Jacob should confirm if off-axis holes or live-tool features
  are intended.

## Verification Performed

| Check | Result | Notes |
|---|---|---|
| Documentation diff review | Pass | Owner request and recommendations reviewed |
| Whitespace/error check | Pass | `git diff --check` |
| Focused tests | Not run | Documentation-only change |
| Full tests | Not run | Documentation-only change |
| Architecture checks | Not run | No Python/import changes |
| Ground-truth comparison | N/A | No geometry or G-code changed |
| G-code round-trip | N/A | No geometry or G-code changed |
| Offline LinuxCNC/mock | N/A | No runtime change |
| Physical machine | N/A | No runtime change |

## Safety Impact

This commit changes documentation only and cannot alter motion or machine state.
The proposed feature is motion-affecting: ambiguous arc choice, contour repair,
unit conversion, radius/diameter conversion, edge-operation reassociation, or
DXF topology errors could generate unintended motion. Generation must fail
closed on every unresolved or unsupported condition, and eventual work requires
software verification plus a conservative commissioning plan before being
described as machine-verified.

## Deployment and Rollback

Deployment commit: See the commit containing this handoff
Preserved machine-state files: No machine-state files touched
Rollback location/commit: Parent of the commit containing this handoff

## Decisions

No implementation decision is final merely because it appears in the
recommendations above. The owner's verbatim request is authoritative. Record
accepted architectural decisions in an ADR before implementation.

The existing decision to defer DXF until multi-toolpath support should be
revisited, not blindly retained: its prerequisite now appears to be satisfied.

## Known Problems and Risks

- `R-008` remains relevant: the current Program-tab arc preview can display the
  wrong sweep/full circle.
- The existing open-profile-plus-implicit-closure model cannot directly express
  this request.
- The current DXF exporter uses millimeters and radius coordinates while the UI
  uses selectable units and X diameter. Import/export must define this boundary
  explicitly.
- Standard DXF does not preserve all conversational machining intent.
- Imported CAD geometry may be unordered, open, duplicated, unsupported, or
  topologically ambiguous; silent cleanup would be unsafe.

## Exact Next Step

Create an ADR defining the canonical contour document and its invariants. Use at
least one simple OD part with one bore and one intentionally ambiguous arc as a
fixture. Prove manual table -> normalized model -> save/load -> kernel preview
before changing planners or accepting imported DXF as toolpath input.
