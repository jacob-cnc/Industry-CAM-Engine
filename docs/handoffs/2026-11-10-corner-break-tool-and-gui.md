# Session: 2026-11-10 - Corner-break tool, OD corner-break engine, GUI tuning

Handoff from the Windows dev PC (Kiro, offline mock) to Claude Code on the lathe
Linux PC (live LinuxCNC). Written at the owner's request: "Leave a detailed handoff
note for integrating the live version with claude cli on the linux pc."

## Workstream

Branch: `work/2026-11-10` (local + `origin`). Not merged to `main`.
Base: `main` @ `2d9b86c` (unchanged on origin since; contains every Claude lathe
branch, including `claude/compound-slide-routing` and `lathe/bench-2026-11-08`).
Head: see `git log -1 origin/work/2026-11-10` (this note is the last commit).
Environment: Windows 11 dev PC, Python 3.12 `.venv`, `QT_QPA_PLATFORM=offscreen` for
tests, offline mock backend. Never run against the machine.
Change classification: **Motion-affecting** (CAM output changes: corner-break
geometry, offset fallback, arc filtering, stock check) plus GUI-only changes.

### Commits on the branch (oldest first)

| Commit | Summary | Class |
|---|---|---|
| `b1b4307` | Dev tooling: ruff/mypy config in `pyproject.toml`, `.kiro/steering/dev-tooling.md`, `requirements.txt` pins | Tooling |
| `1bdae97` | 1920x1080 offline preview, UI debug overlay (`gui/debug_overlay.py`), ribbon/BAR/Program layout tuning, collapsible-section packing fix, segment builder (Insert, numbering, r column), Manual-tab coord toggle + Clear Trail centring | GUI |
| `4c9d357` | OD corner-break vertex solver `geometry/corner_breaks_od.py`, validated against the owner's NX STEP parts | **Motion** |
| `7be1f93` | Corner-break tool (vertex model V1..Vn, badges, graph picking), engine-driven preview | GUI |
| `bfd0be3` | Optional "Smooth" trim (roll onto earlier neighbour), `geometry/kernel_offset.py` fallback, tool exit button + Esc | **Motion** |
| `0ffcf4f` | Stock-size check: refuse a profile that runs along/outside the stock | **Motion** (refuses programs) |
| `ca04bdc` | Vertex dots live after Generate, sim speeds halved, feeds drawn over rapids | GUI |
| (this) | This handoff note + ACTIVE.md entry | Docs |

## Integration steps for the lathe (Claude Code)

Follow `docs/coordination/README.md` first: fetch `agent-sync`, publish your claim.
**Path overlap to resolve:** `1bdae97` edits `gui/manual/manual_tab.py` and
`gui/manual/sections.py` (coordinate-toggle width/centring, Clear Trail button
centring; layout only, no jog/HAL logic). Your status file claims those paths for
compound routing. `git merge-tree` against every remote branch showed no textual
conflicts, but please review that diff (`git diff 2d9b86c 1bdae97 -- gui/manual/`).

1. **Protect machine state** (per `docs/DEPLOYMENT.md`): LinuxCNC stopped; back up
   `industry-cam.var`, `tool.tbl`, `industry-cam.ini` outside the checkout.
   This branch's `tool.tbl` is the repo copy. Do **not** let a merge or checkout
   overwrite the lathe's live `tool.tbl` (the Windows PC's local edits were never
   committed). Check `git status --short` for dirty machine-local files first.
2. **Fetch and check out a lathe test branch**, without touching `main`:
   ```bash
   git fetch origin
   git status --short --branch          # must be clean except machine-local files
   git switch -c lathe/test-2026-11-10 origin/work/2026-11-10
   ```
   If the lathe has unpushed local commits, merge `origin/work/2026-11-10` into a
   new lathe branch instead and report the merge commit.
3. **Python deps (system `python3`; `display_gui.sh` does not use a venv).**
   `requirements.txt` now pins `build123d==0.10.0` and `ocp_gordon>=0.1.17,<0.2`
   (0.11+/OCP 8.0 renamed `TopoDS.Face_s` etc.; ocp_gordon 0.2 imports
   `OCP.collections`). These pins describe what already works; **check before
   installing anything**: `python3 -c "import build123d, OCP; print(build123d.__version__)"`.
   If the lathe already imports fine, change nothing on the RT machine.
4. **Run the suite on the lathe:** `python3 -m pytest tests -q -p no:warnings`.
   Expected (Windows result for `ca04bdc`): 1073 passed, 3 skipped, 1 xfailed,
   3 xpassed, **4 failed** = the known axis-aligned Q tests in
   `tests/integration/test_quadrant_arc_pipeline.py`. Your last lathe baseline listed
   6 quadrant-arc failures; report any failure outside that file as new.
   Note: `tests/conftest.py` pins `QT_FONT_DPI=96` for test runs only.
5. **Launch and look (no motion):** start LinuxCNC normally (`display_gui.sh`).
   Expected on the 1920x1080 panel: window maximized exactly as before.
   `_enable_live_dpi_emulation()` returns early on Linux, and `_show_at_live_size()`
   calls `showMaximized()` when the screen is <= 1920x1080. Optional: `export
   INDUSTRY_CAM_DEBUG_UI=1` before launch for the debug overlay (F12 tags, F11
   outlines, F10 inspect, F9 snapshot to `~/.local/share/IndustryCAMEngine/ui_snapshots`,
   F8/Shift+F8 rulers). Off by default.
6. **Program-tab checks (no motion):**
   - Corner Breaks button swaps the segment builder for the vertex list; button reads
     "Done - Back to Segment Builder  (Esc)"; Esc leaves.
   - Click vertices on the graph, apply chamfer/fillet; a trim conflict asks
     "Smooth?" (No = NX-style kink, Yes = roll onto the earlier break).
   - Generate with the tool open, and open the tool after Generate: vertex dots show
     both ways; they hide while Play runs and return on Pause/Reset/end.
   - Sim speed "1x" should look half as fast as before.
7. **Motion commissioning (owner present, required before cutting):** corner breaks
   change finish-contour G-code. Air-cut first with a feed override, then a scrap
   part. Compare against the NX reference values below. ID corner breaks are
   **not validated** (legacy method, labelled "unvalidated" in the tool).
8. Report the result in `docs/coordination/claude.md`; the owner decides on merging
   to `main`. Do not merge to `main` from the lathe without the owner.

## Engine changes that affect G-code (review these)

- `geometry/corner_breaks_od.py`: OD breaks live on vertices (row k ends at Vk).
  Equal chamfers and equal fillets only; one size per apply. Over-size breaks are
  trimmed to fit (NX "cliff": a cut-short fillet keeps R and leaves a kink, reported),
  never refused. `trim="smooth"` per vertex rolls the fillet onto the earlier
  neighbour (tangent; neighbour shortened/extended). Arc-adjacent vertices fall back
  to the legacy method, flagged "unvalidated". Last vertex is unbreakable.
- `geometry/kernel_offset.py`: offset tries INTERSECTION join, then ARC join; if both
  fail raises `KernelOffsetError` (readable message, raw OCCT error chained).
- `pipeline` `_assemble_moves`: sub-tolerance arcs dropped.
- `pipeline/model_builder.py` `_check_stock_size`: ValueError when the profile runs
  along the stock surface (within finish allowance, with more profile after it) or
  outside the stock. Ending on the stock surface is allowed.
- `models/profile.py`: `CornerBreak.trim: str = "nx"` (saved programs without it load
  as NX style).

NX reference (mm, Ø/Z): (6,0),(6,-6),(12,-6),(12,-12),(6,-12),(6,-18),(15,-18),
(15,-21),(12,-21),(12,-27),(18,-27),(18,-33); V1-V10 = C1,C1,R1,R1,R1,R1,C1,C1,R1,R3.
V9 is the trim conflict: NX result centre Z-21.866 Ø14 with a 15° kink; Smooth result
centre r7 Z-21.9142, chamfer 1.414 -> 1.707. Fixtures:
`tests/fixtures/nx_corner_break/{sharp,broken}.stp`.

## Where the owner paused me, where I left off, and why

The last request had three parts: (1) feed/rapid colours inconsistent on the graph,
(2) corner-break vertex dots missing after Generate until a value was changed,
(3) all sim speeds cut 50 % with labels unchanged.

- **Speeds (done, verified by test).** `SimViewerWidget.SPEED_STEPS` = 0.5, 1, 2, 4,
  8, 16 steps per 16 ms frame (old map 1..32). Fractional steps accumulate. Added
  `playing_changed(bool)`.
- **Colours (paused by the owner mid-investigation).** Root cause **observed** by
  pixel-sampling `snap_015`: each roughing pass retracts to the previous pass's cut
  diameter (e.g. N1810 cut at X0.05, retract to X0.1) and rapids back along it, so the
  red dashed rapid lies exactly on the previous green feed line. Paint order decided
  which colour won and the dash gaps showed green, so rows looked random. Fix in
  `ca04bdc`: rapids z=1, cutting moves z=2. **Verified** only by a unit test of the
  z-values; **not** verified on a fresh on-screen render. Owner said "I'm okay with
  pausing on the color issues for now." Open question for the owner: should roughing
  retract to the previous cut diameter with zero extra clearance?
- **Vertex dots (finished after the pause, verified by tests).** Cause: the dots were
  drawn only by `_update_preview`, which returns early once a toolpath is loaded
  (DISPLAYING), so they came back only when an edit dropped the tab to BUILDING. Fix:
  `ProgramTab._sync_cb_overlay()` redraws them on tool open, on every state change
  (Generate replaces the plot), and on `playing_changed`. Hidden and clicks ignored
  while playing (`_cb_overlay_blocked`).
- **Why it stalled when the owner paused me:** the new Generate-based GUI test hung.
  Not my overlay code: the repo `tool.tbl` has **T1 = Q3 boring bar**, so Generate
  refused the OD block and opened the modal `GenerationErrorDialog`, which blocks an
  offscreen run forever. Tests now pick T4 (CNMG) and turn that dialog into an
  assertion so they fail instead of hanging. Worth knowing on the lathe too: any GUI
  test that generates with default T1 will hit this.
- I also force-stopped stray `.venv` Python processes on the Windows PC to clear the
  hang; that may have closed the owner's offline app there. No effect on the lathe.

## Verification Performed

| Check | Result | Notes |
|---|---|---|
| Focused tests | 24 passed | `test_corner_break_tool.py`, `test_sim_speed_and_draw_order.py` |
| Full tests | 1073 passed / 4 failed (known) / 3 skip / 1 xfail / 3 xpass | Windows, offscreen, `ca04bdc` |
| Ground-truth comparison | Pass | NX STEP fixtures, `test_corner_breaks_od_nx.py` |
| Property tests | Pass | `test_corner_breaks_od_properties.py` |
| Merge dry-run | Clean | `git merge-tree` vs every remote branch |
| Offline LinuxCNC/mock | Manual use on Windows | Not on the lathe |
| Physical machine | **Not done** | Needs owner-present commissioning |

## Known Problems and Risks

- 4 axis-aligned Q/-Q tests fail: `geometry/zone_builder.py` (~437-449) draws
  axis-aligned quadrant arcs as straight lines. Pre-existing.
- Retract routing: with `Desktop/Corner Break Debug (rebuilt).json` and Ø1.1 stock,
  a TRANSITION RAPID gouge is flagged when the profile ends small at the stock end;
  the retract does not route around the part. Not fixed.
- Roughing rapid returns sit exactly on the previous cut diameter (see above).
- ID corner breaks unvalidated; owner will provide an ID reference part.
- Tooltip "+R minor/-R major" wrong; G7 `I` as diameter delta in the simulator not
  verified.

## Exact Next Step

Lathe (Claude): steps 1-6 above on `lathe/test-2026-11-10`, report suite + visual
results in `claude.md`, then owner-present air-cut of an OD part with corner breaks.
Dev PC (Kiro): on owner request, verify the colour fix on a fresh render (F9
snapshot, sample rows near x≈560) and ask the owner about retract clearance.
