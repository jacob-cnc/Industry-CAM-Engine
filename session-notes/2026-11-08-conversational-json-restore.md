# Program-tab conversational JSON restore

Owner reports all conversational fields stay default after opening the lathe-local
`GCH Boring Test Ring Bore.json` from Program Open. Exact file is unavailable in
cloud; Claude has been asked through agent-sync to inspect it. Its exact cause
remains unconfirmed. No machine deployment or machine verification performed.

Classification: motion-affecting input restoration (restored settings affect later
G-code generation); no planner, writer, HAL, INI or offsets changed.

Verified defects and changes:

- Version-2 loader always selected first block, including disabled, hidden, empty
  defaults before the real job. Save now records active_block_id; older files
  prefer an enabled visible populated block. Explicit saved selection is honored.
- Profile restore omitted roughing strategy, peck settings and finishing RPM.
  Restore all saved fields and use widget defaults for missing optional fields
  rather than inheriting another block's values. Derived depth/DOC remain derived.
- JSON Open never loaded G-code but retained the previous Program-view code/cache.
  Clear that output and simulation on successful restore, preventing saving stale
  code as the newly opened job's companion .ngc. Generate again for current output.
  Other tabs/controller are not loaded, cleared or commanded by this operation.
- Normalize legacy single-profile files through the same restore implementation;
  validate basic structure before replacing models; block selection signals while
  replacing the list to avoid saving old fields into a colliding new block ID.
  Remove the now-unused duplicate legacy field loader.

Verification: nine focused tests passed (three new plus six existing depth/DOC),
then a fourth new empty/missing-optional-fields regression passed with the other
three. Full suite: 412 passed, same six quadrant-arc failures, two skipped, two
xfail, two xpass (before adding the fourth regression). Architecture remains
58 errors, existing baseline; no architecture layers changed. git diff --check
passes. Tests use a synthetic GCH-shaped file, not the owner's inaccessible file.

Claude commissioning: preserve original local JSON and companion code; inspect
its schema and block list first. Integrate the handoff on the bench branch, open
that exact JSON from Program Open, check selected block, OD4/pilot2.995/backZ-1,
segments to X3.117 Z-.568 and back to X2.995, and all saved feeds/tools/strategy/
peck/RPM/pass/spring settings against file. Confirm derived depth/DOC and regenerate
before reviewing code. Opening must not command machine state/motion. Compare
regenerated output before any separate owner-controlled run. Report whether this
explains the owner's file or whether further diagnosis is needed. Rollback: revert
this commit; active_block_id is optional metadata ignored by old readers.
