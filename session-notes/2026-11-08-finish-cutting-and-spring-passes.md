# Finish cutting passes, calculated DOC, and spring repeat

Owner-approved behavior: N finish cutting passes remove the finish allowance;
DOC is calculated/read-only; an optional spring pass exactly repeats the final
cut and is not included in N. Classification: motion-affecting. Software-verified
only, not deployed or machine-verified. Base: d8ee085.

## Architecture reviewed before engine edits

ADR-003 records the review and decision. Inspected model ownership, kernel zone
construction/query, cleanup and finish planning, transition planning, the three
validation gates, pipeline assembly, writer, GUI signals and saved block data.

Cleanup already leaves the configured finish allowance, so it remains unchanged.
The former finish planner ignored count/DOC and returned one final trace. The
writer approached only the first pass and concatenated all later cutting moves;
that could not safely support multiple cutting or spring contours.

## Implementation

- FinishingParams carries a positive integer cutting count and separate spring
  flag. Shared scalar calculation is finish allowance / count, in diameter.
  Model builder and pipeline recalculate DOC, ignoring the legacy DOC input.
- Intermediate contours leave allowance * (N-i)/N for i=1..N. Geometry's query
  uses the same open contour construction as the zones, offsets it with OCCT
  on the stock side (OD left / ID right), and extracts ordered kernel edge data.
  There is no manual translation of coordinates or closed stock-boundary cut.
  Failed/disconnected offsets raise; new multi/spring cases require kernel edges.
- The final cutting contour is the exact final profile. A spring pass copies its
  moves, feed and arc data, changing only pass identity/index. It is explicitly
  marked in TurningPass; cutting counts and spring counts are displayed separately.
- The existing transition planner supplies the incoming retract/approach for each
  pass. Pipeline stores these links in TurningPass and validates the assembled
  moves. Writer emits those exact finish-to-finish links and rejects missing links
  or inconsistent counts. No validator tolerance was relaxed.
- Single-cut/no-spring keeps the prior final contour/entry convention. New multi
  or spring cases use consistent entry at stock clearance so the repeated contour
  has the same entry as the final cutting pass.
- DOC is read-only in the GUI, updates with allowance/count, and recalculates on
  block restore/legacy loading. Spring flag now reaches the engine. Fractional or
  nonpositive counts are rejected rather than truncated. Old saved DOC is ignored.
  Saved counts greater than one and saved spring selections now actually execute;
  review those visible settings before regenerating an old program.
- Zero allowance permits one final trace plus optional spring, not multiple claimed
  cutting passes. If distinct contours collapse to identical motion at the selected
  output precision, the writer rejects them instead of silently turning cutting
  passes into extra spring repeats. Reduce count or increase allowance in that case.

## Earlier ID extraction correction discovered during review

The ID reversal in a7a8280 incorrectly called dataclasses.replace on ordinary
EdgeData objects. Its existing exception handler returned None and hid the error
behind the coordinate fallback. The new strict kernel requirement exposed this.
It is corrected with explicit EdgeData construction, and a single-ID regression
forbids the fallback. Multi-cut and spring operation cannot silently use it.
Comparison against d8ee085 confirms unchanged single-contour move/arc values for
representative straight ID and circular OD/ID cases.

## Verification scope

End-to-end tests exercise both roughing strategies, OD/ID straight bores, stepped
ID geometry, circular OD/ID profiles, and single/multiple cuts with/without spring.
They check staged coordinates, exact final/spring move equality, parser round-trip
of emitted cutting moves and links, consistent spring entry, read-only DOC, saved
block restore, invalid counts, and output precision collapse. A deliberately
gouging kernel result is blocked by unchanged Shapely validation. Missing output
links are rejected rather than emitted as a direct return cut.

The six previously failing quadrant-arc cases remain separate. Existing broader
limitations (remaining-stock rapid validation R-001, phase-boundary resets, legacy
single-pass fallback, and other-phase writer/planner duplication) are not repaired
or weakened by this work. No HAL, INI, tool offsets, roughing/cleanup strategy,
or new spindle-speed behavior is introduced.

## Commissioning handoff

Claude should merge/review the exact new commit on its current lathe bench branch;
do not assume older .ngc files contain the feature. Preserve machine-local tool
table and work offsets. With the owner, first verify a one-cut/no-spring baseline,
then preview the 3-cut example with 0.006 diameter allowance and nominal 0.002 DOC.
For the 3.117 bore, expected ID contour diameters are 3.113, 3.115, 3.117, followed
by one more 3.117 trace only when spring is checked. Confirm retract/entry between
every contour, no direct feed return, final depth, active G7 and tool compensation.
Actual tool/bar/stock/pilot clearances must be reviewed before a powered test.

Use owner-approved conservative speed/feed and single-block operation with physical
E-stop available. Stop on unexpected direction, clearance, following error, or
dimensional result. Record exact commit, program, settings and measured outcome.
Rollback to the prior software commit and regenerate the baseline program, while
preserving machine-local offsets. No powered test is claimed by these software checks.

Final verification: 383 passed, the same six existing quadrant-arc failures,
2 skipped, 2 xfailed, 2 xpassed. The 26 new finish cases pass. Architecture check:
69 existing errors, 178 warnings; no new architecture errors. Eight-tab offscreen
mock GUI smoke and git diff --check pass. Representative single-contour ID straight
and OD/ID circular move values match d8ee085 to eight decimal places.
