---
inclusion: auto
---

# Ground Truth Test Fixtures

These fixtures provide CAD-verified zone geometry and toolpath data for validating the engine's zone construction, pass planning, and boundary computation. Each fixture has a source DXF (drawn by the machinist) and a JSON file with extracted coordinates.

**IMPORTANT:** The `reference/CAD Reference/` directory is actively growing. Always search for new or updated DXF files before making claims about ground truth data. New reference files may have been added since the last checkpoint. Use `list_directory` on the reference folders to discover current files.

## Engine Output DXFs

Engine-generated DXF and G-code outputs are saved to `reference/CAD Reference/Engine Output/`. These are regenerated during development and should be compared against the NX reference DXFs for validation.

| Output | Files |
|--------|-------|
| Stepped OD | `Engine Output/Stepped OD/Stepped_OD.ngc`, `Stepped_OD.dxf` |
| Arc OD Staircase | `Engine Output/Arc OD/Arc_OD_Staircase.ngc`, `Arc_OD_Staircase.dxf` |

## Lessons Learned (Contour Roughing Implementation)

### Contour roughing = cleanup planner in a loop
The cleanup planner already does offset+clip for one pass. Contour roughing is the same operation repeated at DOC intervals. Don't overcomplicate — use the same `b3d_offset` + `BRepAlgoAPI_Common` clip pattern.

### Face offset produces the pass contour directly
Offset the finished part face by increasing amounts, clip to the stock rectangle. The profile-side boundary of the clipped result IS the pass contour at that offset distance. Do NOT try to clip against the MTR zone face (it contains all offsets and always returns the same boundary).

### Single face with concave boundary, not multiple faces
When an arc exceeds stock OD, OCCT's clip produces a single face with a concave boundary — the stock OD edge connects the upper and lower arc sections within one wire. The "split" is a vertical edge at stock OD that's part of the boundary wire, not a separate face.

### Don't over-filter boundary edges
Only filter stock OD edges that span nearly the full Z range (true boundary edges). Partial vertical edges at stock OD are connectors between split arc sections — they are real traversal edges that must be kept.

### Pass ordering: compute inside-out, cut outside-in
Offsets are computed from smallest (closest to profile) to largest (closest to stock). Cutting order is reversed — outermost pass first, working inward. Simple list reversal.

### Circular imports with planner packages
The `planners/__init__.py` imports all planners at package load time. Adding a new planner there can create circular dependencies. Use lazy imports (inside the function) in the pipeline for new planners.


### Cleanup Pass Architecture
- Cleanup pass = Finished Part offset equidistant by fin_allowance, clipped at Z0+fin, Z_end, X_start+fin.
- Use the kernel (Build123d `offset` + `BRepAlgoAPI_Common` clip) — NO hand math for offsets.
- Approach feeds along face at Z0+fin from X_start+fin to offset X, then follows offset contour downward.

### Finish Pass Architecture
- Finish pass traces the exact profile contour (not offset).
- Approach: rapid to (X_start, Z0+fin), feed to (X_start, Z0), then trace all profile segments.
- Arc I/K computed from endpoints and radius using `_find_arc_center`.

### DXF Export Arc Rendering
- DXF arcs always go CCW. For both G02/G03 in lathe ZX plane, use `start_angle=ea, end_angle=sa`.
- Guard against zero I/K — skip arc rendering and fall through to line.

### Key Rules
- NEVER use hand math for geometric offsets — always use the CAD kernel.
- NEVER filter edges with tolerance hacks when a kernel clip operation is available.
- Always check new/updated reference DXF files before making claims about ground truth.
- ALWAYS start from NX ground truth when implementing a new mode or profile type: parse DXFs → extract coordinates → write test → make engine match. Never make up test inputs.
- ID and OD use the same kernel-driven architecture with inverted geometry parameters. Do not create "simpler" fallback paths for ID — they will fail on arcs and tapers.

## Fixture Files

| Fixture | JSON | Source DXF | Zone DXFs | Tests |
|---------|------|-----------|-----------|-------|
| Stepped OD | `tests/ground_truth/stepped_od.json` | `reference/CAD Reference/OD Reference/175932-001_01-Stepped OD.dxf` | (zones in main DXF) | Face zone, multi-level roughing, step transitions, OD closure |
| Stepped ID | `tests/ground_truth/stepped_id.json` | `reference/CAD Reference/ID Reference/175933-001_01-ID Reference DXF.dxf` | Separate zone DXFs in `ID Reference/` | ID mode, pilot hole, bore steps, ID closure to stock OD |
| Arc OD | `tests/ground_truth/arc_od.json` | `reference/CAD Reference/Arc Reference/175934-001_01-Arc Reference.dxf` | Separate zone DXFs in `Arc Reference/` | Arc zone construction, arc offset, variable roughing depth |

## Zone DXF Files (Individual Zones)

### ID Reference (`reference/CAD Reference/ID Reference/`)
| File | Zone |
|------|------|
| `175933-001_01-ID Reference DXF.dxf` | All zones overlaid (profile + stock + roughing boundary) |
| `175933-001_01-ID Reference DXF Finished Part Zone.dxf` | Finished Part boundary only |
| `175933-001_01-ID Reference Finish Allowance Zone.dxf` | Finish Allowance band only |
| `175933-001_01-ID Reference Material to Rough Zone.dxf` | Material to Rough boundary only |
| `175933-001_01-ID Reference DXF w Toolpath.dxf` | All zones + roughing/cleanup toolpath |

### Arc Reference (`reference/CAD Reference/Arc Reference/`)
| File | Zone |
|------|------|
| `175934-001_01-Arc Reference.dxf` | All zones overlaid |
| `175934-001_01-Arc Reference Finished Part.dxf` | Finished Part boundary only |
| `175934-001_01-Arc Reference Finish Allowance Zone.dxf` | Finish Allowance band only |
| `175934-001_01-Arc Reference Material to Rough Zone.dxf` | Material to Rough boundary only |
| `175934-001_01-Arc Reference True Face Zone.dxf` | True Face Zone boundary only |
| `175934-001_01-Arc Reference w Toolpath.dxf` | All zones + roughing/cleanup/offset-contour toolpath |

### OD Reference (`reference/CAD Reference/OD Reference/`)
| File | Zone |
|------|------|
| `175932-001_01-Stepped OD.dxf` | All zones overlaid (profile + stock + roughing boundary) |

## Coordinate Convention (All Fixtures)

- **DXF X axis** = lathe X in RADIUS (not diameter)
- **DXF Y axis** = lathe Z in INCHES
- **Origin** (0, 0) = centerline at Z=0 (finished face position)
- **JSON coordinates** = [x_radius, z_inches] pairs
- **JSON segment x_dia** = diameter (user input convention)

## How to Use in Tests

```python
import json

def load_fixture(name):
    """Load a ground truth fixture for testing."""
    with open(f"tests/ground_truth/{name}.json") as f:
        return json.load(f)

def test_zone_construction_stepped_od():
    fixture = load_fixture("stepped_od")
    
    # Build profile from fixture segments
    segments = [ProfileMove(
        segment_type=SegmentType(s["type"]),
        x=s["x_dia"],
        z=s["z"],
        radius=s.get("radius", 0.0)
    ) for s in fixture["segments"]]
    
    profile = ClosedProfile(segments=segments, mode=MachiningMode.OD, z_end=fixture["parameters"]["z_end"])
    stock = StockDef(diameter=fixture["parameters"]["stock_diameter"], ...)
    
    # Execute zone construction
    zone_set = build_zones(profile, stock, tool, params)
    zone_query = ZoneQueryAPI(zone_set)
    
    # Verify against ground truth coordinates
    expected_profile = fixture["expected_zones"]["profile_boundary"]["coordinates"]
    # ... compare extracted boundary against expected
```

## Fixture Design Principles

1. **Each fixture tests different geometry** — straight steps, bore geometry, arcs
2. **Each fixture has CAD-verified boundaries** — the DXF was drawn by the machinist, not computed by the engine
3. **The engine must produce boundaries matching the DXF** — if they differ, the engine has a bug
4. **Coordinates are in radius** (matching Build123d/Shapely internal convention)
5. **Fixtures are independent of the engine** — they can be used to test any implementation

## Key Differences Between Fixtures

| Aspect | Stepped OD | Stepped ID | Arc OD |
|--------|-----------|-----------|--------|
| Mode | OD | ID | OD |
| Closure direction | To centerline | To stock OD | To centerline |
| Face on finish pass | Yes (X=0 to X=0.250r) | No (plunges directly) | Yes (X=0 to X=0.500r) |
| True Face Zone | Exists (X_start=0 ≠ stock) | Exists (X_start ≠ pilot) | Exists (X_start=0 ≠ stock) |
| Arc segments | None | None | 1 (convex, R=1.000") |
| Roughing boundary offset | 0.001" radius | 0.001" radius | 0.002" radius (note: DXF shows 0.001") |
| Variable roughing depth | No (uniform steps) | No (uniform bore) | Yes (thin near arc peak) |

## DXF Layer Convention

All fixtures use:
- **Layer 1** — geometry entities (LINE, ARC, POINT for reference markers)
- **Layer 61** — origin point (0, 0)

## DXF Coordinate Convention

- All DXF files are in **millimeters** — divide by 25.4 to get inches
- DXF X axis = lathe X in RADIUS
- DXF Y axis = lathe Z in INCHES (after mm→inch conversion)
- Origin (0, 0) = centerline at Z=0 (finished face position)

## Individual Zone DXF Usage

The individual zone DXFs allow direct verification of boolean operations:
- Parse the Material to Rough DXF → extract boundary coordinates
- Compare against engine's `boundary_at_x()` results at various X levels
- If they match, the boolean subtraction (stock - keep_zone) is correct

For the Arc Reference, the Material to Rough zone contains an ARC entity — this verifies that the engine's offset operation correctly produces an arc in the roughing boundary (same center, radius + offset).

## Important Notes

- The Arc OD fixture DXF was built with 0.002" diameter (0.001" radius) finish allowance, but the JSON parameters specify 0.004" diameter (0.002" radius). **Use the DXF coordinates as ground truth** — they represent the actual verified geometry.
- All DXF files are in millimeters. Divide by 25.4 to get inches.
- The POINT entities in the DXFs mark key reference locations (arc centers, transition points, zone corners) for visual verification.
