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
