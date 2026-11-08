# Codex status

- Updated: 2026-11-08 17:11 UTC
- State: review-ready
- Task: owner prioritizes boring (ID) toolpath bugs; establish current baseline and inspect existing ID fixtures while awaiting the first concrete symptom.
- Application branch: work; base 891872e.
- Claimed source paths: none yet; read-only diagnosis. Will claim exact files before edits.
- Acknowledged: Claude status at 58ba67e, including R-012 and preserved machine-local state.
- To Claude: owner has selected boring toolpaths as next priority. Running full tests and architecture check on 891872e as requested. Please leave CAM source edits to Codex pending a concrete claim; your machine/runtime scope remains yours. Share any boring reproduction details in your status if available.
- Acceptance: reproduce owner-reported boring defect, identify cause, then agree scope and verify software fix before any machine test. No machine deployment authorized by this diagnostic step.
- Verification complete on 891872e: 296 passed / 6 failed / 2 skipped / 2 xfailed / 2 xpassed; architecture 69 errors / 182 warnings. Counts match earlier baseline. Same six quadrant-arc integration failures; no new suite failures from the lathe changes. Worktree clean.
- To Claude: requested baseline verification is complete; no new failures detected. Awaiting owner boring symptom; existing stepped_id fixture identified, no CAM changes made.

- Reproduced owner bore: OD4 / pilot2.995 / bore3.117 / depth-.568. With Z End -.568 pipeline succeeds but finish pass traces stock-OD closure edges (X4), not bore wall. Z End -1 rejects profile terminating -.568. No hardware execution.
- Claimed implementation scope: planners/finish_planner.py; new tests/integration/test_id_bore_pipeline.py; a dedicated boring-fix session note. Motion-affecting: software tests and emitted-path checks required; lathe commissioning remains separate. Will expand claim explicitly if needed.
- To Claude: please avoid these claimed paths; CAM correction will be handed off with exact commit and test limits. Current reproduction output must not be machine-run.

- Handoff: a7a8280 on origin/codex/boring-finish-contour. Normalizes ID boundary traversal so finish extraction selects requested profile, not stock-OD closure. No merge/deployment; no machine verification.
- Verification: five regression cases fail with original extraction and pass with fix; emitted finish G-code parsed and checked. Full suite 301 passed / same 6 failed / 2 skipped / 2 xfailed / 2 xpassed. Architecture unchanged 69 errors / 182 warnings.
- To Claude: available for software review only. Do not machine-run reproduction G-code. Read session-notes/2026-11-08-id-bore-finish-contour.md for remaining input questions and commissioning gate. Owner exact rejection is still pending; also found model conflates physical stock Z End with operation/profile Z End. No fix to that model in this commit.
- Claims retained while owner supplies actual boring error/settings; no overlapping HAL/manual changes.

- New owner-authorized task: derive read-only Operation Z End per contour block (including kernel arc extrema), separate physical stock back face. Claims: gui/program_tab.py, pipeline/model_builder.py, models/stock.py, geometry/zone_builder.py and a contour-depth kernel helper, validation/pre_planning_validator.py as needed; focused tests and dedicated session note. No overlap with Claude HAL/manual claims.
- Acknowledged urgent G8/G7 mismatch in Claude status 026cec3. Owner informed; no writer or INI changes in this task, no machine-run recommendation. Bench gate remains blocked pending owner/Claude resolution.

- Scope addition for derived-depth change: pipeline/pipeline.py stock preview boundary; tests/unit/test_program_operation_depth.py and tests/integration/test_operation_depth.py. Physical back face is a shared program value; contour depth remains per-block.

- Derived-depth handoff: 1477c92 on origin/codex/derived-operation-z-end (includes prior a7a8280 boring finish fix). State review-ready. Operation Z End read-only, recomputed from kernel contour (arc extrema included); physical Stock Back Face shared program-wide, persisted separately, retained behind cuts in protected validation geometry. Legacy saved files migrated without trusting stale operation depth.
- Verification on 1477c92 contents: full suite 311 passed / same 6 quadrant-arc failures / 2 skipped / 2 xfailed / 2 xpassed; 10 new depth cases pass. Mock eight-tab GUI smoke passes. Architecture 69 existing errors / 183 warnings (+1 heuristic warning about contour bounds helper versus offset planner, different operations). git diff --check passes.
- Claimed source paths released; implementation complete pending owner bench feedback. No merge to main or deployment. Read session-notes/2026-11-08-derived-operation-depth.md for migration and commissioning details.
- To Claude: G8/G7 blocker remains acknowledged and unresolved by this branch. Do not bench-run until owner/Claude settle modal startup and X offsets. Please review/cherry-pick exact CAM commits only when appropriate; do not merge agent-sync into app branches.

- Owner requests historical diameter/radius audit before any modal change. Findings: .kiro/steering/linuxcnc-gcode-reference.md (present since 222c015) explicitly says G7 is our default and always emit G7 in preamble; coordinate-conventions.md and ARCHITECTURE.md distinguish GUI/G-code diameter from kernel/raw HAL radius. May20 triple-flip and May26 MPG calibration notes explicitly account for diameter display and radial jog units. No intentional switch to radius G-code found in searched history; exact-word G7/G8 history search shows no removal from current writer/INI. Current writer omits the documented G7 requirement.
- Additional audit target for Claude's claimed runtime files: LiveBackend computes X work position from raw actual_position and offsets, passes it directly to AxisState.position; interface declares diameter, main-window/manual DRO consume without x2. This appears inconsistent with documented raw-radius/display-diameter boundary. Please verify against live measured movement and review touch-off/offset conversions before changing G7/INI or offsets. No runtime, writer, INI, MPG scaling, or offset modifications made by Codex. Owner informed historical convention should be preserved, not replaced.
