---
inclusion: manual
---
# QtPyVCP Reference — LinuxCNC Python GUI Framework

## What It Is

[QtPyVCP](https://www.qtpyvcp.com/) is the standard Qt/Python framework for building LinuxCNC virtual control panels. Created by Kurt Jacobson. Our project does NOT use QtPyVCP directly — we build a standalone PyQt5 GUI — but it's useful as a reference for how the LinuxCNC community structures Python GUIs.

Source: [github.com/kcjengr/qtpyvcp](https://github.com/kcjengr/qtpyvcp)

## Architecture (for reference only)

QtPyVCP uses a plugin-based architecture:
- **app/** — main() entrypoint and VCP launcher
- **plugins/** — plugin registration and base classes (DataPlugin, Plugin)
- **widgets/** — custom Qt widgets (input, display, HAL, buttons)
- **hal/** — LinuxCNC HAL pin helpers
- **tools/** — CLI utilities
- **utilities/** — logging, config, YAML loading

Key patterns:
- Plugins are the backbone of data access (status monitors, tool tables, inputs, notifications)
- Plugins stored in ordered dict — deterministic init/terminate order
- `getPlugin()` returns NullPlugin in Qt Designer mode (supports live widget editing without LinuxCNC)
- YAML configuration files merged with INI-derived settings
- Console scripts registered via pyproject.toml entry points
- `.ui` files built with Qt Designer, combined with Python for custom behavior

## How This Relates to Our Project

| QtPyVCP Pattern | Our Equivalent |
|-----------------|----------------|
| Plugin system for data access | Direct module imports (models/, pipeline/) |
| HAL integration via hal/ package | `try: import linuxcnc` / `HAS_LINUXCNC` flag |
| .ui files + Qt Designer | Pure Python widget construction |
| YAML config | Frozen dataclasses (NumericFieldConfig, etc.) |
| Plugin-based tool table | pipeline/file_io.py (load_tool_table, save_tool_table) |
| Status monitors as plugins | StatusBar widget with update methods |
| Widget registration for Designer | Not needed (no .ui files) |

## Key Differences (Why We Don't Use QtPyVCP)

1. **We need offline mode** — QtPyVCP requires LinuxCNC running. Our GUI works on Windows for development.
2. **We have a CAM engine** — QtPyVCP is a control panel framework, not a toolpath generator. Our engine (Build123d → planners → G-code) has no equivalent in QtPyVCP.
3. **Simpler architecture** — We don't need plugin registration, YAML config merging, or Designer support. Direct imports are clearer for our use case.
4. **Tight coupling to engine** — Our GUI tabs directly call pipeline.execute() and display PlanResult. A plugin layer would add indirection without benefit.

## Useful Ideas to Borrow

- **HAL pin abstraction** — When we wire to LinuxCNC live, a thin HAL wrapper (like their hal/ package) could keep HAL details out of widget code
- **NullPlugin pattern** — Their approach of returning stub objects when LinuxCNC isn't available is similar to our `HAS_LINUXCNC = False` pattern
- **Widget grouping** — input_widgets, display_widgets, hal_widgets, button_widgets — good organizational pattern we partially follow with gui/components/
- **Entry point via pyproject.toml** — We could register `industry-cam-engine` as a console script for cleaner launching

## Links

- Documentation: https://www.qtpyvcp.com/
- GitHub: https://github.com/kcjengr/qtpyvcp
- LinuxCNC Forum: https://forum.linuxcnc.org/qtpyvcp
- Architecture: https://www.qtpyvcp.com/architecture.html
