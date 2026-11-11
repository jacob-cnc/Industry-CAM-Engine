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
