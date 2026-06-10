# Project Roadmap
into mill control.
This roadmap records ordered outcomes, not a promise about dates. Reorder it when
evidence, machine needs, or safety risks change.

## Milestone 1: Reliable Collaboration and Deployment

**Goal:** Every computer and contributor can identify, deploy, verify, and roll
back an exact project state.

Completion criteria:

- Shared workflow and handoff format adopted
- Deployment packager repaired and tested
- Deployment manifest includes source commit and file hashes
- Machine-state preservation and rollback verified
- First known-good lathe deployment tag created
- Stale critical machine documentation reconciled

## Milestone 2: Threading Commissioning

**Goal:** Validate conservative spindle-synchronized threading on the physical
lathe.

Completion criteria:

- Written commissioning plan reviewed
- Encoder index and synchronization verified
- Light threading test completed at conservative RPM and pitch
- Following error and physical result recorded
- Safe operating envelope documented
- Machine-verified commit tagged

## Milestone 3: Toolpath Safety Floor

**Goal:** Detect motion through remaining uncut material and strengthen confidence
that visualization, plans, and emitted G-code agree.

Completion criteria:

- Remaining-material model designed
- Rapids checked against sequential remaining stock
- Ground-truth and regression fixtures added
- G-code round-trip verification exercised on representative OD/ID profiles
- Program arc preview fixed and tested

## Milestone 4: Machine Commissioning Completion

**Goal:** Move from temporary commissioning operation to a repeatable production
baseline.

Completion criteria:

- Hardware E-stop included and verified in active HAL chain
- Home switches wired and commissioned
- Soft limits and homing requirements enabled
- Z backlash measured and FERROR limits tightened
- Physical jog and cycle controls commissioned as desired
- Updated machine wiring and configuration reference completed

## Milestone 5: Development Infrastructure

**Goal:** Make shared changes easier to verify before they reach a machine.

Completion criteria:

- Reproducible Python environment documented
- CI runs tests and architecture checks
- Ground-truth fixtures are clearly separated from external reference repositories
- Release/checklist process documented
- Documentation drift checks established

## Mill Project Boundary

The Mach-based mill is a separate machine-control project. Reuse should initially
focus on machine-independent concepts such as tool libraries, job models, G-code
inspection, simulation, and validation. LinuxCNC/HAL assumptions must not leak
into mill control.
