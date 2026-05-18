---
inclusion: auto
---

# Machining Formulas & Definitions (Sandvik Coromant Reference)

Content rephrased from Sandvik Coromant knowledge base for compliance with licensing restrictions.
Sources:
- [General Turning Formulas](https://www.sandvik.coromant.com/en-us/knowledge/machining-formulas-definitions/general-turning-formulas-definitions)
- [Threading Formulas](https://www.sandvik.coromant.com/en-us/knowledge/machining-formulas-definitions/threading-formulas-definitions)
- [Parting & Grooving Formulas](https://www.sandvik.coromant.com/en-us/knowledge/machining-formulas-definitions/parting-grooving-formulas-definitions)
- [Cutting Tool Parameters (ISO 13399)](https://www.sandvik.coromant.com/en-us/knowledge/machining-formulas-definitions/cutting-tool-parameters)

## General Turning

### Core Formulas

```python
import math

# Cutting speed (surface speed)
def cutting_speed_metric(Dm_mm, n_rpm):
    """vc in m/min from diameter (mm) and spindle speed (rpm)."""
    return (math.pi * Dm_mm * n_rpm) / 1000

def cutting_speed_imperial(Dm_inch, n_rpm):
    """vc in ft/min from diameter (inch) and spindle speed (rpm)."""
    return (math.pi * Dm_inch * n_rpm) / 12

# Spindle speed from cutting speed
def spindle_speed_metric(vc_m_min, Dm_mm):
    """RPM from cutting speed (m/min) and diameter (mm)."""
    return (vc_m_min * 1000) / (math.pi * Dm_mm)

def spindle_speed_imperial(vc_ft_min, Dm_inch):
    """RPM from cutting speed (ft/min) and diameter (inch)."""
    return (vc_ft_min * 12) / (math.pi * Dm_inch)

# Metal removal rate
def mrr_metric(vc_m_min, ap_mm, fn_mm_rev):
    """Q in cm³/min."""
    return vc_m_min * ap_mm * fn_mm_rev

def mrr_imperial(vc_ft_min, ap_inch, fn_inch_rev):
    """Q in inch³/min."""
    return vc_ft_min * 12 * ap_inch * fn_inch_rev

# Net power
def net_power_metric(vc_m_min, ap_mm, fn_mm_rev, kc_N_mm2):
    """Pc in kW."""
    return (vc_m_min * ap_mm * fn_mm_rev * kc_N_mm2) / (60 * 1000000)

def net_power_imperial(vc_ft_min, ap_inch, fn_inch_rev, kc_psi):
    """Pc in HP."""
    return (vc_ft_min * 12 * ap_inch * fn_inch_rev * kc_psi) / 396000

# Machining time
def machining_time(lm_mm, fn_mm_rev, n_rpm):
    """Tc in minutes. lm = machined length."""
    return lm_mm / (fn_mm_rev * n_rpm)
```

### Parameter Definitions

| Symbol | Definition | Metric Unit | Imperial Unit |
|--------|-----------|-------------|--------------|
| Dm | Machined diameter | mm | inch |
| fn | Feed per revolution | mm/rev | inch/rev |
| ap | Cutting depth (DOC) | mm | inch |
| vc | Cutting speed (surface speed) | m/min | ft/min |
| n | Spindle speed | rpm | rpm |
| Pc | Net power | kW | HP |
| Q | Metal removal rate | cm³/min | inch³/min |
| hm | Average chip thickness | mm | inch |
| hex | Maximum chip thickness | mm | inch |
| Tc | Machining time | min | min |
| lm | Machined length | mm | inch |
| kc | Specific cutting force | N/mm² | lbs/in² |
| KAPR | Entering (lead) angle | degrees | degrees |

### Tangential Cutting Force

```python
def tangential_force(ap_mm, fn_mm_rev, kc04, mc=0.29):
    """Ft in Newtons.
    kc04: specific cutting force at fn=0.4 mm/rev (material property)
    mc: constant (0.29 general value)
    """
    kc = kc04 * (0.4 / fn_mm_rev) ** mc  # adjusted kc for actual feed
    return ap_mm * fn_mm_rev * kc

# Simplified (when KAPR >= 75°, sin(KAPR) ≈ 1):
def tangential_force_simplified(ap_mm, fn_mm_rev, kc):
    """Ft in Newtons (simplified for KAPR >= 75°)."""
    return ap_mm * fn_mm_rev * kc
```

### Chip Thickness

```python
def average_chip_thickness(fn_mm_rev, KAPR_deg):
    """hm in mm. KAPR = entering angle."""
    return fn_mm_rev * math.sin(math.radians(KAPR_deg))

def max_chip_thickness(fn_mm_rev, KAPR_deg, RE_mm):
    """hex in mm. RE = corner radius."""
    # For standard turning with nose radius
    if RE_mm > 0:
        return fn_mm_rev * math.sin(math.radians(KAPR_deg))
    return fn_mm_rev * math.sin(math.radians(KAPR_deg))
```

## Threading

### Thread Turning Parameters

| Symbol | Definition | Metric Unit | Imperial Unit |
|--------|-----------|-------------|--------------|
| ap | Infeed (full cutting depth) | mm | inch |
| n | Spindle speed | rpm | rpm |
| vc | Cutting speed | m/min | ft/min |
| nap | Number of passes | — | — |
| P | Pitch | mm | inch (or TPI) |
| β | Thread profile angle | degrees | degrees |
| φ | Lead angle (helix angle) | degrees | degrees |

### Thread Profile Geometry

```python
# Lead angle calculation
def lead_angle(pitch_mm, pitch_diameter_mm, num_starts=1):
    """φ in degrees. Lead = pitch × num_starts."""
    lead = pitch_mm * num_starts
    return math.degrees(math.atan(lead / (math.pi * pitch_diameter_mm)))

# Thread depth (60° V-thread: UN, Metric)
def thread_depth_60(pitch):
    """Full thread depth for 60° threads (UN/Metric)."""
    H = 0.866025 * pitch  # fundamental triangle height
    return (5/8) * H  # = 0.541266 * pitch

# Thread depth (29° ACME)
def thread_depth_acme(pitch):
    """Full thread depth for 29° ACME threads."""
    return pitch / 2  # = 0.5 * pitch

# Thread depth (NPT - truncated)
def thread_depth_npt(pitch):
    """Full thread depth for NPT (truncated 60°)."""
    H = 0.866025 * pitch
    return 0.8 * H  # = 0.692820 * pitch
```

### Infeed Calculation (Constant-Area / Degressive)

```python
def thread_infeed_passes(full_depth, num_passes):
    """Calculate infeed per pass using constant-area (sqrt) progression.
    
    This produces decreasing DOC per pass, maintaining approximately
    constant chip cross-section area (constant cutting force).
    
    Returns list of cumulative depths and per-pass infeeds.
    """
    cumulative = []
    per_pass = []
    for x in range(1, num_passes + 1):
        # Sandvik formula: depth_x = full_depth * sqrt(x / nap)
        depth = full_depth * math.sqrt(x / num_passes)
        cumulative.append(depth)
        if x == 1:
            per_pass.append(depth)
        else:
            per_pass.append(depth - cumulative[x-2])
    return cumulative, per_pass

# Example: M10×1.5, full depth = 0.94mm, 6 passes
# cumulative: [0.23, 0.42, 0.59, 0.73, 0.84, 0.94]
# per_pass:   [0.23, 0.19, 0.17, 0.14, 0.11, 0.10]
```

### Infeed Methods

| Method | Compound Angle | Description | Best For |
|--------|---------------|-------------|----------|
| Radial | 0° | Straight-in, both flanks cut | ACME, short threads, soft materials |
| Flank | 29.5° (60° thread) | One flank cuts, other clears | General purpose, good chip control |
| Modified flank | 30° | Slight clearance on trailing flank | Better finish, reduced rubbing |
| Alternating | ±29.5° | Alternates cutting side each pass | Difficult materials, deep threads |

### Cutting Speed for Threading

Threading cutting speed is typically 25-50% lower than general turning for the same material, due to:
- Full profile engagement (both flanks loaded)
- Chip evacuation constraints in the thread groove
- Tool tip fragility at the thread root

```python
def threading_speed(general_vc, reduction_factor=0.7):
    """Recommended threading vc = 70% of general turning vc (typical)."""
    return general_vc * reduction_factor
```

## Parting and Grooving

### Parameters

| Symbol | Definition | Metric Unit | Imperial Unit |
|--------|-----------|-------------|--------------|
| ap | Cutting depth (groove depth) | mm | inch |
| vc | Cutting speed | m/min | ft/min |
| fn | Feed rate | mm/rev | inch/rev |
| fnx | Radial cutting feed | mm/rev | inch/rev |
| fnz | Axial cutting feed (side turning) | mm/rev | inch/rev |
| n | Spindle speed | rpm | rpm |
| OH | Overhang | mm | inch |
| CDX | Maximum cutting depth | mm | inch |
| CW | Cutting width (insert width) | mm | inch |
| WB | Blade thickness | mm | inch |
| δ | Deflection | mm | inch |

### Cutting Speed for Parting

```python
def parting_speed(Dm_mm, n_rpm):
    """vc at current diameter during parting (decreases toward center)."""
    return (math.pi * Dm_mm * n_rpm) / 1000

# Note: As parting approaches center, Dm decreases.
# If n is constant, vc drops to 0 at center.
# CSS (constant surface speed) mode compensates by increasing RPM.
# Our machine has no VFD — RPM is manual. Parting uses constant RPM.
```

### Tool Deflection

```python
def tool_deflection(Ft_N, OH_mm, E_GPa, I_mm4):
    """δ in mm. Cantilever beam deflection.
    Ft: tangential force (N)
    OH: overhang (mm)
    E: Young's modulus (GPa) — ~210 for steel holders
    I: moment of inertia (mm⁴) — H³×WB/12 for rectangular section
    """
    E_N_mm2 = E_GPa * 1000  # convert GPa to N/mm²
    return (Ft_N * OH_mm**3) / (3 * E_N_mm2 * I_mm4)

def moment_of_inertia_rect(H_mm, WB_mm):
    """I for rectangular cross-section blade."""
    return (H_mm**3 * WB_mm) / 12
```

### Parting Notes for Our Machine

- No VFD = no CSS mode. Parting at constant RPM.
- As diameter decreases, vc drops. Compensate with higher starting RPM.
- Maximum parting diameter limited by tool overhang and deflection.
- Rule of thumb: Ft should not exceed 90% of maximum load for the blade.

## Cutting Tool Parameters (ISO 13399 — Key Subset for Lathe)

### Parameters Relevant to Our ToolDef Dataclass

| ISO 13399 Code | Our ToolDef Field | Definition |
|----------------|-------------------|-----------|
| RE | nose_radius | Corner radius (mm/inch) |
| KAPR | — (derived) | Tool cutting edge angle (entering angle) |
| PSIR | — (derived) | Tool lead angle |
| SIG | tip_angle | Point angle (included angle of insert) |
| L | edge_length | Cutting edge length |
| IC | — | Inscribed circle diameter (insert size) |
| S | — | Insert thickness |
| AN | — | Clearance angle major |
| HAND | direction | Hand of cut (R/L/N) |
| SC | — | Insert shape code (C, D, T, V, W, etc.) |

### Insert Shape Codes (Common for Lathe)

| Code | Shape | Included Angle | Common Use |
|------|-------|---------------|-----------|
| C | Rhombic 80° | 80° | General turning, copying |
| D | Rhombic 55° | 55° | Profiling, finishing (DCMT/DNMG) |
| T | Triangle | 60° | General turning |
| V | Rhombic 35° | 35° | Profiling, tight access |
| W | Trigon 80° | 80° | Heavy turning |
| S | Square | 90° | Facing, 90° shoulders |
| R | Round | 360° | Profiling, heavy roughing |

### Nose Radius (RE) Standard Sizes

| RE (mm) | RE (inch) | Typical Use |
|---------|-----------|-------------|
| 0.2 | 0.008 | Fine finishing, small parts |
| 0.4 | 0.016 | Finishing |
| 0.8 | 0.031 | General purpose |
| 1.2 | 0.047 | Semi-roughing |
| 1.6 | 0.063 | Roughing |
| 2.4 | 0.094 | Heavy roughing |

### Surface Finish vs Nose Radius and Feed

```python
def theoretical_surface_finish_Ra(fn_mm_rev, RE_mm):
    """Theoretical Ra in micrometers (μm).
    Based on the geometric relationship between feed and nose radius.
    Actual Ra will be worse due to BUE, vibration, etc.
    """
    # Ra ≈ fn² / (32 × RE) × 1000 (convert mm to μm)
    return (fn_mm_rev**2 / (32 * RE_mm)) * 1000

def theoretical_surface_finish_Rmax(fn_mm_rev, RE_mm):
    """Theoretical Rmax (peak-to-valley) in micrometers."""
    # Rmax ≈ fn² / (8 × RE) × 1000
    return (fn_mm_rev**2 / (8 * RE_mm)) * 1000

# Example: fn=0.15 mm/rev, RE=0.8mm
# Ra = 0.15² / (32 × 0.8) × 1000 = 0.88 μm
# Rmax = 0.15² / (8 × 0.8) × 1000 = 3.52 μm
```

## Unit Conversions (Our Machine = Inches)

```python
# Our machine operates in inches (G20). These conversions are needed
# when using metric cutting data recommendations.

def mm_to_inch(mm): return mm / 25.4
def inch_to_mm(inch): return inch * 25.4
def m_min_to_ft_min(m_min): return m_min * 3.28084
def ft_min_to_m_min(ft_min): return ft_min / 3.28084
def kw_to_hp(kw): return kw * 1.341
def hp_to_kw(hp): return hp / 1.341
def n_mm2_to_psi(n_mm2): return n_mm2 * 145.038
```

## Application to Our Engine

These formulas are used in the engine for:

1. **Feed rate validation** — verify user-entered feed is reasonable for the tool/material
2. **Cutting speed calculation** — compute RPM from desired vc and current diameter (manual spindle, so this is advisory)
3. **Threading infeed** — calculate pass depths for thread turning operations
4. **Surface finish estimation** — predict Ra from feed and nose radius (quality advisory in Req 16)
5. **Tool deflection** — warn if parting overhang exceeds safe limits
6. **Power estimation** — verify the cut is within machine capability (advisory)

Note: Our machine has a manual spindle (no VFD). RPM is set by the operator. The engine calculates recommended RPM and displays it, but cannot command it. CSS mode is not available.
