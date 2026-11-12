# Plan: threading as a field-driven operation (straight and tapered, standard thread lists, hints)

Status: PLAN ONLY (nothing implemented). Written 2026-11-12 by Claude at the owner's request.
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

## 1. Fields

Owner's list, then the additions this plan proposes. Additions are marked **(new)**, with the reason.

| Field | Notes |
|---|---|
| OD / ID | **(new)** Which side. It sets the direction of the cut, the retract rule and which hint is shown. |
| Tool | **(new)** As on every block. The tool's included angle is checked against the thread form (60 / 29 / 30 deg). |
| Thread list + class | Optional drop-down list (section 2). Choosing a thread fills X start, X end and pitch. "Custom" leaves them all editable. |
| X start, X end | The **major** diameter at Z start and at Z end. Equal values give a straight thread; different values give a taper. |
| Z start, Z end | Z start includes the lead-in (see the check in section 5). |
| Pitch | In TPI or mm, depending on the list. Stored as inches per thread. |
| Thread depth | **(new)** Radial depth, filled in from the thread form and pitch (e.g. UN = .61343 x P; Acme 2G = .5P + allowance) and editable. X alone can't give it, because X is the major diameter only. |
| Pilot / bore dia (ID only) | **(new)** The bore the thread is cut in. It is the crest for the cycle and the base for the retract rule. It is filled in from the hint (section 3). |
| RPM | Checked against Z speed (section 5). |
| Number of passes, # of spring passes | As today. |
| # of starts | As today: P = lead, and each start is shifted one pitch in Z. |
| Entry angle | The compound infeed angle (G76 Q). Defaults by form: 29.5 for 60 deg threads, 14.5 for Acme (29 deg), 15 for Trapezoidal (30 deg). 0 is a straight plunge. |
| Pull-out (chamfer) | **(new, today's field kept)** How far the tool exits at the thread end, in threads. It becomes G76 E/L for straight threads. Use 0 when the thread runs out into a groove. |
| Hand (RH / LH) | **(new, owner to decide)** LH means cutting away from the chuck (Z start behind the thread, cutting toward +Z), still with M3. If LH isn't needed, leave it out. |

Kept in the background, with defaults shown under "Advanced": depth degression (G76 R, default 1.0 = constant area per pass) and the first-pass depth. Both are derived from the number of passes, as they are today.

## 2. Thread lists and classes

| List | Owner's request | Note for the owner |
|---|---|---|
| UNC, UNF | 2A / 2B, 3A / 3B | As requested. ASME B1.1 has class formulas for pitch diameter tolerance and allowance. |
| Metric Coarse, Metric Fine | "2A/B, 3A/B" | **Metric doesn't use A/B classes.** The usual classes are **6g / 6H** (medium, the default) and **4h / 5H** (close); 4g6g also exists. Offer 6g/6H and 4h/5H? (ISO 965-1) |
| Metric Trapezoidal (Tr) | same | Classes are **7e / 7H** (medium) and **8e / 8H** (coarse). Offer 7e/7H only? (ISO 2903) |
| Acme | same | General-purpose classes are **2G / 3G / 4G** (internal and external share the class name). Centralizing 2C–6C is left out. Offer 2G and 3G? (ASME B1.5) |
| NPT | (in today's list) | Today's panel has NPT. It is tapered (1:16), and its gauging is different. Drop it, or keep it as a taper preset with no tolerance hint? |

**Where the numbers come from.** The data lives in a data file in `models/` or `data/`. It is built from the published standard formulas, and the tests check it against tabulated values in the standards / Machinery's Handbook: at least three sizes per list, to .0001". Today's panel computes UN tolerances inline and uses a "simplified" metric 6g. That code is replaced, so the panel only looks values up. No tolerance values will be made up or estimated; any size the data doesn't cover is shown as "Custom".

## 3. Hints (read-only, under the fields)

- **OD:** the pitch diameter window for the chosen class (max / min, e.g. 1/4-20 2A: PD .2164 – .2127, values taken from the data file). Also the major diameter range, because that is what a micrometer reads before the wires go on.
- **ID:**
  - the nominal pilot / bore diameter and the nearest standard drill (e.g. 1/4-20: #7, .201);
  - also the class's **minor diameter window**. A single-point ID thread is normally cut in a **bored** hole, so the drill is the roughing size and the minor window is the size to bore to;
  - the internal pitch diameter window for a gauge or wire check.
- Changing X, pitch or depth by hand after picking a size drops the hint to "Custom (no tolerance data)". The hint never describes a thread other than the one being cut.

## 4. Motion

**Retracts (owner rule):**
- OD threads retract to the larger of X start / X end + .020" (dia).
- ID threads retract to pilot dia − .005" (dia).
- Retracts are always outside the material, between passes and at the end.

Today's ID drive line is crest − .020; under this plan it becomes pilot − .005.

**Straight threads:** G76, as merged today (verified with rs274: full depth, approach stays clear). Only the drive line changes, to the retract rule above. OD stays the same: major + .020.

**Tapered threads:** LinuxCNC's G76 can't cut a taper (its E/L only shapes the exit). Tapers are cut as a series of **G33 passes** generated by the planner, one per depth:
1. Rapid to the retract X at Z start.
2. Rapid to the pass start X.
3. G33 to (X end at this depth, Z end).
4. Rapid out in X to the retract.
5. Rapid back in Z.

- The infeed per pass follows the entry angle (each pass's Z start shifts by depth × tan(angle)). The depth per pass follows the same degression as G76. Spring passes and multi-start use the same rules.
- I could use G33 for straight threads too, so both work the same way. But G76 is verified and familiar in the code, so I'd keep it.

**Verification:**
- rs274 canon on straight and tapered OD/ID threads: the deepest pass reaches the root along the whole taper; every retract is above major + .020 (OD) / below pilot − .005 (ID); the spindle sync covers every cutting move.
- The rapid-collision check against the stock.
- Air-cut it once with the owner before first metal.

## 5. Checks at Generate (same red / amber reporting as the other checks)

- **Spindle sync:** pitch × starts × RPM must be within the Z MAX_VELOCITY in the INI, with margin for spindle-speed variation. If not, show an error that gives the highest usable RPM.
- **Lead-in:** Z start must be far enough in front of the material for Z to reach sync speed (from Z MAX_ACCELERATION). If not, show a warning that gives the minimum.
- **Tool:** a warning if the tool's angle doesn't suit the form (e.g. 60 deg insert on an Acme thread).
- **ID:** pilot − .005 must stay above the boring bar's minimum bore, if the tool has one recorded.
- **Taper:** "any size and pitch" means anything the machine can sync. Steep tapers (above 45 deg) are refused, because G33 lead along X is a different mode.

## 6. Program file and migration

- New fields: x_start, x_end, depth, pilot_dia, thread_list, thread_class, entry_angle, hand.
- They replace major_diameter, taper_amount and infeed_method.
- Old v2 threading blocks convert as follows:
  - X start = X end = major (taper_amount, which is refused today, is carried over as X end);
  - entry angle comes from infeed_method;
  - an ID block's pilot comes from the stock's pilot hole.
- The corpus gate: every saved program with a straight thread regenerates text-identical G-code, **except** ID threads. Their drive line moves from crest − .020 to pilot − .005, and that difference is listed for the owner to review.

## 7. Phases

| # | Delivers | Verification |
|---|---|---|
| T1 | Thread data file and tests against the published tables. | Spot values from the standards / handbook, to .0001". |
| T2 | Panel: new fields, list + class, hints, Custom. | Offscreen GUI tests; check by eye with the owner. |
| T3 | Planner/writer: X start/end, depth, pilot, owner retract rule, G33 tapers, Generate checks. | rs274 canon tests in section 4, corpus, air cut. |

These are independent of the part-model phases. Threads stay their own operation (owner, 2026-11-12).

## 8. To decide (owner)

1. Classes for metric (6g/6H, 4h/5H?), Tr (7e/7H?) and Acme (2G/3G?), since A/B classes are UN only.
2. Keep NPT as a taper preset, or drop it?
3. Is LH needed?
4. ID hint: show both the drill and the bore-to minor window (as proposed), or the drill only?
