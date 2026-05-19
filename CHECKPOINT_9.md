# Checkpoint 9 — Encoder Assignment Correction

## Date: 2026-05-18

## Summary
Identified and corrected all five encoder assignments in the HAL files. The hostmot2
driver enumerates 7i85s encoders first (enc 0–3) then the 7i96s onboard encoder last,
so the original mapping had every encoder wrong except X MPG.

## Root Cause
Previous HAL was written assuming:
- encoder.00/01 = linear encoders on 7i85s TB1
- encoder.02 = spindle (7i96s TB2 onboard)
- encoder.03/04 = MPGs on 7i85s TB2/TB3

Physical wiring audit revealed:
- Linear encoders and Z MPG are all on 7i85s TB3 (enc 0, 1, 2)
- X MPG is on 7i85s TB2 (enc 3)
- Spindle is on 7i96s TB2 — enumerated last as encoder.04, not .02

## Corrected Mapping

| HAL Pin    | Physical                  | Role             |
|------------|---------------------------|------------------|
| encoder.00 | 7i85s TB3 enc 0           | Z linear encoder |
| encoder.01 | 7i85s TB3 enc 1           | X linear encoder |
| encoder.02 | 7i85s TB3 enc 2           | Z MPG            |
| encoder.03 | 7i85s TB2 enc 3           | X MPG            |
| encoder.04 | 7i96s TB2 (onboard)       | Spindle          |

## Symptoms This Fixed
- Z axis moving with chuck rotation (spindle counts → mpg-z-counts → joint.1.jog-counts)
- Z MPG doing nothing (Z MPG counts were routed to spindle HAL signals)
- X/Z linear encoder feedback swapped (masked by loose FERROR=0.050" + FF1=1.0)
- X MPG was already correct (encoder.03 unchanged)

## Changes This Session

### `industry-cam.hal` and `industry-cam-commissioning.hal`
- Section 4: encoder.00 scale → [JOINT_1] (Z), encoder.01 scale → [JOINT_0] (X)
- Section 5: X PID feedback → encoder.01.position; Z PID feedback → encoder.00.position
- Section 6: Spindle encoder → encoder.04 (was .02)
- Section 11: Z MPG scale/filter/count → encoder.02 (was .04)
- Header comments updated to reflect true physical wiring

### `CLAUDE.md`
- Corrected stepgen/encoder table
- Updated encoder summary line
- Updated linear encoder and MPG hardware rows

## File Manifest (modified)
- industry-cam.hal
- industry-cam-commissioning.hal
- CLAUDE.md
