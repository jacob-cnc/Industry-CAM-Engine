# Ground Truth Notes — NX CAD Reference DXFs

## Stepped OD (175932-001_01)

**Profile:** X0→X0.5 at Z=0, step to X1.0 at Z=-0.5, continue to Z=-1.0
**Stock:** 1.25 dia (0.625 radius), Z_start=0.1, Z_end=-1.0
**DOC:** 0.050 dia (0.025 radius)
**Fin Allowance:** 0.002 dia (0.001 radius)

### NX Toolpath (verified from DXF):
- **Face passes:** 4 total at Z=0.075, 0.050, 0.025, 0.001
  - All face passes cut from X=0.625r (stock OD) to X=0 (centerline)
  - Final face pass at Z=0.001 (fin_allowance/2) ✓
- **Roughing passes:** 15 vertical passes
  - X levels: 0.600r→0.251r (DOC=0.025r steps)
  - Passes at X≥0.525r: Z[0.001→-1.000] (full length, above step)
  - Passes at X<0.525r: Z[0.001→-0.499] (short, below step shoulder)
- **Cleanup pass:** At X=0.251r (roughing boundary = profile + fin_allowance)
- **Finish pass:** Profile contour at X=0.250r, X=0.500r

### Our Engine Match Status:
- Zones: ✅ Exact vertex match
- Face passes: ✅ 4 passes including Z=0.001
- Roughing X levels: ✅ Match
- Roughing Z boundaries: ✅ Match (shoulder at Z=-0.499)
- Cleanup: ✅ At roughing boundary
- Finish: ✅ Profile contour

---

## Arc OD (175934-001_01)

**Profile:** X0→X0.5 at Z=0, X=0.5 at Z=-0.5, ARC (R=1.0, CCW) to Z=-1.5, X=0.5 at Z=-2.0
**Stock:** 1.5 dia (0.75 radius), Z_start=0.1, Z_end=-2.0
**DOC:** 0.050 dia (0.025 radius)
**Fin Allowance:** 0.002 dia (0.001 radius)

### NX Toolpath (verified from DXF):
- **Face passes:** 2 at Z=0.050, Z=0.001
  - Face DOC appears to be 0.1 dia (larger than roughing DOC)
  - Final face pass at Z=0.001 ✓
  - Face cuts from X=0.75r (stock OD) to X=0 (centerline)
- **Roughing passes:** 10 X levels (0.750r→0.501r), each with:
  - Upper straight segment: Z[0.000→Z_arc_top] (where arc boundary intersects this X)
  - **ARC segment** following the offset arc boundary at this DOC level
  - Lower straight segment: Z[Z_arc_bottom→-2.000]
  - Arc center: (-0.367r, -1.000) with radius increasing by DOC per level
- **Arc Z intersections (NX ground truth):**
  - X=0.750r: Z_top=-0.4367, Z_bot=-1.5633
  - X=0.725r: Z_top=-0.4427, Z_bot=-1.5573
  - X=0.700r: Z_top=-0.4488, Z_bot=-1.5512
  - X=0.675r: Z_top=-0.4549, Z_bot=-1.5451
  - X=0.650r: Z_top=-0.4611, Z_bot=-1.5389
  - X=0.625r: Z_top=-0.4673, Z_bot=-1.5327
  - X=0.600r: Z_top=-0.4736, Z_bot=-1.5264
  - X=0.575r: Z_top=-0.4800, Z_bot=-1.5200
  - X=0.550r: Z_top=-0.4865, Z_bot=-1.5135
  - X=0.525r: Z_top=-0.4931, Z_bot=-1.5069
  - X=0.501r: Z_top=-0.4997, Z_bot=-1.5003
  - X=0.500r: Z_top=-0.5000, Z_bot=-1.5000
- **Cleanup pass:** At roughing boundary (R=1.001, offset from profile R=1.0)
- **Finish pass:** Profile contour arc (R=1.0, center (-0.366r, -1.0))

### Our Engine Match Status:
- Zones: ✅ Match (finished part, MTR boundaries correct)
- Face passes: ⚠️ Count differs (ours: 4, NX: 2) — DOC parameter difference, not a bug
- Face Z=0.001 rule: ✅ Both have final pass at Z=0.001
- Roughing X levels: ⚠️ Missing X=0.750r (stock OD level)
- Roughing Z boundaries: ❌ WRONG — our Fiber queries compute different arc intersections
- Arc moves in roughing: ❌ MISSING — NX emits G02/G03 arcs connecting upper/lower segments
- Cleanup: ✅ At roughing boundary
- Finish: ✅ Profile contour with arc

### Known Bugs (Arc OD):
1. Fiber/interval queries compute wrong Z intersections with arc boundary
2. Staircase planner doesn't emit arc connecting moves between split intervals
3. Missing roughing pass at stock OD (X=0.750r)

---

## ID Bore (175933-001_01)

**Profile:** X=1.2 dia bore wall Z[0→-1.0], step to X=0.8 dia at Z=-1.0, continue to Z=-1.5
**Stock:** 2.0 dia, pilot hole 0.5 dia
**DOC:** 0.050 dia

### NX Toolpath: (not yet fully analyzed — pipeline fails on ID mode)

### Our Engine Match Status:
- Zones: ✅ Build correctly
- Finish allowance wire extraction: ⚠️ Returns empty (zone too thin for ID mode)
- Pipeline: ❌ FAILS — Shapely detects gouges (staircase planner generates passes beyond bore wall)
- Root cause: Staircase planner ID mode steps X outward past profile boundary into finished part

---

## Key Rules Confirmed by NX Ground Truth

1. **Last face pass always at Z=fin_allowance/2** (Z=0.001 for fin_allowance=0.002)
2. **Roughing passes start at Z=fin_allowance/2** (not Z=0)
3. **Arc profiles require arc moves in roughing** — straight Z cuts + arc connection at each DOC level
4. **Roughing boundary = profile + fin_allowance offset** (equidistant, not just X offset)
5. **Cleanup pass follows roughing boundary contour** (including arcs)
6. **Finish pass follows profile contour exactly** (including arcs)
