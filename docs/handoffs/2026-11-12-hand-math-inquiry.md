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
