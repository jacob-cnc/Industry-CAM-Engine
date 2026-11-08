# ID boring finish contour: artificial closure selected

Classification: motion-affecting. Software-verified for the cases below;
not machine-verified or deployed. Base: 891872e.

## Observed and reproduced

Owner reports difficulty generating an ID operation: stock OD 4.000 inches,
physical thickness 1.000, front face Z0, pilot diameter 2.995, requested bore
diameter 3.117 down to Z-0.568. Exact UI fields, validator message, and tooling
are still pending, so this is not yet a complete reproduction of that rejection.

Using a two-point bore wall, operation Z End -0.568, Z Start 0.050,
DOC 0.020 diameter, finish allowance 0.002 diameter, and a representative
0.008-radius boring tool, the pipeline reports success. However, the finish
pass feeds from the wall at Z0 to X4.000, along the artificial OD closure,
then back to the wall at Z-0.568. Those closure edges are construction geometry,
not the requested bore contour. Boundary validation permits them because they
lie on the finished-part boundary; a successful validation was insufficient.

Setting operation Z End -1.000 while leaving the profile ending at -0.568
instead fails pre-planning validation. Current model_builder shares z_end
between StockDef and ClosedProfile. Physical stock length and operation depth
are therefore conflated. This patch does not change that model or recommend
discarding the physical stock below the operation when assessing safety.

## Correction

OD closure is toward the centerline; ID closure is toward stock OD. The resulting
ID wire traverses the profile in the opposite direction to that assumed by
FinishPlanner._extract_profile_edges. Normalize ID edge traversal before the
existing extraction walk. Preserve OCCT geometry, centers, and raw curve edges.
The extracted finish path then follows the user contour instead of its closure.
No validation assertion, zone construction, approach, retract, or HAL behavior
has been relaxed or changed.

## Verification

- Five new tests fail against the original extraction method and pass with
  the correction. Four cover the owner's dimensions, both staircase and
  offset-contour strategies, and X Start at pilot or finished bore diameter.
- Finish endpoints are X3.117 Z0 and X3.117 Z-0.568; no X4 closure moves.
  Writer output is parsed back and finish feed endpoints checked as well.
- The checked-in stepped_id ground-truth fixture retains its four requested
  contour vertices, without stock-closure vertices.
- Full suite: 301 passed, 6 failed, 2 skipped, 2 xfailed, 2 xpassed. The same
  six quadrant-arc failures existed before this patch.
- Architecture check: 69 errors, 182 warnings, unchanged from baseline.

## Remaining work and commissioning gate

Obtain the owner's exact failing input and validator error. Confirm pilot-hole
depth, actual tool geometry/orientation, roughing parameters, and desired
shoulder treatment before calling the operation correct. The sample tool and
feeds above are reproduction assumptions, not a machine program recommendation.

For eventual machine verification, Claude and the owner must review an exact
commit and generated program, including compensation/lead-in, bar clearance,
depth, shoulder, and entry/exit paths. Preserve machine-local offsets and tool
table. Start with a clear-machine preview and agreed conservative commissioning
limits, then controlled single-block testing with physical E-stop available.
Abort on any unexpected direction, clearance, following error, or motion.
Rollback is to the previously identified machine-tested commit, preserving
machine-local state. No powered test is authorized or claimed by this note.
