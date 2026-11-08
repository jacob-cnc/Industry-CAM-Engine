# 2026-11-08 — Lathe sync, MPG route restore, G54 touch-off, mode indicator, GUI fit

Machine: lathe Linux PC (LinuxCNC 2.9.6, Mesa 7i96s + 7i85s). Agent: Claude Code.
Session spanned 2026-11-07 evening (interrupted by a power outage) and 2026-11-08.

## Sync

- Local `main` fast-forwarded `4e55d6c -> 1f490eb`. Junk boring-bar edits to
  `tool.tbl` discarded (owner: not a real offset). Untracked local `tool.tbl.bak`
  (old schema) was set aside and then deleted on 2026-11-08.

## Fixes (classification -> verification)

| Change | Class | Verification |
|---|---|---|
| `industry-cam.hal`: restore direct `mpg-x/z-counts => joint.N.jog-counts` | Machine-control | Machine-verified: MPG jog solid, both axes |
| `gui/tools_tab.py`: Set X/Z send `G10 L20 P1` (G54) and return to `MODE_MANUAL` after the MDI | Machine-control | Machine-verified: DRO reads entered value, MPG works immediately after, no tab switch |
| Ribbon task-mode indicator (MANUAL blue / MDI amber / AUTO green) | Software-only | Machine-observed: shows MANUAL, flashes MDI during touch-off |
| GUI fits 1920x1080 in live mode (ElidedLabel for G-codes, errors, sim info; spacing; Program splitter) | Software-only | Machine-observed: window fits, opens maximized |
| `hal/live_backend.py`: active G-code string keeps decimals (G17.1, G91.1, G64.1), includes G0, skips the line-number slot | Software-only | Offline format check only; NOT yet observed live |

## Root causes

1. **MPGs dead after pulling main.** `1f490eb` removed the direct jog-counts nets
   expecting `postgui.hal`'s mux2 chain to take over, but this config never loads
   `postgui.hal` (no `POSTGUI_HALFILE`; `DISPLAY = display_gui.sh`). LiveBackend
   only wires mpg-scale-sel / jog-vel-mode at runtime. The compound-slide jog route
   therefore remains unimplemented (see risk R-012).
2. **MPGs dead after Set X/Z.** `_send_mdi_command` switched to MDI and never
   returned to MANUAL; jog counts are ignored outside MANUAL. Not a following error.
3. **Set X/Z wrote the wrong coordinate system.** `G10 L20 P{tool_number}` -
   P is the WCS index, so with T2 active it would have edited G55.
4. **Live window too wide.** Live-only text (full modal G-code list, LinuxCNC error
   messages) in un-elided QLabels raised the ribbon minimum to ~2740-3150 px.
   Offscreen-measured minimum widths after fix: ribbon 1709 (1827 with an error
   shown), Edit tab 1668, Program tab 1295.

## Not done / next

- Wire the full compound-slide jog-counts chain in `LiveBackend` (bench-test plan required).
- Font/size cleanup of the ribbon and tabs (owner: later, low priority).
- Tool-length touch-off (G10 L10) waits for home switches (owner: weeks out).
- Observe the live G-code string once on the machine.

## Notes

- `hm2_7i96s.0: error finishing read!` at session end is the owner powering off the
  Mesa stack during shutdown — expected, not a fault.
- pytest is not installed on the lathe PC's Python; automated suite not run here.
