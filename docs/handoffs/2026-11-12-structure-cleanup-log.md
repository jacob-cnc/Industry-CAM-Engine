# Structure cleanup: work log (overnight 2026-11-11 → 12, autonomous)

Branch `claude/structure-cleanup` from main `01f6cf3`, worktree `~/linuxcnc/wt-structure`
(the live checkout `~/linuxcnc/configs/industry-cam` stays on main; the GUI runs from it).
Afterwards: branch `claude/hand-math-kernel` for the hand-math inquiry.

This log is written as I go so every change can be traced back. Newest entries at the
bottom of each section. Times are PST.

## Owner direction (2026-11-11 ~23:00)

- Organize the code first (best practice), then hunt hand math on its own branch.
- Layering decision (a): planners may import ONE public kernel module, `geometry.kernel`;
  raw OCP / build123d stay inside `geometry/`.
- G-code need NOT be byte-identical. The baseline is regenerated from current main (it
  already has the .020 feed-in). Every difference is judged like a machinist: does the
  geometry make sense, is the tool described well enough, will it gouge, where is the
  material at each stage. Use build123d, shapely, STEP files and the GCH programs the
  owner has run. If understanding is lacking, build a basic tool/test first.
- No GUI approval tonight: GUI files only get import-path updates; nothing merges to main.

## Baseline (before any change)

- Full suite on main 01f6cf3, lathe runtime: 1310 passed, 0 failed.
- `python -m validation.architecture_check`: 88 errors (62 dependency, 22 hand math,
  4 import fallbacks), 197 warnings (150 dead code, 10 dual implementation, …).

## Survey (2026-11-11 ~23:00)

- Kernel work leaked out of geometry/: planners/cleanup_planner, contour_roughing_planner,
  finish_planner call OCP directly (23 OCP + 4 build123d imports); outputs/ uses Shapely
  and imports geometry internals and planners; geometry/tool_reach imports pipeline/.
- Misplaced: pipeline/ holds tool-table I/O, the GUI tool-card model and insert data;
  outputs/ holds verification (cut_regions, material_sim).
- Dead: planners/offset_contour_planner.py (OffsetContourPlanner) — not used by the
  pipeline or any test, untouched since the initial commit.
- Arc math spread over geometry/arc_helpers, arc_math, arc_entry, adaptive_sampling.
- Large files: gui/program_tab.py 2821, outputs/gcode_writer.py 1487.

## Plan

1. Guardrails: `scripts/regression/` — regenerate the program corpus headlessly through
   the GUI's own Generate, record G-code + cut sections (rs274 + cut_regions); compare
   two runs like a machinist. Architecture-check gate (error count must not rise).
2. Remove confirmed dead code.
3. Move misplaced modules (moves + import updates only).
4. Kernel boundary: `geometry/kernel.py` public facade; OCP/build123d out of planners.
5. Split large non-GUI files where it clarifies.

## Steps

(entries follow)

### Step 1 — guardrails (2026-11-11 23:30 → 2026-11-12 00:40)

- `scripts/regression/regen.py`: headless GUI Generate (real ProgramTab, offscreen) +
  cut sections via `outputs/cut_regions` → `<name>.ngc` + `<name>.result.json` (status,
  notes, dialogs, section areas, section geometry as WKT in radius space).
  - First full run hung on "Hemisphere Test": a modal GenerationErrorDialog waits for a
    click offscreen. Fix: record every dialog (title + text, incl. custom dialogs' labels)
    and answer with its default. Never a choice the GUI wouldn't make by default.
- `scripts/regression/compare.py`: SAME / COMMENTS / MOTION-PART-OK / PART-CHANGED /
  BOTH-REFUSE / MISSING. Machinist metrics: finished-part symmetric difference + Hausdorff,
  gouge and not-removed growth, band (face/rough/cleanup/finish) area shifts.
- Corpus (21): 13 owner/reference programs that generate; 4 old reference programs refuse
  because T1 is now a boring bar (Q3) — correct GUI behaviour; their "(T4 derived)" copies
  (tool 1→4 like the owner's own T4 copies) add coverage incl. the only threading program
  (Quarter-20 Cap Screw). "Test Program Tab (T4 derived)" still refuses: "Cannot build
  face(s): wires not planar" — a kernel/profile issue to look at in the hand-math phase.
- Sanity check against what the owner ran (GCH Boring Test Ring Bore NEW, saved 11-10):
  differences are exactly the 11-11 mouth-chamfer collinear entry and the .020 feed-ins.
  Observation (not changed): in the collinear-entry case the outward feed-in is followed
  by an inward entry along the chamfer, so the nut is loaded by the entry move (.080 dia)
  — harmless, but the feed-in does no work there. Candidate refinement for later.
- Determinism: baseline generated twice from a detached worktree of main 01f6cf3 →
  21/21 SAME. Baseline = scratchpad `base_v2` (16 generate, 5 refuse identically; no
  program has gouge or left material).
- Architecture ratchet: `tests/architecture/test_architecture_ratchet.py` +
  `validation/architecture_baseline.json` (dependency 62, fallback 4, hand_math 22).

### Step 2 — dead code (2026-11-12 00:40 → 01:15)

Each candidate checked by searching the whole repo (gui, tests, scripts) for any use outside
its own definition / package re-export, not trusting the checker's list alone (it puts
`build_state_section` in pipeline/ — it is in gui/manual/sections.py — and counts
`from __future__ import annotations` as unused).

Removed:
- `planners/offset_contour_planner.py` (OffsetContourPlanner) — unused since the initial
  commit; the pipeline uses ContourRoughingPlanner. Note: it was the one written the
  intended way (kernel answers injected via ZoneQueryAPI) — the live one uses raw OCP. Step 4
  moves the live one's kernel work behind geometry.kernel instead.
- `planners/protocols.py` (RoughingPlanner protocol, nothing implemented or used it).
- `tools/tool_shape.py` (ToolShape, ToolReachError — only re-exported). tools/ kept as the
  home for tool data in step 3.
- `outputs/sim_adapter.py` (the GUI's simulator parses G-code instead).
- `pipeline/file_io.py` + `test_public_file_io_uses_same_radius_serializer`: a second public
  tool-table API nobody called (the GUI uses pipeline/tool_table_io directly); the test only
  guarded that the duplicate delegated to the real serializer.
- `geometry/arc_helpers.interpolate_quadrant_arc`, `outputs/svg_exporter._boundary_to_radius_coords`.
- 57 unused imports in non-GUI packages (names that appear nowhere else in their file,
  strings and quoted annotations included; `__future__` kept). One emptied
  `if TYPE_CHECKING:` block removed with them (contour_roughing_planner).
- Package `__init__.py` re-exports (geometry, intervals, outputs, pipeline, planners, tools,
  transitions, validation) → docstring only. Nothing used package-level names; the eager
  imports meant e.g. the Tools tab's `pipeline.tool_table_io` import loaded the whole
  pipeline and OCP. Kept: `hal/` (public `get_backend` facade) and `models/` (light
  dataclasses; old scripts use `from models import *`).

Not removed (GUI, no owner check tonight): `gui/manual/sections.build_state_section` and the
other gui/ dead-code warnings.

Verification: suite 1310 passed (1309 + ratchet); regression vs base_v2: 16 SAME, 5
BOTH-REFUSE (compare now ignores tracebacks in refusal dialogs — paths differ between
checkouts). Architecture: dependency errors 62 → 60 (unused OCP/build123d imports gone
from contour_roughing_planner) — ratchet lowered.

### Step 2b — remove the dormant material simulator (2026-11-12 01:15 → 01:35)

- `outputs/material_sim.py` (1055 lines) was an earlier material-removal simulator. Nothing
  in production called `material_sim.compute()`: program_tab imported the module but never
  used it, and `graph_adapter.convert()` only serialized material states when given
  `material_sim_data`, which no caller passed (`graph_convert(first_plan_result)`). Zone
  shading now comes from `outputs/cut_regions` (rs274-based), so it was a second, dead
  simulator. Removed with its two property-test files (13 tests), the adapter's
  `_convert_material_sim` + parameter, and program_tab's unused import (the only gui/ edit).
- Kept: `MaterialStateData` and `GraphData.material_states` (always None now) — gui/
  graph_widget and sim_viewer still read them (their code returns early when None).
  Pruning that dormant GUI rendering is a GUI change for an owner-checked session.
- Verification: suite 1297 passed (1310 − 13 removed); regression 16 SAME, 5 BOTH-REFUSE.
  Dependency errors 60 → 56 (Shapely gone from outputs/ x4) — ratchet lowered.

### Step 3a — tool modules pipeline/ → tools/ (2026-11-12 01:35 → 02:00)

- `git mv` (history kept): tool_card_data, tool_table_io, filter_cascade,
  insert_geometry_lookup from pipeline/ to tools/. They depend only on models/ and each
  other; pipeline/ is orchestration. Fixes geometry/tool_reach importing pipeline/
  (dependency errors 56 → 55, ratchet lowered).
- References updated in code, tests, scripts and one code comment (models/tool.py).
  gui/ edits are import lines only (tools_tab, main_window, components/tool_geometry_row).
- Historical documents NOT rewritten (handoffs from earlier days, .kiro specs, ACTIVE.md's
  recorded checker messages, this log): they record what was true when written.
  ARCHITECTURE.md describes the current layout → one update at the end of the cleanup.
- regen.py imports the tool modules from tools/ or pipeline/, whichever the checkout has,
  so it can still regenerate baselines from checkouts before the move.
- Verification: suite 1297 passed; regression 16 SAME, 5 BOTH-REFUSE.

### Step 3b — cut_regions outputs/ → validation/ (2026-11-12 02:00 → 02:25)

- It checks what the G-code does (rs274 + Shapely sections, gouge / not removed): a
  validation, not an output. Its imports (geometry/, Shapely) are what validation/ may use.
  Importers updated: gui/program_tab (one import line + location comments in gui files),
  tests/integration/test_cut_regions.py, regen.py (both locations supported).
- Dependency errors 55 → 45 (outputs/ no longer imports Shapely or geometry internals).
- Hand-math errors 22 → 23: the ratchet caught it. Not new code — validation/ is scanned
  for hand math and outputs/ is not, so `parse_canon`'s existing arc densification
  (atan2 + cos/sin of rs274 ARC_FEED) became visible. Baseline raised to 23 with the reason
  recorded in architecture_baseline.json "_history"; it goes on the hand-math list.
- Also noted for the kernel step: cut_regions calls PRIVATE geometry helpers
  (`tool_reach._densify`, `zone_builder._profile_to_radius_coords`) — they should be public
  geometry API.
- Verification: suite 1297 passed; regression 16 SAME, 5 BOTH-REFUSE.

### Step 3c — the writer stops planning (2026-11-12 02:25 → 02:55)

- `GCodeWriter.write_threading_block` called `ThreadingPlanner().compute_g76_params()` and
  `write_grooving_block` called the PRIVATE `GroovingPlanner._compute_plunge_positions()`:
  an output module planning. Now the writer takes the planned values
  (`write_threading_block(params, g76, tool, …)`, `write_grooving_block(params,
  plunge_positions, tool, …)`) and the caller plans: gui/program_tab's
  `_generate_threading_block` / `_generate_grooving_block` (2 call sites, ~3 lines each)
  and one unit test. `compute_plunge_positions` is public now.
- Dependency errors 45 → 43 (ratchet lowered).
- Verification: suite 1297 passed; regression 16 SAME, 5 BOTH-REFUSE — includes the only
  threading program (Quarter-20 Cap Screw, T4 derived). No program in the corpus grooves, so
  grooving was checked directly: three blocks (OD peck, OD single plunge, ID multi-plunge
  peck) emitted with main's code and with this branch → identical text.
- Question for the owner (existing behaviour, unchanged): a zero-width groove at Z−.200 with
  a .094 blade plunges at Z−.153 (= Z−.200 + half the blade). Right or wrong depends on which
  blade corner the grooving tool's Z offset refers to — worth a look before grooving.

### Step 4a — geometry/kernel.py facade + rule (a) in the checker (2026-11-12 02:55 → 03:30)

- `geometry/kernel.py`: the planners' only door into geometry/ (re-exports with `__all__`:
  Arc, arc_from_kernel, short_sweep, split_at_quadrants, is_arc_within_x_bounds,
  profile_to_radius_coords, EdgeData, offset_face, KernelOffsetError). Every runtime
  `from geometry.<x> import` in planners/ now reads `from geometry.kernel import`.
  Type-hint-only imports under TYPE_CHECKING (ZoneQueryAPI, EdgeData, ContourIntersect) are
  unchanged: no runtime dependency, and the checker exempts them.
- validation/architecture_check: `ALLOWED_SUBMODULE_IMPORTS = {"planners": {"geometry.kernel"}}`
  + three tests (facade allowed; other geometry modules and raw OCP still violations).
- Public names for helpers used across modules: zone_builder `_profile_to_radius_coords` →
  `profile_to_radius_coords` (6 modules + 2 tests), tool_reach `_densify` → `densify_coords`.
- Dependency errors 43 → 32 (ratchet lowered).
- Verification: suite 1300 passed (1297 + 3 facade-rule tests); regression 16 SAME, 5 BOTH-REFUSE.

Findings while reading the planners' kernel code (for 4b and the hand-math branch):
- The canonical face builder (zone_builder `_build_face_from_coords`) makes quadrant arcs
  TRUE circular quarters (ThreePointArc; owner 2026-11-11 "ellipses are retired"). The copies
  in cleanup_planner and contour_roughing_planner still build them as a 64-segment ELLIPSE
  POLYLINE. No corpus program has quadrant arcs (radius "Q"/"-Q"), so the regression corpus
  does not exercise this; tests do. → hand-math branch: replace with the canonical builder and
  add a basic corpus program with Q arcs first.
- contour_roughing_planner's fallback `_build_face` passes `RadiusArc(-radius)`: the
  documented 2026-11-10 bug ("every arc bulged the wrong way", fillet gouges). It runs only if
  `zone_set.finished_part` is missing, which the pipeline never allows (build_zones raises on
  failure) and no test does → unreachable, but a silent gouge if it ever ran. Removed in 4b.
- cleanup_planner offsets with raw `b3d_offset(kind=INTERSECTION)`; everything else uses
  `kernel_offset.offset_face` (sharp, then logged rounded-join fallback, readable error).
- Every kernel step in cleanup is wrapped in `except Exception: return []` ("triggers
  fallback to zone boundary") — a silent fallback; keep for now (behaviour), hand-math branch.

### Step 4b — raw kernel code out of cleanup + contour roughing planners (03:30 → 04:15)

- New `geometry/face_ops.py` (exported via geometry.kernel), each function moved VERBATIM
  from the planners with its origin and debts in the docstring:
  `face_from_coords_polyline_quadrants` (cleanup's face builder, ellipse polyline kept),
  `offset_face_sharp_only` (cleanup's raw INTERSECTION offset), `first_ocp_face`,
  `translate_face`, `clip_to_box` (outer wires of every clipped face),
  `wire_edges(wire, split_arcs=...)` (True = contour roughing's canonical ≤90° arc pieces,
  False = cleanup's whole arcs). Planners hold kernel shapes as opaque handles.
- cleanup_planner: six blocks replaced by those calls inside the SAME try/except structure;
  clip-edge filtering and the ID same-X rule stay in the planner (CAM context). The unused
  `BRepTools.OuterWire_s(ocp_face)` after the offset was dropped (its result was never used).
- contour_roughing_planner: `_translate`, `_do_offset`, the clip and the wire walk call the
  kernel; filtering/ordering stay. REMOVED the fallback `_build_face` (RadiusArc(-radius): the
  documented wrong-way arcs). It could only run without `zone_set.finished_part` — the
  pipeline always provides it, no test omits it — so now a clear ValueError instead of a
  silent gouge. No reachable behaviour changed.
- Dependency errors 32 → 8 (ratchet lowered). Hand math unchanged (23): code moved, not changed.
- Verification: suite 1300 passed; regression 16 SAME, 5 BOTH-REFUSE. The corpus exercises
  both planners: the NX "_offset" programs use contour roughing; every staircase program runs
  the cleanup planner.
- Noted: both wire walks drop edges that are neither lines nor circles without a word
  (documented on wire_edges) — not triggered by line/arc offsets, but a silent missing cut if
  it ever were.

### Step 4c — finish planner's curve fitting → geometry/curve_fit (04:15 → 04:50)

- `FinishPlanner._decompose_curve_edge` evaluated the OCP curve (BRepAdaptor_Curve) and
  carried its own 3-point circumcentre, line-deviation check and adaptive subdivision.
  Moved verbatim to `geometry/curve_fit.py` (via geometry.kernel): `circumcenter`,
  `max_line_deviation`, `subdivide_curve_spans`, and `curve_arc_spans(ocp_edge, start, end,
  chord_error)` → per piece (start, mid, end) in diameter, same direction detection (.001)
  and first/last endpoint snapping. The planner keeps building the G2/G3 moves (feeds, I/K).
- tests/unit/test_edge_decomposition.py: `FinishPlanner._circumcenter` → `geometry.kernel.
  circumcenter` (5 refs). Its 15 tests (real OCCT ellipse + B-spline edges) pass.
- Reachability: CURVE edges need non-circular geometry; since quadrant arcs became true circles
  (owner 2026-11-11) the zone builder makes only lines and circles, so no Generate path reaches
  this today. Kept (tested) for future spline input; documented in the module.
- Dependency errors 8 → 7. Hand math 23 → 24 is a counting artifact, not new math: the
  checker counts one finding per function, and `_decompose_curve_edge`'s two sqrt distances
  are now split between `curve_arc_spans` (direction check) and the planner (arc radius).
  Recorded in the baseline history.
- Verification: suite 1300 passed; regression 16 SAME, 5 BOTH-REFUSE.

### Step 4d — staircase nose clearance injected from the pipeline (04:50 → 05:25)

- The staircase planner imported `validation.polygon_builder` and used Shapely to build the
  nose-forbidden tip region (keep zone grown by the nose radius, shifted nose-centre → tip;
  the 2026-11-11 fix for the nose overhanging a falling flank) and to clip each pass line.
- Moved verbatim to `validation/nose_clearance.py`: `NoseClearance.build(zone_query, tool)`
  (None when zone polygons are unavailable, the keep zone is empty, or the tool is sharp —
  as before) and `free_spans(r, z_top, z_bottom)`. The pipeline builds it and passes
  `nose_clearance=` to `StaircasePlanner.plan`; the planner only calls `free_spans`. Only the
  pipeline (and an old debug script) calls the staircase planner.
- **Planners now have ZERO dependency violations.** Dependency errors 7 → 4 (ratchet lowered).
  The 4 left: outputs/gcode_writer → geometry.arc_math (arc sweep) and Shapely (comp lead-out
  material probe), outputs/graph_adapter → geometry.adaptive_sampling (display densification),
  gui/program_tab Shapely (union of shaded sections). See "Open decisions" below.
- Verification: suite 1300 passed; regression 16 SAME, 5 BOTH-REFUSE (most corpus programs are
  staircase: identical nose trimming).
