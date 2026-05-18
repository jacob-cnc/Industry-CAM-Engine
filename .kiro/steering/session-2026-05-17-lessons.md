---
inclusion: auto
---

# Session 2026-05-17 — Lessons Learned

## Arc Preview Rendering (program_tab.py `_update_preview`)

### Problem
Preview rendered full circles or wrong arcs instead of the correct short arc.

### Root Cause
1. Center placement used wrong sign convention
2. Sweep angle used CW/CCW direction-based adjustment instead of [-π, π] normalization

### Fix
- Work in RADIUS space throughout (X_dia / 2)
- Center placement: CW → `mid + h*perp`, CCW → `mid - h*perp`
  - Perpendicular: `px = -dz/chord`, `pz = dx_r/chord` (points LEFT of chord)
- Sweep: normalize to [-π, π] (NOT CW/CCW based). Matches proven sim viewer.
- Verified against engine G-code output (I/K values confirm center position)

### Key Insight
The center placement encodes which arc to draw. The [-π, π] normalization then gives the short path. Don't use `if radius > 0: diff -= 2π` — that's the old broken approach.

---

## PyQtGraph Ghost Line Artifact (Issue #2178)

### Problem
Solid horizontal line at profile X level, extending beyond data. Only with arcs (many points). Disappears when profile scrolled off-screen.

### Root Cause
PyQtGraph's "segmented line" optimization (PR #2011) for thick lines (width > 1) creates ghost segments at PlotCurveItem bounding-box edges.

### Fix
Set pen alpha to 254 (not 255). Visually identical but bypasses the optimization:
```python
color = QColor(COLORS['graph_profile'])
color.setAlpha(254)
pen = pg.mkPen(color, width=2)
```

### Additional Mitigation
Split profile into separate PlotCurveItems per segment type (line sub-paths vs arc sub-paths).

---

## Build123d Zero-Length Line Crash (zone_builder.py)

### Problem
`_build_true_face()` crashes with `StdFail_NotDone` when x_min == x_max.

### Root Cause
When X Start = 0 and stock_diameter = 2.0, the code computed x_min = x_max = stock_radius. Build123d can't create a zero-length Line.

### Fix
Guard in `_build_true_face`: return `None` when `abs(x_max - x_min) < 1e-6` or `abs(z_start) < 1e-6`. Downstream code (ZoneQueryAPI, FacePlanner) already handles None.

---

## Face Pass X_start (program_tab.py + face_planner.py)

### Problem
Face passes weren't feeding to the correct X endpoint. When X Start = 0, they should feed from stock OD all the way to X=0 (centerline).

### Root Cause
GUI code was substituting `stock_diameter` for `x_start` when the field was 0, making x_start == stock_dia → no face zone.

### Fix
Pass x_start=0 directly to the pipeline. The face planner uses it as the feed endpoint. The `_build_true_face` None guard prevents the crash.

### Face Planner Enhancement
Added two moves per face pass (was one):
1. FEED: Z step-down at stock OD (approach to Z level)
2. FEED: X cut from stock OD to X_start (the actual face cut)

This ensures the graph adapter sees the full face cut as a FEED segment for visualization.

---

## Cleanup Pass Ordering (cleanup_planner.py)

### Problem
Cleanup pass was reversed and missing the arc. It traced the offset boundary in the wrong direction.

### Root Cause (combo of two issues)
1. **Filter tolerance too tight** (1e-4): Build123d offset produces floating-point drift. Face-level edges at Z=z0_fin weren't being filtered because they were at Z=0.002499 instead of Z=0.0025.
2. **Edge ordering assumed "highest Z first"**: This picked the face-level edge (if it leaked through the filter) and chained backward around the clip boundary.

### Fix
1. **Relative tolerance**: `tol = max(1e-3, z_range * 0.001, x_range * 0.001)` — catches floating-point drift from kernel operations.
2. **Approach-point-based ordering**: Find the edge endpoint closest to `(x_start+fin, z0+fin)` — where the tool arrives. Chain from there. Works for ANY profile shape (tapers, steps, arcs) because it doesn't assume X direction.

### Validation Tolerance
The cleanup pass traces the OUTER boundary of the finish allowance zone. Due to Build123d offset drift, the arc may slightly penetrate the Shapely polygon boundary. Fix: buffer the finish_allowance polygon inward by 0.001" before checking `crosses()`.

---

## GUI Left Panel Sizing

### Problem
Left panel too narrow, couldn't be dragged wider.

### Fix
- `setMinimumWidth(210)` — prevents crushing
- NO `setMaximumWidth` — allows user to drag wider
- `setSizes([220, 780])` — default proportions
- `setStretchFactor(0, 0)` / `setStretchFactor(1, 1)` — right panel grows with window

---

## Toolpath Progressive Reveal (sim_viewer.py + graph_widget.py)

### Problem
All toolpath lines appeared immediately after Generate, cluttering the view.

### Fix
- Toolpath PlotCurveItems start hidden (`setVisible(False)`)
- `reveal_toolpath_up_to(move_index)` — called during playback, shows segments progressively
- `show_all_toolpath()` — "Show All" button reveals everything
- `hide_all_toolpath()` — "Reset" button hides everything
- Rapids visibility toggle respected during progressive reveal

---

## Z_start Safe Approach (`_safe_z_start` in model_builder.py)

### Rule
When Z_start ≤ fin_allowance/2 + 0.001 (user wants to skip face passes), bump to `fin_allowance/2 + 0.050"`. This provides safe rapid approach clearance without generating TFZ face passes.

When Z_start > threshold (e.g., 0.1"), keep it as-is — face passes will generate normally.

---

## General Rules Reinforced

- **Don't derive values the user explicitly set** — if X Start = 0, pass 0 to the pipeline
- **Guard kernel calls against degenerate geometry** — zero-length lines, zero-area faces
- **Use relative tolerances when filtering kernel output** — Build123d offset introduces drift
- **Order edges by proximity to approach point** — not by coordinate assumptions about profile shape
- **Profile boundary in generated view is redundant** — toolpath traces + preview profile are sufficient
