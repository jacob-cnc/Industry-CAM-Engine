# Arc segments: strategy (2026-11-10, Claude on the lathe PC)

Owner request (verbatim intent): solve arc *segments* (not fillets). Use the NX
STEP parts with every fillet re-entered as its own arc segment. Keep OD and ID
arc handling separate but modular. Single-quadrant arcs first, then
two-quadrant arcs; 3/4-quadrant arcs are out of scope. Be creative; leave the
current system where it causes undue hardship; note critical engine
dependencies; closed contours are acceptable if they make things much easier.

Status: **strategy + evidence + one prototype** (branch `claude/arc-proto`,
not for merge as is). Nothing here changes `main`.

## 1. What the tests showed

Test bed (scratchpad scripts; to become pytest fixtures in Phase 0):
NX OD part and NX ID part walked from `broken.stp` / `id_broken.stp` and
re-entered as LINE + ARC segments (OD: five 90° arcs R1/R3 + the 60° cut-short
arc; ID: three 90° arcs). Plus synthetic two-quadrant cases, OD and ID:
180° bead (bump), 180° full-radius groove, 120° crest.

| Case | main today | Cause |
|---|---|---|
| NX OD/ID arcs as tangent segments | **OK**: finish pass identical to the fillet version; rs274 PROGRAM_END | single-quadrant, tangent, sign entered right |
| Any arc crossing its X extreme (180° bead/groove, 120° crest) entered as ONE segment | refused: "Arc … exceeds X bounds" | pre-planning rule, a guard for the guesses below |
| Same arcs entered as two ≤90° segments | groove/crest/ID OK; **OD bead crashes** ("No Shapely geometry … null") | OCCT merges the halves back into one exact 180° edge; polygon builder takes the "shorter" sweep = undefined at 180° |
| OD groove, cleanup pass | **cuts the wrong way round** (over the top instead of into the groove) | offset of a concave 180° arc is 186°; cleanup planner normalises sweep to ±180° |
| ID bead (bump into the bore) | **rapid through the bead, undetected** (`G00 X0.8900 Z0.0050` passes 0.007" inside it) | finished-part polygon drawn with the 180° arc on the wrong side, so the gouge check is blind |
| Q / -Q quadrant arcs | 4 known failing tests | Q is a 64-segment polyline of a quarter ELLIPSE; same-X or same-Z Q collapses to a straight line |

## 2. Root cause

An arc travels through the engine as **start + end + centre (+ a sign that
means different things in different files), with no sweep**. Every consumer
re-derives the direction: at least 4 copies of "pick the centre" (two swap
to the other centre when the arc leaves its X bounds, i.e. silently make a
major arc), 4 separate `RadiusArc` constructions (one with the sign flipped),
3 different CW/CCW tests (contour roughing's is the negation of finish's),
`EdgeData.direction` hard-coded `"cw"`, and densifiers that always take the
shorter sweep. Docs disagree on the sign in five places. Everything works
only while every arc is < 180° and nobody looks at its sweep.

## 3. Strategy

### Principle A: one arc identity, carried end to end
An arc is `(start, end, centre, ccw)` — or equivalently start / end / any
interior point. Never "endpoints + signed radius". Derived once, from the
geometry kernel or from the operator's explicit choice, and **never
re-guessed**. One module (`geometry/arc_math.py`) owns sweep, split,
densify, tangent and offset helpers; all current copies are deleted.

### Principle B: canonical single-quadrant pieces internally
Every arc edge that leaves the kernel is split at the quadrant boundaries of
its centre (0/90/180/270°). Each piece is ≤ 90° and monotonic in X and Z, so:
the "shorter sweep" guesses in legacy consumers become correct; the X-bounds
refusal becomes unnecessary (it is a symptom); staircase/section logic,
material sim and validators see well-behaved pieces. A two-quadrant arc is
simply two pieces. The writer may merge co-circular pieces back for clean
G-code. **Prototype** (`claude/arc-proto`, `geometry/zone_query.py`): the true
sweep is read from OCCT (start → mid-parameter point → end) at the single
choke point `_edge_data_from_wire`, and arcs are split there. Results:
OD groove cleanup now goes into the groove; the ID bead's rapid-through-part
is now caught; NX parts and saved programs still reach PROGRAM_END in rs274;
toolpaths identical within 0.0003" (4-decimal rounding of the new split
points); GCH bore, Test Run Program, Quarter-20 byte-identical.

### Principle C: the operator picks the arc, the GUI never guesses
Reuse the compound-slide pattern (`hal/compound_logic.py`,
`gui/components/quadrant_graphic.py`): the logic computes the candidate
arcs, the graphic draws them (blue arc, green start, red end) in operator
orientation, the operator clicks one, and the choice is stored explicitly.
Entry modes, all producing the same stored identity:
1. **Tangent to previous** (default; covers every NX fillet-as-arc): enter the
   end point, or the radius; the centre follows from tangency.
2. **Quadrant arc** (replaces Q/-Q): a true circular quarter tangent to both
   axes — R = |ΔX/2| = |ΔZ|, two candidates (convex/concave), picked on the
   graphic. Unequal legs are refused with the nearest valid end point offered
   (no more ellipses; old Q files migrate with a visible warning).
3. **Half round** (two-quadrant): bead or groove between two points on the
   same diameter (or same Z), R = chord/2; pick bump or dip.
4. **End point + radius**: up to 2 candidate centres, both drawn, operator picks.

Saved programs store `{"type": "arc", "x", "z", "cx", "cz", "ccw"}`; the old
signed-radius field is read once at load, converted with today's RadiusArc
semantics, and shown for confirmation.

### Principle D: OD and ID are policies around one core
Shared core: arc identity, quadrant split, tangency, offset. Mode policy
module per side (OD/ID), like the corner-break solver: material side and
convex/concave labels, comp side (G42/G41), which candidates are presented,
tool-reach checks (back side of a bead / groove wall needs clearance angle —
OD and ID differ), and retract routing.

### On closed contours
Not needed to fix arcs: the failures are representation and direction,
not closure. Keep the open profile + implied closure for turning. Closed
contours do pay off for ID pockets/undercuts and DXF (handoffs 2026-11-08
and 2026-09-13); this plan's explicit arc identity is the same contour model
those handoffs need, so it does not block that path.

## 4. Phases (each gated by the NX test bed + rs274 + a regression diff)

0. **Foundation, no visible change.** `arc_math` module; true sweep + quadrant
   split at `_edge_data_from_wire` (prototype); EdgeData carries direction;
   delete centre-guess copies in planners/validators; fix contour-roughing's
   mirrored sign; polygon builder / material sim / post-planning densify use
   the sweep. Test bed becomes pytest (NX OD/ID arc parts + synthetic
   two-quadrant set, OD and ID, rs274 ARC_FEED centre/sweep checks).
1. **Single-quadrant entry.** Stored arc identity + migration; picker graphic;
   tangent-to-previous; circular quadrant arc (fixes the 4 Q tests by
   redefining Q — owner decision needed on same-X "quadrant", which is
   geometrically ill-defined). OD then ID.
2. **Two-quadrant.** Drop the X-bounds refusal; half-round entry; tool-reach
   check for back flanks; retract routing around bumps (shares the fix for the
   ID-undercut retract gouge).
3. **Arcs next to corner breaks.** Exact line-arc / arc-arc fillets in the
   vertex solver (today: legacy chord method, flagged unvalidated).

## 5. Critical dependencies to tailor

`models/profile.py` + JSON format (sign semantics, migration) ·
`pipeline/model_builder.py` · `geometry/zone_builder.py` (RadiusArc is
minor-arc only; Q polylines) · `geometry/zone_query.py`
(`_edge_data_from_wire`: the choke point; OCCT `clean()` re-merges
co-circular edges, so splitting must happen after the kernel) ·
`geometry/arc_helpers.py`, `adaptive_sampling.py` · `planners/finish_planner.py`,
`cleanup_planner.py`, `contour_roughing_planner.py` (mirrored arcs),
staircase via `contour_intersect.py` · `validation/pre_planning_validator.py`
(X-bounds rule), `post_planning_validator.py`, `polygon_builder.py`,
`pre_output_validator.py` · `outputs/gcode_dialect.py`, `gcode_writer.py`
(`_compute_pass_max_x` overestimates for concave arcs; `I-0.0000`),
`gcode_parser.py`, `graph_adapter.py`, `material_sim.py` ·
`transitions/` (retract routing) · `gui/program_tab.py` preview (its own
centre guess, risk R-008), `gui/components/segment_list.py` entry/hints ·
`geometry/corner_breaks_od.py` legacy arc-adjacent path.

## 6. Safety note for main (until Phase 0 lands)

Avoid ID profiles where arcs form a bump into the bore (rapid can pass
through it undetected) and 180° arc pairs in general. Single-quadrant
tangent arcs, as in the NX parts, generate correctly today.

## 7. Status and owner decisions (2026-11-11)

Branch `claude/arc-phase0`. It holds Phase 0 plus the first part of Phase 1, and is
up to date with `main`. Not merged; merging needs the owner's OK.

**Phase 0 is done.** Arcs are read from the kernel with their true sweep, split into
canonical pieces of 90° or less at `_edge_data_from_wire`, and rejoined by the
writer. The prototype became `geometry/arc_math.py` plus the test bed
(`tests/integration/test_arc_phase0.py`). Two tests that encoded the pre-Phase-0
behaviour were corrected:
- The parser round-trip now compares against the writer's rejoined arcs.
- A hand-built material-sim arc labelled CW actually turned CCW in (r, z).

**Owner decisions (2026-11-11):**
1. **Retire ellipses.** Q / -Q is a true quarter circle. The legs must be equal,
   |ΔX|/2 = |ΔZ|. Unequal legs are refused, and the message offers the two nearest
   valid end points. Old programs with unequal-leg Q now show that error instead
   of cutting an ellipse.
2. **An arc that begins and ends at the same X is two quadrants.** The owner's
   example was X1 Z0 → X1 Z-1. The owner allowed either a prompt or an automatic
   split; the split was chosen (it is non-blocking). X is a diameter, so the R .5
   bead peaks at **X2.0** Z-.5, not X1.5. X1.5 would be an ellipse.

**Implemented (Phase 1, part 1)** in `geometry/arc_entry.py`, the single definition:
- **The circular quadrant:** the centre is the bounding-box corner.
  - +Q is centred at (start r, end z). It leaves radially and arrives along Z.
  - -Q is centred at (end r, start z). It leaves along Z and arrives radially.
  - The zone builder draws it as a `ThreePointArc`, so it reaches G-code as real
    G2/G3 moves rather than a polyline.
- **Same-X Q becomes +Q to the apex, then -Q back.** +Q bulges toward the tool:
  on OD that is a bead (larger diameter); on ID it is a bump into the bore.
  -Q is the groove.
- **Same-Z Q is refused.** It has no defined bulge.
- **Radius arcs that pass their own X extreme** are split at that extreme into two
  arcs with the same signed R. This covers every same-X R arc, and it replaces the
  "exceeds X bounds" refusal.
- **Where the split happens:**
  - In the model: `profile_from_fields` and `pipeline.execute`. It is idempotent,
    and the new apex vertex gets no corner break.
  - In the Program tab, on the rows themselves, when the operator leaves the row.
    It never happens mid-typing. The status line says what was split, and the
    tooltip has the details.
- **Preview** draws the true circle; a same-X Q is drawn as its two quadrants.
- **Segment list:**
  - An unequal-leg or same-Z Q shows red, with the fix in the message.
  - The hints offer Q only for a true quarter, and offer "half round" for same-X
    rows.
- **Tests:**
  - `tests/integration/test_arc_entry.py`, including the owner's bead run through
    rs274 with no long-way arcs.
  - The rewritten Q pipeline, preview and bounding-box tests.
  - The 4 long-standing Q failures on main are fixed.

**Known limit (Phase 2):** a part that **ends behind a bead** has nothing after the
bead, and finishes at a smaller diameter than its peak. Its closing rapid back to the
start would run through the bead. The post-planning check **blocks** that program,
so it is caught rather than cut (there is a test for this). A bead followed by a step
up, as on real parts, generates fine. Rapid routing around bumps remains Phase 2.

**Phase 1, part 2 (2026-11-11): entry without the sign convention**
- **Decision: the stored identity stays end point + signed R. There is no
  file-format change.**
  - Principle C proposed storing {cx, cz, ccw}. Since arcs past their own X extreme
    are now split, every entered R arc is at most 180°.
  - For those, the signed R (+R = clockwise in (r, z), with the centre to the right
    of travel) already identifies the arc uniquely, and the engine carries the
    explicit sweep internally from Phase 0.
  - Changing the file format would have cost a migration and a matching change on
    the Codex CAM side, for no difference in the geometry.
  - What actually needed fixing was the operator having to know the sign.
- **Picker graphic:** `gui/components/arc_picker.py`. It sits under the segment
  table and shows whenever a radius-arc row is selected.
  - Both arcs for the end point and |R| are drawn the way the operator sees the
    part: Z+ right, larger Ø down, green start, red end, and a grey stub for the
    incoming direction. The selected arc is solid; the other is dashed.
  - Clicking an arc sets the sign of R.
  - The caption gives R and says convex (outside corner) or concave (inside corner)
    for OD or ID. It adds "smooth with previous" when the selected arc is tangent
    to the previous segment.
- **Tangent entry:** typing `T` in the radius cell replaces it with the signed R of
  the arc that leaves smoothly from the previous segment. That works after a line,
  an R arc or a Q arc (`arc_entry.end_direction`).
  - If no tangent arc exists, the `T` stays and the cell is flagged with the
    reason: the point is straight ahead (that's a line), or the arc would turn more
    than 180°.
- **Core:** `arc_entry.arc_candidates`, `end_direction` and `tangent_arc`. The
  tangent maths was checked on 995 random cases.
- **Tests:** `tests/unit/test_arc_picker_ui.py`.

**Phase 1, part 3 (2026-11-11): tool reach, OD and ID.** `geometry/tool_reach.py`
- **The model.** The insert is the wedge between its front edge F and back edge B.
  These come from the tool table I/J words (insert defaults in
  `pipeline/insert_geometry_lookup.py`) and are measured in the tool's own frame:
  from its feed direction round toward the air.
  - At every tangent of the finished contour (both ends of every line, both ends
    and every quadrant point of every arc, corner breaks included), the wedge must
    sit on the air side. That means rise ≤ F and fall ≤ 180 − B.
  - ID is the same check with X mirrored; a left-hand tool mirrors Z.
  - So a CNMG in a 95° holder (95/175) handles square shoulders but can only follow
    a falling contour for 5°. A neutral VNMG (72.5/107.5) handles both up to 72.5°.
- **ToolDef now carries `front_angle` and `back_angle`** from the tool card. Before
  this they were collapsed into the included angle and lost.
- **Superseded the same day by the owner's decision below (leave it uncut).**
- *(Original behaviour, superseded)* **`pipeline.execute` makes a violation an ERROR** (category `tool_reach`, unused
  until now) for the roughing tool and for a separate finish tool.
  - Tolerance is 1°, because the table holds insert defaults, not measured holders.
  - The check is skipped for tools whose angles are unknown (0/0), and for
    threading and grooving tools.
- **Why ERROR.** On the owner's NX OD part, today's engine runs the CNMG finish pass
  straight down the back face of the collar (X.3937→X.315 at Z-.4724) and down a
  60° falling chamfer, and reports SUCCESS. The insert's back edge would plough
  into the part. None of the existing validators look at the insert's shape.
- **What it reports on the reference programs, using the real `tool.tbl`:**
  - Corner Break Test: 45° falling chamfers, with T4 CNMG.
  - Hemisphere Test and Test Program Tab: 60° and 7.4° falls. These were saved
    with T1, a boring bar, on an OD block, which the mode check refuses anyway.
  - No problems: Bearing Sleeves (ID), GUI Conv Test, Test Cut, Test Run Program.
- **Tests:** `tests/integration/test_tool_reach.py`, 28 tests covering both sides.
  - OD: shoulders, falls of 3–90° for CNMG and VNMG, a left-hand tool, arcs at their
    steepest tangent, and the OD test-bed parts.
  - ID: the mouth chamfer and steps in, a bore opening up, and the ID test-bed parts.
  - Pipeline: blocking, the finish tool, and the skip when angles are unknown.
- **What this means for the owner:** a contour with a face that looks toward the
  chuck (a neck, the back of a collar or bead, a groove's far wall) needs its own
  block with a tool that reaches it: left-hand, neutral, or a grooving tool. The
  engine now says so instead of producing a gouging program. Cutting such a part
  in one program with two tools, each cutting only what it reaches, is future work
  that belongs with Phase 2 retract routing.
**Owner decision 2026-11-11: leave what the insert can't reach UNCUT.** The owner
said to generate G-code for everything the tool can reach, leave the rest uncut,
report where and why, and suggest an insert. Stay minimally invasive. Multi-tool
segment builds that know what is already cut come later; for now the operator cuts
complex features one block at a time.
- **`tool_reach.make_reachable(profile, tool)`** replaces the finished contour with
  the one the insert can follow. Wherever the contour falls more steeply than the
  back clearance, or climbs more steeply than the front edge, the stretch is bridged
  by a straight line at the limit angle.
  - The line runs from the point where the contour first gets steeper than the
    limit (the tangent point on a convex arc) to where it meets the contour again.
  - Climbs are handled by the same pass with Z mirrored and the order reversed.
  - That line is exact: a point is reachable only if the whole wedge placed there
    is in air, so the unreachable material is the part swept along the wedge's edge
    directions.
  - Partial arcs stay arcs (a split quadrant becomes a signed R). Corner breaks are
    baked in.
- **`pipeline.execute`** runs everything (roughing, finish, validation, G-code)
  unchanged on that contour, for the roughing tool and a separate finish tool.
  - Each region becomes a WARNING (category `tool_reach`): "Left uncut: X..–X..,
    Z.. to Z.. – why. The tool follows a straight line from … instead, leaving up
    to … of material."
  - It then suggests inserts from `insert_geometry_lookup`, right- or left-hand.
    First choice is inserts that reach the whole contour. Next is inserts that reach
    just this region (cut it as its own block). If no single insert covers the
    region: "a grooving or form tool, or cut the falling side with …".
  - Anything still out of reach afterwards is an ERROR (a safety net).
  - A contour the tool can fully reach is untouched; it's the same object.
- **The Program tab** lists the warnings in the status notes (hover).
- **The G-code header** gets an `=== UNCUT: THIS TOOL CAN'T REACH ===` section, and
  the PROFILE listing shows the contour actually followed.
- **Results on the test parts:**
  - NX OD part with a CNMG: the neck is bridged at 5° (grooving tool suggested). The
    60° chamfer plus the neck behind it is bridged too (DNMG / VNMG / TNMG
    suggested).
  - Bead: a left-hand 95° tool for the back. Groove with a VNMG: a 95° tool for
    each wall.
  - The owner's Corner Break Test with T4 now generates. It leaves X.25–X.50,
    Z-.495 to Z-.75 uncut and suggests SNMG/TNMG/DNMG for the falling side.
  - Plotted and checked against the finish tool path.
- **Fixed on the way:**
  - The writer's `; WARNING:` comment lines weren't wrapped. A long warning made a
    line over LinuxCNC's 255-character limit, and rs274 refused the whole program.
    Comments are now wrapped at 100 characters, with a test that checks the limit.
  - Three GUI tests created a top-level ProgramTab and never closed it. Garbage
    collection could free it with Qt events still queued, and a later test's
    teardown segfaulted. That depended on timing and memory layout: it never showed
    on main, then showed on this branch with a warm `__pycache__`. Those tests now
    close and delete their tab, and three back-to-back full runs pass.

**Phase 2:** rapid routing around bumps (the end-behind-a-bead case), and reach
checks for the back flank of a bead or a groove wall.
