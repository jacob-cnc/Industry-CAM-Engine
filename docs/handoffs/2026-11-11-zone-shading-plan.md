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

**Real defects the check found in existing code** (1 and 2 FIXED, see §7; 3 to
discuss):
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

## 7. Defects 1 and 2 fixed (2026-11-11, owner: "fix 1 and 2, then we talk about 3")

**1. Roughing beside a falling flank: fixed for both roughing strategies.**
- **Staircase** (`planners/staircase_planner.py`): every pass interval is trimmed
  against a nose-aware forbidden region, translate(keep ⊕ disk(TNR), −nose offset),
  where keep = finished part ∪ finish allowance (`ValidationPolygons`). On
  diameters and faces that region equals the zone, so ordinary turning is
  unchanged. On the NX part with a CNMG, only the one pass beside the bridged flank
  moved (its start went from Z-.8479 to Z-.8646).
- **Offset-contour** (`planners/contour_roughing_planner.py`): the part is offset
  by (offset + TNR) for the nose centre, and the result is shifted back to the tip.
  The path is the same on diameters and faces, with full nose clearance on falls.
- `models.tool.Q_TIP_DIRECTION` and `nose_centre_offset` are now the single
  definition, shared with cut_regions.

**2. ID bore-mouth chamfer: fixed in the writer** (`_emit_contour_pass`).
- The ID lead from the approach height (Z0+.001) to the contour start is now
  recognised as air even though it isn't exactly radial (it was 0.001" off), and is
  dropped.
- A contour that starts with a sloped line toward the chuck is entered **in line
  with that line**, from the air behind its start: comp-off down to the entry
  point, then G41/G42, then the entry move along the first cut. Compensation sees
  no corner, so the nose cuts the chamfer from its very top.
- The existing straight-down entry for bores and walls and the OD face entry are
  unchanged.
- Side effect, intended: with X start at the pilot hole, the counterbore finish now
  enters straight down the wall instead of running the lead under comp
  (`test_id_bore_pipeline` updated).

**Also adjusted:**
- `arc_entry.EXTREME_TOL` went from .0001 to .0005 (the engine's TOLERANCE, which is
  what the old X-bounds refusal allowed). A .00012 dip on GUI Conv Test was being
  split into a sub-degree sliver piece that later blocked the program.
- A tool with no nose radius and no edge angles (the T99 QCTP master tool) sweeps no
  area that can be modelled. The graph now says it can't tell, instead of painting
  everything as "not removed".

**Verified:**
- Every saved reference program generates, runs in rs274, and checks clean with
  the repo `tool.tbl` (Test Run Program gets the honest "can't tell" for T99).
  This is now a test.
- The crest and groove with a VNMG check clean under both strategies, and so does
  the NX ID part. The full suite passes twice: 1203 tests, plus the new ones.

**Still open:**
- Defect 3 (the face left at the face allowance): to discuss with the owner.
- An OD profile that starts with a chamfer *at the face* is refused by the writer's
  existing comp guard on the cleanup pass (a .003 sliver before a concave corner).
  This happened before these changes; it fails safe.

## 8. Defect 3 and the face-chamfer refusal, measured (2026-11-11, for the owner)

**How the face is cut today.** The face passes step down from Z start to
Z = fin_allowance/2. On OD they cut from the stock OD in to X start; on ID, from
the pilot out to X start. They deliberately leave the allowance for the finish
pass. Whether anything finishes the face depends on how the profile starts:

| How the profile starts | What happens to the face | Example |
|---|---|---|
| X0, then a **face segment** along Z0 | The finish faces it flat through the centre (OD face entry: one nose radius before centre). **Clean.** | Corner Break Test, GUI Conv Test, Test Cut, Test Program Tab |
| Above X0 (no face segment), X start 0 | The finish crosses the face on a lead from X0 at **Z+.0010** down to the first point at Z0. The face comes out **slightly conical**: .0008 proud at X.05, tapering to 0 at the first point. A **centre pip** .005–.0058 tall inside about X.02 remains, because the OD face entry needs an exactly level first move and this one is .001 off. | NX OD part (first point X.2362) |
| X0, then an **arc** (dome) | The finish comes straight down X0 onto the dome and follows it. Comp can't cross the centre, so a **pip** about the nose radius tall is left: .0155 tall, about .025 across. | Hemisphere Test |
| ID block | The end face outside the bore (first point → stock OD) is never touched. It stays at stock Z start (+.025 on Bearing Sleeves, +.100 on the NX ID part). | Bearing Sleeves, NX ID |
| X start = stock OD (no facing) | Nothing in front of Z0 is cut. | operator choice |

The graph check judges only Z0 and back, so none of these are flagged. They show
as finished-part material in front of Z0.

**The face-chamfer refusal (cleanup pass, writer guard).**
- **When it happens:** the profile starts at the chamfer's top (e.g. X.6 Z0 →
  X.8 Z-.1) with no face segment before it, or the same chamfer is drawn as a V1
  corner break.
- **What the cleanup pass does:** it runs across the face at Z+allowance from the
  centre to above the chamfer start, then steps straight down .0029 (fin .020) or
  .0007 (fin .005), then turns onto the chamfer's offset line. The true offset
  corner would be the intersection, at X.6083 Z.010, with no step.
- **Why it's refused:** that step followed by the 45° turn is an inside corner
  for the compensated nose. LinuxCNC needs R·tan(22.5°) = .0066 of straight move
  before it, otherwise it stops with "straight feed in concave corner cannot be
  reached". The writer refuses in advance; the GUI shows it as a generation error.
- **The working form:** drawn as X0 → face to X.6 → chamfer, it generates and
  checks clean at both allowances.

**Also found while measuring:** with a .010–.020 finish allowance, the Hemisphere
cleanup pass doesn't run to the end in LinuxCNC (its first G03 out of the centre;
the writer's guard doesn't catch it). At the saved .005 it runs. The graph says
"not shown: interpreter did not run the program to the end", and the machine
would stop at the same line.

## 9. Owner decisions on 1 and 2, and what was done (2026-11-11)

**1 (face): no implicit facing cycle.** Users often don't want the part faced.
The owner likes a toolpath that runs up or down the face straight into the
profile, because that motion avoids the burr at the face/profile transition (and
at a chamfer, unless it's cut in one smooth motion). Alternatives such as a
facing-specific block are to be discussed.

**2 (centre nib): done.** When X start is 0 or segment 1 is at X0, the finish
nose goes **nose radius + .002 past the centreline**, for flat faces as well.
- Planner (`finish_planner`): on OD, when X start is inside the first point
  (facing requested) or the profile starts at the centre, the lead from X start to
  the first point runs at exactly **Z0** (it was Z0+.001). It is a flat face cut
  that flows straight into the profile; before, the face came out .001 conical and
  the writer's centre entry didn't engage.
- Writer (`_emit_contour_pass`):
  - Zero-length leading moves are skipped.
  - The OD face entry at the centre uses `_CENTRE_OVERSHOOT` = .002 on top of the
    nose radius (entry X-.0360 for a .016 nose).
  - A contour starting at X0 with a non-face cut (a dome, a cone point) gets the
    same centre entry, then flows straight into it.
- Result: no nib and a flat face on the NX OD part (X start 0, first point
  X.2362), the Hemisphere dome and flat-face → chamfer. Facing off (X start = stock
  OD) leaves the face untouched. All are tests.

**Bug caught and fixed in the same round:** the "enter in line with a sloped
first cut" rule from fix 2 also fired on a near-radial lead and extended it to
**X18.2** (only on this unmerged branch). It now requires ≥ 15° of slope.
`test_cut_regions` also checks that every generated program stays inside a sane
X/Z envelope.

**Robustness:** the section boolean operations now run snap-rounded on a 1e-7"
grid and keep only polygonal results. The centre-overshoot entry produced
near-coincident edges that made plain GEOS overlay fail.

**Still open:**
- Chamfer-first profile refusal: the cleanup's .0007–.0029 step at the face →
  chamfer corner (§8).
- Item 3: the graph flagging leftovers in front of Z0.
- Item 4: the Hemisphere cleanup at larger allowances.
- Observed, not changed: with facing off but stock in front of Z0 (Z start > 0),
  roughing starts at Z+fin/2 as if the face were clear, and the finish and cleanup
  leads cross the uncut stub between the first point and the stock OD.

## 10. 1a done: face chamfer / rounded edge at the start of the profile (2026-11-11)

- **Cleanup** (`cleanup_planner._face_level_extension`): when an OD offset contour's
  first cut starts below the face-allowance level (the offset of a chamfer or
  rounded edge), the first cut is run back along its own line or start tangent to
  the face level, instead of a .0007–.0029 vertical step. The cleanup then runs
  along the face and straight down the chamfer in one motion; the corner lands
  exactly at the true offset intersection (X.6083 Z.010 in the example). That step
  had made an inside corner LinuxCNC comp can't make, so the program was refused.
- **Facing off with the face already at Z0:** `StockDef.face_at_z0` (set by
  `model_builder` when the operator's Z start ≤ allowance; the old Z-start bump
  hid that fact). The inward lead over the finished face is air, and the writer
  drops it. Passes then enter in line with a chamfer, or straight down a
  diameter, instead of reversing onto it under comp (the ID mouth-chamfer problem,
  mirrored).
- **Results:** chamfer-first (faced, at .005 and .020 allowance), a rounded edge
  first, chamfer-first with facing off and the face at Z0, and the same chamfer
  drawn as a V1 corner break all generate and check clean. Saved programs are
  unchanged and clean.
- **Still open (item 3):** facing off with stock left in front of Z0 (Z start >
  allowance, X start = stock OD). The passes still come in on the inward lead and
  the graph flags the chamfer top red.
