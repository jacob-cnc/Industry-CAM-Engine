---
inclusion: auto
---

# Thread Data Reference — NPT, UN, Metric, ACME

This file contains thread profile formulas, dimension tables, and cutting parameters for all thread standards supported by the engine. Data compiled from public engineering references (Engineers Edge, Machining Doctor, ASME/ISO standard summaries).

Content was rephrased for compliance with licensing restrictions. Sources:
- [Engineers Edge - NPT Thread Data](https://www.engineersedge.com/hardware/taper-pipe-threads.htm)
- [Machining Doctor - Unified Threads](https://www.machiningdoctor.com/charts/unified-inch-threads-charts/)
- [Machining Doctor - ACME Threads](https://www.machiningdoctor.com/threadinfo-acme/?tid=5010)

## Thread Profile Geometry Constants

| Standard | Form Angle | Thread Depth Formula | Crest Flat | Root Flat |
|----------|-----------|---------------------|------------|-----------|
| UN (60° V) | 60° | H = 0.866025 × P; depth = 5/8 × H = 0.541266 × P | P/8 | P/4 |
| NPT (60° V, tapered) | 60° | H = 0.866025 × P; depth = 0.8 × H = 0.692820 × P | 0.033 × P | — |
| Metric ISO (60° V) | 60° | H = 0.866025 × P; depth = 5/8 × H = 0.541266 × P | P/8 | P/4 |
| ACME (29° trap) | 29° | depth = P/2 = 0.5 × P | 0.3707 × P | 0.3707 × P |

## Unified National Threads (UN/UNC/UNF/UNEF)

### Formulas (ASME B1.1)

All dimensions in inches. P = 1/TPI.

```python
# Fundamental triangle height
H = (sqrt(3) / 2) * P  # = 0.866025404 * P

# External thread (bolt)
hs = (5/8) * H          # thread height external
has = (3/8) * H          # thread addendum external  
d2 = d - 2 * has         # pitch diameter (d = major dia)
d1 = d - 2 * hs          # minor diameter
Fcs = P / 8              # crest flat width
Frs = P / 4              # root flat width

# Internal thread (nut)
hn = (5/8) * H           # thread height internal
han = (1/4) * H          # thread addendum internal
D1 = D - 2 * hn          # minor diameter (D = major dia)
D2 = D1 + 2 * han        # pitch diameter
```

### UNC Series — Common Sizes

| Designation | Major Dia (in) | TPI | Pitch (in) | Pitch Dia (in) | Minor Dia (in) |
|-------------|---------------|-----|-----------|----------------|----------------|
| #4-40 UNC | 0.1120 | 40 | 0.0250 | 0.0958 | 0.0893 |
| #6-32 UNC | 0.1380 | 32 | 0.0313 | 0.1177 | 0.1096 |
| #8-32 UNC | 0.1640 | 32 | 0.0313 | 0.1437 | 0.1356 |
| #10-24 UNC | 0.1900 | 24 | 0.0417 | 0.1629 | 0.1521 |
| 1/4-20 UNC | 0.2500 | 20 | 0.0500 | 0.2175 | 0.2045 |
| 5/16-18 UNC | 0.3125 | 18 | 0.0556 | 0.2759 | 0.2614 |
| 3/8-16 UNC | 0.3750 | 16 | 0.0625 | 0.3344 | 0.3181 |
| 7/16-14 UNC | 0.4375 | 14 | 0.0714 | 0.3906 | 0.3720 |
| 1/2-13 UNC | 0.5000 | 13 | 0.0769 | 0.4500 | 0.4300 |
| 9/16-12 UNC | 0.5625 | 12 | 0.0833 | 0.5079 | 0.4862 |
| 5/8-11 UNC | 0.6250 | 11 | 0.0909 | 0.5660 | 0.5423 |
| 3/4-10 UNC | 0.7500 | 10 | 0.1000 | 0.6850 | 0.6590 |
| 7/8-9 UNC | 0.8750 | 9 | 0.1111 | 0.8028 | 0.7739 |
| 1-8 UNC | 1.0000 | 8 | 0.1250 | 0.9188 | 0.8863 |
| 1-1/8-7 UNC | 1.1250 | 7 | 0.1429 | 1.0322 | 0.9950 |
| 1-1/4-7 UNC | 1.2500 | 7 | 0.1429 | 1.1572 | 1.1200 |
| 1-3/8-6 UNC | 1.3750 | 6 | 0.1667 | 1.2667 | 1.2233 |
| 1-1/2-6 UNC | 1.5000 | 6 | 0.1667 | 1.3917 | 1.3483 |
| 1-3/4-5 UNC | 1.7500 | 5 | 0.2000 | 1.6201 | 1.5680 |
| 2-4.5 UNC | 2.0000 | 4.5 | 0.2222 | 1.8557 | 1.7978 |

### UNF Series — Common Sizes

| Designation | Major Dia (in) | TPI | Pitch (in) | Pitch Dia (in) | Minor Dia (in) |
|-------------|---------------|-----|-----------|----------------|----------------|
| #0-80 UNF | 0.0600 | 80 | 0.0125 | 0.0519 | 0.0486 |
| #1-72 UNF | 0.0730 | 72 | 0.0139 | 0.0640 | 0.0604 |
| #2-64 UNF | 0.0860 | 64 | 0.0156 | 0.0759 | 0.0718 |
| #4-48 UNF | 0.1120 | 48 | 0.0208 | 0.0985 | 0.0930 |
| #6-40 UNF | 0.1380 | 40 | 0.0250 | 0.1218 | 0.1153 |
| #8-36 UNF | 0.1640 | 36 | 0.0278 | 0.1460 | 0.1387 |
| #10-32 UNF | 0.1900 | 32 | 0.0313 | 0.1697 | 0.1616 |
| 1/4-28 UNF | 0.2500 | 28 | 0.0357 | 0.2268 | 0.2175 |
| 5/16-24 UNF | 0.3125 | 24 | 0.0417 | 0.2849 | 0.2741 |
| 3/8-24 UNF | 0.3750 | 24 | 0.0417 | 0.3479 | 0.3371 |
| 7/16-20 UNF | 0.4375 | 20 | 0.0500 | 0.4045 | 0.3915 |
| 1/2-20 UNF | 0.5000 | 20 | 0.0500 | 0.4675 | 0.4545 |
| 9/16-18 UNF | 0.5625 | 18 | 0.0556 | 0.5259 | 0.5114 |
| 5/8-18 UNF | 0.6250 | 18 | 0.0556 | 0.5889 | 0.5744 |
| 3/4-16 UNF | 0.7500 | 16 | 0.0625 | 0.7094 | 0.6931 |
| 7/8-14 UNF | 0.8750 | 14 | 0.0714 | 0.8286 | 0.8100 |
| 1-12 UNF | 1.0000 | 12 | 0.0833 | 0.9459 | 0.9242 |
| 1-1/4-12 UNF | 1.2500 | 12 | 0.0833 | 1.1959 | 1.1742 |
| 1-1/2-12 UNF | 1.5000 | 12 | 0.0833 | 1.4459 | 1.4242 |

## NPT — National Pipe Thread (Tapered)

### Key Parameters

- Taper rate: 1/16 (3/4" per foot) = 1°47'24" (1.7899°) half-angle
- Thread form: 60° symmetric V
- Thread depth: H = 0.866025 × P; truncated depth = 0.8 × H
- Standard: ASME B1.20.1

### Formulas

```python
# NPT thread geometry
taper_per_foot = 0.75  # inches per foot
taper_per_inch = 0.0625  # inches per inch (1/16)
half_angle_deg = 1.7899  # degrees

# Thread depth
H = 0.866025 * P
thread_depth = 0.8 * H  # = 0.692820 * P

# Diameter change per unit length (on diameter)
delta_dia_per_inch = 2 * taper_per_inch  # = 0.125" dia change per inch of length

# Pitch diameter at hand-tight plane
# (given in table below for each size)
```

### NPT Dimension Table

| Nominal Size | OD (in) | TPI | Pitch (in) | Pitch Dia E0 (in) | Hand-Tight Length L1 (in) | Effective Length L2 (in) |
|-------------|---------|-----|-----------|-------------------|--------------------------|-------------------------|
| 1/16 | 0.3125 | 27 | 0.03704 | 0.27118 | 0.160 | 0.2611 |
| 1/8 | 0.4050 | 27 | 0.03704 | 0.36351 | 0.1615 | 0.2639 |
| 1/4 | 0.5400 | 18 | 0.05556 | 0.47739 | 0.2278 | 0.4018 |
| 3/8 | 0.6750 | 18 | 0.05556 | 0.61201 | 0.2400 | 0.4078 |
| 1/2 | 0.8400 | 14 | 0.07143 | 0.75843 | 0.3200 | 0.5337 |
| 3/4 | 1.0500 | 14 | 0.07143 | 0.96768 | 0.3390 | 0.5457 |
| 1 | 1.3150 | 11.5 | 0.08696 | 1.21363 | 0.4000 | 0.6828 |
| 1-1/4 | 1.6600 | 11.5 | 0.08696 | 1.55713 | 0.4200 | 0.7068 |
| 1-1/2 | 1.9000 | 11.5 | 0.08696 | 1.79609 | 0.4200 | 0.7235 |
| 2 | 2.3750 | 11.5 | 0.08696 | 2.26902 | 0.4360 | 0.7565 |
| 2-1/2 | 2.8750 | 8 | 0.12500 | 2.71953 | 0.6820 | 1.1375 |
| 3 | 3.5000 | 8 | 0.12500 | 3.34062 | 0.7660 | 1.2000 |
| 4 | 4.5000 | 8 | 0.12500 | 4.33438 | 0.8440 | 1.3000 |

### NPT Threading Notes for CNC

- The taper is on the Z axis (longitudinal) — X changes as Z progresses
- For external NPT: start at major dia, each pass the X start shifts by taper
- X change per Z travel: `delta_x_dia = Z_travel × taper_per_inch × 2` (diameter)
- Thread start diameter = OD at the large end (gauge plane)
- LinuxCNC G76 can handle tapered threads with the `E` word (taper amount)

## ISO Metric Threads (M)

### Formulas (ISO 68-1)

All dimensions in millimeters. Same 60° profile as UN but dimensioned in metric.

```python
# Fundamental triangle height
H = (sqrt(3) / 2) * P  # = 0.866025 * P

# External thread
d2 = d - 0.6495 * P     # pitch diameter
d1 = d - 1.0825 * P     # minor diameter
d3 = d - 1.2269 * P     # minor dia (rounded root)

# Internal thread  
D1 = D - 1.0825 * P     # minor diameter
D2 = D - 0.6495 * P     # pitch diameter

# Thread depth (external)
hs = 0.5413 * P         # = 5/8 * H

# Thread depth (internal)
hn = 0.5413 * P         # = 5/8 * H
```

### Metric Coarse Series — Common Sizes

| Designation | Major Dia (mm) | Pitch (mm) | Pitch Dia (mm) | Minor Dia (mm) |
|-------------|---------------|-----------|----------------|----------------|
| M3 × 0.5 | 3.000 | 0.500 | 2.675 | 2.459 |
| M4 × 0.7 | 4.000 | 0.700 | 3.545 | 3.242 |
| M5 × 0.8 | 5.000 | 0.800 | 4.480 | 4.134 |
| M6 × 1.0 | 6.000 | 1.000 | 5.350 | 4.917 |
| M8 × 1.25 | 8.000 | 1.250 | 7.188 | 6.647 |
| M10 × 1.5 | 10.000 | 1.500 | 9.026 | 8.376 |
| M12 × 1.75 | 12.000 | 1.750 | 10.863 | 10.106 |
| M14 × 2.0 | 14.000 | 2.000 | 12.701 | 11.835 |
| M16 × 2.0 | 16.000 | 2.000 | 14.701 | 13.835 |
| M18 × 2.5 | 18.000 | 2.500 | 16.376 | 15.294 |
| M20 × 2.5 | 20.000 | 2.500 | 18.376 | 17.294 |
| M22 × 2.5 | 22.000 | 2.500 | 20.376 | 19.294 |
| M24 × 3.0 | 24.000 | 3.000 | 22.051 | 20.752 |
| M27 × 3.0 | 27.000 | 3.000 | 25.051 | 23.752 |
| M30 × 3.5 | 30.000 | 3.500 | 27.727 | 26.211 |
| M36 × 4.0 | 36.000 | 4.000 | 33.402 | 31.670 |
| M42 × 4.5 | 42.000 | 4.500 | 39.077 | 37.129 |
| M48 × 5.0 | 48.000 | 5.000 | 44.752 | 42.587 |

### Metric Fine Series — Common Sizes

| Designation | Major Dia (mm) | Pitch (mm) | Pitch Dia (mm) | Minor Dia (mm) |
|-------------|---------------|-----------|----------------|----------------|
| M8 × 1.0 | 8.000 | 1.000 | 7.350 | 6.917 |
| M10 × 1.25 | 10.000 | 1.250 | 9.188 | 8.647 |
| M12 × 1.25 | 12.000 | 1.250 | 11.188 | 10.647 |
| M12 × 1.5 | 12.000 | 1.500 | 11.026 | 10.376 |
| M14 × 1.5 | 14.000 | 1.500 | 13.026 | 12.376 |
| M16 × 1.5 | 16.000 | 1.500 | 15.026 | 14.376 |
| M18 × 1.5 | 18.000 | 1.500 | 17.026 | 16.376 |
| M20 × 1.5 | 20.000 | 1.500 | 19.026 | 18.376 |
| M20 × 2.0 | 20.000 | 2.000 | 18.701 | 17.835 |
| M24 × 2.0 | 24.000 | 2.000 | 22.701 | 21.835 |
| M30 × 2.0 | 30.000 | 2.000 | 28.701 | 27.835 |

### Metric Threading Notes for CNC

- Our machine is inch-based (G20). Metric threads require pitch conversion: `P_inch = P_mm / 25.4`
- LinuxCNC G76 accepts pitch in distance-per-revolution regardless of G20/G21 mode
- Diameter values must be converted: `D_inch = D_mm / 25.4`

## ACME Threads (General Purpose)

### Formulas (ASME B1.5)

All dimensions in inches. P = 1/TPI.

```python
# Thread geometry (29° trapezoidal)
thread_angle = 29  # degrees (total included angle)
half_angle = 14.5  # degrees

# Thread depth
depth = P / 2  # = 0.5 * P

# Flat widths
flat_width = 0.3707 * P  # crest and root flat

# Pitch diameter
d2 = d - depth  # = d - P/2

# Minor diameter
d1 = d - 2 * depth  # = d - P
```

### ACME Dimension Table — Common Sizes

| Designation | Major Dia (in) | TPI | Pitch (in) | Pitch Dia (in) | Minor Dia (in) | Thread Depth (in) | Flat Width (in) |
|-------------|---------------|-----|-----------|----------------|----------------|-------------------|-----------------|
| 1/4-16 ACME | 0.2500 | 16 | 0.0625 | 0.2188 | 0.1875 | 0.03125 | 0.0232 |
| 5/16-14 ACME | 0.3125 | 14 | 0.0714 | 0.2768 | 0.2411 | 0.03571 | 0.0265 |
| 3/8-12 ACME | 0.3750 | 12 | 0.0833 | 0.3333 | 0.2917 | 0.04167 | 0.0309 |
| 1/2-10 ACME | 0.5000 | 10 | 0.1000 | 0.4500 | 0.4000 | 0.05000 | 0.0371 |
| 5/8-8 ACME | 0.6250 | 8 | 0.1250 | 0.5625 | 0.5000 | 0.06250 | 0.0463 |
| 3/4-6 ACME | 0.7500 | 6 | 0.1667 | 0.6667 | 0.5833 | 0.08333 | 0.0618 |
| 7/8-6 ACME | 0.8750 | 6 | 0.1667 | 0.7917 | 0.7083 | 0.08333 | 0.0618 |
| 1-5 ACME | 1.0000 | 5 | 0.2000 | 0.9000 | 0.8000 | 0.10000 | 0.0741 |
| 1-1/4-5 ACME | 1.2500 | 5 | 0.2000 | 1.1500 | 1.0500 | 0.10000 | 0.0741 |
| 1-1/2-4 ACME | 1.5000 | 4 | 0.2500 | 1.3750 | 1.2500 | 0.12500 | 0.0927 |
| 1-3/4-4 ACME | 1.7500 | 4 | 0.2500 | 1.6250 | 1.5000 | 0.12500 | 0.0927 |
| 2-4 ACME | 2.0000 | 4 | 0.2500 | 1.8750 | 1.7500 | 0.12500 | 0.0927 |
| 2-1/2-3 ACME | 2.5000 | 3 | 0.3333 | 2.3333 | 2.1667 | 0.16667 | 0.1236 |
| 3-2 ACME | 3.0000 | 2 | 0.5000 | 2.7500 | 2.5000 | 0.25000 | 0.1854 |
| 3-1/2-2 ACME | 3.5000 | 2 | 0.5000 | 3.2500 | 3.0000 | 0.25000 | 0.1854 |
| 4-2 ACME | 4.0000 | 2 | 0.5000 | 3.7500 | 3.5000 | 0.25000 | 0.1854 |
| 5-2 ACME | 5.0000 | 2 | 0.5000 | 4.7500 | 4.5000 | 0.25000 | 0.1854 |

### ACME Threading Notes for CNC

- ACME uses a 29° included angle (14.5° per side) vs 60° for UN/Metric
- The flat crest and root mean the tool tip is NOT pointed — it has a flat width
- Infeed for ACME is typically straight-in (radial) not flanked, due to the symmetric profile
- Multi-start ACME threads: lead = pitch × number_of_starts
- LinuxCNC G76 handles ACME with the `Q` word (compound slide angle = 0 for straight infeed)

## CNC Threading Parameters (LinuxCNC G76)

### G76 Syntax (LinuxCNC)

```gcode
G76 P[pitch] Z[end_z] I[taper] J[first_pass_depth] K[full_thread_depth] R[degression] L[chamfer] H[spring_passes] E[taper_dist] Q[compound_angle]
```

### Key Parameters for Each Standard

| Parameter | UN/UNF | NPT | Metric | ACME |
|-----------|--------|-----|--------|------|
| P (pitch) | 1/TPI | 1/TPI | P_mm/25.4 | 1/TPI |
| K (full depth) | 0.541266 × P | 0.692820 × P | 0.541266 × P | 0.5 × P |
| Q (compound angle) | 29.5° or 30° | 29.5° or 30° | 29.5° or 30° | 0° (straight) |
| E (taper) | 0 | taper_amount | 0 | 0 |
| H (spring passes) | 1-3 | 1-2 | 1-3 | 1-2 |

### Infeed Strategies

| Strategy | Compound Angle | Best For | Notes |
|----------|---------------|----------|-------|
| Flank infeed | 29.5° (UN/Metric) | General purpose, good chip control | One flank cuts, other rubs |
| Modified flank | 30° | Better finish on trailing flank | Slight clearance on non-cutting side |
| Radial (straight) | 0° | ACME, short threads | Both flanks cut equally |
| Alternating flank | ±29.5° | Difficult materials, deep threads | Alternates cutting side each pass |

### Depth-per-Pass Calculation

```python
# Constant-area infeed (recommended for consistent chip load)
# Each pass removes approximately the same cross-sectional area
def constant_area_passes(full_depth, num_passes):
    """Generate pass depths using constant-area (sqrt) progression."""
    depths = []
    for n in range(1, num_passes + 1):
        depth = full_depth * math.sqrt(n / num_passes)
        depths.append(depth)
    return depths

# Example: 1/2-13 UNC, full depth = 0.0417"
# 6 passes: [0.0170, 0.0241, 0.0295, 0.0341, 0.0381, 0.0417]
```
