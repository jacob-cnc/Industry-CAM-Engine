---
inclusion: auto
---

# ID Program Rules & Lessons Learned

## NX Ground Truth Reference

All ID program validation MUST be compared against the DXFs in:
`reference/CAD Reference/ID Reference/`

Files:
- `175933-001_01-ID Reference Finished Part.dxf`
- `175933-001_01-ID Reference Finish Allowance Zone.dxf`
- `175933-001_01-ID Reference Material to Rough Zone.dxf`
- `175933-001_01-ID Reference Roughing Staircase.dxf`
- `175933-001_01-ID Reference Cleanup Pass.dxf`
- `175933-001_01-ID Reference Finish Pass.dxf`

Ground truth fixture parameters: `tests/ground_truth/stepped_id.json`

## Core Mental Model: ID is the Mirror of OD

| Concept | OD | ID |
|---------|----|----|
| Safe boundary | Stock OD (large X) | Pilot hole (small X) |
| DOC direction | Inward (decreasing X) | Outward (increasing X) |
| Retract direction | Outward to stock OD | Inward to pilot hole |
| Approach from | Stock OD | Pilot hole |
| Profile boundary | Small X (near center) | Large X (bore wall) |
| Offset direction | Away from centerline (+X) | Toward centerline (-X) |
| Closure | To centerline (X=0) | To stock OD |
| Finished Part | Between profile and centerline | Between profile and stock OD |

**Never treat ID as a special case or edge case.** It uses the same architecture as OD with inverted geometry parameters.

## Key Rules

### 1. X_start >= X of first segment (validation rule)
For ID programs, X_start must always be >= the X value of the first profile segment. If violated, produce an error alerting the user.

### 2. True Face Zone collapse
TFZ only generates face passes when X_start > X of the first segment below Z=0. When X_start = X of the first segment, TFZ X bounds collapse to zero width → NO face passes generated.

When no face passes exist:
- Roughing passes start at Z_start (not Z=0+fin)
- Cleanup pass starts at Z_start
- Finish pass starts at Z_start

### 3. Roughing Z_start
For ID mode, roughing passes always start at Z_start (the staircase planner uses `z_begin = stock.z_start` for ID). The zone's Z top boundary (which may be at fin_allowance) is irrelevant — the pass start is determined by where the tool enters.

### 4. MTR zone Z_end clipping
For ID mode, the MTR zone bottom boundary is at Z_end + fin_allowance (not Z_end). This leaves room for the finish pass to trace the bore bottom.

### 5. Pilot hole is the safe boundary
- All approach moves come from pilot hole side (smaller X)
- All retract moves go toward pilot hole side
- Rapids at pilot hole diameter are always safe
- G-code writer uses `safe_x = pilot_hole_dia` for ID mode

## Cleanup Pass Architecture (ID)

The ID cleanup uses the same kernel-driven approach as OD — completely decoupled code path in `_compute_offset_profile_id`:

1. **Build finished part face** — profile segments + closure to stock OD
2. **Offset equidistant with kernel** — POSITIVE offset expands face outward in all directions. For ID finished part (bore wall to stock OD), "outward" on the bore side = toward centerline (smaller X). This produces the roughing boundary.
3. **Clip to bore region** — rectangle from pilot hole to just past the LARGEST roughing boundary X, Z from z0_fin to Z_end+fin
4. **Extract edges from clipped wire** — full curve type info (LINE + ARC with center/radius)
5. **Filter clip boundary edges** — remove edges at pilot hole X, clip X_max, Z_top, Z_bot, and Z=fin_allowance (offset face top boundary)
6. **Order from highest Z downward** — same chaining logic as OD

### Critical details:
- **Offset direction**: POSITIVE (expands outward). Negative shrinks the face and moves the bore-side boundary the wrong way.
- **Clip X_max**: Use MAX profile X (largest bore diameter) minus fin + margin. Using min profile X cuts off larger bore sections.
- **Z=fin_allowance filter**: The offset face's actual top boundary is at Z=fin_allowance (from zone builder), not at Z_start. Edges at this Z level are non-cutting boundaries that must be filtered.
- **No fallback path**: Do not fall back to zone boundary extraction. The kernel offset approach handles arcs and tapers correctly; zone boundary extraction loses arc center/radius data.

## Finish Pass Architecture (ID)

- Traces the exact profile contour (bore wall)
- Starts at Z_start (when no TFZ) or Z=0+fin (when TFZ exists)
- First move feeds from approach position to first segment endpoint
- Then traces all subsequent segments in order
- G-code writer handles approach rapid from pilot hole

## Lessons Learned (2026-05-16 Session)

### Always start from NX ground truth
Parse reference DXFs → extract expected coordinates → write test → make engine match. Never make up test inputs based on assumptions.

### Don't abandon proven architecture
When the kernel offset approach doesn't immediately work for ID, fix the parameters — don't fall back to a simpler method that can't handle arcs. The architecture is sound; only geometry parameters differ between modes.

### Decouple OD and ID code paths completely
Sharing code between modes introduces subtle bugs. Build separate methods (`_compute_offset_profile` for OD, `_compute_offset_profile_id` for ID). The OD path is proven and must never be touched when working on ID.

### Wire traversal direction ≠ cutting direction
OCCT wire explorer returns edges in CCW order around the zone. ID cutting goes top-to-bottom (high Z to low Z). The edge ordering/chaining logic must sort by highest Z start and chain downward, reversing edges as needed.

### Clip region must encompass the target boundary
The clip rectangle must include the entire roughing boundary contour. For stepped bores, this means using the LARGEST profile X (not the smallest) to compute clip X_max.
