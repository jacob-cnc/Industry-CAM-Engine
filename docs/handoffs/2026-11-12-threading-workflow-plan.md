# Plan: threading as a field-driven operation (straight and tapered, standard thread lists, hints)

Status: IMPLEMENTED on branch `claude/threading-build` (2026-11-12, owner said go) - see section 10. Not merged; needs owner review + air cut. Written 2026-11-12 by Claude at the owner's request; owner
decisions recorded the same day (section 8).
Change classification when implemented: **Motion-affecting** (new tapered-thread motion, new ID retract).
Companion to `2026-11-12-part-model-and-import-plan.md` (threads do NOT use profile segments).

## Owner's request (verbatim, 2026-11-12)

> threads will not use the profile segments, they should have a user input field based workflow. Input
> fields should be 'X start, X end, Z start, Z end, pitch, RPM, number of passes, # of spring passes,
> # of starts, entry angle. (Am I missing anything?) this should allow for both straight and tapered
> threads of any size and pitch. I'd also like there to be a drop down list of common UNC, UNF, Metric
> Coarse, Metric Fine, Metric Trapezoidal, and Acme threads where a user can choose a thread type and
> fit class (2a/b or 3a/b, 1a/v isn't common enough to include) and the user fields will auto populate
> the X values (nominal major dia) and pitch. It would be helpful also if there was a 'hint' or 'tip'
> that displayed for the user the acceptable pitch diameter tolerance window for OD threads after
> choosing a thread type and fit class, and for ID threads the nominal pilot hole diameter and drill
> size. Retractions should be always above nominal major dia for OD and always below pilot hole size
> for ID threads. OD retractions can be nominal OD + .020" dia, ID threads will need to be a bit
> tighter, pilot hole dia - .005" dia.

Follow-up (verbatim, 2026-11-12):

> Yes, add OD/ID signifier and tool # fields. Thread depth should be calculated from ASME standards and
> fit class not user entered. Yes on pilot dia for ID. Z end should be used at where the tool pulls
> out. Good call on the hints. For ID threads just pick the tap drill size, don't worry about boring.
> Yes there needs to be a custom thread option as well. I agree with your list of fit classes. Include
> NPT as a preset just like the other thread types which auto populate. No LH threads at this time.

## 1. Fields

| Field | Entered / derived | Notes |
|---|---|---|
| OD / ID | entered | Sets the infeed direction, the retract rule and which hint is shown. |
| Tool # | entered | Tool angle checked against the thread form (60 / 29 / 30 deg) at Generate. |
| Thread type + class | entered (drop-down) | Section 2. Choosing a size fills X start, X end and pitch; "Custom" is the first entry. |
| X start, X end | filled, editable | **Major** diameter at Z start and at Z end. Equal = straight; different = taper. |
| Z start | entered | Includes the lead-in (checked, section 5). |
| Z end | entered | **Where the tool pulls out** (owner). Each pass cuts to Z end and retracts straight out in X there - no separate pull-out / chamfer field (G76 E = 0, L = 0). |
| Pitch | filled, editable | TPI or mm per the list; stored as inches per thread. |
| Thread depth | **derived, read-only** | Calculated from the standard and the fit class (owner: not user entered) - section 3. Shown with its source, e.g. "depth .0307 (UN 2A)". |
| Pilot dia (ID only) | filled, editable | Filled with the tap drill diameter (section 4). The crest for the cycle and the base of the ID retract. |
| RPM | entered | Checked against Z speed (section 5). |
| Number of passes, # of spring passes | entered | As today. |
| # of starts | entered | As today: P = lead; each start shifted one pitch in Z. |
| Entry angle | filled by form, editable | Compound infeed angle (G76 Q): 29.5 for 60 deg forms, 14.5 for Acme (29 deg), 15 for Tr (30 deg), 0 = straight plunge. |

Kept in the background (defaults, shown under "Advanced"): depth degression (G76 R, default 2.0 = constant
area per pass - LinuxCNC: R1 = constant depth, R2 = constant area); the first-pass depth is derived from the depth, passes and degression as today.

No LH threads (owner, at this time): Z end is always behind Z start (cutting toward the chuck, M3).

## 2. Thread types and classes (owner-agreed)

| Type | Classes offered | Standard |
|---|---|---|
| UNC, UNF | 2A / 2B, 3A / 3B | ASME B1.1 |
| Metric Coarse, Metric Fine | 6g / 6H (medium), 4h / 5H (close) | ISO 965-1 |
| Metric Trapezoidal (Tr) | 7e / 7H | ISO 2903 |
| Acme | 2G / 3G | ASME B1.5 |
| NPT | (none - gauged, see below) | ASME B1.20.1 |
| Custom | none | - |

The OD / ID field picks the external (A, g, e, G) or internal (B, H, G) class of the pair automatically.

**NPT preset** (owner: auto-populates like the others). Pitch from the size; the taper is fixed at 1:16
on diameter, so **X end is derived from X start and the Z length** (X end = X start + |Z end - Z start| / 16,
growing toward the larger end). X start is the major diameter at the small end (the pipe end / mouth of
the tapped hole) from the standard's E0 and thread height. Cut as a tapered thread (section 6).

**Custom**: every X / pitch field editable; the user also picks the **form** (60 deg / Acme 29 deg /
Tr 30 deg / NPT 60 deg taper) so the depth can still be calculated - depth is never typed. No class, no
tolerance hint.

**Where the numbers come from.** A data file (`models/` or `data/`) generated from the published
standard formulas, with tests that check it against tabulated values in the standards / Machinery's
Handbook (at least three sizes per type, to .0001"). Today's panel computes UN tolerances inline and a
"simplified" metric 6g; that code is replaced, the panel only looks values up. No tolerance value is
invented or estimated; a size the data doesn't cover is not offered (use Custom).

## 3. Thread depth (derived)

Depth = the radial distance the tool feeds from the crest to the root, for the chosen standard and class:

- **External** (OD): from the class's **major diameter (max)** down to the **minor diameter for the
  class** (UN: the max minor of the 2A / 3A external thread; metric: d3 from ISO 965 for g / h; Tr / Acme:
  the standard's external minor for the class). X start / X end are populated with the nominal major as
  the owner asked; the depth is measured from there, and the hint shows the major range for the class.
- **Internal** (ID): from the **pilot (tap drill)** out to the class's **major diameter (min)** (UN 2B /
  3B: min major = basic major; metric H: D basic; Tr / Acme per standard), so the tool reaches full form
  even with a tap-drill-sized bore.
- **NPT**: thread height 0.8P (ASME B1.20.1, truncation per the standard).
- **Custom**: the form's basic depth (60 deg: .61343P external / .54127P internal; Acme: .5P + the 2G
  allowance; Tr: .5P + ac) - stated as "basic depth, no class".

The data file stores these per size / class; the planner gets the depth, never a formula in the GUI.
If the pilot is edited, the ID depth updates (it is pilot -> major).

## 4. Hints (read-only, under the fields)

- **OD**: pitch-diameter window for the class (max / min - e.g. 1/4-20 2A: PD .2164 / .2127) and the
  major range. NPT: no PD window (it is gauged) - the hint shows the L1 hand-tight length and "check with
  an L1 ring gauge".
- **ID**: the **tap drill** (owner: drill only, no boring advice) - e.g. 1/4-20: #7 (.2010); M6x1: 5.0 mm;
  1/4 NPT: 7/16. The pilot field is filled with its diameter.
- Editing X or pitch by hand after choosing a size turns the hint into "Custom (no tolerance data)" -
  the hint never describes a thread other than the one being cut.

## 5. Checks at Generate (same red / amber reporting as the other checks)

- **Spindle sync**: pitch x starts x RPM <= the Z MAX_VELOCITY in the INI with margin for spindle-speed
  variation; error with the highest usable RPM.
- **Lead-in**: Z start far enough in front of the material for Z to reach sync speed (from Z
  MAX_ACCELERATION); warning with the minimum.
- **Tool**: angle vs form (e.g. 60 deg insert on an Acme thread) - warning.
- **ID**: pilot - .005 above the boring bar's minimum bore when the tool has one recorded.
- **Taper**: steeper than 45 deg is refused (G33 with the lead along X is a different mode).
- **Z end behind Z start** (no LH) - error otherwise.

## 6. Motion

**Retracts (owner rule)**: OD -> the larger of X start / X end + .020" (dia); ID -> pilot - .005" (dia).
Always outside the material, between passes and at the end; the retract happens **at Z end**, straight
in X (owner: Z end is where the tool pulls out). Today's ID drive line is crest - .020; it becomes
pilot - .005.

**Straight threads**: G76 as merged today (verified with rs274: full depth, clear approach), with the
drive line set by the retract rule and E = 0, L = 0 (straight pull-out at Z end).

**Tapered threads (incl. NPT)**: LinuxCNC's G76 cannot cut a taper. The planner writes a series of G33
passes, one per depth: rapid to the retract X at Z start -> rapid to the pass start X -> G33 to (X end at
that depth, Z end) -> rapid out in X to the retract -> rapid back in Z. Infeed per pass follows the entry
angle (the pass's Z start shifts by depth x tan(angle)); depth per pass follows the same degression as
G76; spring passes and multi-start the same rules.

**Verification**: rs274 canon on straight and tapered OD / ID threads (incl. an NPT): the deepest pass
reaches the root along the whole taper; every retract is above major + .020 (OD) / below pilot - .005
(ID); spindle sync covers every cutting move; the rapid-collision check against the stock; an air cut
with the owner before first metal.

## 7. Program file and migration

New fields: side (OD / ID), x_start, x_end, pilot_dia, thread_type, size, thread_class, form (Custom),
entry_angle; depth becomes derived (stored for the record, recomputed on load). They replace
major_diameter, taper_amount, infeed_method, thread_depth, chamfer_threads. Old v2 threading blocks
convert: X start = X end = major, entry angle from infeed_method, ID pilot from the stock's pilot hole,
designation matched to the new data where it exists (else Custom with the form from the old standard).

Corpus gate: saved programs with threads will **not** regenerate identical G-code - the depth now comes
from the class (today it is the typed value), the ID drive line moves, and the pull-out chamfer goes.
Each difference is listed per program for the owner to review before merge.

## 8. Owner decisions (2026-11-12)

- OD / ID and tool # fields: **yes**.
- Thread depth: **calculated from the standard and fit class, not entered**.
- Pilot dia for ID: **yes**. ID hint: **tap drill only**.
- Z end = **where the tool pulls out** (no separate pull-out field).
- Custom thread option: **yes**.
- Classes: **6g/6H + 4h/5H (metric), 7e/7H (Tr), 2G/3G (Acme)**, 2A/2B + 3A/3B (UN).
- NPT: **a preset that auto-populates like the others**.
- LH threads: **not at this time**.
- Implementation: **not yet** - plan only.

## 9. Phases

| # | Delivers | Verification |
|---|---|---|
| T1 | Thread data file (sizes, pitches, class majors / minors / PD windows, depths, tap drills, NPT E0 / L1) + tests against the published tables | spot values from the standards / handbook, to .0001" |
| T2 | Panel: fields, type + class, Custom (with form), NPT preset, hints | offscreen GUI tests; eyeball with owner |
| T3 | Planner / writer: X start / end, derived depth, pilot, owner retract at Z end, G33 tapers, Generate checks | rs274 canon tests (section 6), corpus diff review, air cut |

Independent of the part-model phases; threads stay their own operation (owner 2026-11-12).

## 10. Implementation notes (2026-11-12, branch claude/threading-build)

Files: `models/thread_data.py` (new: catalogue, class limits, depths, tap drills, legacy
converter), `models/program.py` (ThreadingParams), `models/results.py` (ThreadPlan),
`planners/threading_planner.py`, `outputs/gcode_writer.py` (threading block),
`gui/components/threading_panel.py`, `gui/program_tab.py` (wiring, checks),
`gui/components/block_list.py` (OD / ID changes the block type). Tests:
`test_thread_data.py`, `test_g76_threading.py`, `test_threading_panel.py`.

Data, checked against published tables (sources in `tests/unit/test_thread_data.py`):

- UN 2A / 3A / 2B / 3B: ASME B1.1 formulas with its rounding order; matches the tables to the
  last digit (1/4-20 UNR minor .1875 vs table .1876 - rounding).
- Metric 6g: ISO 965-1 formulas + R40 rounding, es table; matches M6, M10, M12, M20. 4h:
  grade factor applied to the ROUNDED grade-6 value (reproduces the ISO widths incl. Td(4)
  P1.75 = 170). Internal (H): root = basic major; no internal PD window is computed (the ID
  hint is the tap drill only).
- Tr 7e / 7H: ISO 2901 profile (es on d2 only; d3 = d - 2(.5P + ac); D4 = d + 2ac). The 7e
  pitch-diameter limits are TABLE values, so **only the 5 sizes found in the published table
  are offered**: Tr10x2, Tr16x4, Tr20x4, Tr24x5, Tr40x7 (more can be added from the owner's
  handbook).
- Acme 2G / 3G: B1.5 relations (allowance a = .020 / .010, minor max = D - P - a, internal
  major min = D + a; PD allowance .008 / .006 sqrt(D), tolerance .006 sqrt(D) + .030 sqrt(P) /
  .0028 sqrt(D) + .014 sqrt(P)). Matches the handbook tables for 1/2-10, 3/4-6, 1-5, 1-1/2-4.
  The handbook's allowance table is computed per diameter RANGE; the other offered sizes use
  the sqrt(D) relation directly (can differ by .0001 - owner to spot-check one).
- NPT: E0 = D - (.05D + 1.1)p, E1 = E0 + L1/16, h = .8P, L1 from the table; matches 1/8 - 2.
  **Tap drills: published charts disagree by 1/64 - 1/32** (engineersedge NPT chart, used here:
  1/8 R, 1/4 7/16, 3/8 37/64, 1/2 23/32, 3/4 59/64, 1 1-5/32, 1-1/4 1-1/2, 1-1/2 1-47/64,
  2 2-7/32; Briggs / Dryseal charts are a size smaller). Owner to confirm the chart he uses.
- Acme / Tr "tap drill" = the internal minor (D - P); no standard drill sizes.

Depth: external root = the class's max minor (UNR for UN, d3 for metric / Tr, D - P - a for
Acme); internal root = the class's min major; internal crest = the pilot.

Motion findings (rs274):

- G76 J printed to .0001 and rounded DOWN made LinuxCNC add a sliver pass (7 instead of 6):
  J is now rounded UP (`first_cut_dia`).
- G76's retract between passes goes past the drive line by (K - current depth) - outward for
  OD, toward the centre for ID; the planner refuses an ID thread where that would pass X0.
- G76 shifts each pass start (and end) by -depth x tan(Q); the G33 taper passes use the same
  start shift (verified: the G33 pass starts equal G76's for a straight thread) and all end
  at Z end (the owner's pull-out point).
- Tapered passes that lie inside the retract X (ID: inside the pilot hole) are air cuts and
  are left in (no material).

Generate: plan errors (Z speed > 90% of [AXIS_Z]MAX_VELOCITY with the highest usable RPM,
Z end not behind Z start, pilot >= major, taper > 45 deg, ID too small for G76's retract)
block the hand-off to Edit / Run like the other checks; warnings (lead-in from
[AXIS_Z]MAX_ACCELERATION, insert angle vs form) are Generate notes. Old saved threading
blocks load through `thread_data.from_saved` (designation mapped onto the catalogue; class 1A
-> 2A; pull-out chamfer dropped with a note).
