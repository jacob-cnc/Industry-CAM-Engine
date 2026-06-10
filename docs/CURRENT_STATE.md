# Current Project State

**Last consolidated:** 2026-06-09
**Repository baseline:** `main` at `4e55d6c`
**Source:** Checked-in configuration and session notes through 2026-05-26

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

1. Establish safe, repeatable deployment and rollback.
2. Validate threading on the physical lathe.
3. Add remaining-material rapid validation.
4. Fix Program-tab arc preview.
5. Reconcile stale machine and feature documentation.
6. Add automated CI once a reproducible test environment is defined.
