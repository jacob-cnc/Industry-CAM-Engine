# Industry CAM Engine Agent Guide

This repository controls and generates motion for a physical CNC lathe. Treat
machine safety, traceability, and verified behavior as primary requirements.

## Start Here

Before substantial work, read:

1. `docs/CURRENT_STATE.md`
2. `docs/WORKFLOW.md`
3. `docs/RISK_REGISTER.md`
4. `CLAUDE.md` for detailed machine context
5. `ARCHITECTURE.md` and relevant `.kiro/steering/` files for the area changed
6. The newest relevant file in `session-notes/`

When documents conflict, prefer measured facts in the newest dated session note
and the checked-in machine configuration. Record and resolve the conflict rather
than silently choosing one.

## Evidence and Reference Discipline

Treat existing behavior and external references as evidence, not authority.
Before substantial work, perform a proportional review of relevant project
history, tests, configuration, and `reference/` material. Review depth should
increase with uncertainty, machine impact, and difficulty of rollback.

Do not preserve surprising behavior merely because it exists, and do not replace
it merely because it looks unconventional. Challenge both the current design and
the proposed change, then prefer the explanation best supported by applicable
evidence and focused verification.

Use `reference/INDEX.md` to find relevant material and understand its scope,
version, and limitations. See
`docs/decisions/ADR-002-evidence-reference-and-change-discipline.md` for the
decision policy.

## Critical Machine Facts

- `stepgen.00` drives Z / Joint 1.
- `stepgen.01` drives X / Joint 0.
- Linear encoder `encoder.00` is Z; `encoder.01` is X.
- MPG encoder `encoder.02` is Z; `encoder.03` is X.
- Spindle encoder is `encoder.04`.
- X is diameter in the UI and G-code, but radius in geometry, validation, and
  raw machine coordinates.
- The hardware E-stop input is connected, but the active HAL estop net does not
  currently include `gpio.004`.
- Home, limit, jog, and cycle switches are not yet commissioned.

Never infer hardware mappings from numbering. Verify them against the current
HAL, INI, and latest commissioning notes.

## Architecture Rules

The strict dependency direction is:

`models -> tools -> geometry -> intervals -> planners -> transitions -> validation -> outputs -> pipeline -> gui`

- Build123d/OCCT produces geometric answers.
- Shapely validates safety.
- The G-code writer emits machine instructions.
- Do not add silent fallbacks or parallel geometry implementations.
- Do not perform manual coordinate geometry when a kernel query is required.
- Preserve the separation between LinuxCNC machine control and CAM logic.

See `.kiro/steering/architecture-rules.md`,
`.kiro/steering/coordinate-conventions.md`, and
`.kiro/steering/validation-rules.md`.

## Change Classification

Classify every meaningful change before implementation:

- **Software-only:** Cannot alter physical machine motion or machine state.
- **Motion-affecting:** Can change generated G-code, paths, feeds, rapids,
  coordinates, tool geometry, offsets, validation, or execution behavior.
- **Machine-control:** Changes HAL, INI, LinuxCNC backend behavior, jogging,
  homing, E-stop, spindle synchronization, or physical I/O.

Motion-affecting and machine-control changes require an explicit commissioning
plan and must not be described as machine-verified until tested on the lathe.

## Verification Expectations

Use the smallest relevant verification set, then expand with risk:

- Run focused tests for the changed module.
- Run the full test suite for shared behavior or before merging.
- Run architecture checks for architecture-sensitive changes.
- Compare CAM geometry against NX ground truth when a fixture exists.
- Round-trip generated G-code for motion-affecting changes.
- Record physical-machine observations separately from software test results.

Current standard commands:

```bash
python -m pytest -q
python -m validation.architecture_check
```

If dependencies or commands are unavailable, report that clearly. Do not claim
tests passed based only on older session notes.

## Machine Work Rules

- Never deploy from an ambiguous or dirty worktree.
- Never overwrite `industry-cam.var` or `tool.tbl` without preserving them.
- Preserve tuned INI values or explicitly reconcile them during deployment.
- Use conservative speeds and clear tooling for first powered tests.
- A software E-stop does not replace the physical E-stop.
- Stop and investigate unexpected direction, following error, noise, stall, or
  movement. Do not tune around a mechanical or wiring fault.

## Documentation and Handoffs

Update durable documentation when a change affects:

- Current machine state
- Hardware mapping or wiring
- Coordinate or architecture rules
- Deployment or rollback
- Known risks
- Machine-verified behavior

Use `docs/handoffs/TEMPLATE.md` for substantial sessions. Label conclusions as:

- **Observed:** Directly seen or measured.
- **Verified:** Confirmed by a repeatable test.
- **Inferred:** Supported by evidence but not directly verified.
- **Assumed:** Not yet tested.

## Definition of Done

A work item is complete only when:

1. Acceptance criteria are met.
2. Relevant automated checks pass or unavailable checks are documented.
3. Documentation and handoff notes are updated.
4. Safety impact is stated.
5. Motion-affecting work is explicitly marked either software-verified or
   machine-verified.
