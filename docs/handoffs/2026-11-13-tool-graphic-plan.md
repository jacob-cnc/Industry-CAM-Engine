# Plan: true-scale tool graphic on the Manual, Run and sim screens

Status: PLAN ONLY, owner decisions recorded 2026-11-13 (section 9): insert only (no holder, no bar),
IC from ISO code or field, material removal in sim AND live. Written by Claude at the owner's request.

## Owner's request (verbatim, 2026-11-13)

> Let's make a plan to accurately represent the cutting tool on the screens graphic, with the tool
> nose being displayed in its exact location both during manual jogging as well as during program
> runs. The current dot can stay for when a tool is not assigned yet, but once a tool is assigned
> such as swapping to tool 1 on startup, the representation should change to show that tool's
> graphic. I want to achieve the same level of granular accuracy as much as possible, so it's a
> useful tool for operators to visualize what is happening or what will happen. I think it will
> also support showing material removal during sim or live cuts as well, but that's a secondary goal

## 1. How the screens draw the tool today

| Screen | Widget | Tool shown as | Position source |
|---|---|---|---|
| Manual | `gui/components/position_graph.py` | 14 px white dot + trail | `s.x.position`, `s.z.position` from a 100 ms poll (`manual_tab._setup_polling`) |
| Run (live) | `sim_viewer.update_live_position` -> `graph_widget.set_tool_position` | 16 px dot | the same work position, from the Run tab poll |
| Run / Edit (sim) | `sim_viewer._update_display` | 16 px dot | the program's own G-code parser (`parse_gcode_for_sim`, with a hand-written G76 expansion) |

Where the position comes from: `hal/live_backend.py` gives work coordinates as
`actual_position - g5x - g92 - tool_offset`. `actual_position` is the feedback position (the linear
scales), and `tool_offset` already includes wear (tool.tbl stores geometry + wear together). With a
tool loaded, that number is the tool's **controlled point**: in LinuxCNC that is the imaginary tool
tip for orientations Q1-Q8 and the nose centre for Q9.

The insert shape already exists, but only as a 160 px picture in the tool editor
(`gui/components/orientation_graphic.py`). Its maths sits in the widget, and it has had Q-mapping
bugs before (fixed 2026-11-08).

## 2. Problems to fix for "exact"

1. **A dot has no size.** The operator can't see where the nose radius, the edges or the holder are.
2. **The sim does not follow tool-nose compensation.** The writer uses G41/G42 on every cutting pass
   (`outputs/gcode_writer.py:648`). The sim parser draws the programmed path, but LinuxCNC drives the
   controlled point along the *compensated* path. The difference can be as large as the nose radius
   (about .016 for T4). The sim's G76 expansion is also our own code, not LinuxCNC's.
3. **10 Hz is too slow.** At a .75 in/s Z rapid the dot falls up to .075 behind between polls.
4. **Two pieces of insert maths.** The editor picture and the new screen graphic must come from one
   source, or they will drift apart (as Q1-Q4 did).

## 3. Design

### 3.1 One tool-outline model (new, `geometry/tool_outline.py`)
- `tool_outline(tool) -> ToolOutline` returns these pieces in the tool's frame, with the controlled
  point at (0, 0), in true inches:
  - the nose arc: centre and radius;
  - the two cutting edges, from front and back angles (tool.tbl I/J) and the edge length;
  - the full insert polygon;
  - the holder polygon (section 3.2).
- It is built with geometry kernel calls, in keeping with the no-hand-math rule. Q1-Q9 place the nose
  centre relative to the controlled point (Q2 = -X,-Z for a right-hand OD tool and so on: the same
  table already corrected in `orientation_graphic.py`).
- Placing it on screen is a single translate to the current work position. It is drawn as radius vs Z
  on the plot, which is 1:1 aspect-locked, so the shape is true scale at every zoom. The plot's
  inverted Y is handled once, in the model-to-screen step.
- `orientation_graphic.py` is switched to use the same model, so the tool editor shows exactly what
  the screens show.

### 3.2 Data needed that the tool table doesn't have yet

| Need | Today | Proposal |
|---|---|---|
| Insert size (IC / edge length) | not stored (`edge_length=0.0`, "not tracked") | Read it from the full ISO code (CNMG **43**2 -> IC 1/2", r 1/32) when one is given. Otherwise add an IC field to the tool editor. |
| Nose radius, angles, Q | in tool.tbl (D, I, J, Q) | as now |
| Grooving / threading insert | `blade=` width; thread form | Draw the blade width, or the thread form's included angle |
| Holder | not stored | **Owner choice (section 9, Q1)** |

New fields go in the existing tool.tbl comment (`;ice=2|...|ic=0.500|holder=...`), like `insert=`
and `blade=` today. LinuxCNC ignores the comment, so `tool.tbl` remains a valid table.

### 3.3 When the dot is shown and when the tool is shown
- `tool_in_spindle == 0`, an unknown tool, or a tool with no shape data -> the dot (as now).
- After a T-change (`tool_in_spindle` changes) -> that tool's outline. A tool table reload or a wear
  edit rebuilds the outline.
- A small cross is always drawn at the controlled point, and optionally at the nose centre. The DRO
  number then lands on a visible mark.

### 3.4 Position and refresh
- Live: the feedback position, as now. The X and Z scales resolve .0002 (5 um), which sets how
  accurate the graphic can be. The screen shows where the tool *is*, not where it was commanded,
  so following error appears as it really happens.
- Refresh rate goes from 10 Hz to about 30 Hz for the graphic only. Each update just moves one
  existing plot item; nothing is redrawn. I measure the GUI's CPU use before and after.
  `linuxcnc.stat` polling is userspace, so the RT side is not involved, but I will not run any
  stress test (owner rule): just normal use with `top`.
- Live run: the same item, on the Run screen's graph.

### 3.5 The sim draws what LinuxCNC will do
- The sim gets its path from LinuxCNC's own interpreter: the rs274 canon already used for cycle time
  and cut regions (`validation/cycle_time._canon`). That canon already includes G41/G42
  compensation, G76 and G33 passes, and the tool table offsets, so sim positions are the controlled
  point positions the machine will reach. The hand-written G76 expansion and the parser's
  positioning role are removed (the G-code line highlighting keeps using line numbers from the
  canon).
- The tool outline then follows the canon path, changing tool at each `CHANGE_TOOL`.

### 3.6 Material removal (secondary, phase 5)
- The material removed by each move is the tool shape swept along that move: the outline's convex
  hull at the start and end of a straight move, or sampled along an arc. Built with the geometry
  kernel / Shapely and subtracted from the stock polygon.
- **Sim:** computed in advance from the canon, so playback, stepping and scrubbing just look up the
  result.
- **Live:** updated as the program runs, sweeping between successive feedback samples. This only
  happens while the spindle is on and the move is a feed move, and repeated samples are merged.
- This also allows a warning before anything is cut: the *holder* or the *back of the insert*
  touching the stock in the sim is drawn red (holder collision / rub), which is the "what will
  happen" part of the request. It complements `geometry/tool_reach.py`, which checks only the edges.
- The existing `material_states` (from the planner, at pass level) stay for Program-tab preview;
  the sweep replaces them on the Run/sim screens.

## 4. Accuracy checks (how "exact" is proven)

1. **Unit:** for each Q1-Q9 and each insert in `insert_geometry_lookup`, check that:
   - the outline's controlled point is at (0, 0);
   - the nose centre is at the right offset;
   - the edges leave at the I/J angles.
2. **Against LinuxCNC comp:** for a G42 contour through the canon, the nose arc must touch the
   programmed profile at every point (distance from the nose centre = r, within .0001).
3. **Screen:** an offscreen render at a known zoom. Check pixel positions of the tip and the nose
   arc against the model (catches the inverted-Y / mirror mistakes the old widget made).
4. **On the machine (owner):**
   - Touch off T1 or T4.
   - Jog the nose to a gauge pin or a faced shoulder and compare the screen with reality at high zoom.
   - Run an air cut and check that the sim and the live graphic lie on top of each other.

## 5. Where the code goes (architecture)
- Outline maths: `geometry/tool_outline.py` (kernel only). The tool data fields go in
  `tools/tool_card_data.py` and `models/tool.py`.
- The graphics item is one shared `gui/components/tool_graphic_item.py` (a pyqtgraph item), used by
  `position_graph.py`, `graph_widget.py` and `sim_viewer.py`.
- Sim path: a new `validation/` or `pipeline/` function that turns canon into timed controlled-point
  samples, with no G-code parsing in the GUI.
- Material sweep: `geometry/` (kernel / Shapely).
- I run the architecture ratchet as I build and flag any new violation before merge.

## 6. What doesn't change
- The DRO numbers and the wear-offset workflow (owner: keep as is).
- tool.tbl's LinuxCNC fields. New data goes only in the comment.
- The dot stays as the no-tool state.

## 7. Risks
- **Missing data:** a tool without IC data falls back to drawing only the nose and edges, at a nominal
  length, labelled "size unknown". The tool is never drawn at a made-up size without saying so.
- **Q settings:** a wrong Q in the table puts the graphic in the wrong place. Today's dot hides that
  mistake; the outline will show it.
- **Live material removal:** depends on the feedback samples. At 30 Hz a .010/rev feed at 1000 RPM moves about .006
  between samples, so the swept shape is fine. Fast rapids are excluded anyway.

## 8. Phases (each one is shippable and testable on its own)
1. **T1 - outline model + data.** The `tool_outline` model (insert only), IC from the ISO code / editor
   field, and the tool editor picture switched to the model. Unit tests (4.1).
2. **T2 - Manual screen.** Tool graphic in place of the dot once a tool is loaded, the cross at the
   controlled point, 30 Hz update, and an update on tool change and wear edit. Render test (4.3).
3. **T3 - Run screen, live.** The same item on the Run graph during program runs.
4. **T4 - Sim from LinuxCNC's canon.** Compensated path, G76/G33 as LinuxCNC runs them, tool
   change per T word. Comp test (4.2). Owner air-cut check (4.4).
5. **T5 - material removal (secondary).** The sim sweep first, then the live sweep, with the
   back-of-insert rub warning.

## 9. Owner decisions (2026-11-13)

> 1: no holder representation  2: yes  3: not going to represent the bar itself
> 4: both during real cuts and simulation if possible

- **No holder** and **no boring bar** are drawn. The graphic is the insert only: the nose arc, the
  cutting edges and the insert body at its true IC size. The holder rows in sections 3.1 and 3.2 and
  the holder-collision part of the warning in 3.6 are dropped. The warning in 3.6 is kept only for
  the **back / non-cutting side of the insert** touching the stock in the sim.
- **Insert size:** read the IC from a full ISO code (CNMG432 -> 1/2") when one is typed, otherwise from
  a plain IC field in the tool editor.
- **Material removal:** both the sim (computed in advance from the canon) and real cuts (live sweep
  between feedback samples, spindle on, feed moves only), as in 3.6 / phase 5.

### Original questions (answered above)
1. **Holder:** how much of the holder to draw?
   - (a) insert only;
   - (b) insert plus a generic holder outline sized from a shank width / head length typed per tool
     (recommended: enough to see clearance into a shoulder or a bore, and it enables the rub
     warning);
   - (c) measured holder outlines per tool.
2. **Insert size:** read the IC from a full ISO code (e.g. "CNMG432") typed in the editor, or a
   plain IC field? (Recommended: both. Use the ISO code when it's given, and the field otherwise.)
3. **Boring bars:** draw the bar's diameter along its length as well (shows bar-to-bore clearance)?
4. **Live material removal:** wanted during real cuts too, or the sim only? (It is about the same
   work once the sim version exists.)

## 10. Implementation notes

### T1 (2026-11-13, branch claude/tool-graphic-build)
- `models/tool.py`: `InsertSpec` (Q, nose radius, I, J, shape, IC, blade width).
- `tools/insert_geometry_lookup.py`:
  - `INSERT_SHAPE` maps each insert family to its body shape.
  - `parse_iso_code` reads the inch codes (ANSI B212.4: IC n/8", radius n/64") and the metric codes
    (ISO 1832: edge-length digits -> IC for the common sizes; radius in 0.1 mm).
  - A size it can't read returns None; it never guesses.
- `tools/tool_card_data.py`:
  - `iso_code` / `ic` fields.
  - `insert_spec(card)`: IC from the field, else from the ISO code, else unknown.
  - `iso_radius_mismatch(card)`: a note when the ISO code's nose radius differs from the table's D/2.
- `tools/tool_table_io.py`: `iso=` / `ic=` in the comment, written only when set, so existing lines
  are unchanged (the repo `tool.tbl` round-trips byte-identical).
- `geometry/tool_outline.py`: `tool_outline(spec) -> ToolOutline`, built with build123d / OCCT only
  (no trig; the architecture ratchet is unchanged).
  - Shapes:
    - rhombic bodies (C, D, V, S, custom): two strips of width IC crossing at the included angle;
    - T and 60 deg thread: three half-planes;
    - W: six half-planes;
    - 55 / 29 deg thread: the tooth wedge cut to the IC triangle (body nominal, edges exact);
    - groove: blade width x length;
    - R: a circle.
  - Corners are filleted with the nose radius. The body is then turned so its bisector is at
    (I+J)/2 in the Q frame, and the nose centre is placed at controlled point - r * Q direction.
  - Arc samples include the quadrant points, so the outline reaches the true touch-off lines.
  - Unknown edge angles (I0 J0, non-round) raise ValueError with a reason: the screens keep the dot.
  - An unknown size is drawn at a nominal IC (thread .375, groove .25, others .5), flagged
    `size_known=False`.
- `gui/components/orientation_graphic.py`: the editor picture is now drawn from `tool_outline` (the
  old hand-built shapes and the Q mirror tables are gone). It shows a reason when the insert can't
  be drawn, and "size not set" when the size is nominal.
- `gui/components/tool_geometry_row.py`: ISO code and IC fields, plus a warning label for an
  unreadable code or a nose-radius mismatch.
- Tests: `tests/unit/test_tool_outline.py`:
  - Q1-Q9 nose centre; the 95 deg holder touching both touch-off lines (Q1-Q4);
  - edge angles for 4 I/J pairs x 4 Q;
  - the ISO inscribed circle for C, D, V, S, T, W;
  - round Q9; groove; nominal size; refusal; ISO parsing; IC priority;
  - tool table round trip.
- Full suite 1463 passed.
- Current tool table: T1 (CCMT, Q3), T2 (60 deg thread, Q2) and T4 (CNMG, Q2) draw at a nominal size until an
  ISO code or IC is entered. T3 (Custom) and T99 (QCTP master) have I0 J0 and keep the dot.

### T2 (2026-11-13, branch claude/tool-graphic-build)
- `gui/components/tool_graphic_item.py`:
  - `ToolGraphic` is one object per graph: a filled body path, the cutting edges, a "+" at the
    controlled point, and the dot plus a note. The path is built once per tool; motion is just
    `setPos` (pens are cosmetic, so line widths stay the same at any zoom).
  - `graphic_for(card, tool_in_spindle, tool_offset)` returns the outline, or None with a reason:
    - no tool -> plain dot;
    - "Tn is not in the tool table";
    - **"offset not active (G43)"**: LinuxCNC's active tool offset differs from the card's
      geometry + wear, so the work position is not this tool's controlled point. The dot is
      shown instead of a misplaced insert;
    - edge angles unknown.
- `PositionGraphWidget` (Manual):
  - The dot is replaced by `ToolGraphic`.
  - `set_tool_outline(outline, note)`; `move_tool(x_dia, z)` (tool only, no trail).
- `ManualTab`:
  - A 33 ms (~30 Hz) graphics timer runs only while the tab is visible. It reads
    `backend.work_position()` and moves the tool; the 100 ms poll keeps the DRO, trail etc.
  - The tool graphic is rebuilt on a tool change, an active-offset change, or a table edit / reload.
- `HALBackend.work_position()`: a fresh feedback position with no side effects. The live backend
  polls `linuxcnc.stat` only; it does **not** drain the error channel, which `poll()` does, so a
  faster graphics read cannot swallow an error the rest of the GUI should show.
- Wiring (`MainWindow`): `ManualTab.set_tool_card_resolver(ToolsTab.get_tool)`. `tool_changed` and the
  new `ToolsTab.tools_reloaded` (emitted by `_accept_table`) trigger `refresh_tool_graphic()`.
- `hal/interface.py`: the `tool_offset_x` comment corrected to RADIUS (it always held `tool_offset[0]`).
- Tests: `tests/unit/test_tool_graphic_screen.py`:
  - the controlled point maps to the DRO position's screen pixel (1e-6), and +X is down;
  - `move_tool` moves only the tool;
  - the dot and its reasons; the G43 mismatch; `work_position`.

### T3 (2026-11-13, branch claude/tool-graphic-build)
- `MachiningGraphWidget` (Run / sim graph):
  - The dot is replaced by `ToolGraphic`, rebuilt lazily after `clear()` (a program load clears
    every plot item).
  - `set_live_tool_outline(outline, note)` holds the spindle tool.
  - `set_tool_position(x_r, z, live=False)`: live=True draws the spindle tool. Sim playback
    (live=False) keeps the dot until phase T4 gives the sim each move's own tool (the spindle
    tool would be the wrong tool for a multi-tool program).
- `SimViewerWidget`:
  - `show_machine_position` / `update_live_position` pass live=True.
  - `set_live_tool_outline`.
  - `move_live_tool` moves the tool only, and not while sim playback is running.
- `RunTab`:
  - The same `graphic_for` logic as Manual (G43 check, reasons).
  - A 33 ms graphics timer runs only while the tab is active.
  - Wired from `MainWindow` with `ToolsTab.get_tool`, `tool_changed`, `tools_reloaded`.
- Tests: the live tool vs the sim dot on the Run graph; the tool survives `clear_toolpath()`.
- Already there, not caused by this branch: `tests/unit/test_run_from_line.py` aborts when run by
  itself (it does on main too: its teardown closes a RunTab that Qt has already deleted). It passes
  in the full suite.

### T4 (2026-11-13, branch claude/tool-graphic-build)
- `validation/sim_path.py`: the program goes through rs274 (`cycle_time.prepare` + `_canon`) with the
  machine's INI and `tool.tbl`. Each code line is given its line number as an N word first, so every
  canonical move carries its source line.
  - Segments: rapid / feed / arc / thread (between START/STOP_SPEED_FEED_SYNCH), with the tool from
    SELECT_TOOL + CHANGE_TOOL and the offset from USE_TOOL_LENGTH_OFFSET (None after a change with no
    G43). G21 programs are scaled to inches.
  - Positions are program coordinates of the controlled point (checked: no G5x or tool offset in
    them), the same point the live graphic puts at the DRO position.
  - **Comp line lag:** under G41/G42 rs274 prints each move under the NEXT motion block (it holds the
    move to find the corner). Those moves are given back to the last line before it with an X/Z/I/K
    word. Tested with G42 on its own line and an F-only line in between.
  - An interpreter error returns the path up to there plus the message (error text + the block).
    `cycle_time` gets the same clearer message.
- **Comp check (4.2) passes:** under LinuxCNC's own G42, the nose centre stays R from the programmed
  chamfer / straight / R.1 fillet / shoulder within .0001 (rs274 prints 4 decimals).
- **G76 in G7:** LinuxCNC reads G76 I / J / K as diameters (halved). `threading_planner` already
  writes them as diameters - checked, no change.
- `gui/components/sim_viewer.py`: `build_sim_moves(gcode) -> (moves, note)` used by the Run, Edit and
  Program tabs.
  - Each move draws with its own tool's outline, read from the same tool.tbl the interpreter used.
    Dot + reason for no G43 / not in table / angles unknown; "size not set" for nominal sizes.
  - The drawn toolpath is still the programmed path; reveal maps each interpreter move to the
    segment of its own line.
  - Without rs274 installed (not the lathe) the old G-code parser is used and the note says
    "Approximate ... without cutter comp". `parse_gcode_for_sim` (with its G76 expansion) stays only
    for that and for the line-to-segment map.
- Speed: `tool_outline` took ~1.4 s per tool (build123d find_tangent). Quadrant points are now found
  with `param_at_point` (~.03 s) and outlines are cached. This also removes a >1 s freeze on a tool
  change on Manual / Run (T2/T3). A 318-line program builds its sim in ~.4 s.


### T5 (2026-11-13, branch claude/tool-graphic-build)
- `validation/material_sweep.py` (not `geometry/` as section 5 said: the architecture rule allows
  Shapely only in validation/, where cut_regions does its sweeps).
  - Each move removes the insert outline swept along the interpreter's own points. The outline is
    convex, so each straight step sweeps exactly the convex hull of the two placements. The nose
    arc is kept at full resolution; the rest of the body is simplified to .0001.
  - Only feed / arc / thread moves cut. Only the steps where the insert meets the stock are swept.
  - **Rub:** stock met by a LEADING non-cutting edge (anything but the nose and its two edges) on a
    feed move. **Rapid into stock:** stock in a rapid's sweep. Both count only where the material is
    thicker than .004 (GRAZE): the nose-radius cusp a pass leaves at a shoulder, grazed by the
    retract, is not a crash.
- Stock: from the program header (`outputs/program_header.py`). A program without one gets no material
  and says so (never guessed). The writer now adds `; Stock Face Z:` (StockDef.face_at_z0). Older
  programs use cut_regions' rule (face at Z Start, not ahead of Z0) and the note says so.
- Sim: computed in a background thread after loading (~.3 s for the GCH bore, ~7 s for a 3,600-line
  roughing program). Playback looks up each move's result; inside a cutting move the part done so
  far is swept on the spot (median 12 ms, p95 16 ms per frame). Rubs / rapids are drawn red hatched
  and listed in the info line. "Hide Material" button.
- Live (Run tab): when a program starts the bar resets (Run From: the sim's bar before that line).
  The spindle tool is swept between 30 Hz feedback samples while the measured spindle speed is over
  5 RPM and LinuxCNC's motion_type is feed / arc (new `motion_type` in MachineState and
  `motion_sample()` read with the position). Redrawn ~10x a second; kept after the program ends until
  the sim is played.
- Found with it: "Regenerated 2026-11-10 (arc fix)/GUI Conv Test (T4).ngc" on the Desktop has 27 arcs
  that LinuxCNC runs as 353-359 deg near-full circles (e.g. line 177, N1040 G02). Do not run that
  file. The same job regenerated with current main has no long arcs and no warnings.
