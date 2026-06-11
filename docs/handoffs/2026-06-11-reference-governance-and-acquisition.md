# Session: 2026-06-11 - Reference Governance and Acquisition

## Workstream

Branch: `main`
Commit: See the commit containing this handoff
Environment: Windows Codex PC, offline from physical lathe
Change classification: Software-only

## Starting State

The repository had a substantial `reference/` library but no central index,
consistent provenance policy, or applicability warnings. Existing governance
required reference review but did not explicitly balance preservation of proven
behavior against creative challenge and momentum.

The Windows workspace initially lacked Python, so project tests and architecture
checks could not run.

## Goal and Acceptance Criteria

- Goal: Establish balanced reference/evidence rules, gather available
  high-priority official references, index the library, and preserve exact next
  steps across machines and intervening sessions.
- Acceptance criteria:
  - Durable decision policy adopted.
  - Official Mesa/NIST and runtime-matched LinuxCNC references gathered.
  - Reference index records authority, scope, limitations, and acquisition gaps.
  - Ready-to-use Linux Claude acquisition prompt created.
  - Windows development-environment setup recorded as the next local task.

## Changes Made

- Added `ADR-002-evidence-reference-and-change-discipline.md`.
- Integrated proportional reference review into `AGENTS.md`, `docs/WORKFLOW.md`,
  and `.kiro/steering/reference-codebases.md`.
- Added `reference/INDEX.md`.
- Added official Mesa 7i96S/7i85S manuals and NISTIR 6556 with source URLs and
  SHA-256 hashes.
- Added a targeted official LinuxCNC `v2.9.6` source snapshot for arcs, G76,
  interpreter checks, motion, and spindle-index behavior.
- Added `docs/prompts/linux-claude-reference-gap-acquisition.md` for the next
  Linux/Claude session.
- Updated `docs/CURRENT_STATE.md` so both queued next tasks survive unrelated
  intervening sessions.

## Evidence and Measurements

- **Observed:** `reference/linuxcnc-source/VERSION` reports `2.10.0~pre1`.
- **Observed:** `CLAUDE.md` documents the lathe runtime as LinuxCNC `2.9.6`.
- **Verified:** Official LinuxCNC tag `v2.9.6` resolves to
  `8ed1eb5c486782137810430b1bc1113a597d4722`.
- **Verified:** The targeted `2.9.6` snapshot contains arc tolerance, G76
  conversion, threading-pass, and spindle-index logic.
- **Verified:** Downloaded Mesa and NIST PDFs have valid PDF headers and hashes
  matching `reference/official-docs/README.md`.
- **Observed:** `reference/Hardware Integration Resources/` contains stale
  encoder mappings and commissioning status that conflict with current
  configuration and newer session notes.
- **Assumed:** The physical lathe still runs the documented LinuxCNC `2.9.6`
  package until verified on the Linux PC.

## Verification Performed

| Check | Result | Notes |
|---|---|---|
| Focused tests | Not run | Documentation/reference-only changes |
| Full tests | Not run | Python unavailable on Windows workspace |
| Architecture checks | Unavailable | Neither `python` nor `py` is installed/on PATH |
| Ground-truth comparison | Not applicable | No CAM behavior changed |
| G-code round-trip | Not applicable | No motion output changed |
| Offline LinuxCNC/mock | Not applicable | No runtime behavior changed |
| Physical machine | Not performed | Windows/offline session |
| `git diff --check` | Passed | No whitespace errors |
| Reference integrity | Passed | PDF headers and manifest hashes verified |

## Safety Impact

No machine behavior, HAL, INI, firmware, G-code generation, or active
machine-state files were changed. The documentation reduces the risk of applying
stale or version-mismatched reference material as current machine truth.

The future Linux acquisition task is evidence-only and explicitly prohibits
firmware flashing or active machine-control changes.

## Deployment and Rollback

Deployment commit: Not applicable; documentation/reference-only work
Preserved machine-state files: Not touched
Rollback location/commit: Parent of the commit containing this handoff

## Decisions

- Accepted
  `docs/decisions/ADR-002-evidence-reference-and-change-discipline.md`.
- Existing behavior and external references are evidence, not authority.
- Reference review must be proportional to risk and uncertainty.
- Reversible experiments are preferred when they answer uncertainty faster.
- Runtime-dependent LinuxCNC decisions should start with the `2.9.6` source
  snapshot until the actual Linux PC runtime identity is captured.

## Known Problems and Risks

- Existing risks in `docs/RISK_REGISTER.md` remain unchanged.
- Exact LinuxCNC runtime/package identity remains unverified on the Linux PC.
- Installed Mesa firmware identity/export remains uncaptured.
- Exact UIRobot UIM8696PM, SINO scale, spindle encoder, and installed tooling
  documentation remains incomplete.
- Python and project development dependencies are absent from the Windows Codex
  PC, preventing automated verification.

## Exact Next Step

On this Windows Codex PC, establish the reproducible project development
environment. Install and verify Python, then install the project dependencies
including Build123d/OCP, Shapely/GEOS, ezdxf, PyQt5, pyqtgraph, NumPy,
Matplotlib, Hypothesis, and pytest. Record exact versions, run
`python -m validation.architecture_check`, run focused smoke checks, then run
`python -m pytest -q`.

Separately, during the next Linux/Claude session, use
`docs/prompts/linux-claude-reference-gap-acquisition.md` to close the remaining
machine-reference gaps. This Linux task remains queued even if unrelated agent
sessions occur first.
