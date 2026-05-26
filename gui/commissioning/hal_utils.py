"""HAL Monitor Utilities — Pure functions for tree building and formatting.

All functions are pure (no side effects, no Qt dependencies) for easy testing.
"""

from typing import List

from gui.commissioning.pin_providers import PinInfo


# =============================================================================
# Constants
# =============================================================================

FILTER_PRESETS = {
    "Home": ["gpio.000", "gpio.003", "debounce.0.0", "debounce.0.3"],
    "E-Stop": ["gpio.004"],
    "Jog": ["gpio.005", "gpio.006", "gpio.007", "gpio.008",
             "debounce.0.4", "debounce.0.5", "debounce.0.6", "debounce.0.7"],
    "Cycle": ["gpio.009", "gpio.010", "debounce.0.8", "debounce.0.9"],
    "MPG": ["encoder.03", "encoder.04", "mux8.jogscale", "or2.jog-vel-mode"],
    "Spindle": ["encoder.02", "spindle.0"],
    "PID": ["pid.x", "pid.z"],
    "Stepgen": ["stepgen.00", "stepgen.01"],
    "Encoders": ["encoder.00", "encoder.01"],
}

REFRESH_INTERVALS = [
    (50, "50ms"),
    (100, "100ms"),
    (250, "250ms"),
    (500, "500ms"),
]


# =============================================================================
# Pure Functions
# =============================================================================

def build_pin_tree(pins: List[PinInfo]) -> dict:
    """Build a nested dict from a flat pin list by splitting names on '.'.

    Intermediate keys map to child dicts. Leaf keys map to PinInfo objects.

    Example:
        Input:  [PinInfo("pid.x.command", ...), PinInfo("pid.x.output", ...)]
        Output: {"pid": {"x": {"command": PinInfo(...), "output": PinInfo(...)}}}
    """
    tree = {}
    for pin in pins:
        parts = pin.name.split(".")
        node = tree
        for part in parts[:-1]:
            if part not in node or isinstance(node[part], PinInfo):
                node[part] = {}
            node = node[part]
        node[parts[-1]] = pin
    return tree


def format_pin_value(value, pin_type: str) -> str:
    """Format a HAL pin value for display.

    Returns:
        "TRUE"/"FALSE" for bit, 6 decimal places for float,
        plain integer for s32/u32.
    """
    if pin_type == "bit":
        return "TRUE" if value else "FALSE"
    elif pin_type == "float":
        try:
            return f"{float(value):.6f}"
        except (ValueError, TypeError):
            return str(value)
    elif pin_type in ("s32", "u32"):
        try:
            return str(int(value))
        except (ValueError, TypeError):
            return str(value)
    return str(value)


def filter_pins(pins: List[PinInfo], filter_text: str) -> List[PinInfo]:
    """Return pins whose name contains filter_text (case-insensitive)."""
    if not filter_text:
        return list(pins)
    lower = filter_text.lower()
    return [p for p in pins if lower in p.name.lower()]


def match_preset(pin_name: str, patterns: List[str]) -> bool:
    """Return True if pin_name contains any of the given patterns."""
    return any(pattern in pin_name for pattern in patterns)
