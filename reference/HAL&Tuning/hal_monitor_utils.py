"""
HAL Monitor Utilities — Pure functions and constants for the HAL Monitor tab.

Provides tree building, value formatting, pin filtering, and preset
definitions used by HALMonitorTab. All functions are pure (no side effects,
no Qt dependencies) to simplify testing.
"""


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FILTER_PRESETS = {
    "Limits/Home": ["gpio.000", "gpio.001", "gpio.002", "gpio.003",
                    "debounce.0.0", "debounce.0.1", "debounce.0.2", "debounce.0.3"],
    "E-Stop":      ["gpio.004"],
    "Jog Buttons": ["gpio.005", "gpio.006", "gpio.007", "gpio.008",
                    "debounce.0.4", "debounce.0.5", "debounce.0.6", "debounce.0.7"],
    "Cycle Ctrl":  ["gpio.009", "gpio.010",
                    "debounce.0.8", "debounce.0.9"],
    "MPG":         ["encoder.03", "encoder.04", "mux4.jogscale"],
    "Spindle":     ["encoder.02", "near-spindle", "spindle.0"],
    "PID":         ["pid.x", "pid.z"],
    "Stepgen":     ["stepgen.00", "stepgen.01"],
    "Linear Enc":  ["encoder.00", "encoder.01"],
    "Overrides":   ["analogin", "scale.feed-override", "scale.spindle-override",
                    "scale.jog-velocity"],
}

REFRESH_INTERVALS = [
    (50, "50ms"),
    (100, "100ms"),
    (250, "250ms"),
    (500, "500ms"),
]


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------

def build_pin_tree(pins):
    """Build a nested dict from a flat pin list by splitting names on '.'.

    Args:
        pins: List of pin dicts, each with at least a 'name' key.

    Returns:
        Nested dict where intermediate keys map to child dicts,
        and leaf keys map to the full pin dict.

    Example:
        Input:  [{"name": "pid.x.command", ...}, {"name": "pid.x.output", ...}]
        Output: {"pid": {"x": {"command": {...}, "output": {...}}}}
    """
    tree = {}
    for pin in pins:
        parts = pin["name"].split(".")
        node = tree
        for part in parts[:-1]:
            if part not in node or not isinstance(node[part], dict):
                node[part] = {}
            node = node[part]
        # Leaf node stores the full pin dict
        node[parts[-1]] = pin
    return tree


def format_pin_value(value, pin_type):
    """Format a HAL pin value for display.

    Args:
        value: The raw pin value.
        pin_type: One of "bit", "float", "s32", "u32".

    Returns:
        Formatted string: "TRUE"/"FALSE" for bit,
        6 decimal places for float, plain integer for s32/u32,
        or str(value) for unknown types.
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
    else:
        # Unknown type — display raw value as string
        return str(value)


def filter_pins(pins, filter_text):
    """Return pins whose name contains filter_text (case-insensitive).

    Args:
        pins: Full list of pin dicts, each with a 'name' key.
        filter_text: Substring to match against pin names.

    Returns:
        Filtered list of pin dicts.
    """
    if not filter_text:
        return list(pins)
    lower = filter_text.lower()
    return [p for p in pins if lower in p["name"].lower()]


def match_preset(pin_name, patterns):
    """Return True if pin_name contains any of the given patterns as a substring.

    Args:
        pin_name: Full HAL pin name.
        patterns: List of substring patterns from a filter preset.

    Returns:
        True if any pattern is a substring of pin_name.
    """
    for pattern in patterns:
        if pattern in pin_name:
            return True
    return False
