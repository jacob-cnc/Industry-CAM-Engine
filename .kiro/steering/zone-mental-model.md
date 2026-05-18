---
inclusion: auto
---

# Zone Mental Model

This document defines the machining zones used throughout the engine for toolpath generation, retract/approach logic, safety validation, and testing.

## Zone Definitions

### Profile Boundary

The contour that the finish pass will trace. Defined by user input segments in the GUI. Used to create the Finished Part.

### Roughing Boundary

The Profile Boundary contour adjusted by the finish allowance offset. Offset direction changes based on ID/OD:
- **OD**: X offset away from centerline (toward stock), Z offset depends on part geometry. Equidistant Offset.
- **ID**: X offset toward centerline (toward pilot hole), Z offset depends on part geometry. Equidistant Offset.

### Finished Part

**OD mode:** Any area between Profile Boundary and X centerline, bounded by Z=0 and Z(most negative).

**ID mode:** Any area between Profile Boundary and Stock Boundary on the X+ side of the Profile Boundary(Away from centerline). ID Finished Part is also bounded by Z=0 and Z(most negative).

This is the area that never gets removed for OD and ID. Any feed or rapid move should never move inside or through this zone for OD and ID.

### Finish Allowance Zone

The area between the Roughing Boundary and the Profile Boundary. The finish tool removes this area.

### Material to Rough Out

The area between Stock Boundary and the Roughing Boundary. This area must be removed by roughing passes.

### Pilot Hole

The absence of material between X centerline and User Input Pilot Hole Diameter for ID profiles. Bounded by Z Start and Z(most negative). Material does not and has never existed here. The tool may move freely through this zone at any time. The face planner does not cut here because there is nothing to cut.

### Stock Boundary

**OD mode:** The rectangle created by connecting coordinates: User Input Stock Diameter (X), Z=0, Z(most negative), and X centerline.

**ID mode:** The area bounded in X by Pilot Hole Diameter User Input and the Profile Boundary. Bounded in Z by Z=0 and Z(Most Negative).

### True Face Zone

**OD mode:** The area bounded by the rectangle created from Z=0, X Stock Diameter (user input), Z Start, and X Start.

**ID mode:** The area bounded by Z=0, Pilot Hole Diameter (X), Z Start, and X Start.

## Program Execution Rules

Every program must satisfy these conditions:

### Rule 1: True Face Zone is always cut first and completely removed.

**Face Pass Z-Level Rule:** Face passes step from Z_start toward Z=fin_allowance/2 (typically Z=0.001"). The **last face pass is always at Z=fin_allowance/2** regardless of DOC stepping:
- If natural DOC stepping lands below Z=fin_allowance/2 → clamp the last pass to Z=fin_allowance/2
- If natural DOC stepping lands above Z=fin_allowance/2 → cut the natural pass AND add a final pass at Z=fin_allowance/2

This ensures the face is always cleaned to the exact level where roughing passes begin (Z=0+fin_allowance/2), leaving no uncut material between the last face pass and the first roughing pass Z_start.

### Rule 2: Material to Rough Out zone is completely removed by roughing passes.

### Rule 3: Finish Allowance Zone is removed by the cleanup pass and finish pass.

**Cleanup Pass Definition:** The cleanup pass traces the Finished Part zone offset equidistant outward by fin_allowance, clipped at:
- Z begin: Z0 + fin_allowance (top)
- Z end: Z_end (bottom, most negative Z)
- X begin: X_start + fin_allowance

The cleanup pass is computed by offsetting the Finished Part face using the geometry kernel (Build123d offset), then clipping the result to the turning region using a boolean intersection (BRepAlgoAPI_Common) with a clip rectangle. The approach feeds along the face at Z0+fin from X_start+fin to the offset profile X, then follows the offset contour downward.

**Finish Pass Definition:** The finish pass traces the exact profile contour (Finished Part boundary). Approach: rapid to (X_start, Z0+fin), feed to (X_start, Z0), then trace all profile segments in order from the first point to the last.

### Rule 4: Finished Part is never cut into or moved through. No gouging whatsoever. Must be accurately coupled to the user input segments.

### Rule 5: Tool Movement Freedom

The tool may move through:
1. Any area not governed by another zone definition (air — outside Stock Boundary)
2. The Pilot Hole zone (ID mode — pre-existing empty space)
3. Any area where previous passes have already removed the zone section that was there

The tool may NOT move through:
- Finished Part — never, under any circumstances
- Finish Allowance Zone — only the finish tool may enter
- Uncut areas within Material to Rough Out — rapids through uncut stock are uncontrolled cuts

Retract strategy follows from this:
- OD: retract to Stock Diameter or beyond (air) before Z traversal
- ID: retract to Pilot Hole Diameter or smaller (pilot hole = air) before Z traversal
- For OD Mode: Within already-cleared regions: the tool may traverse at the previous pass's X level without retracting fully
- Diagonal rapids that would cross the Roughing Boundary or uncut areas must be split into safe segments

> **Note:** A fully fleshed out retract and approach logic document will be created as a separate steering file covering all cases (valley passes, multi-interval transitions, offset-contour links, face-to-turning transitions, etc.)

> **FUTURE WORK — Uncut Material Validator:** The current post-planning validator only checks against the Finished Part and Finish Allowance polygons. It does NOT detect rapids through uncut material within the MTR zone. A future enhancement should build a "remaining material" polygon (starts as MTR, subtract each pass's swept region in execution order) and verify that rapids don't cross through remaining material. This requires pass execution order and swept geometry per pass — a significant architectural addition. Track in: `validation/remaining_material_validator.py` (to be created).

### Retract X Rule (Universal)
The safe retract X after a roughing pass is computed by `_compute_pass_max_x()` in the G-code writer:
- For linear moves: `max(move.x for all moves)` — the endpoint X
- For arc moves: `(center_x_r + radius_r) * 2` — the arc peak X (rightmost point of the arc circle), only if the arc bulges outward (peak > both endpoints)
- Result is capped at stock OD — no retract beyond stock needed

This replaces the old `prev_retract_x = p.x_level` which only captured the straight-section X and missed arc humps.

**Why universal:** Works for staircase (no arcs = no change), contour roughing (captures arc peak), split passes (caps at stock OD), and future tapers (any move beyond x_level is captured).


## Zone Relationships

```
Finished_Part = Profile Boundary closed to centerline (OD) or to Stock OD (ID)
Finish_Allowance_Zone = area between Roughing Boundary and Profile Boundary
Material_to_Rough = area between Stock Boundary and Roughing Boundary
True_Face_Zone ⊂ Material_to_Rough (face area is a subset of roughing area)
Pilot_Hole = absence of material (never existed, not a zone to cut)
```

## ID Program Rules

### NX Ground Truth Reference
All ID program validation should be compared against the DXFs in:
`reference/CAD Reference/ID Reference/`

Files:
- `175933-001_01-ID Reference Finished Part.dxf`
- `175933-001_01-ID Reference Finish Allowance Zone.dxf`
- `175933-001_01-ID Reference Material to Rough Zone.dxf`
- `175933-001_01-ID Reference Roughing Staircase.dxf`
- `175933-001_01-ID Reference Cleanup Pass.dxf`
- `175933-001_01-ID Reference Finish Pass.dxf`

### ID Validation Rule: X_start >= X of first segment
For ID programs, X_start must always be >= the X value of the first profile segment. If violated, the engine should produce an error/warning alerting the user.

### True Face Zone for ID Programs
The True Face Zone for ID is bounded by: Z=0, Pilot Hole Diameter (X), Z_start, and X_start.

**Critical rule:** TFZ only generates face passes when X_start > X of the first segment below Z=0. When X_start = X of the first segment, the TFZ X bounds collapse (zero width) and NO face passes are generated.

When no face passes are generated:
- Roughing passes start at Z_start (not Z=0+fin)
- Cleanup pass starts at Z_start
- Finish pass starts at Z_start

### ID Roughing Pass Rules
- DOC intervals build OUTWARD from pilot hole toward roughing boundary
- First pass at pilot_hole_dia + DOC, stepping outward
- All passes start at Z_start (when no TFZ) or Z=0+fin (when TFZ exists)
- Passes at X levels above a step boundary stop at the step Z (minus fin_allowance)
- Passes at X levels below a step boundary continue to Z_end (minus fin_allowance)

### ID Approach/Retract Rules
- Pilot hole is the safe boundary (equivalent to stock OD for OD programs)
- All approach moves come from pilot hole side (smaller X)
- All retract moves go toward pilot hole side (smaller X)
- Rapids at pilot hole diameter are always safe (no material exists there)
- Within already-cleared regions: tool may traverse at previous pass X level

### ID Cleanup Pass
- Traces the roughing boundary (profile offset inward toward pilot hole by fin_allowance)
- For stepped bores: follows the full stepped contour at offset coordinates
- Starts at Z_start (when no TFZ) or Z=0+fin (when TFZ exists)
- Approach from pilot hole side

### ID Finish Pass
- Traces the exact profile contour (bore wall)
- For stepped bores: follows the full stepped contour at profile coordinates
- Starts at Z_start (when no TFZ) or Z=0+fin (when TFZ exists)
- Approach from pilot hole side
- Includes the step transition (horizontal segment at step Z)

## Validation Mapping

| Zone | Check | Method |
|------|-------|--------|
| Finished Part | No move enters or crosses | `finished_part_poly.intersects(move_strip)` must be False |
| Finish Allowance Zone | Only finish tool enters | Roughing move strips don't intersect `finish_allowance_poly` |
| Material to Rough Out | Completely removed after roughing | `mtr_poly.difference(swept_union).area < TOLERANCE_SQ` |
| True Face Zone | Completely removed by face passes | Face swept area covers entire True Face Zone |
| Pilot Hole (ID) | Always safe | No check needed (absence of material) |
| Air (beyond stock) | Always safe | No check needed |
| Already-cleared regions | Safe for subsequent passes | Rapid at prev_x_level is safe because prior pass cleared it |
