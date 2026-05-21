# Z Axis Commissioning, FERROR Diagnosis, and PID Tuning

## Date: 2026-05-20 (evening session continuation)

Follow-up to `2026-05-20-axis-convention-triple-flip.md`. After both X and Z were brought into lathe convention, the focus shifted to Z's closed-loop behavior under load — first FERROR-on-motion, then PID gain hunting/lag, then motor velocity ceiling.

---

## What was done

### 1. Z sign-convention verification under load
After the Z triple flip (`STEP_SCALE -27093.333`, `ENCODER_SCALE +5080`, jogscale-z positive), MPG direction and DRO direction confirmed correct on single-click jogs. CW MPG → carriage toward tailstock → DRO increments → loop stable, no FERROR on single clicks.

### 2. FERROR-during-motion investigation
Symptom: FERROR trip after ~0.6" of continuous motion. The investigation considered:

- **Sign mismatch** (the X scenario): ruled out — live halcmd snapshot showed `joint.1.motor-pos-cmd` and `motor-pos-fb` tracking each other when stationary, so the loop was sign-stable.
- **STEP_SCALE accuracy**: stepgen.position-fb vs encoder.position showed a suspicious 2:1 ratio (1.302" vs 0.6315") that *looked* like a doubled STEP_SCALE. Set aside pending the physical verification.
- **PID gain too aggressive** for an integrated closed-loop stepper: `P=500/D=0` was the original commissioning value, suspected of causing hunting.

### 3. PID tuning iterations on Z
| P | D | Slow click result | Fast spin (100 clicks) result |
|---|---|---|---|
| 500 | 0 | Hunting / back-and-forth | FERROR after ~0.6" |
| 100 | 0.0001 | Much smoother — clean tracking | FERROR trips earlier than P=500 |
| 200 | 0.001 | Less accurate / worse than P=100 | Still FERROR |
| 100 | 0.0001 (reverted) | Best slow behavior — kept this |

Decision: PID tuning is not the right tool for fast-jog FERROR. The motor is hitting a real velocity/acceleration ceiling that PID can't compensate for.

### 4. STEP_SCALE accuracy verification (carriage measurement test)
Jacob used a dial indicator and stepped through a sweep:
- 0.020" of travel, one slow click at a time → DRO and indicator agreed within a few tenths
- 10 clicks at medium speed → clean
- 20 clicks quick → clean
- 50 clicks quick → clean
- 100 clicks quick → clean
- **100 clicks fast → FERROR**

This conclusively proved STEP_SCALE is correct — `27093.333` matches the physical mechanical ratio. The stepgen.position-fb 2:1 reading earlier was just cumulative integration across multiple moves and not meaningful for this diagnosis.

### 5. Motion-limit reduction (final session state)
Reduced Z's motion limits to find the motor's actual ceiling without PID having to mask it:

| Setting | Was | Now |
|---|---|---|
| `MAX_VELOCITY` | 2.0 in/s | **1.0 in/s** |
| `MAX_ACCELERATION` | 10.0 in/s² | **5.0 in/s²** |
| `STEPGEN_MAXVEL` | 2.5 | **1.5** |
| `STEPGEN_MAXACCEL` | 12.5 | **7.0** |

PID kept at the best-tested values: `P=100, D=0.0001, FF1=1.0`. Not yet tested — Jacob will run the sweep next session.

---

## What went right

- **Triple flip is now a known pattern.** Z's convention fix followed the X recipe and worked on first try. Session note `2026-05-20-axis-convention-triple-flip.md` codified the diagnostic rules so we recognized Z's pattern fast.
- **Live halcmd diagnosis worked well.** Reading `encoder.00.rawcounts` and `count` before/after a known motion gave us hard empirical data on the encoder's count direction, which was the unambiguous tiebreaker when reasoning got stuck.
- **STEP_SCALE physical verification was clean and fast.** A dial indicator + stepping through click counts at increasing speeds isolated the failure regime (only fast spin, only at higher click totals) without needing more sophisticated instrumentation.
- **Conservative incremental tuning.** P=500 → 100 → 200 → 100 isolated the actual problem (motor velocity ceiling) rather than chasing PID in circles.
- **STEP_SCALE confirmed correct.** Pre-existing memory said Z STEP_SCALE = 27093.333, half of X. The physical test confirmed this is correct — Z and X really do have different leadscrew pitches / drive microstepping. No correction needed.

## What went wrong / what to be careful of

- **Initial misinterpretation of stepgen.position-fb.** I read the 2:1 ratio between stepgen.position-fb and encoder.position as evidence of doubled STEP_SCALE. In velocity-mode stepgen, position-fb is a running integral of velocity commands, not directly comparable to encoder for diagnostic purposes. **Lesson: in stepgen velocity mode, compare `joint.N.motor-pos-cmd` to `joint.N.motor-pos-fb`, not `stepgen.position-fb` to anything.**
- **Sign-flip-alone trap on Z (round 1).** Just as on X, attempting to fix DRO direction by flipping `ENCODER_SCALE` alone produced a positive-feedback loop. The diagnostic rule from the earlier session note saved us from chasing this further — went straight to triple flip after the first failed attempt.
- **Brief misobservation between flips.** Right after the first `+5080 → -5080` flip, FERROR appeared "still drifting in same as before" — but live HAL pins showed `f-error = 0` and `motor-pos-cmd ≈ motor-pos-fb`. The "still" observation was stale or from a different velocity regime. Lesson: when symptoms don't match the expected result of a change, **read live HAL pins** before doing more changes.
- **Tuning iterations on the wrong axis of the problem.** Jumping P=100 → 200 spent a cycle chasing PID when the fundamental issue was motor capability. Could have skipped that iteration by first asking "what speed does the motor actually max out at?" instead of "does this PID gain combo work?".

## What we learned

### About the machine
- **Z encoder count direction:** rawcounts **increase** when carriage moves toward tailstock. (Opposite of X — X rawcounts increase toward center.)
- **Z mechanical scale is correct:** STEP_SCALE = 27093.333 steps/inch matches physical motion to within a few tenths over 0.1" sweeps.
- **Z motor has a real velocity ceiling** somewhere below MAX_VELOCITY = 2.0 in/s. Where exactly is TBD — next test sweep will probe it.
- **Z PID with integrated closed-loop steppers wants light gains.** P=100, D=0.0001 with FF1=1.0 carrying the velocity feedforward gives clean tracking on slow/medium moves. P=500 (original commissioning value) was 5× too high.

### Diagnostic rules added
- **In stepgen velocity mode, don't compare `stepgen.position-fb` to encoder.** They have different semantics. Use joint.N.motor-pos-cmd vs motor-pos-fb to compare commanded vs actual.
- **FERROR mode signatures:**
  - Instant trip on first click → sign mismatch in STEP_SCALE × ENCODER_SCALE
  - Drift in proportional to distance → STEP_SCALE accuracy off, *or* motor genuinely can't follow commanded velocity (stepgen saturation)
  - Only at high speed → motor velocity ceiling
  - On direction reversal → mechanical backlash
- **PID tuning rule for integrated closed-loop steppers**: FF1=1.0 does the work. P should be light (50-200 range), D small (0.0001-0.001). I=0. Hunting on slow = P too high. FERROR on fast that doesn't respond to PID = motor limit, not tuning.

### About session workflow
- Update memory immediately when convention-affecting values change. The "X ENCODER_SCALE must be -5080" memory note was stale and almost caused us to revert a correct change. Stale memory is worse than no memory.
- Keep `.claude/` untracked. Local Claude Code session state is not for the repo.

---

## Current Z state (end of session)

```ini
[JOINT_1]
MAX_VELOCITY = 1.0
MAX_ACCELERATION = 5.0
STEPGEN_MAXVEL = 1.5
STEPGEN_MAXACCEL = 7.0
STEP_SCALE = -27093.333
ENCODER_SCALE = 5080
P = 100
I = 0.0
D = 0.0001
FF1 = 1.0
FERROR = 0.500
MIN_FERROR = 0.100
```

```hal
setp mux4.jogscale-z.in0  0.000025
setp mux4.jogscale-z.in1  0.00025
setp mux4.jogscale-z.in2  0.0025
setp mux4.jogscale-z.in3  0.025
```

---

## Next session — Z follow-up

1. **Run the 100-click-fast sweep again** with current settings. Three outcomes possible:
   - Tracks cleanly → motor's ceiling is ≥1.0 in/s; ratchet MAX_VELOCITY up (try 1.5, 1.8) until we find the actual limit.
   - Trips earlier in the sweep → motor's ceiling is below 1.0 in/s; halve again to 0.5 in/s and test.
   - Trips only on the fast spin → it's an acceleration limit, not velocity. Drop MAX_ACCELERATION further (5.0 → 2.5).
2. **Watch live HAL during the failing motion**: `hm2_7i96s.0.stepgen.00.velocity-cmd` and `joint.1.f-error`. If stepgen-velocity-cmd is hitting STEPGEN_MAXVEL = 1.5, motor is saturated. If it's well below, problem is elsewhere (drive, mechanical).
3. **Once Z has a known stable ceiling**, repeat the same tuning approach for X (verify X velocity ceiling, may want to drop X MAX_VELOCITY similarly since we never load-tested it).
4. **Tighten FERROR** from 0.500" → 0.100" or tighter once both axes track cleanly. Loose FERROR has been masking issues.
5. Resume the broader commissioning queue: home switches, limit switches, jog buttons, cycle start/stop (all still NOT wired).

---

## Aside: computer freeze during a Claude session (separate from lathe work)

Investigated a hard freeze that happened ~10 min before this session continuation started. Findings:
- System rebooted at 16:22:45 after a hard freeze that locked Xorg around 16:19:27 (3-minute death spiral with input lag growing 22ms → 3274ms).
- Pattern is classic resource starvation, not kernel oops.
- Could not see kernel ring buffer history without sudo, so the offending userspace process couldn't be pinpointed.
- 16 GB RAM but only 975 MiB swap. Recommendation for next time: bump swap to ~8 GB and set `vm.swappiness=10` so the kernel has somewhere to dump pages instead of grinding the disk. (Deferred — Jacob declined for now.)
- Not a Linux bug, almost certainly userspace overcommit by a desktop process.

This is separate from the lathe config; included for context since it interrupted the session.
