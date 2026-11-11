# Zone shading on the graph: plan and status (2026-11-11)

**Owner request (2026-11-11).** Shade the graph's discrete sections in different
colours: material to be removed, the finished part, the cleanup allowance, and so
on, so the operator can tell them apart. "It's imperative that the
sim/preview/graph is 100% accurate so the user can rely on it as a valuable
validation tool." Look at why the earlier shading failed, then plan for success.

Status: **S0–S2 built 2026-11-11** on `claude/arc-phase0` (see §6). S3 (playback)
is not started. Owner choices: cleanup and finish are one band; the finished part
is steel; the live preview shows only the finished part, and all sections appear
after Generate.

## 1. What failed before, and why

| Attempt | Where | What went wrong | Root cause |
|---|---|---|---|
| Zone polygons as `QGraphicsPolygonItem` | CHECKPOINT_8 | "added to ViewBox but not visible" | Wrong import first; then the polygon item wasn't put in the ViewBox's data coordinates. A rendering plumbing bug, not a geometry one. |
| Rasterised zones (`_draw_zones_as_image`, "the nuclear option") | graph_widget.py, still in the code | Grey bands; edges never line up with the toolpath | Painted into a bitmap at 200 px/in, capped at 800 px. Zooming in shows the pixels, so an edge can be off by about 1/200" (.005"). That can't be made accurate. |
| Material-removal sim (`.kiro/specs/material-removal-simulation/SHELVED.md`) | material_sim.py, sim_viewer.py | Fill missing, wrong shape, or snapping between states | (a) `PlotCurveItem(fillLevel=…)` fills down to a horizontal baseline, not inside a polygon. (b) G-code moves were matched back to planner moves by end points within .001", which is fragile. (c) Per-move states were too many and too jumpy. (d) A field was missing in the data plumbing. |
| Profile boundary from the kernel | graph_widget.py comment | A visible gap of about .0001" between the boundary and the toolpath, so the boundary was removed | Zone outlines came from OCCT wires (kernel tolerance) while the toolpath came from exact numbers. Two sources means two answers. |
| Zone shading in general | graph_widget.py comment | Removed as "visually cluttered" | Every zone on at once, no legend, no way to turn zones off. |

In short, the geometry was mostly right. The failures were: (1) rendering methods that
can't draw an arbitrary polygon exactly; (2) the shading and the lines coming from
different sources of truth; (3) inferring what got cut by matching G-code back to
planner moves; (4) clutter.

## 2. The sections to show

Each section is a closed region, possibly with holes, in (X dia, Z), with its own
colour and its own on/off toggle in a small legend:

| Section | Meaning to the operator | Colour (gui-color-system) | Default |
|---|---|---|---|
| **Finished part** | what's left when the program is done, as cut | crimson 30% `graph_zone_finished` | on |
| **Face stock** | removed by the facing passes (in front of Z0) | blue, lighter | on |
| **Roughing** | removed by the roughing passes | blue 15% `graph_zone_material` | on |
| **Cleanup / finish** | what roughing leaves and the cleanup and finish passes take: the allowance band plus the roughing steps | peach 20% `graph_zone_allowance` | on |
| **Left uncut, by choice** | the tool can't reach it; reported with an insert suggestion (built already) | coral, dashed edge | on |
| **Not removed: program error** | material the program should remove but doesn't. Should never appear; if it does, it's a red flag, not decoration | solid crimson, hatched | always on |

The lines on top stay as they are: the drawn profile (white), the stock outline
(dashed), and the toolpath (feed and rapid colours).

The "Cleanup / finish" band is the important one. It isn't a nominal offset band: it
is the actual material between the roughing result and the finished part, so
staircase steps and corners left by roughing show up exactly where cleanup will cut.

## 3. How: the rules that keep it 100% accurate

**Rule 1: what was cut comes from what the machine will run, not from what the
planner meant.** "Removed by roughing" is the area swept by the roughing moves
**of the G-code**, run through LinuxCNC's own interpreter (`rs274`, already used by
the tests; well under a second). The same applies to the cleanup, finish and face
sections. That removes our parser, our arc maths and the move-matching from the
answer altogether.
- No need to match G-code moves back to planner moves (failure 3). Each block comes
  from the `rs274` output for that pass; pass boundaries come from the comment and
  N-number structure the writer already emits.
- Swept area = the tool nose circle (TNR) swept along the path, placed according to
  how that move is programmed:
  - Roughing is uncompensated, so the programmed point is the imaginary tip with
    orientation Q, and the nose centre is offset from it by Q.
  - Cleanup and finish run in G41/G42. **Phase S0 verifies from rs274's canonical
    output exactly which point the interpreter reports under comp**, with a test on a
    straight pass and an arc pass, before anything is built on it.
- If `rs274` isn't available, the graph says so instead of quietly switching to a
  different calculation.

**Rule 2: the zone edges and the lines use the same numbers.**
- The finished-part section is built from the same point list the profile line is
  drawn from, so the shading edge and the line share identical floats. No kernel
  wire extraction, so no .0001" gap (failure 4).
- One densifier for every arc drawn anywhere on the graph (profile, toolpath, zones),
  set by chord error rather than "points per inch": at most .00002", well below one
  pixel at the deepest zoom. Today the sim viewer, the preview and the material sim
  each sample arcs their own way. They will all use `geometry/arc_math`.
- X diameter → graph radius in exactly one function.

**Rule 3: draw polygons as polygons.**
- A `QPainterPath` in data coordinates per section (odd-even fill for holes), added to
  the plot as a `QGraphicsPathItem`. That's the method the uncut shading uses, and it
  is proven on screen. No `fillLevel` (failure 1), no bitmap (failure 2).
- Seams: adjacent sections share edges exactly (they're built by Shapely boolean
  operations from one set of geometry), and the boundary lines are drawn on top, so
  antialiasing never shows a hairline between two fills.
- Z order: sections < uncut < profile line < toolpath < tool dot.

**Rule 4: the sections must add up, and the graph checks it on every Generate.**
These checks are cheap (Shapely, milliseconds):
- face ∪ rough ∪ cleanup ∪ finished ∪ uncut == stock: area difference < 1e-6 in², with
  no overlaps.
- Stock − everything swept − finished − uncut (allowed) = "not removed". If its area is
  above 1e-6, it's drawn as the red error section, and the status line says where.
- Nothing swept enters the finished part (the post-planning validator already
  checks this from planner moves; this checks it from the G-code).
- The finish-pass nose envelope coincides with the finished-part boundary: the
  Hausdorff distance is under .00005", outside the uncut regions.

So the shading can't quietly drift from the program. If they disagree, the
disagreement is what gets shown.

**Rule 5: no clutter.** A legend with a checkbox per section, remembered between
sessions. The defaults are in the table above.

## 4. Phases

- **S0, foundations (desk):**
  - One arc densifier.
  - The `ShadedRegion` drawing primitive (polygon with holes → path item), with the
    uncut shading moved onto it.
  - A test helper that renders the graph offscreen and reads pixel colours at chosen
    (X, Z) points: just inside and just outside each edge, at high zoom.
  - The rs274 comp test from Rule 1.
- **S1, sections from the G-code:**
  - A per-pass swept-area builder from the rs274 output.
  - The finished part from the as-cut profile.
  - The five sections plus the error section, built with Shapely boolean operations.
  - The Rule 4 checks on every Generate.
- **S2, GUI:** the legend and toggles, the colours, and the error-section status
  message. Remove the dead rasterised path and the shelved material-sim rendering.
- **S3, optional playback:** during playback, show the material as it stands after
  each completed pass, from the same swept areas (stable, no per-move snapping). This
  is the "consider simpler approach" item from the shelved spec.

**Tests that must pass before it ships:**
- Pixel probes at high zoom for OD and ID test parts: a straight turn, the NX OD and
  ID parts, a groove and a bead (uncut), and a face plus chamfer.
- The Rule 4 invariants on every reference program.
- A deliberately broken program (a roughing pass deleted from the G-code) must show
  the red "not removed" section in the right place.
- Generate timing on the NX part, before and after.

## 5. Open points for the owner

1. Are these the right sections? In particular: "Cleanup / finish" as one band, or
   cleanup and finish as two?
2. Colours: the existing colour-system values, or does the finished part read better
   as a calm solid (steel) than as the crimson "danger" colour?
3. Should the sections also show in the live preview while editing? There, only
   planned geometry exists, with no G-code yet. Proposal: show finished part + uncut
   only in the preview, and everything after Generate.

## 6. What was built (2026-11-11)

**`outputs/cut_regions.py`**
- `tag_sections` puts a `(ICAM_SECTION x)` comment after each `; === … ===` header.
  CLEANUP is matched before ROUGH, because the cleanup header says "roughing
  boundary".
- `run_rs274` runs the program with a generated tool table (the program's tools,
  zero offsets).
- `parse_canon` turns the output into moves. It follows SELECT_TOOL, and arcs use
  one chord-error densifier (2e-5").
- **Verified:** rs274 reports the imaginary tip, compensated or not. On a G42
  chamfer, the nose centre (tip minus TNR × Q direction) sits exactly TNR from the
  drawn line (test).
- Swept area: the nose circle along the path, plus the insert wedge (front and back
  edges, 0.25" long). Wedge contact with the intended part is ignored; the nose
  decides the part edge.
- Sections come from Shapely boolean operations. They partition the stock exactly
  (checked every time).
- Error sections:
  - **gouge** = intended part ∩ nose sweep.
  - **not removed** = as cut − intended, judged at Z0 and behind only, outside
    nose-radius margins at concave corners, the start point and Z end.
  - Both are filtered at 1e-4" thickness and reported as "GRAPH CHECK" notes.
- About 70–230 ms per block.

**GUI**
- `graph_widget.set_sections`: one `QGraphicsPathItem` per section (odd-even fill,
  data coordinates).
- Colours `graph_sec_*` in `colors.py` are #RRGGBBAA. They are parsed with
  `pg.mkColor`; `QColor` would read them as #AARRGGBB, which is what made "steel"
  render olive on the first try.
- Errors draw as red hatch and always show.
- `sim_viewer` has a legend row of checkboxes (QSettings `IndustryCAM/graph`) that
  shows only the sections present.
- `program_tab._show_cut_sections` runs after every Generate. If rs274 is missing, a
  note says so and only the uncut regions are shaded; never a guessed picture.
- The preview shades the finished part from the same points as the profile line.
- The rasterised `_draw_zones_as_image` was removed.

**Tests**
- `tests/integration/test_cut_regions.py` (14): interpreter semantics, the
  partition, matching the intended part, every test-bed part running in LinuxCNC,
  a program with its finish pass deleted, an injected gouge, and the two real
  defects below.
- `tests/unit/test_cut_sections_ui.py` (3): pixel probes .0005" either side of the
  finished edge at about .0001"/px, OD and ID, and the legend toggles.
- The full suite passes three times in a row.

**Real defects the check found in existing code** (shown red on the graph; fixes
pending, owner to prioritise):
1. **Roughing beside a falling flank cuts into the part.** Roughing is
   uncompensated, so LinuxCNC drives the imaginary tip and the nose sits above and
   behind it (Q2). A plunge next to a contour falling toward the chuck puts the
   nose into the flank: .0125" on the 60° crest with a VNMG, against a .005"
   allowance. The post-planning check looks at the tip path only. The CNMG's reach
   limit keeps normal OD turning out of this; VNMG/DNMG/left-hand tools on falling
   contours are exposed.
2. **An ID bore-mouth chamfer is left up to .005" proud.** The finish pass enters
   along Z0 across the mouth and turns back down the chamfer (135°). LinuxCNC comp
   treats the in-air entry line as a surface and stops the nose short of the top of
   the chamfer. Any ID program that starts with a mouth chamfer segment is affected.
3. **The face is left at the face pass's allowance when the profile doesn't start
   at X0.** The face pass stops at Z+fin allowance (.010 here) and the finish
   starts at the profile's first point, so the face inside it is never finished.
   It may be intended; owner to confirm. Shown as finished-part material in front
   of Z0, not flagged.

**Also fixed while building this:**
- The reach bridge could end a few thou before the end of a contour piece. That
  left a short arc or line after a concave corner, which LinuxCNC comp refuses
  (bridged grooves failed in rs274). The bridge now runs to the end of a piece that
  short.
- More GUI tests leaked top-level tabs (RunTab, DebugTab); they now close and
  delete them.
