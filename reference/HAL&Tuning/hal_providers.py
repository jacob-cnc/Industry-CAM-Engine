"""
HAL Pin Data Providers — Live and Offline implementations.

Provides two duck-typed providers with the same interface:
  - LiveHALProvider: reads real HAL pin data via the LinuxCNC hal module
  - OfflineHALProvider: returns static demo data mirroring the machine config

Both return pin dicts with keys: name, type, direction, value, signal.
"""

# ---------------------------------------------------------------------------
# Direction and type mappings for the hal module
# ---------------------------------------------------------------------------

_DIR_MAP = {1: "IN", 2: "OUT", 3: "I/O"}
_TYPE_MAP = {1: "bit", 2: "float", 3: "s32", 4: "u32"}


# ===========================================================================
# LiveHALProvider
# ===========================================================================

class LiveHALProvider:
    """Reads real HAL pin data via the linuxcnc hal module.

    Only usable on Linux with LinuxCNC installed.  The ``hal`` module is
    imported lazily so this file can be imported on Windows without error
    (the caller should instantiate OfflineHALProvider instead when
    HAS_LINUXCNC is False).
    """

    def __init__(self):
        import hal  # noqa: F811 — only available on LinuxCNC
        self._hal = hal
        # Sanity check: verify get_info_pins returns usable data.
        # If LinuxCNC isn't running, this may return empty or garbage.
        raw = self._hal.get_info_pins()
        if not raw:
            raise RuntimeError("hal.get_info_pins() returned no data — LinuxCNC not running?")
        # Check that at least one entry has numeric type/direction fields
        has_valid = any(
            len(entry) >= 4 and isinstance(entry[2], int)
            for entry in raw
        )
        if not has_valid:
            raise RuntimeError("hal.get_info_pins() returned no valid pin entries")

    # ------------------------------------------------------------------
    def get_all_pins(self):
        """Return all HAL pins as a list of dicts.

        Uses ``hal.get_info_pins()`` which returns a list of tuples:
        ``(name, direction_int, type_int, value)``.

        Skips any entries that don't have the expected numeric type/direction
        fields (e.g. header rows returned when LinuxCNC isn't fully running).
        """
        raw = self._hal.get_info_pins()
        pins = []
        for entry in raw:
            if len(entry) < 4:
                continue
            name, direction, pin_type, value = entry[:4]
            # Skip entries where direction or type aren't integers
            # (hal may return header/metadata rows as strings)
            if not isinstance(pin_type, int) or not isinstance(direction, int):
                continue
            pins.append({
                "name": name,
                "type": _TYPE_MAP.get(pin_type, "unknown"),
                "direction": _DIR_MAP.get(direction, "???"),
                "value": value,
                "signal": "",  # signal info not available from get_info_pins
            })
        return pins

    # ------------------------------------------------------------------
    def get_pin_value(self, pin_name):
        """Read the current value of a single pin by name."""
        for name, _direction, _pin_type, value in self._hal.get_info_pins():
            if name == pin_name:
                return value
        raise KeyError(f"HAL pin not found: {pin_name}")

    # ------------------------------------------------------------------
    def get_pin_info(self, pin_name):
        """Return full info dict for a pin, or None if not found."""
        for name, direction, pin_type, value in self._hal.get_info_pins():
            if name == pin_name:
                return {
                    "name": name,
                    "type": _TYPE_MAP.get(pin_type, "unknown"),
                    "direction": _DIR_MAP.get(direction, "???"),
                    "value": value,
                    "signal": "",
                }
        return None


# ===========================================================================
# OfflineHALProvider — static demo data
# ===========================================================================

# Mesa board prefix used in the real HAL file
_MESA = "hm2_10.10.10.10"

# fmt: off
DEMO_PINS = [
    # ------------------------------------------------------------------
    # Limit / Home switches — gpio.000–003 raw + debounced pairs
    # ------------------------------------------------------------------
    {"name": f"{_MESA}.gpio.000.in",     "type": "bit", "direction": "IN",  "value": False, "signal": "z-minus-home-raw"},
    {"name": f"{_MESA}.gpio.000.in_not", "type": "bit", "direction": "IN",  "value": True,  "signal": "z-minus-home-raw"},
    {"name": f"{_MESA}.gpio.001.in",     "type": "bit", "direction": "IN",  "value": False, "signal": "z-plus-limit-raw"},
    {"name": f"{_MESA}.gpio.001.in_not", "type": "bit", "direction": "IN",  "value": True,  "signal": "z-plus-limit-raw"},
    {"name": f"{_MESA}.gpio.002.in",     "type": "bit", "direction": "IN",  "value": False, "signal": "x-minus-limit-raw"},
    {"name": f"{_MESA}.gpio.002.in_not", "type": "bit", "direction": "IN",  "value": True,  "signal": "x-minus-limit-raw"},
    {"name": f"{_MESA}.gpio.003.in",     "type": "bit", "direction": "IN",  "value": False, "signal": "x-plus-home-raw"},
    {"name": f"{_MESA}.gpio.003.in_not", "type": "bit", "direction": "IN",  "value": True,  "signal": "x-plus-home-raw"},
    {"name": "debounce.0.0.in",          "type": "bit", "direction": "IN",  "value": True,  "signal": "z-minus-home-raw"},
    {"name": "debounce.0.0.out",         "type": "bit", "direction": "OUT", "value": False, "signal": "z-minus-home"},
    {"name": "debounce.0.1.in",          "type": "bit", "direction": "IN",  "value": True,  "signal": "z-plus-limit-raw"},
    {"name": "debounce.0.1.out",         "type": "bit", "direction": "OUT", "value": False, "signal": "z-plus-limit"},
    {"name": "debounce.0.2.in",          "type": "bit", "direction": "IN",  "value": True,  "signal": "x-minus-limit-raw"},
    {"name": "debounce.0.2.out",         "type": "bit", "direction": "OUT", "value": False, "signal": "x-minus-limit"},
    {"name": "debounce.0.3.in",          "type": "bit", "direction": "IN",  "value": True,  "signal": "x-plus-home-raw"},
    {"name": "debounce.0.3.out",         "type": "bit", "direction": "OUT", "value": False, "signal": "x-plus-home"},

    # ------------------------------------------------------------------
    # E-Stop — gpio.004
    # ------------------------------------------------------------------
    {"name": f"{_MESA}.gpio.004.in",     "type": "bit", "direction": "IN",  "value": False, "signal": ""},
    {"name": f"{_MESA}.gpio.004.in_not", "type": "bit", "direction": "IN",  "value": True,  "signal": "estop-ext"},

    # ------------------------------------------------------------------
    # Jog buttons — gpio.005–008 raw + debounced pairs
    # ------------------------------------------------------------------
    {"name": f"{_MESA}.gpio.005.in_not", "type": "bit", "direction": "IN",  "value": False, "signal": "jog-z-minus-raw"},
    {"name": f"{_MESA}.gpio.006.in_not", "type": "bit", "direction": "IN",  "value": False, "signal": "jog-z-plus-raw"},
    {"name": f"{_MESA}.gpio.007.in_not", "type": "bit", "direction": "IN",  "value": False, "signal": "jog-x-minus-raw"},
    {"name": f"{_MESA}.gpio.008.in_not", "type": "bit", "direction": "IN",  "value": False, "signal": "jog-x-plus-raw"},
    {"name": "debounce.0.4.in",          "type": "bit", "direction": "IN",  "value": False, "signal": "jog-z-minus-raw"},
    {"name": "debounce.0.4.out",         "type": "bit", "direction": "OUT", "value": False, "signal": "jog-z-minus"},
    {"name": "debounce.0.5.in",          "type": "bit", "direction": "IN",  "value": False, "signal": "jog-z-plus-raw"},
    {"name": "debounce.0.5.out",         "type": "bit", "direction": "OUT", "value": False, "signal": "jog-z-plus"},
    {"name": "debounce.0.6.in",          "type": "bit", "direction": "IN",  "value": False, "signal": "jog-x-minus-raw"},
    {"name": "debounce.0.6.out",         "type": "bit", "direction": "OUT", "value": False, "signal": "jog-x-minus"},
    {"name": "debounce.0.7.in",          "type": "bit", "direction": "IN",  "value": False, "signal": "jog-x-plus-raw"},
    {"name": "debounce.0.7.out",         "type": "bit", "direction": "OUT", "value": False, "signal": "jog-x-plus"},

    # ------------------------------------------------------------------
    # Cycle start / stop — gpio.009–010 raw + debounced pairs
    # ------------------------------------------------------------------
    {"name": f"{_MESA}.gpio.009.in_not", "type": "bit", "direction": "IN",  "value": False, "signal": "cycle-go-raw"},
    {"name": f"{_MESA}.gpio.010.in_not", "type": "bit", "direction": "IN",  "value": False, "signal": "cycle-stop-raw"},
    {"name": "debounce.0.8.in",          "type": "bit", "direction": "IN",  "value": False, "signal": "cycle-go-raw"},
    {"name": "debounce.0.8.out",         "type": "bit", "direction": "OUT", "value": False, "signal": "cycle-go-btn"},
    {"name": "debounce.0.9.in",          "type": "bit", "direction": "IN",  "value": False, "signal": "cycle-stop-raw"},
    {"name": "debounce.0.9.out",         "type": "bit", "direction": "OUT", "value": False, "signal": "cycle-stop"},

    # ------------------------------------------------------------------
    # Spindle encoder — encoder.02 (7i96s TB2)
    # ------------------------------------------------------------------
    {"name": f"{_MESA}.encoder.02.position",     "type": "float", "direction": "OUT", "value": 1234.567890, "signal": "spindle-pos"},
    {"name": f"{_MESA}.encoder.02.velocity",     "type": "float", "direction": "OUT", "value": 12.345678,   "signal": "spindle-vel"},
    {"name": f"{_MESA}.encoder.02.index-enable", "type": "bit",   "direction": "I/O", "value": False,       "signal": "spindle-index"},

    # ------------------------------------------------------------------
    # MPG encoders — encoder.03 (X) and encoder.04 (Z) on 7i85s
    # ------------------------------------------------------------------
    {"name": f"{_MESA}.encoder.03.count",    "type": "s32",   "direction": "OUT", "value": 4200,       "signal": "mpg-x-counts"},
    {"name": f"{_MESA}.encoder.03.position", "type": "float", "direction": "OUT", "value": 42.000000,  "signal": ""},
    {"name": f"{_MESA}.encoder.04.count",    "type": "s32",   "direction": "OUT", "value": -1500,      "signal": "mpg-z-counts"},
    {"name": f"{_MESA}.encoder.04.position", "type": "float", "direction": "OUT", "value": -15.000000, "signal": ""},

    # ------------------------------------------------------------------
    # MPG jog scale — mux4 outputs
    # ------------------------------------------------------------------
    {"name": "mux4.jogscale-x.out", "type": "float", "direction": "OUT", "value": 0.001000, "signal": "mpg-x-scale"},
    {"name": "mux4.jogscale-z.out", "type": "float", "direction": "OUT", "value": 0.001000, "signal": "mpg-z-scale"},

    # ------------------------------------------------------------------
    # Linear encoders — encoder.00 (X) and encoder.01 (Z) on 7i85s TB1
    # (planned hardware — not yet wired)
    # ------------------------------------------------------------------
    {"name": f"{_MESA}.encoder.00.position", "type": "float", "direction": "OUT", "value": 0.000000, "signal": "x-pos-fb"},
    {"name": f"{_MESA}.encoder.01.position", "type": "float", "direction": "OUT", "value": 0.000000, "signal": "z-pos-fb"},

    # ------------------------------------------------------------------
    # PID — pid.x and pid.z
    # ------------------------------------------------------------------
    {"name": "pid.x.command",  "type": "float", "direction": "IN",  "value": 0.000000,  "signal": "x-pos-cmd"},
    {"name": "pid.x.feedback", "type": "float", "direction": "IN",  "value": 0.000000,  "signal": "x-pos-fb"},
    {"name": "pid.x.output",   "type": "float", "direction": "OUT", "value": 0.000000,  "signal": "x-pid-out"},
    {"name": "pid.x.error",    "type": "float", "direction": "OUT", "value": 0.000000,  "signal": ""},
    {"name": "pid.z.command",  "type": "float", "direction": "IN",  "value": 0.000000,  "signal": "z-pos-cmd"},
    {"name": "pid.z.feedback", "type": "float", "direction": "IN",  "value": 0.000000,  "signal": "z-pos-fb"},
    {"name": "pid.z.output",   "type": "float", "direction": "OUT", "value": 0.000000,  "signal": "z-pid-out"},
    {"name": "pid.z.error",    "type": "float", "direction": "OUT", "value": 0.000000,  "signal": ""},

    # ------------------------------------------------------------------
    # Stepgen — stepgen.00 (Z axis) and stepgen.01 (X axis)
    # ------------------------------------------------------------------
    {"name": f"{_MESA}.stepgen.00.position-fb",  "type": "float", "direction": "OUT", "value": 0.000000, "signal": ""},
    {"name": f"{_MESA}.stepgen.00.velocity-cmd", "type": "float", "direction": "IN",  "value": 0.000000, "signal": "z-pid-out"},
    {"name": f"{_MESA}.stepgen.01.position-fb",  "type": "float", "direction": "OUT", "value": 0.000000, "signal": ""},
    {"name": f"{_MESA}.stepgen.01.velocity-cmd", "type": "float", "direction": "IN",  "value": 0.000000, "signal": "x-pid-out"},

    # ------------------------------------------------------------------
    # Analog pot inputs (planned hardware — not yet wired)
    # ------------------------------------------------------------------
    {"name": f"{_MESA}.7i96s.0.0.analogin0", "type": "float", "direction": "IN", "value": 5.000000, "signal": "feed-ovr-raw"},
    {"name": f"{_MESA}.7i96s.0.0.analogin1", "type": "float", "direction": "IN", "value": 5.000000, "signal": "spindle-ovr-raw"},
    {"name": f"{_MESA}.7i96s.0.0.analogin2", "type": "float", "direction": "IN", "value": 5.000000, "signal": "jog-vel-raw"},

    # ------------------------------------------------------------------
    # Scale outputs — feed override, spindle override, jog velocity
    # ------------------------------------------------------------------
    {"name": "scale.feed-override.out",    "type": "float", "direction": "OUT", "value": 1.000000, "signal": "feed-ovr-scaled"},
    {"name": "scale.spindle-override.out", "type": "float", "direction": "OUT", "value": 0.750000, "signal": "spindle-ovr-scaled"},
    {"name": "scale.jog-velocity.out",     "type": "float", "direction": "OUT", "value": 2.500000, "signal": "jog-vel-scaled"},

    # ------------------------------------------------------------------
    # Spindle component pins
    # ------------------------------------------------------------------
    {"name": "spindle.0.revs",      "type": "float", "direction": "IN",  "value": 1234.567890, "signal": "spindle-pos"},
    {"name": "spindle.0.speed-in",  "type": "float", "direction": "IN",  "value": 12.345678,   "signal": "spindle-vel"},
    {"name": "spindle.0.at-speed",  "type": "bit",   "direction": "IN",  "value": True,         "signal": "spindle-at-speed"},

    # ------------------------------------------------------------------
    # Near-spindle at-speed detection
    # ------------------------------------------------------------------
    {"name": "near-spindle.out", "type": "bit", "direction": "OUT", "value": True, "signal": "spindle-at-speed"},
]
# fmt: on


class OfflineHALProvider:
    """Returns simulated demo pin data for offline development.

    The demo data mirrors the actual machine's HAL configuration so that
    tree navigation, filtering, and watch list features can be tested
    without a LinuxCNC connection.
    """

    def __init__(self):
        # Build a lookup dict for O(1) access by name
        self._pins = list(DEMO_PINS)
        self._lookup = {p["name"]: p for p in self._pins}

    # ------------------------------------------------------------------
    def get_all_pins(self):
        """Return all demo pins as a list of dicts."""
        return list(self._pins)

    # ------------------------------------------------------------------
    def get_pin_value(self, pin_name):
        """Return the static demo value for a pin."""
        pin = self._lookup.get(pin_name)
        if pin is None:
            raise KeyError(f"HAL pin not found: {pin_name}")
        return pin["value"]

    # ------------------------------------------------------------------
    def get_pin_info(self, pin_name):
        """Return full info dict for a pin, or None if not found."""
        pin = self._lookup.get(pin_name)
        if pin is None:
            return None
        return dict(pin)  # return a copy
