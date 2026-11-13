# Plan: true-scale tool graphic on the Manual, Run and sim screens

Status: PLAN ONLY (2026-11-13). Written by Claude at the owner's request; no implementation until
the owner approves it and answers section 9.

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
1. **T1 - outline model + data.** The `tool_outline` model, IC from the ISO code / editor field,
   the holder data (per Q1), and the tool editor picture switched to the model. Unit tests (4.1).
2. **T2 - Manual screen.** Tool graphic in place of the dot once a tool is loaded, the cross at the
   controlled point, 30 Hz update, and an update on tool change and wear edit. Render test (4.3).
3. **T3 - Run screen, live.** The same item on the Run graph during program runs.
4. **T4 - Sim from LinuxCNC's canon.** Compensated path, G76/G33 as LinuxCNC runs them, tool
   change per T word. Comp test (4.2). Owner air-cut check (4.4).
5. **T5 - material removal (secondary).** The sim sweep first, then the live sweep, with the
   holder / back-of-insert rub warning.

## 9. Questions for the owner
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
