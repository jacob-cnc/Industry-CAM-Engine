# Team Workflow

This workflow coordinates development across the NX/Kiro Windows computer, the
Linux lathe controller/Claude environment, and the Windows Codex/CAD/CAM/mill
computer.

## Source of Truth

- GitHub `main` is the shared code and documentation source of truth.
- The physical lathe is the source of truth for measured machine behavior.
- Checked-in configuration is not automatically machine-verified.
- Machine-local changes must be committed or documented before they are treated
  as durable project knowledge.

## Roles

| Environment | Primary Responsibilities |
|---|---|
| NX/Kiro Windows PC | CAD ground truth, CAM comparison, geometry specifications |
| Linux lathe/Claude | Live commissioning, LinuxCNC integration, tuning |
| Windows Codex PC | Integration, architecture review, testing, documentation, releases, mill bridge |

These are defaults, not ownership barriers. Every contributor follows the same
verification and handoff rules.

## Work Item Lifecycle

Every substantial work item moves through:

`Proposed -> Designed -> Implemented -> Software Verified -> Machine Verified -> Complete`

Machine verification is required only for motion-affecting or machine-control
work, but those items are not complete without it.

## Branches and Threads

- Use one focused branch per workstream.
- Use descriptive branch names, such as:
  - `codex/deployment-safety`
  - `claude/threading-commissioning`
  - `kiro/arc-preview`
- Use one focused Codex or Claude thread per workstream.
- Keep a pinned project-coordination thread for status, priorities, and handoffs.
- Archive focused threads after their durable conclusions are recorded.

Do not mix unrelated cleanup into machine-testing or safety-critical branches.

## Starting a Work Session

1. Pull the latest shared branch.
2. Confirm the worktree and branch are expected.
3. Read `AGENTS.md` and `docs/CURRENT_STATE.md`.
4. Read the relevant steering files and newest related session notes.
5. State the goal, acceptance criteria, and change classification.
6. For machine work, state the initial physical condition and test limits.

## Change Classification

| Class | Examples | Required Verification |
|---|---|---|
| Software-only | Documentation, non-motion UI polish | Relevant tests/review |
| Motion-affecting | Planners, transitions, G-code, tool geometry, validation | Tests, ground truth/round-trip, commissioning plan |
| Machine-control | HAL, INI, jogging, homing, E-stop, spindle sync | Offline review plus controlled physical commissioning |

## Verification Ladder

Use the applicable levels in order:

1. Static review and architecture rules
2. Focused automated tests
3. Full automated test suite
4. Ground-truth CAD/NX comparison
5. G-code round-trip and visualization review
6. Offline LinuxCNC/mock verification
7. Powered machine commissioning

Passing a lower level does not imply a higher level passed.

## Decision and Reference Review

Before substantial design or implementation:

1. State the decision, uncertainty, and possible machine impact.
2. Search the relevant current code, tests, Git history, session notes, and
   `reference/INDEX.md`.
3. Check official version-matched material for runtime-dependent behavior.
4. Record meaningful source/version mismatches and unresolved assumptions.
5. Prefer a focused reversible experiment when it can answer the question faster
   than further reading.

Existing behavior is evidence, not proof of correctness. Reference
implementations are guidance, not drop-in authority. Review depth should be
proportional to risk and should not become an open-ended prerequisite for
routine work.

## Machine Commissioning Record

Before powered testing, record:

- Exact commit
- Files/configuration changed
- Expected motion and limits
- Initial machine position and tooling state
- Maximum speed, feed, travel, and RPM allowed
- Abort condition and rollback plan

After testing, record:

- What was observed
- Measurements and raw errors
- Whether the result is repeatable
- Any unexpected behavior
- Final machine-local state
- Exact next step

Use `docs/handoffs/TEMPLATE.md` or a dated `session-notes/` entry.

## Merge Readiness

A branch is ready to merge when:

- Acceptance criteria are met.
- Relevant checks pass or unavailable checks are documented.
- Safety impact is stated.
- Current-state and risk documents are updated when needed.
- Motion-affecting work clearly states software-verified versus machine-verified.
- Deployment and rollback implications are known.

## Release and Known-Good Markers

Tag commits that are confirmed on the physical machine. Suggested format:

```text
lathe-tested-YYYY-MM-DD
lathe-threading-validated-v1
mill-controller-baseline-YYYY-MM-DD
```

The tag message should summarize the tested configuration and link to the
commissioning note.

## Coordination Cadence

At the end of a meaningful session:

1. Commit focused changes.
2. Write or update the handoff.
3. Update `docs/CURRENT_STATE.md` if machine or project status changed.
4. Update `docs/RISK_REGISTER.md` if a risk was created, changed, or closed.
5. Push the branch or known-good main state.
6. Notify the project-coordination thread with the commit and exact next step.
