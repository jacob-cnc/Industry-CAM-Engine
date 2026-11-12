# Plan: one part model, operations on segment groups, STEP / DXF import

Status: PLAN ONLY (nothing implemented). Written 2026-11-12 by Claude at the owner's request.
Change classification when implemented: Software-only (phases 1-3), Motion-affecting (phase 4).

## Owner's request (verbatim) and decisions

> Start planning out, not implementing, the step DXF import [...]. Ideally it should populate the
> profile segments, but a user will need to work backwards to assign the correct block type to the
> profile segment with the architecture we've currently got. It might be a good sign to pull the
> profile segments out of the block and let blocks be assigned to profile segment groups. Noodle on
> this for awhile and see what you can come up with

Owner answers to the open questions (2026-11-12):

1. **OD and ID are separate** (an operation targets one of them), **but they may overlap at the face
   if the user chooses.**
2. **Operations may overlap** (e.g. rough the whole OD, finish only part of it with another tool).
3. **DXF = a half section, radial**: "like the sketch that would be revolved to make the solid model"
   (Z along the axis, radius - not diameter - across).
4. **Recognised fillets / chamfers become corner breaks**, unless that is prohibitively difficult or
   confusing for the converter; keeping them as plain geometry is not an issue.
5. **Op1 / Op2 stay separate programs** - no setup integration.

Everything below the line is design advice, to be confirmed phase by phase.

---

## 1. Where we are and why it hurts

A **block** is the unit of everything (`models.program.ProgramBlock`, `params_data`):

- each OD / ID profile block owns its segments AND its own stock / roughing / finishing fields;
- threading and grooving blocks carry diameters and Z ranges **typed by hand**, independent of
  any profile;
- nothing knows what an earlier block removed.

The owner's Quarter-20 Cap Screw Op1 shows the cost:

- the relief groove (Ø.19, Z-.72..-.78) is drawn **inside** the OD profile, so a turning tool is asked
  to make it and tool reach leaves its back wall uncut;
- the threading block **repeats** the profile's geometry by hand (major .2448, end Z -.77) and only
  matches because the owner kept them in step;
- a second operation cannot know the first already removed material ("rest machining", bookmarked)
  and cross-operation collisions can't be checked.

## 2. Target model: the part first, operations on segment groups

### 2.1 Part

```
Part
  units, datum: Z0 = the faced front surface (as today; owner 2026-11-11)
  stock: diameter, pilot hole, Z start (cushion), back face           (one, shared)
  od:  Chain    - outer contour, front to back
  id:  Chain    - bore contour, mouth to back (optional)
Chain
  segments: [Segment]            each with a PERMANENT id (operations survive edits)
  corner_breaks: {vertex id: CornerBreak}   (as today, attached to vertices)
Segment
  id, type (line | arc | quadrant), end point (Ø, Z), radius / quadrant sign (as today)
```

- The **front face** is where OD and ID may meet (owner answer 1): it is part of the OD chain's
  start and, for a bored part, of the ID chain's mouth. An operation on either chain may include it;
  which operation cuts it is the user's choice.
- Segment rows, corner breaks, quadrant arcs, the corner-break tool and the engine-drawn preview all
  stay as they are - they move from the block to the part.

### 2.2 Operation (today's "block")

```
Operation
  id, type, tool(s), enabled, label, user settings (feeds, DOC, passes, ...)
  target: (chain: od | id, first segment id, last segment id)   - a contiguous run
          or none for "manual" operations (see 2.4)
```

| type | target must be | taken from the geometry | the user sets |
|---|---|---|---|
| Turn (OD / ID; rough + cleanup + finish) | any run on one chain | the profile for the pipeline (today's ClosedProfile, unchanged planners) | strategy, DOC, feeds, allowances, tools |
| Groove (OD / ID) | a recess: wall - bottom - wall | Z start / end, width, depth, bottom Ø | blade, pecks, feeds |
| Thread (OD / ID) | ONE straight Z segment | major Ø (OD) / minor Ø (ID), Z range | standard, pitch, class, passes; warns if the segment Ø doesn't suit the class (e.g. .2448 vs 1/4-20 2A) |
| Part-off | the back of the part | Z | blade, feeds |

- **Operations may overlap** (owner answer 2). The list order is the machining order.
- **In-process stock** (phase 4): the material left after each operation = stock minus what the earlier
  operations remove (computed from their G-code as LinuxCNC runs it - the machinery behind the
  cut-section and rapid checks). That gives: rest machining (an uncut tool-reach region becomes a
  ready target for the next operation), collision checks against the material that is really there,
  no air-cutting over material an earlier operation already took.

### 2.3 Engine adapter

A Turn operation becomes today's `ClosedProfile` (its run of segments + corner breaks, the engine
adds the closure) and today's pipeline runs **unchanged**. Groove / thread operations fill today's
`GroovingParams` / `ThreadingParams` from the geometry. So phases 2-3 are a data-model and UI change;
the planners don't move.

### 2.4 File format v3 and migration

```json
{ "version": 3,
  "part":  { "stock": {...}, "od": {"segments": [...], "corner_breaks": {...}}, "id": {...} },
  "operations": [ {"id": 1, "type": "turn_od", "target": {"chain": "od", "from": "s1", "to": "s6"},
                   "tool": 4, "settings": {...}}, ... ] }
```

- v1 / v2 load through a converter: each old profile block becomes its segments (as a chain) plus one
  Turn operation over all of them; old threading / grooving blocks become **manual** operations with
  their typed values kept. Acceptance: every corpus program regenerates **text-identical** G-code
  through v3 (scripts/regression, as for every merge this week).
- Two profile blocks of the same side (rare) - the converter keeps the first as the chain and reports
  the second as a manual turn operation; decide case by case if one shows up.

## 3. Import: two front ends, one result

Both produce: an OD chain and/or an ID chain in radius space (r, z), units converted to inches,
plus recognised corner breaks - then a **preview** where the user confirms.

### 3.1 STEP (solid model)

Probed 2026-11-12 on the owner's NX fixture `tests/fixtures/nx_corner_break/broken.stp`:

- **Axis**: the common axis of the cylinder / cone / torus faces (found: model X through the origin).
  Refuse if they don't share one axis ("not a turned part").
- **Profile elements from the faces, not a boolean section.** A boolean cut through the axis
  returned B-SPLINE approximations even for straight cylinder and chamfer edges (that would need
  curve fitting - hand math). Instead each face of revolution generates one exact element:
  cylinder / cone -> line, plane (disc) -> radial line, torus / sphere -> arc (centre, radius from the
  surface). This is what `tests/unit/test_corner_breaks_od_nx.py::nx_elements` already does.
- **Chain** the elements by end points into the boundary loop of the half section; split it into the
  OD chain (outer, from the front face to the back) and the ID chain (bore); the faces between are
  the front / back faces.
- **Units**: STEP carries them (NX fixtures are mm) -> inches.
- **Refuse** with a clear message: spline surfaces of revolution, non-revolved features (flats, cross
  holes, knurls - list what was ignored), no common axis.

### 3.2 DXF (the revolve sketch; owner answer 3)

- Entities: LINE, ARC, LWPOLYLINE / POLYLINE with bulges (ezdxf 1.4.4, already in
  requirements-lathe.txt). SPLINE / ELLIPSE refused.
- **Axis**: the sketch's centreline - a line on a CENTER linetype or a chosen layer; otherwise the
  user picks it on the preview. Z along it, radius across (not diameter).
- **Chain** with a small gap tolerance (reported if closed); same OD / ID split as STEP.
- Optional layer filter (construction / dimension layers ignored).

### 3.3 Orientation (Z0) - both formats

The preview shows the chains; the user picks **which end is the front (Z0)** and can flip the part
end-for-end. (Op1 / Op2 are separate programs - owner answer 5 - so each import picks its own end.)

### 3.4 Corner-break recognition (owner answer 4)

Turn a short element between two longer ones into a corner break on the sharp outline when it is
unambiguous; otherwise keep it as plain geometry (no harm):

- **Fillet**: an arc tangent (within 0.01°) to both neighbours -> fillet R at their intersection.
- **Chamfer**: a line whose two ends are equal distances (within .0005) from the neighbours'
  intersection -> equal-leg chamfer of that size.
- Rebuild check: the corner solver (`geometry/corner_breaks_od.py`) must reproduce the imported
  element exactly (same end points, same centre / radius - the NX test's 1e-3 mm criterion), or the
  element stays plain geometry. So a conversion can never change the part.
- Neighbours that are arcs: the solver handles them since C1 (kernel fillet / chamfer), so the same
  rule applies.

### 3.5 Suggested operations after import

From the shapes: "Turn OD, segments 1-6"; "Groove, segments 3-5 (.060 wide, Ø.19)" for a recess; "Thread?
segment 1, Ø.2448 fits 1/4-20 2A" for a straight segment whose Ø matches a standard major. The user
accepts, edits or deletes each.

## 4. Program tab workflow (phase 3)

- **Part editor** = today's segment builder (OD / ID tabs), unchanged behaviour.
- **Operation list** = today's block list; selecting an operation highlights its segment run on the
  graph and in the table; geometry-derived fields show read-only with their source ("from segment 1").
- **New operation from selection**: select rows or graph segments -> type suggested from the shape.
- Editing the part re-derives every operation's geometry; an operation whose target became invalid
  (e.g. a groove that is no longer a recess) is flagged, not silently changed.

## 5. Phases (each usable on its own; each verified before it moves on)

| # | Delivers | Verification |
|---|---|---|
| 1 | **Import into today's segment builder**: STEP / DXF -> the active OD or ID block's segments (+ corner breaks), preview + Z0 choice. No restructure - the user assigns blocks by hand, as today. | Import the NX fixtures (sharp / broken / id_*) and compare with their known profiles (the NX tests' element match); a DXF of the same parts; refusal messages for splines / no axis. |
| 2 | **Data model v3** (Part + Operations) + v1/v2 converter + engine adapter. No UI change. | Corpus regenerates text-identical through v3; round trip v2 -> v3 -> save -> load. |
| 3 | **Program tab**: part editor + operation list with targets; thread / groove params from geometry; suggested operations after import. | GUI tests offscreen (as the preview / run-control tests); the Cap Screw rebuilt as Turn + Groove + Thread operations gives the same thread and a proper groove. |
| 4 | **In-process stock between operations**; rest machining of tool-reach regions; collision / gouge checks against the real remaining material. | rapid / cut-section checks per operation against the accumulated material; corpus; owner first-article. |

Phase 1 is small and independent. Phases 2-3 are the restructure. Phase 4 is where the extra machining
value is (and needs owner review: it changes motion).

## 6. Risks and how they are handled

- **Breaking saved programs** - v3 converter + text-identical corpus gate (phase 2).
- **Imported geometry the engine can't cut** (splines, undercuts beyond the tools) - refused at import
  with the reason; tool reach still reports what a tool can't reach.
- **Ambiguous corner breaks** - only converted when the corner solver reproduces them exactly.
- **Segment ids vs. edits** - operations reference permanent ids; inserting / deleting rows never
  re-targets an operation silently.
- **Architecture** - import code lives in `geometry/` (kernel reads STEP, faces of revolution) and a
  new `tools`-level or `geometry/` DXF reader; the GUI only calls them (rule (a) unchanged).

## 7. Still to decide (owner)

- Phase order: start with phase 1 alone (quick value), or go straight to 2-3?
- Thread suggestion tolerance: how far off the standard major may a segment be before the suggestion
  is dropped (class 2A / 3A limits from the thread tables)?
- Should an import also set the stock (bar Ø = next size up from the part's max Ø + a margin), or
  leave stock to the user?
