# Hand-math inquiry (branch claude/hand-math-kernel, overnight 2026-11-12)

Owner direction (2026-11-11): once the code is clean and organized, search for the hand math
that should be kernel work. If you hit a wall, call it out with reasonable suggestions. If the
engine's confines make the kernel unusable in some scenario, explore altering the engine to
support the kernel rather than patching. Build understanding tools/tests from a basic level.

Standing rule (owner, 2026-11-11): any geometric answer that feeds a program (split points,
reach, profile edits) comes from Build123d/OCCT in geometry/; the arc math that remains lives
only in geometry/arc_math.py.

Branch `claude/hand-math-kernel` starts from `claude/structure-cleanup` 9962c59. Every change
is checked with the full suite and the regenerated corpus (scripts/regression, machinist
compare against main's baseline).

## Tools built for the inquiry

- `scripts/hand_math/inventory.py` — every function in the engine packages doing trig / roots /
  squares, with the architecture checker's flag. 77 functions (97 trig, 77 roots, 63 squares);
  the checker flags 24 of them.
- `scripts/hand_math/fallback_probe.py` — runs the corpus through the GUI's Generate and counts
  how often each known fallback / hand-math path actually runs.

## Findings and changes

### F1 — "wires not planar": the kernel was fine; a float comparison was not (FIXED)

The engine-vs-kernel case the owner asked about, live in the corpus: "Test Program Tab" (a
reference program; T4-derived copy) refused in the GUI with "Cannot build face(s): wires not
planar". Basic reproduction (direct pipeline call) generated fine; the GUI path did not. Traced
with a spy on `_build_stock_face`:

- Profile: stepped shaft ending with a concave R.5 arc at Z-1.5 = the stock back face (-1.5).
- `contour_z_end` took the kernel's bounding-box minimum: **-1.4999999999999865** (1.35e-14 of
  bounding-box noise above the arc's exact end point).
- `build_zones` compared `physical_z_end (-1.5) < z_end` with no tolerance → built a
  retained-stock rectangle **1.35e-14 tall** → OCCT cannot make a face of it.

So any profile whose last arc ends exactly on the stock's Z end failed to generate. Fix
(geometry/zone_builder.py):
1. `contour_z_end`: the kernel's bounding box still decides (an arc may dip below every vertex),
   but when its minimum agrees with the lowest profile vertex within 1e-9 the vertex's exact Z is
   returned.
2. `build_zones`: retained stock only when the back face is more than TOLERANCE behind the
   operation end.

Tests (tests/integration/test_operation_depth.py, +4): exact depth on a vertex; the profile
generates with both strategies with the back face on its end; an arc dipping below its end
points still sets the depth (kernel extremum, ~-0.53, not snapped). They failed before the fix
(3 of 4, "wires not planar") and pass after.

Machinist check of the program that now generates: gouge 0, not-removed 0; one honest note —
the concave arc first dips to X.9916 falling 7.2° toward the chuck and T4's back edge clears
5.0°, so up to .0010 stays (4.5e-5 in²), with suggested tools. Correct tool-reach physics.

Verification: suite 1304 passed (+4); regression 16 SAME, 4 BOTH-REFUSE, the fixed program now
generates.

Also seen: for this concave R.5 profile, OCCT's sharp-join offset fails on every contour-
roughing pass (24×) and kernel_offset falls back to rounded joins (logged). See F-later.

### F2 — The finish contour came from hand math when a walk failed (FIXED: kernel-only)

`scripts/hand_math/fallback_probe.py` on the corpus: every program used kernel paths except
"Hemisphere Test (T4 derived)", whose finish pass silently came from the hand-math fallback
(`FinishPlanner._moves_from_segments` → `_find_arc_center`).

Why (traced inside the GUI's Generate): T4 can't follow the dome's lower half, so tool reach
substitutes the reachable profile (arc to X.498 Z−.272, a line along the back-edge angle to
X.414 Z−.75, then the back shoulder out to X1.0 at Z−.75 — correct). The finish planner found
its edges by WALKING THE CLOSED finished-part outline for the profile's end points. That
outline is the profile plus the engine's own closure along the operation end (Z−.75) to the
centreline — and the back shoulder lies ON that closure line: the outline folds onto itself
(a zero-width spike) and no edge starts at the profile's last point. This is the owner's
"engine confines vs kernel" case: the engine handed the kernel an outline it can't represent,
then patched around it with hand math.

The kernel already had the right query: `ZoneQueryAPI.profile_offset_edges(profile, d)` builds
the profile's OPEN wire (no closure, no search) — the intermediate finish cuts used it with an
allowance. Understanding tool first: `scripts/hand_math/open_wire_vs_walk.py` compared the walk
with `profile_offset_edges(profile, 0)` on every corpus program: identical edges (type, ends,
centres, radii, arc direction and sweep) on all 16 where the walk works — incl. the ID bores —
and 4 kernel edges for the Hemisphere where the walk fails. (Only straight lines' meaningless
"direction" default differed.)

Change: the final finish pass uses `profile_offset_edges(profile, 0.0)` (one kernel path for all
finish cuts); no try/except, no coordinate fallback — a profile the kernel can't build raises.
Removed as unreachable hand math: `FinishPlanner._moves_from_segments`,
`_moves_from_expanded_coords`, `_find_arc_center`, `_split_edge_at_point`, and cleanup's dead
`_find_arc_center` copy (~320 lines).

Those `_find_arc_center` copies were not just duplicates: they SWAPPED to the other centre when
the arc exceeded its X bounds (cleanup checked the alternative with `not is_cw`, finish with
`is_cw`) — i.e. they could emit a different arc than the pre-planning validator checked. Gone.

Result: the Hemisphere's G-code is byte-identical (the hand math happened to agree there), now
from the kernel. Tests: dome + back-shoulder profile gets kernel finish edges ending on the
shoulder; the "no hidden coordinate fallback" test now asserts the fallback methods are gone.
Hand-math errors 24 → 22.

### F3 — The cleanup "ellipse polyline" was dead code (REMOVED) — and a correction

Added a basic corpus program with quadrant arcs (none existed): "Quadrant Arcs Basic (T4,
staircase / offset)" — a convex Q onto X1.0 and a concave −Q up to X1.5. Expected the cleanup pass
to show 64-segment polylines; it shows clean G02/G03. Reason: the cleanup planner's face-offset
route (`_compute_offset_profile`, with the ellipse polyline and the raw sharp-only offset) and
`_plan_from_zone_boundary` have NO callers — cleanup uses `profile_offset_edges` for OD and ID.

**Correction to the structure-cleanup branch:** in step 4b I moved that dead method's kernel code
into geometry/face_ops.py (`face_from_coords_polyline_quadrants`, `offset_face_sharp_only`)
believing it live. Behaviour-neutral, but it relocated dead code. My step-2 dead-code check
relied on the architecture checker, which does not find methods without callers. A method-level
scan (every engine-package method, zero references anywhere incl. tests/gui) now finds and this
branch removes: those two face_ops functions, `CleanupPlanner._compute_offset_profile` (259 lines)
and `_plan_from_zone_boundary`, `ZoneQueryAPI.line_zone_intersection`,
`ThreadingPlanner.compute_pass_depths`, and three unused `Fiber` helpers. `wire_edges` loses its
`split_arcs` flag (only the canonical split form is used).

### F6 — One arc-centre implementation, checked against the kernel (DONE)

"Arc centre from start, end and signed radius" was implemented five times. After F2 removed the
two planner copies, three remained (pre_planning_validator, arc_helpers, arc_entry; the GUI's
program_tab has a sixth, not touched tonight). Understanding tool first:
`scripts/hand_math/arc_centre_agreement.py` compares each with the kernel's own answer,
build123d `RadiusArc(P0, P1, R).arc_center` (the call the zone builder uses to draw profile
arcs): 1600 random arcs, both signs, near-semicircle to nearly flat → all three agree to
1.4e-12 in. So they were correct copies of one answer.

Change: `radius_arc_centre` moved verbatim to geometry/arc_math.py (owner rule: arc math that
remains lives only there); the validator's `_compute_arc_center` and arc_helpers'
`_select_center` became 2-line adapters ((|R|, is_cw) → signed R). Only difference: a chord
under 1e-10 (validator / arc_helpers) vs 1e-12 (arc_entry) is "no arc" — irrelevant for real
profiles (the validator rejects such segments anyway). Hand-math errors 22 → 20.
Verification: suite 1305 passed; regression 18 SAME; agreement tool still 0 disagreements.

### F4 — A real kernel wall: OCCT sharp-join offsets of concave features (RECOMMENDATION)

`fallback_probe.py`: "GUI Conv Test" (both copies) and "Test Program Tab (T4)" — all
offset-contour roughing — log 29 sharp-join failures per run; kernel_offset falls back to rounded
joins (logged, NOT shown to the operator). `scripts/hand_math/offset_join_probe.py` asks the
kernel directly, sharp joins only, for every roughing distance:

| program | closed finished-part face | open profile wire |
|---|---|---|
| GUI Conv Test / Test Program Tab (concave arc into the back face) | fails at all 39 distances (from .0435) | fails from .2435 (22/39) |
| Quadrant Arcs Basic (offset) (convex Q + concave −Q) | fails from .1435 (35/39) | fails from .1435 (35/39) |
| NX corner-break offset program | all OK | all OK |

So unlike F2 this is not the engine's closure: OCCT's GeomAbs_Intersection offset cannot resolve
large offsets of concave features (the offset curve self-intersects) — the open wire only delays
it. That is a wall in the kernel as used.

What it means at the metal: rounded joins keep EXACTLY the offset distance around convex
corners (the true constant-distance path) instead of extending the corner sharp. For a round-nosed
tool roughing to a finish allowance that is arguably the more correct path, and cut_regions shows
no gouge and nothing left on all three programs.

Recommendations (owner decision — changes roughing geometry on these programs):
1. Make rounded joins the deliberate policy for contour-roughing passes (not an error-path
   fallback); keep sharp joins where corner extension is intended (the keep zone used for
   validation, `zone_builder`).
2. Whenever a sharp-join request is replaced, add a Generate note so the operator knows.
3. If sharp roughing corners are wanted, the robust route is rounded-join offset followed by
   explicit corner extension at convex vertices (a kernel-side post-step), not OCCT's
   intersection join — worth a prototype on its own branch.

### F5 — Zone boundary polylines were up to .118 in off their arcs (FIXED)

`pipeline._extract_zone_boundary` (and its `_optional` twin — two copies, trig in the
orchestration layer) densified boundary arcs using DIAMETER-space start/end/centre with the
RADIUS-space radius and a re-guessed ±π sweep. Basic check: an R.25 quarter arc came out up to
.118 in off the true arc (squashed in X); on real zones, points up to .0206 in off the kernel's
own outline. Consumers: zone shading in the graph adapter (when the parsed-G-code path isn't
used), DXF/SVG debug exports, and — machining-relevant — the G-code writer's comp lead-out,
which tests `Polygon(pr.finished_part_boundary)` to decide whether material lies beyond a
contour end. (cut_regions and the post-planning validator build their own geometry: unaffected.)

Fix: `geometry.zone_query.boundary_polyline(edges)` samples each arc ON the kernel's arc (radius
space, the edge's own signed sweep from `_edge_data_from_wire`, exact end points); both pipeline
functions call it (pipeline has no trig left). Tests (tests/unit/test_boundary_polyline.py, 5):
every finished-part / material-to-rough boundary point of two arc profiles lies on the kernel
outline within 1e-7 (failed before: .0206); an arc sample check to 1e-12.
Verification: suite 1310 passed; regression 18 SAME (no corpus lead-out decision sat near a
distorted arc — the geometry is now right where it would).

Checked and correct (no change): `post_planning_validator._densify_arc_move` — radius space, the
move's own direction ("never the shorter guess"), shared adaptive densifier.

## Where the hand math stands now (inventory after F1–F6)

`scripts/hand_math/inventory.py`: 77 → 67 functions with geometric arithmetic; planners 24 → 5
operations (3 functions); pipeline 16 → 0; checker-flagged 24 → 20. Classified by the question
each answers (owner rule: geometric answers that feed a program come from the kernel; remaining
arc math lives only in geometry/arc_math.py):

| class | where | verdict |
|---|---|---|
| A. not a geometry decision | threading_planner.compute_g76_params (thread depth formula), models/constants (TOLERANCE_SQ), adaptive_sampling (display/validation densifier, exempt by design), pre_output_validator (tolerance checks on emitted arcs), cut_regions._wedge (insert outline from tool-table angles), graph_adapter (display), arc_helpers.format_validation_message | fine |
| B. canonical arc identity | arc_math: wrap, angle_of, Arc.point_at, split_at_quadrants, sweep_piece, merge_co_circular, radius_arc_centre | allowed (owner rule) |
| C1. corner breaks | corner_breaks_od (hand vector algebra: _sub/_add/_unit/_cross/_dot, angles, roll-onto, cliff fillet) + zone_builder.profile_to_radius_coords | **should be kernel**: build123d 0.10 has 2D `fillet` / `chamfer` on sketch vertices. Biggest correctness surface (every zone, every pass starts from these coords). |
| C2. tool reach | tool_reach (tangents, shadow pass, piece geometry, bridges) | **should be kernel**: tangent / intersection queries against the profile wire (bookmark plan: "the biggest part"). |
| C3. writer geometry | gcode_writer: collinear chamfer entry (sin 15°, vector back-off), concave-corner shortening R·tan(turn/2), comp lead-out direction + material probe, _line_intersection, _compute_pass_max_x | **should move**: decisions belong in planners with kernel queries; the writer should only emit. Touches cutter-comp output → owner-reviewed branch. |
| C4. arc picker helpers | arc_entry (quadrant points, candidates, tangent arc, end direction), arc_helpers (min / tangent / bounded radius, X extremum, max Z/X for radius) | these SUGGEST profile geometry the operator accepts; kernel constructs exist (TangentArc, RadiusArc, bounding boxes). Medium priority. |
| C5. G-code check densifier | cut_regions.parse_canon (rs274 ARC_FEED → points with atan2/cos/sin) | low risk: switch to arc_math.Arc.point_at (LinuxCNC's arc, canonical sampling). |
| C6. small leftovers | cleanup._face_level_extension (one sqrt), finish._decompose_curve_edge (arc radius from 3 points; unreachable today), curve_fit | fold into C2/C4 work; curve_fit only matters once splines exist. |

## Walls (kernel limits met tonight)

1. **OCCT sharp-join (GeomAbs_Intersection) offsets of concave features** fail beyond a
   distance, closed face or open wire (F4). Rounded joins work and are the true constant-distance
   path. Recommendation in F4.
2. **Zero-width outline spikes**: when a profile runs along the engine's own closure line, the
   closed finished-part face folds onto itself (F2). Not a kernel bug — the engine asked for an
   unrepresentable shape. Rule of thumb that fixed it: ask the kernel about the OPEN profile wire
   (`profile_offset_edges`) instead of searching a closed face the engine assembled. The zone
   builder's finished-part face still contains the fold for such profiles; the validation polygons
   and the keep zone tolerate it today (no gouge in cut_regions), but it is worth an engine change:
   build the finished part as profile-face ∪ retained stock without a closure that can overlap the
   profile.
3. **Bounding boxes are not exact** (F1): never compare a kernel bounding-box value with an exact
   value without a tolerance, and snap to known vertices when they agree.

## Recommended next steps (owner decides; each on its own branch with the regression corpus)

1. Merge `claude/structure-cleanup`, then this branch (F1, F2, F5 fix real defects; F3/F6 remove
   dead/duplicate math; all behaviour verified on the corpus).
2. F4 policy: rounded joins for contour roughing + an operator note (owner call).
3. C1 corner breaks on kernel fillet/chamfer — first a comparison tool against the NX STEP fixtures
   (tests/fixtures/nx_corner_break/*.stp) and today's coords, like open_wire_vs_walk.py.
4. C3 writer decisions → planners (comp entry / lead-out / concave shortening as planned moves).
5. C2 tool reach on kernel tangents/intersections.
6. Corpus growth: an ID program with arcs and corner breaks; a grooving program; a program with a
   back shoulder at the operation end (the F2 shape) — each found or confirmed a defect tonight.

## Branch summary (claude/hand-math-kernel, from claude/structure-cleanup 9962c59)

| commit | finding |
|---|---|
| 30a8c0d | F1 "wires not planar" on a contour ending at the stock back face (fixed; +4 tests) |
| 8333207 | F2 finish contour kernel-only, hand-math fallback chain removed; F3 dead cleanup offset route + other zero-reference methods removed; +2 quadrant-arc corpus programs |
| c49ff1b | F6 one arc-centre implementation (kernel-checked) |
| d865db5 | F4 OCCT sharp-join wall: probe + recommendation |
| 68c4bdb | F5 zone boundary polylines on the kernel's arcs (fixed; +5 tests) |

Suite 1310 passed (main 1310 → structure branch 1300 → this branch 1310). Regenerated corpus
(23 programs) vs main's baseline: 18 SAME, 4 identical refusals, 1 newly generating program (F1,
machinist-checked). Architecture errors: dependency 4 (main 62), hand math 20 (main 22),
fallback 4. Nothing merged to main.

## F4 follow-up — rounded-join policy implemented (owner approved 2026-11-12, branch claude/f4-rounded-joins)

- `geometry/kernel_offset.py`: `offset_face` / `offset_wire` take `joins="sharp"` (default: sharp, rounded
  fallback) or `joins="rounded"` (Kind.ARC only). Every sharp->rounded fallback inside
  `record_join_fallbacks()` is recorded.
- `planners/contour_roughing_planner.py`: roughing offsets ask for `joins="rounded"`. A kernel failure now
  RAISES (KernelOffsetError) — before, `_do_offset` returned None and the pass loop silently stopped,
  ending roughing early and leaving the rest to the cleanup pass.
- `pipeline/pipeline.py`: `execute()` wraps the run in `record_join_fallbacks()`; any fallback (keep zone,
  cleanup/finish contour) becomes ONE Generate WARNING (category geometry) naming the offsets.
- Tests: `tests/unit/test_offset_join_policy.py` (13). Suite 1323 passed; architecture errors unchanged (28).

Correction to the prediction above ("changes roughing geometry on these programs"): the three programs
that fell back were already rounded at (nearly) every distance, so GUI Conv Test ×2 and Test Program Tab
(T4 derived) come out SAME. What changes is every offset-contour program with convex corners where sharp
joins used to work. Corpus vs main 72eeab4 (scripts/regression, 23 programs):

| program | verdict | rough / cleanup band |
|---|---|---|
| Corner Break Test, Corner Break Test (T4) | MOTION/PART-OK (150 -> 179 motion lines) | rough +1.81e-04 in², cleanup −1.81e-04 |
| NX_ref_breaks_nx / smooth _noV1_V10R2_offset | MOTION/PART-OK (181 -> 211) | rough +8.25e-05, cleanup −8.25e-05 |
| Quadrant Arcs Basic (T4, offset) | MOTION/PART-OK (239 -> 239; mixed sharp/rounded passes now all rounded) | rough +1.79e-04, cleanup −1.79e-04 |
| other 13 generating | SAME | — |
| 5 refusing | BOTH-REFUSE (same message) | — |

Machinist read: finished part identical (max deviation 0), gouge 0, nothing left, on all five. Each roughing
pass now arcs around convex corners at exactly allowance + n·DOC (e.g. NX pass 1: X.7245 at the face, G03
out to X.7262 at Z−.016, instead of a sharp drop at X.7262), so roughing takes the corner material the sharp
extension used to leave and the cleanup pass sees an even DOC. No corpus program triggers the new WARNING
(no keep-zone or cleanup/finish fallback occurs).

## C1 — corner breaks from the kernel (owner approved 2026-11-12, branch claude/c1-corner-breaks)

Probe first (`scripts/hand_math/corner_break_probe.py`):
- NX part, line-line: OCCT 2D fillet / chamfer (BRepFilletAPI_MakeFillet2d, build123d `fillet_2d` /
  `chamfer_2d`) on the sharp outline reproduces NX at 9/10 vertices; V9 (the deliberate "does not fit")
  is refused by OCCT (StdFail_NotDone) — the owner's NX trim rule stays hand-solved for that case.
- Next to arcs the engine used a chord construction: the break's end point was put along the CHORD,
  off the arc, and the operator's arc redrawn through it — centre moved .008 in (.05 fillet) /
  .034 in (.05 chamfer), 29–43° kinks where a fillet should be tangent. Kernel: centre kept, tangent.
- Pitfalls met: OCCT's analytic `ChFi2d_FilletAPI` picked a fillet on the arc's EXTENSION (wrong);
  the topological MakeFillet2d is right. OCCT can also "succeed" with a chamfer longer than its edge
  (it starts past the edge end) — kernel results are checked to start/end on their edges.

Engine (`geometry/corner_breaks_od.py`): every break that fits is built by the kernel on the two
neighbouring edges as the zone builder builds them (new `zone_builder.edge_from_coords`); kernel
refusal → NX trim rules (line-line) or "skipped" with a message (next to an arc). 2000 random
profiles: kernel refusals == NX trims exactly. Trimmed quadrant arcs are emitted as plain arcs of
the same circle. Convex/concave from real tangents. Removed: `_legacy_vertex`, the unreachable
pre-solver code in `profile_to_radius_coords`. hand_math 20 → 19.

Preview (`gui/program_tab.py`): draws `zone_builder.sample_outline` over the solver's coords (the
kernel edges the zone builder machines) per row; its own geometry (chord breaks, arc-centre pick
with a bounds swap, quadrant points; other blocks' arcs as chords; the tool's chord ghost) removed.
Half-typed rows degrade per element (straight guide). `scripts/hand_math/preview_render.py` renders
the preview offscreen and compares two checkouts.

Also: the writer never prints a signed zero (`z.4f`); main printed `-0.0000` in 12 of 19 programs.

Verification: suite 1328 passed. Corpus vs main: with `-0.0000` normalised, all 23 programs
text-identical. Previews of the 23: within .000033 in (sampling). Synthetic quadrant program with
breaks at its arc junctions: main MACHINED a part up to .073 in (radius) off the operator's quadrants
(three of those junctions are tangent — no corner — and are now reported "skipped"); the branch
machines the sharp profile plus exactly the one real break (cut_regions vs a no-break copy:
7.8e-4 in² = ½·.04², deviation .027 = .04·sin45°). No owner program has a break next to an arc.

Still open in C1: NX trim rules next to arcs (cut-short / smooth) — not built; such breaks are
reported "skipped". Vertex labels after an arc split (normalize_profile inserts points, the V numbers
in reports shift) — pre-existing, worth a look with the owner.

## C3 — writer geometry planned before output (owner approved 2026-11-12, branch claude/c3-writer-geometry)

- `planners/comp_contour.py` (new): every cutter-comp decision the writer made for cleanup / finish
  contours — contour start (approach artefacts skipped), comp entry (wall line; OD face / centre entry,
  nose radius + .002 past centre; collinear with a sloped first cut; sliver protection), arc-piece
  re-joining, sharpening concave arcs <= TNR, the comp lead-out, and the concave-corner check — moved
  UNCHANGED. The pipeline plans each pass (`_plan_comp_contours`, starting exactly where the writer
  is) and carries it on `TurningPass.comp_contour` (`models.results.CompContour`). The writer keeps only
  sequencing from its position (rise, rapid, the .020 feed-in) and emission; it refuses a contour
  without a plan.
- Lead-out "material beyond the end?" is a kernel query now (`ZoneQueryAPI.contains`,
  BRepClass_FaceClassifier on the finished-part and stock faces) instead of shapely polygons in the
  writer; the sharpened corner is the kernel's line intersection (`geometry.kernel.line_intersection`,
  IntAna2d). The writer no longer imports geometry or shapely: dependency_violation 4 → 2.
- Verification: corpus TEXT-IDENTICAL to main (19 SAME, 4 BOTH-REFUSE; the two arc-break test
  programs identical too); variants exercised by the corpus: lead-out 1, collinear entry 3, face
  entry 16, plain entry 20, no-TNR 1; sharpened arcs by tests (incl. rs274 runs). Suite passed.
- Kept as is: `check_concave_corners` predicts LinuxCNC's own comp arithmetic (R·tan(turn/2)), not part
  geometry.

OWNER DECISION found here — roughing retract X (`GCodeWriter._compute_pass_max_x`): for an arc move
it adds the circle's top X whenever that is above both end points, but a concave arc piece never
reaches its circle's top. Compared with the exact arc extent (arc_math pieces) over the corpus: 132 of
280 roughing passes over-state, by up to 3.58 in (capped at the safe X); the rule is never LOW. So
today's retracts are higher than needed (safe side). Exact values would shorten those rapids but
bring them closer to material — a clearance judgement, so nothing was changed.
