# MPG Velocity Mode — Design & Integration Notes — 2026-05-25

## Problem

In incremental/position jog mode (`jog-vel-mode=0`), every MPG count queues a position
increment. If the operator spins faster than the axis can move, commanded position races
ahead. When the wheel stops, the motor keeps moving until it clears the backlog. On Z at
MAX_VEL=0.20 in/s, 100 fast clicks of .001" queues .1" that takes 0.5 seconds to clear.

## Solution

Two position modes (.0002" and .001") stay as incremental. Three new velocity modes
replace the coarse increments (.01"/.1"). In velocity mode (`jog-vel-mode=1`), the axis
velocity is proportional to MPG spin speed. Stopping the wheel stops the axis within the
deceleration ramp (v²/2a at current MAX_VEL=0.20, Z: .002"). Single-click precision is
fully preserved in the two position modes.

## Mode Table

| Index | Label | jog-vel-mode | Scale (X) | Scale (Z) | Note |
|---|---|---|---|---|---|
| 0 | 0.0002" | 0 (pos) | 0.000025 | 0.000025 | One encoder count per detent |
| 1 | 0.001" | 0 (pos) | 0.000125 | 0.000125 | Standard fine jog |
| 2 | Vel Slow | 1 (vel) | 0.000125 | 0.000125 | ~0.1 in/s at moderate spin |
| 3 | Vel Med | 1 (vel) | 0.000375 | 0.000375 | ~0.3 in/s at moderate spin |
| 4 | Vel Fast | 1 (vel) | 0.000750 | 0.000750 | ~0.6 in/s (capped by MAX_VEL) |

Velocity scale math: `velocity = (counts/period) × scale / servo_period`. At moderate
spin (~2 rev/s = 800 counts/s = 1.6 counts/period, servo_period=0.002s):
- Slow: 1.6 × .000125 / .002 = 0.1 in/s
- Med:  1.6 × .000375 / .002 = 0.3 in/s
- Fast: 1.6 × .000750 / .002 = 0.6 in/s (capped by MAX_VEL in practice)

These values are starting points — tune empirically after first test.

## jog-vel-mode Signal Logic

`jog-vel-mode = sel1 OR sel2`

- Position mode (indices 0, 1): sel1=0, sel2=0 → LOW → pos mode
- Velocity mode (indices 2, 3, 4): sel1=1 OR sel2=1 → HIGH → vel mode

One `or2` component feeds both X and Z jog-vel-mode pins.

## Select Bit Encoding

Index = sel0 + 2×sel1 + 4×sel2

| Index | sel2 | sel1 | sel0 |
|---|---|---|---|
| 0 | 0 | 0 | 0 |
| 1 | 0 | 0 | 1 |
| 2 | 0 | 1 | 0 |
| 3 | 0 | 1 | 1 |
| 4 | 1 | 0 | 0 |

---

## Implementation — File by File

### 1. `industry-cam.hal`

**Replace mux4 with mux8, add or2:**

```diff
-loadrt mux4 names=mux4.jogscale-x,mux4.jogscale-z
+loadrt mux8 names=mux8.jogscale-x,mux8.jogscale-z
+loadrt or2  names=or2.jog-vel-mode
```

**Update addf block:**

```diff
-addf mux4.jogscale-x               servo-thread
-addf mux4.jogscale-z               servo-thread
+addf mux8.jogscale-x               servo-thread
+addf mux8.jogscale-z               servo-thread
+addf or2.jog-vel-mode              servo-thread
```

**Replace jog scale setp block (section 11):**

```diff
-setp mux4.jogscale-x.in0  0.000025
-setp mux4.jogscale-x.in1  0.000125
-setp mux4.jogscale-x.in2  0.00125
-setp mux4.jogscale-x.in3  0.0125
-
-setp mux4.jogscale-z.in0  0.000025
-setp mux4.jogscale-z.in1  0.00025
-setp mux4.jogscale-z.in2  0.0025
-setp mux4.jogscale-z.in3  0.025
+# Index 0: 0.0002" position, Index 1: 0.001" position
+# Index 2: Vel Slow, Index 3: Vel Med, Index 4: Vel Fast
+setp mux8.jogscale-x.in0  0.000025
+setp mux8.jogscale-x.in1  0.000125
+setp mux8.jogscale-x.in2  0.000125
+setp mux8.jogscale-x.in3  0.000375
+setp mux8.jogscale-x.in4  0.000750
+setp mux8.jogscale-x.in5  0.000750
+setp mux8.jogscale-x.in6  0.000750
+setp mux8.jogscale-x.in7  0.000750
+
+setp mux8.jogscale-z.in0  0.000025
+setp mux8.jogscale-z.in1  0.000125
+setp mux8.jogscale-z.in2  0.000125
+setp mux8.jogscale-z.in3  0.000375
+setp mux8.jogscale-z.in4  0.000750
+setp mux8.jogscale-z.in5  0.000750
+setp mux8.jogscale-z.in6  0.000750
+setp mux8.jogscale-z.in7  0.000750
```

**Replace MPG connections block:**

```diff
-net mpg-x-counts   hm2_7i96s.0.encoder.03.count  =>  joint.0.jog-counts  axis.x.jog-counts
-net mpg-x-scale    mux4.jogscale-x.out            =>  joint.0.jog-scale   axis.x.jog-scale
-net mpg-z-counts   hm2_7i96s.0.encoder.02.count  =>  joint.1.jog-counts  axis.z.jog-counts
-net mpg-z-scale    mux4.jogscale-z.out            =>  joint.1.jog-scale   axis.z.jog-scale
+net mpg-x-counts   hm2_7i96s.0.encoder.03.count  =>  joint.0.jog-counts  axis.x.jog-counts
+net mpg-x-scale    mux8.jogscale-x.out            =>  joint.0.jog-scale   axis.x.jog-scale
+net mpg-z-counts   hm2_7i96s.0.encoder.02.count  =>  joint.1.jog-counts  axis.z.jog-counts
+net mpg-z-scale    mux8.jogscale-z.out            =>  joint.1.jog-scale   axis.z.jog-scale
```

**Remove static sel0/sel1 setp lines** (these will be driven dynamically from postgui.hal):

```diff
-setp mux4.jogscale-x.sel0  1
-setp mux4.jogscale-x.sel1  0
-setp mux4.jogscale-z.sel0  1
-setp mux4.jogscale-z.sel1  0
```

**Remove static jog-vel-mode setp lines** (now driven by or2):

```diff
-setp joint.0.jog-vel-mode 0
-setp axis.x.jog-vel-mode 0
-setp joint.1.jog-vel-mode 0
-setp axis.z.jog-vel-mode 0
```

---

### 2. `postgui.hal`

**Replace mux4 loads and sel routing:**

```diff
-# --- MPG jog scale (mux4 for increment selection) ---
-# Index 0: 0.0002"  (sel0=0, sel1=0)
-# Index 1: 0.001"   (sel0=1, sel1=0) — default
-# Index 2: 0.01"    (sel0=0, sel1=1)
-# Index 3: 0.1"     (sel0=1, sel1=1)
-net mpg-scale-sel0 compound-slide.mpg-scale-sel0 => mux4.jogscale-x.sel0 mux4.jogscale-z.sel0
-net mpg-scale-sel1 compound-slide.mpg-scale-sel1 => mux4.jogscale-x.sel1 mux4.jogscale-z.sel1
+# --- MPG jog scale (mux8 for increment/velocity selection) ---
+# Index 0: 0.0002" pos  (sel2=0, sel1=0, sel0=0)
+# Index 1: 0.001"  pos  (sel2=0, sel1=0, sel0=1) — default
+# Index 2: Vel Slow     (sel2=0, sel1=1, sel0=0)
+# Index 3: Vel Med      (sel2=0, sel1=1, sel0=1)
+# Index 4: Vel Fast     (sel2=1, sel1=0, sel0=0)
+net mpg-scale-sel0 compound-slide.mpg-scale-sel0 => mux8.jogscale-x.sel0 mux8.jogscale-z.sel0
+net mpg-scale-sel1 compound-slide.mpg-scale-sel1 => mux8.jogscale-x.sel1 mux8.jogscale-z.sel1
+net mpg-scale-sel2 compound-slide.mpg-scale-sel2 => mux8.jogscale-x.sel2 mux8.jogscale-z.sel2
```

**Add jog-vel-mode wiring after the mux8 sel nets:**

```
# --- jog-vel-mode: velocity mode when sel1 OR sel2 is HIGH ---
net mpg-scale-sel1 => or2.jog-vel-mode.in0
net mpg-scale-sel2 => or2.jog-vel-mode.in1
net jog-vel-mode-sig or2.jog-vel-mode.out => joint.0.jog-vel-mode axis.x.jog-vel-mode joint.1.jog-vel-mode axis.z.jog-vel-mode
```

**Update mux2 and mpg count routing** — replace `mux4` references with `mux8`:

No changes needed in the mux2.x-jog / mux2.z-jog block (those reference `mpg-x-counts` /
`mpg-z-counts` nets, not the mux4/mux8 components directly).

---

### 3. `hal/live_backend.py`

In the compound-slide HAL component definition, add `mpg-scale-sel2` pin:

Find the block that creates the compound-slide component pins (look for `mpg-scale-sel0`
and `mpg-scale-sel1` pin creation). Add alongside them:

```python
hal.Pin('mpg-scale-sel2', hal.HAL_BIT, hal.HAL_OUT)
```

In `_connect_scale_select_pins()` (or equivalent), wire sel2 to the HAL net:

```python
hal.connect('compound-slide.mpg-scale-sel2', 'mpg-scale-sel2')
```

---

### 4. `hal/constants.py`

Replace `JOG_INCREMENTS` with a structure that carries the label and mode type:

```python
# Each entry: (label, is_velocity_mode)
JOG_MODES = [
    ("0.0002\"", False),
    ("0.001\"",  False),
    ("Vel Slow", True),
    ("Vel Med",  True),
    ("Vel Fast", True),
]
DEFAULT_JOG_MODE_INDEX = 1  # 0.001" position mode
```

Or keep it as two parallel lists if the GUI iterates them separately. The key constraint:
index must map directly to the mux8 select encoding above.

---

### 5. GUI — Increment/Mode Selector

The jog increment selector widget currently shows 4 options. It needs to show 5, with
visual distinction between position and velocity modes (e.g. separator, color, icon).

The selector must write `sel0`, `sel1`, `sel2` to the compound-slide HAL pins. The
mapping from index to select bits:

```python
SEL_BITS = [
    (0, 0, 0),  # index 0 → sel2=0, sel1=0, sel0=0
    (1, 0, 0),  # index 1 → sel2=0, sel1=0, sel0=1
    (0, 1, 0),  # index 2 → sel2=0, sel1=1, sel0=0
    (1, 1, 0),  # index 3 → sel2=0, sel1=1, sel0=1
    (0, 0, 1),  # index 4 → sel2=1, sel1=0, sel0=0
]
# Usage: sel0, sel1, sel2 = SEL_BITS[index]
```

The GUI should also reflect the current mode visually (e.g. "JOG" vs "VEL" indicator).

---

## Testing Checklist

1. LinuxCNC starts without HAL errors
2. `halcmd show pin joint.0.jog-vel-mode` — verify it is 0 when indices 0/1 selected, 1 when 2/3/4
3. `halcmd show pin or2.jog-vel-mode.out` — same check
4. Position mode .0002": 10 clicks forward/back, verify .0002" per click on indicator
5. Position mode .001": same test, .001" per click
6. Velocity slow: fast MPG spin, stop, verify motor stops within deceleration distance
7. Velocity med/fast: same — confirm no coasting after wheel stops
8. Single-click in velocity mode: confirm axis barely moves (not a fixed increment)
9. Switch between pos and vel modes mid-session: no HAL errors, behavior switches cleanly

## Notes

- `mux8` is a standard LinuxCNC HAL component — no extra loading required
- `or2` is also standard
- In5–In7 of mux8 are set to the Fast velocity scale (in4 value) as safe fallback for
  unused indices — the operator cannot reach them but they should not be zero
- Velocity scale values are initial guesses — tune after first live test
- The compound-slide component's `jog-scale` pin (fed from mux8.out) should still work
  identically for the compound jog feature; only the mode (pos/vel) changes
