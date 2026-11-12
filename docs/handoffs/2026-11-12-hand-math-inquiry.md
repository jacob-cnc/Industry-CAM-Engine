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
