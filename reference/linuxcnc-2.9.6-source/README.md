# LinuxCNC 2.9.6 Targeted Source Reference

This is a targeted read-only snapshot from the official LinuxCNC `v2.9.6` tag,
matching the runtime version documented in `CLAUDE.md`.

- Upstream: <https://github.com/LinuxCNC/linuxcnc>
- Tag: `v2.9.6`
- Tag commit: `8ed1eb5c486782137810430b1bc1113a597d4722`
- Retrieved: 2026-06-11

## Included Scope

| Files | Purpose |
|---|---|
| `src/emc/rs274ngc/interp_arc.cc` | Arc interpretation and validation |
| `src/emc/rs274ngc/interp_convert.cc` | G-code conversion, including G76 threading cycle |
| `src/emc/rs274ngc/interp_check.cc` | Interpreter word and cycle checks |
| `src/emc/rs274ngc/interp_internal.hh` | Interpreter constants and tolerances |
| `src/emc/motion/control.c` | Runtime motion control and spindle index handling |
| `src/emc/motion/motion.c` | Motion HAL pins and controller integration |

## Limitations

- This is not a complete LinuxCNC source checkout.
- Confirm the physical lathe actually runs the documented stock `2.9.6` build
  before treating source-level behavior as machine-verified.
- Configuration, firmware, HAL wiring, and physical measurements still determine
  how the machine behaves.
