# Risk Register

Update this file when a risk is discovered, materially changed, mitigated, or
closed. Evidence and mitigation status should link to commits or session notes.

| ID | Risk | Severity | Status | Current Mitigation / Next Action |
|---|---|---|---|---|
| R-001 | Rapids can pass through remaining uncut material because validation checks finished-part and finish-allowance zones, not sequential remaining stock | High | Open | Design and implement remaining-material validator before trusting complex transitions |
| R-002 | Hardware E-stop input is connected but not included in the active HAL estop net | Critical | Open | Commission the hardware chain with a controlled procedure before normal cutting |
| R-003 | `package_for_linux.py` can clean the flattened repository root | High | Open | Do not run; redesign packager with dedicated output, dry run, manifest, and rollback |
| R-004 | Threading has not been validated on the physical machine | High | Open | Perform conservative spindle-synchronized test and record results |
| R-005 | Home/limit switches are not commissioned and `NO_FORCE_HOMING=1` is active | High | Accepted temporarily | Maintain conservative manual operation; wire and commission switches |
| R-006 | Z `MIN_FERROR` and `FERROR` are intentionally loose because backlash is unmeasured | Medium | Open | Measure backlash with indicator and tighten limits |
| R-007 | X stepgen velocity headroom is constrained by hardware step-rate ceiling | Medium | Monitored | Do not raise X stepgen max velocity; lower joint max if clipping appears |
| R-008 | Program-tab arc preview can display an incorrect long arc/full circle | Medium | Open | Fix preview and add regression tests; do not use preview alone as motion proof |
| R-009 | Machine, README, architecture, and steering documents contain stale/conflicting values | Medium | Open | Reconcile documents against current configuration and dated observations |
| R-010 | No CI currently runs the automated suite on shared changes | Medium | Open | Define reproducible environment and add CI |
| R-011 | Material-removal simulation can visually misrepresent cutting | Medium | Mitigated | Feature remains disabled until renderer is proven accurate |

## Severity Guide

- **Critical:** Could directly defeat a primary safety function or cause
  uncontrolled hazardous motion.
- **High:** Could cause collision, machine damage, unsafe motion, or loss of
  important machine state.
- **Medium:** Could mislead the operator, create incorrect output, or significantly
  slow safe development.
- **Low:** Limited operational impact with straightforward recovery.
