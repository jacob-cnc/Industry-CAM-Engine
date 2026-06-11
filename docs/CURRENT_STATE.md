# Current Project State

**Last consolidated:** 2026-06-11
**Repository baseline:** `main` through the reference-governance handoff
**Source:** Checked-in configuration and session notes through 2026-05-26, plus
reference-governance work through 2026-06-11

This document is the concise cross-machine status summary. Update it after
meaningful commissioning, deployment, or architecture changes.

## Status Vocabulary

- **Software-verified:** Confirmed by automated or offline testing.
- **Machine-verified:** Confirmed on the physical lathe.
- **Observed:** Seen or measured once; may need repeatable verification.
- **Unverified:** Designed or implemented but not sufficiently tested.

## System Summary

Industry CAM Engine is a conversational CAM system and LinuxCNC GUI for a
two-axis CNC lathe. It supports offline Windows development and online LinuxCNC
machine control.

The software is organized around:

- Kernel-driven geometry with Build123d/OCCT
- Shapely runtime safety validation
- OD and ID lathe toolpath planning
- G-code generation and visualization
- PyQt5 operator GUI
- Live and mock LinuxCNC backends

## Software Status

| Area | Status | Notes |
|---|---|---|
| OD staircase roughing | Software-verified | Compared against NX ground truth |
| OD contour roughing | Software-verified | Compared against NX ground truth |
| ID staircase roughing | Software-verified | Compared against NX ground truth |
| ID contour roughing | Unverified | Architecture exists; needs ground truth |
| Cleanup and finish passes | Software-verified | OD and ID ground-truth comparisons exist |
| Three validation gates | Implemented | Does not yet model remaining uncut material |
| G-code visualization/playback | Implemented | Material removal visualization disabled |
| Program arc preview | Known defect | Can render the wrong sweep/full circle |
| Manual/Run/Tools/Setup/Help GUI | Implemented | Some documentation still calls Run/Help future |
| Material removal simulation | Shelved | Data exists; GUI rendering was misleading |
| Automated tests | Previously reported passing | Not independently run during this consolidation |
| CI | Not configured | No `.github` workflow currently exists |

## Machine-Verified State

Based on the latest commissioning notes:

- Both axes move under LinuxCNC control.
- X and Z linear encoders provide feedback in the correct direction.
- X and Z MPG handwheels work.
- Spindle encoder reads.
- Physical E-stop input is connected.
- Manual operation is stable with the settled May 26 tuning values.

## Current Machine Configuration

### Mapping

| Function | HAL Mapping |
|---|---|
| Z motor | `stepgen.00`, Joint 1 |
| X motor | `stepgen.01`, Joint 0 |
| Z linear encoder | `encoder.00` |
| X linear encoder | `encoder.01` |
| Z MPG | `encoder.02` |
| X MPG | `encoder.03` |
| Spindle encoder | `encoder.04` |

### Settled Motion Values

| Setting | X / Joint 0 | Z / Joint 1 |
|---|---:|---:|
| Joint max velocity | 1.7 in/s | 1.5 in/s |
| Axis jog max velocity | 1.8 in/s | 0.75 in/s |
| Stepgen max velocity | 1.8 in/s | 2.0 in/s |
| P | 125 | 60 |
| I | 0 | 0 |
| D | 0.002 | 0.005 |
| FF1 | 1.0 | 1.0 |
| FERROR | 0.100 in | 0.200 in |
| MIN_FERROR | 0.050 in | 0.100 in |

The checked-in `industry-cam.ini` is the authoritative detailed configuration.

## Not Yet Commissioned

- Home switches
- Limit switches
- Physical jog buttons
- Cycle Start/Stop buttons
- Hardware E-stop participation in the active HAL estop net
- Threading under load
- Tight Z backlash/FERROR values

## Next Machine Milestone

Validate spindle-synchronized threading with a conservative first test:

- Clear setup and light cut
- 200-300 RPM
- 16 TPI or finer initially
- Confirm encoder index, synchronization, direction, and following error
- Record exact program, material, tool, RPM, result, and observed error

## Immediate Project Priorities

1. Establish the Windows Codex PC development environment: Python, project
   dependencies, architecture checks, and full tests.
2. During the next Linux/Claude session, run
   `docs/prompts/linux-claude-reference-gap-acquisition.md`; keep this queued
   across unrelated intervening sessions.
3. Establish safe, repeatable deployment and rollback.
4. Validate threading on the physical lathe.
5. Add remaining-material rapid validation.
6. Fix Program-tab arc preview.
7. Reconcile stale machine and feature documentation.
8. Add automated CI once a reproducible test environment is defined.

## Reference and Environment Status

- Reference/evidence policy is recorded in
  `docs/decisions/ADR-002-evidence-reference-and-change-discipline.md`.
- `reference/INDEX.md` maps reference authority, scope, limitations, and
  unresolved acquisition gaps.
- Official Mesa 7i96S/7i85S manuals, NISTIR 6556, and a targeted LinuxCNC
  `v2.9.6` source snapshot are checked in.
- The existing broader LinuxCNC snapshot reports `2.10.0~pre1` and must not be
  treated alone as authority for the documented `2.9.6` machine runtime.
- Exact Linux runtime/package, Mesa firmware, motor, scale, spindle-encoder, and
  installed-tooling identities remain queued for the Linux/Claude acquisition
  session.
- Python and project development dependencies are not yet installed/on PATH on
  the Windows Codex PC.
