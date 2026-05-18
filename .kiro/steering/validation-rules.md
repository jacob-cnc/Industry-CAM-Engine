---
inclusion: auto
---

# Validation Rules — Shapely Runtime Safety

## Architecture

Build123d produces exact geometry → Shapely validates it's safe → G-code writer emits.

Shapely is a RUNTIME dependency. The pipeline refuses to generate G-code without validation passing.

## Polygon Construction (After build_zones)

1. Extract boundary edges from Build123d zone Faces using `boundary_wire_extraction()`
2. For LINE edges: use exact start/end coordinates
3. For ARC edges: adaptive densification with cosine-limit predicate

### Adaptive Densification Algorithm

```python
def densify_arc_adaptive(start, end, center, radius, direction, cos_limit=0.9999, max_depth=12):
    """Recursively bisect arc until flatness predicate satisfied."""
    mid = arc_midpoint(start, end, center, radius, direction)
    
    v1 = normalize(mid - start)
    v2 = normalize(end - mid)
    
    if dot(v1, v2) >= cos_limit or depth >= max_depth:
        return [end]  # Flat enough
    else:
        left = densify_arc_adaptive(start, mid, ..., depth+1)
        right = densify_arc_adaptive(mid, end, ..., depth+1)
        return left + right
```

### Error Budget

| Parameter | Value | Meaning |
|-----------|-------|---------|
| cos_limit | 0.9999 | Flatness threshold |
| max_chord_error | R × (1 - cos_limit) = R × 0.0001 | Maximum deviation from true arc |
| For R=0.251" | 0.0000251" | Hump test offset arc |
| System TOLERANCE | 0.0005" | Operating tolerance |
| Safety margin | TOLERANCE / max_error = 20× | Polygon is 20× more accurate than needed |

### Inscribed Chord Safety Property

Polygon chords are always INSIDE the true arc (inscribed). This means:
- Shapely polygon is a CONSERVATIVE (smaller) approximation of the true zone
- If Shapely says point is INSIDE polygon → DEFINITELY inside true zone (no false positives for gouge)
- If Shapely says point is OUTSIDE polygon → might be barely inside true zone by up to chord_error
- With 0.000025" error at 0.0005" tolerance, this is irrelevant

## Three Validation Gates

### Gate 1: Pre-Planning (before build_zones)
- Arc radius >= chord_length / 2
- Arc center computable (discriminant >= 0)
- Profile closure gap <= TOLERANCE
- No self-intersecting segments
- All X values >= 0

### Gate 2: Post-Planning (Shapely — every move checked)
```python
for pass in all_passes:
    for move in pass.moves:
        if move.move_type == "RAPID":
            line = LineString([(start_x_r, start_z), (end_x_r, end_z)])
            assert not line.intersects(finished_part_poly.boundary)
            assert not line.intersects(finish_allowance_poly.boundary)  # roughing rapids
        elif move.move_type in ("FEED", "ARC_CW", "ARC_CCW"):
            # Build strip/arc and check against finished_part
            strip = build_move_strip(start, end, ...)
            assert not strip.intersects(finished_part_poly)
        # Endpoint check
        assert not finished_part_poly.contains(Point(end_x_r, end_z))
```

### Gate 3: Pre-Output (G-code geometry)
- No zero-length moves
- Arc endpoint-to-center distance matches radius within 0.00283"
- No consecutive identical positions
- Feed rate set before first feed move
- All coordinates finite

## Performance Budget

| Operation | Target | Notes |
|-----------|--------|-------|
| Polygon construction | < 10ms | One-time after build_zones |
| Point-in-polygon | < 5μs | Per check |
| Line-polygon intersection | < 10μs | Per rapid move |
| Full validation (60 passes × 6 moves) | < 5ms | Total post-planning |

## Failure Reporting

Every validation failure includes:
- Gate number (1, 2, or 3)
- Specific check name
- Coordinates involved
- Pass number and move index (if applicable)
- Suggested fix (if determinable)

```python
raise ValidationError(
    gate=2,
    check="rapid_crosses_keep_zone",
    pass_num=7,
    move_idx=1,
    start=(1.2200, -0.5000),
    end=(0.9800, -0.5000),
    detail="Rapid from X1.22 to X0.98 at Z-0.5 crosses keep_zone boundary at X1.002"
)
```
