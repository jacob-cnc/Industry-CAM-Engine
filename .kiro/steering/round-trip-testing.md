---
inclusion: auto
---

# Round-Trip Testing & No-Fallback Enforcement

## The Round-Trip Test Chain

```
USER INPUT (segments, stock params, cutting params)
    │
    ▼
BUILD123D (zone construction — boolean ops on 2D Faces)
    │
    ├─→ Wire extraction (boundary_wire_extraction) → ordered polygon vertices
    │       │
    │       ▼
    │   SHAPELY POLYGONS (zone validation)
    │       │
    │       ▼
    │   VALIDATION #1: "Are the zones geometrically valid?"
    │
    ├─→ Fiber queries (boundary_at_x) → material intervals
    │       │
    │       ▼
    │   PLANNERS → PlanResult (tool_moves[])
    │       │
    │       ├─→ VALIDATION #2: "Do engine moves gouge?" (Shapely, every move)
    │       │
    │       ▼
    │   G-CODE WRITER → G-code text
    │                       │
    │                       ▼
    │                   G-CODE PARSER → List[ToolMove]
    │                       │
    │                       ▼
    │                   VALIDATION #3: "Does G-code gouge?" (Shapely, same polygons)
    │                       │
    │                       ▼
    │                   G-CODE DXF (what machine will execute)
    │
    └─→ ENGINE DXF (what engine computed — zones + toolpath)
```

## Three Validation Checkpoints

| # | Source | Validates Against | Catches |
|---|--------|-------------------|---------|
| 1 | Build123d wire extraction | Shapely is_valid | Bad zone construction, wire extraction bugs |
| 2 | PlanResult.tool_moves[] | Zone Shapely polygons | Planner bugs, transition errors |
| 3 | Parsed G-code moves | Same zone Shapely polygons | Writer bugs, missed rapids, diagonal gouges |

## Two DXF Outputs

| DXF | Derived From | Purpose |
|-----|-------------|---------|
| Engine DXF | Wire extraction (zones) + PlanResult (toolpath) | Verify engine logic |
| G-code DXF | Parsed G-code text | Verify what machine will actually do |

If Engine DXF ≠ G-code DXF → writer added/changed moves (retract/approach). This is EXPECTED.
If G-code DXF has gouges that Engine DXF doesn't → writer introduced a safety violation. This is a BUG.

## Critical Dependency

ALL Shapely validations use polygons from Build123d wire extraction.
If wire extraction is wrong → all validations check against wrong geometry.
Wire extraction MUST be correct. There is NO fallback.

## Ground Truth Validation (Checkpoint 0)

BEFORE the pipeline proceeds past zone construction, the engine's zone boundaries
MUST be validated against ground truth DXFs (when available).

```
Build123d (zone construction) → wire extraction → zone vertices
                                                      │
                                                      ▼
                                              COMPARE against ground truth DXF
                                                      │
                                              ┌───────┴───────┐
                                              │               │
                                          MATCH           MISMATCH
                                              │               │
                                              ▼               ▼
                                      Continue pipeline    STOP. Fix zone_builder.
                                                          Do NOT proceed.
                                                          Do NOT create workaround.
```

### Rules for Ground Truth Comparison

1. IF a ground truth DXF exists for the test profile → comparison is MANDATORY
2. Comparison checks: same vertex count, same vertex coordinates (within TOLERANCE)
3. Extra vertices in engine output = Build123d added geometry (fillets, chamfers at corners) → FIX zone_builder
4. Missing vertices = wire extraction dropped an edge → FIX wire extraction
5. Wrong coordinates = offset computation error → FIX zone_builder offset parameters
6. The pipeline MUST NOT proceed past zone construction if ground truth comparison fails
7. Ground truth DXFs live in `reference/CAD Reference/` organized by part

### What Ground Truth Catches

| Issue | Symptom | Root Cause |
|-------|---------|-----------|
| Fillet corners in offset | Extra vertices with diagonal segments | Build123d offset using Kind.ARC instead of Kind.INTERSECTION |
| Face zone included in MTR | Extra vertices at X=0, Z=0.1 | Boolean subtraction not excluding True Face Zone |
| Z values below Z_end | Vertices at Z < -1.0 | Offset extending beyond stock boundary |
| Negative X values | Vertices at X < 0 | Offset extending past centerline |

## NO-FALLBACK RULE (Absolute)

### What Happened (Anti-Pattern)

During implementation, `boundary_wire_extraction()` returned edges with inconsistent orientation.
Instead of fixing the bug, a hand-math function `_build_display_polygons()` was created as a
"temporary" fallback. This violated:
- Requirement 12 (No Hand Math)
- Requirement 14 (No Fallback Patterns)
- Design Principle P2 (Geometry Kernel as Single Source of Truth)
- Design Principle P3 (One Path, One Implementation)

### The Rule

```python
# FORBIDDEN — silent fallback
try:
    coords = boundary_wire_extraction(zone_name)
except Exception:
    coords = _compute_coords_manually()  # NEVER DO THIS

# FORBIDDEN — parallel implementation
def _build_display_polygons():  # NEVER CREATE THIS
    # Hand math that duplicates what the kernel should provide
    ...

# REQUIRED — raise on failure
coords = boundary_wire_extraction(zone_name)
# If this fails, the pipeline RAISES. No output is produced.
# The developer must FIX the extraction, not work around it.
```

### Enforcement

1. **Runtime**: Wire extraction raises on failure. No try/except wrapping with fallback.
2. **Architecture check**: Detects functions with "fallback", "placeholder", "manual", "hand" in name/comments.
3. **Architecture check**: Detects `+ fin_r`, `+ fin_allowance`, `+ offset` arithmetic on coordinates outside geometry/.
4. **Code review**: Any function that computes zone coordinates must live in geometry/ and use Build123d.

### What To Do When Wire Extraction Fails

1. STOP. Do not create a workaround.
2. Debug the wire extraction (edge orientation, vertex matching).
3. Use ground truth DXFs to verify expected output.
4. Fix the extraction until it produces correct ordered vertices.
5. Only then does the pipeline produce output.

## Single Source of Truth for Zone Coordinates

There is ONE path to get zone polygon coordinates:

```
Build123d Face → boundary_wire_extraction() → ordered (x_dia, z) vertices
```

These vertices feed:
- Shapely polygon construction (validation)
- PyQtGraph display (zone shading)
- DXF export (engine zones)
- PlanResult boundary fields (for graph_adapter)

There is NO second path. No hand math. No "display-only" approximation.
If the extraction is broken, everything downstream is broken — and that's CORRECT.
A broken extraction should be visible and loud, not hidden behind a workaround.
