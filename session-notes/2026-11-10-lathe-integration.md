# 2026-11-10 — Lathe integration of work/2026-11-10 (owner-verified working)

Owner verdict: "best working version". Merged to `main` and tagged
`lathe-2026-11-10-working`. The previous known-good state is tagged
`lathe-2026-11-09-working` (= 9e98a36, branch `claude/rt-cpu-tuning`); a
read-only copy of that whole config directory, including live `tool.tbl` and
`.var`, is at `~/linuxcnc/configs/industry-cam.pre-integration-2026-11-10/`.

## What came in

Kiro (Windows dev PC), `work/2026-11-10`, see
`docs/handoffs/2026-11-10-corner-break-tool-and-gui.md`:
- OD corner-break vertex solver validated against the owner's NX part
  (no 40 % clamp; NX-style cut-short fillets; optional Smooth trim).
- Corner-break tool in the Program tab; kernel offset fallback; stock-size
  refusal; GUI layout tuning; sim speeds halved; debug overlay (opt-in).

Claude (lathe), on top:

| Commit | Change | Class |
|---|---|---|
| 50ec0df | Merge `claude/rt-cpu-tuning` (boot-time CPU tuning runs from the checkout) | Deploy |
| 5e7d561 | **Arc G-code fix.** LinuxCNC G7 reads `I` as a RADIUS offset and its G02/G03 is the mirror of the engine's internal ARC_CW/CCW. `outputs/gcode_dialect.py` is the single translation point (writer, move parser, sim parser). Pre-existing on main; every earlier `.ngc` with arcs is wrong — regenerate. | Motion |
| 8b09211 | Tests: rs274 runs generated arc programs; arcs match planner centres and sweep | Test |
| 4e04c5e | Software E-STOP button sends STATE_ESTOP (was STATE_OFF); ribbon shows grey OFF | Machine control |
| c3da369 | Concave fillet with R <= nose radius cut as the sharp inside corner (tool leaves R=TNR), with notes in the program, after Generate and on the vertex | Motion |
| 2470663, 675afcb | Hardware E-stop: NC button TB3 P5 = gpio.004 through `estop_latch` (plain and2 failed: release cleared ESTOP by itself) | Machine control |

## Verification

- Saved programs (no arcs or OD/ID without breaks): G-code byte-identical
  main vs Kiro's branch before the arc fix.
- rs274 (LinuxCNC's interpreter, no RT): GCH ID bore with R.010 fillet, NX OD
  candidates, GUI Conv Test (29 arcs), Corner Break Test run to PROGRAM_END.
- Suite (miniforge 3.13, offscreen): 1074 pass / 4 known quadrant-arc fails;
  Kiro's two whole-window GUI test files run separately (they segfault/hang
  in the full run on Linux); 1 known 3 px layout assertion.
- Machine (owner present): air cut of the regenerated GCH bore with the ID
  fillet — as expected. Software E-STOP: ribbon reflects state. Hardware
  E-stop: press -> ESTOP + machine off; release -> stays ESTOP; Reset while
  held -> ignored (6 pulses); Reset released -> clears; On works.

## Known open items

- offset_contour roughing gouges large concave fillets (validator blocks it);
  pre-existing.
- V1 chamfer at the front face refused by the comp-entry check; pre-existing.
- ID corner breaks still use the legacy (unvalidated) method.
- Kiro's GUI tests: order-dependent segfault/hang on Linux; 423 != 420 px.
- `requirements.txt` pins ocp_gordon<0.2; the lathe runs 0.2.0 fine — do not
  `pip install -r` on the lathe.
- Any `.ngc` with G02/G03 generated before 5e7d561 must be regenerated.
