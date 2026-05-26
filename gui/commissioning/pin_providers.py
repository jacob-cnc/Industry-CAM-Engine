"""HAL Pin Data Providers — Low-level pin access for diagnostics.

This is SEPARATE from hal/interface.py (which handles machine control).
Pin providers give raw access to individual HAL pins for:
    - HAL Monitor tab (browse all pins, watch values)
    - Tuning tab (read PID error, encoder positions)
    - Signal tracing (follow signal connections)

Two implementations:
    LivePinProvider — reads real HAL pins via linuxcnc hal module
    OfflinePinProvider — returns demo data matching machine config

Both expose the same interface so UI code never checks which is active.
"""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# Direction and type mappings for the hal module
_DIR_MAP = {1: "IN", 2: "OUT", 3: "I/O"}
_TYPE_MAP = {1: "bit", 2: "float", 3: "s32", 4: "u32"}


# =============================================================================
# Pin Data Structure
# =============================================================================

class PinInfo:
    """Lightweight container for a single HAL pin's metadata + value.

    Attributes:
        name: Full HAL pin name (e.g., 'pid.x.Pgain')
        pin_type: One of 'bit', 'float', 's32', 'u32'
        direction: One of 'IN', 'OUT', 'I/O'
        value: Current value (bool, float, or int)
        signal: Connected signal name (empty string if unconnected)
    """
    __slots__ = ('name', 'pin_type', 'direction', 'value', 'signal')

    def __init__(self, name: str, pin_type: str, direction: str,
                 value, signal: str = ""):
        self.name = name
        self.pin_type = pin_type
        self.direction = direction
        self.value = value
        self.signal = signal

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.pin_type,
            "direction": self.direction,
            "value": self.value,
            "signal": self.signal,
        }


# =============================================================================
# Abstract Provider Interface
# =============================================================================

class PinProvider:
    """Base interface for HAL pin data access.

    Subclasses must implement:
        get_all_pins() -> List[PinInfo]
        get_pin_value(pin_name) -> value
        get_signal_pins(signal_name) -> List[PinInfo]
    """

    def get_all_pins(self) -> List[PinInfo]:
        """Return all HAL pins."""
        raise NotImplementedError

    def get_pin_value(self, pin_name: str):
        """Read current value of a single pin by name.

        Raises KeyError if pin not found.
        """
        raise NotImplementedError

    def get_pin_info(self, pin_name: str) -> Optional[PinInfo]:
        """Return full PinInfo for a pin, or None if not found."""
        raise NotImplementedError

    def get_signal_pins(self, signal_name: str) -> List[PinInfo]:
        """Return all pins connected to a given signal.

        This enables signal tracing: click a signal → see all connected pins.
        """
        raise NotImplementedError

    def set_pin_value(self, pin_name: str, value) -> bool:
        """Set a HAL pin value at runtime (via halcmd setp).

        Only works for writable pins when LinuxCNC is running.
        Returns True on success, False on failure.
        """
        raise NotImplementedError


# =============================================================================
# Live Provider — Real HAL data
# =============================================================================

class LivePinProvider(PinProvider):
    """Reads real HAL pin data via the linuxcnc hal module.

    Only usable on Linux with LinuxCNC running. Instantiation will raise
    if the hal module isn't available or LinuxCNC isn't running.
    """

    def __init__(self):
        import importlib.util as _ilu
        _spec = _ilu.spec_from_file_location(
            "hal_lcnc", "/usr/lib/python3/dist-packages/hal.py"
        )
        _mod = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        self._hal = _mod
        # Verify we can read pins
        raw = self._hal.get_info_pins()
        if not raw:
            raise RuntimeError(
                "hal.get_info_pins() returned no data — LinuxCNC not running?"
            )
        logger.info("LivePinProvider: connected, %d pins available", len(raw))

    def get_all_pins(self) -> List[PinInfo]:
        raw = self._hal.get_info_pins()
        pins = []
        for entry in raw:
            if len(entry) < 4:
                continue
            name, direction, pin_type, value = entry[:4]
            # Accept both int and string type/direction values
            if isinstance(pin_type, int):
                type_str = _TYPE_MAP.get(pin_type, "unknown")
            elif isinstance(pin_type, str):
                type_str = pin_type
            else:
                continue
            if isinstance(direction, int):
                dir_str = _DIR_MAP.get(direction, "???")
            elif isinstance(direction, str):
                dir_str = direction
            else:
                continue
            pins.append(PinInfo(
                name=name,
                pin_type=type_str,
                direction=dir_str,
                value=value,
                signal="",
            ))
        if not pins:
            # Fallback: parse halcmd show pin output
            pins = self._get_all_pins_halcmd()
        return pins

    def _get_all_pins_halcmd(self) -> List[PinInfo]:
        """Fallback: enumerate pins via halcmd show pin."""
        import subprocess
        pins = []
        try:
            result = subprocess.run(
                ['halcmd', 'show', 'pin'],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode != 0:
                return pins
            for line in result.stdout.splitlines():
                # halcmd show pin format:
                # <owner> <type> <dir> <value> <name> [<== signal]
                parts = line.split()
                if len(parts) < 5:
                    continue
                # Skip header lines
                if parts[0] in ('Owner', 'Comp', '-----'):
                    continue
                try:
                    int(parts[0])  # owner is numeric
                except ValueError:
                    continue
                pin_type = parts[1].lower()  # bit, float, s32, u32
                direction = parts[2]  # IN, OUT, I/O
                value_str = parts[3]
                name = parts[4]
                signal = parts[6] if len(parts) >= 7 and parts[5] in ('==>', '<==', '<=>') else ""
                # Parse value
                if pin_type == 'bit':
                    value = value_str == 'TRUE'
                elif pin_type == 'float':
                    value = float(value_str)
                elif pin_type in ('s32', 'u32'):
                    value = int(value_str)
                else:
                    value = value_str
                pins.append(PinInfo(
                    name=name,
                    pin_type=pin_type,
                    direction=direction,
                    value=value,
                    signal=signal,
                ))
        except (subprocess.TimeoutExpired, OSError, ValueError) as e:
            logger.warning("halcmd show pin fallback failed: %s", e)
        return pins

    def get_pin_value(self, pin_name: str):
        for entry in self._hal.get_info_pins():
            if len(entry) >= 4 and entry[0] == pin_name:
                return entry[3]
        # Fallback: try halcmd getp (slower but handles name mismatches)
        import subprocess
        try:
            result = subprocess.run(
                ['halcmd', 'getp', pin_name],
                capture_output=True, text=True, timeout=1,
            )
            if result.returncode == 0:
                return float(result.stdout.strip())
        except (subprocess.TimeoutExpired, ValueError, OSError):
            pass
        raise KeyError(f"HAL pin not found: {pin_name}")

    def get_pin_info(self, pin_name: str) -> Optional[PinInfo]:
        for entry in self._hal.get_info_pins():
            if len(entry) >= 4 and entry[0] == pin_name:
                name, direction, pin_type, value = entry[:4]
                return PinInfo(
                    name=name,
                    pin_type=_TYPE_MAP.get(pin_type, "unknown"),
                    direction=_DIR_MAP.get(direction, "???"),
                    value=value,
                )
        return None

    def get_signal_pins(self, signal_name: str) -> List[PinInfo]:
        # hal module doesn't directly expose signal→pin mapping,
        # so we'd need to parse halcmd output. For now, return empty.
        # TODO: implement via subprocess halcmd show sig <name>
        return []

    def set_pin_value(self, pin_name: str, value) -> bool:
        import subprocess
        try:
            result = subprocess.run(
                ['halcmd', 'setp', pin_name, str(value)],
                capture_output=True, text=True, timeout=2,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
            logger.warning("halcmd setp failed: %s", e)
            return False


# =============================================================================
# Offline Provider — Demo data matching machine config
# =============================================================================

# Mesa board prefix
_MESA = "hm2_7i96s.0"


def _build_demo_pins() -> List[PinInfo]:
    """Build the complete set of demo pins matching the real machine."""
    pins = []

    def _add(name, pin_type, direction, value, signal=""):
        pins.append(PinInfo(name, pin_type, direction, value, signal))

    # --- Home switches (gpio.000, gpio.003) ---
    _add(f"{_MESA}.gpio.000.in", "bit", "IN", False, "z-home-raw")
    _add(f"{_MESA}.gpio.000.in_not", "bit", "IN", True, "")
    _add(f"{_MESA}.gpio.003.in", "bit", "IN", False, "x-home-raw")
    _add(f"{_MESA}.gpio.003.in_not", "bit", "IN", True, "")

    # --- E-Stop (gpio.004, TB3 P5) — connected, not yet in estop net ---
    _add(f"{_MESA}.gpio.004.in", "bit", "IN", True, "")
    _add(f"{_MESA}.gpio.004.in_not", "bit", "IN", False, "")

    # --- Jog buttons (gpio.005–008) ---
    _add(f"{_MESA}.gpio.005.in_not", "bit", "IN", False, "jog-z-minus-raw")
    _add(f"{_MESA}.gpio.006.in_not", "bit", "IN", False, "jog-z-plus-raw")
    _add(f"{_MESA}.gpio.007.in_not", "bit", "IN", False, "jog-x-minus-raw")
    _add(f"{_MESA}.gpio.008.in_not", "bit", "IN", False, "jog-x-plus-raw")

    # --- Cycle start/stop (gpio.009–010) ---
    _add(f"{_MESA}.gpio.009.in_not", "bit", "IN", False, "cycle-go-raw")
    _add(f"{_MESA}.gpio.010.in_not", "bit", "IN", False, "cycle-stop-raw")

    # --- Spindle encoder (encoder.04 on 7i96s TB2 onboard) ---
    _add(f"{_MESA}.encoder.04.position", "float", "OUT", 0.0, "spindle-pos")
    _add(f"{_MESA}.encoder.04.velocity", "float", "OUT", 13.33, "spindle-vel")
    _add(f"{_MESA}.encoder.04.index-enable", "bit", "I/O", False, "spindle-index")

    # --- MPG encoders (encoder.02=Z MPG, encoder.03=X MPG on 7i85s) ---
    _add(f"{_MESA}.encoder.02.count", "s32", "OUT", 0, "mpg-z-counts")
    _add(f"{_MESA}.encoder.02.position", "float", "OUT", 0.0, "")
    _add(f"{_MESA}.encoder.03.count", "s32", "OUT", 0, "mpg-x-counts")
    _add(f"{_MESA}.encoder.03.position", "float", "OUT", 0.0, "")

    # --- Linear encoders (encoder.00=Z, encoder.01=X on 7i85s TB3) ---
    _add(f"{_MESA}.encoder.00.position", "float", "OUT", 0.0, "z-pos-fb")
    _add(f"{_MESA}.encoder.00.velocity", "float", "OUT", 0.0, "")
    _add(f"{_MESA}.encoder.01.position", "float", "OUT", 0.0, "x-pos-fb")
    _add(f"{_MESA}.encoder.01.velocity", "float", "OUT", 0.0, "")

    # --- PID (pid.x and pid.z) ---
    _add("pid.x.command", "float", "IN", 0.0, "x-pos-cmd")
    _add("pid.x.feedback", "float", "IN", 0.0, "x-pos-fb")
    _add("pid.x.output", "float", "OUT", 0.0, "x-pid-out")
    _add("pid.x.error", "float", "OUT", 0.0, "")
    _add("pid.x.Pgain", "float", "IN", 1000.0, "")
    _add("pid.x.Igain", "float", "IN", 0.0, "")
    _add("pid.x.Dgain", "float", "IN", 0.0, "")
    _add("pid.x.FF0", "float", "IN", 0.0, "")
    _add("pid.x.FF1", "float", "IN", 1.0, "")
    _add("pid.x.FF2", "float", "IN", 0.0, "")
    _add("pid.x.deadband", "float", "IN", 0.00005, "")
    _add("pid.x.maxoutput", "float", "IN", 2.5, "")
    _add("pid.x.maxerror", "float", "IN", 0.0005, "")

    _add("pid.z.command", "float", "IN", 0.0, "z-pos-cmd")
    _add("pid.z.feedback", "float", "IN", 0.0, "z-pos-fb")
    _add("pid.z.output", "float", "OUT", 0.0, "z-pid-out")
    _add("pid.z.error", "float", "OUT", 0.0, "")
    _add("pid.z.Pgain", "float", "IN", 1000.0, "")
    _add("pid.z.Igain", "float", "IN", 0.0, "")
    _add("pid.z.Dgain", "float", "IN", 0.0, "")
    _add("pid.z.FF0", "float", "IN", 0.0, "")
    _add("pid.z.FF1", "float", "IN", 1.0, "")
    _add("pid.z.FF2", "float", "IN", 0.0, "")
    _add("pid.z.deadband", "float", "IN", 0.00005, "")
    _add("pid.z.maxoutput", "float", "IN", 2.5, "")
    _add("pid.z.maxerror", "float", "IN", 0.0005, "")

    # --- Stepgen (stepgen.00=Z, stepgen.01=X — REVERSED from joint #) ---
    _add(f"{_MESA}.stepgen.00.position-fb", "float", "OUT", 0.0, "z-stepgen-fb")
    _add(f"{_MESA}.stepgen.00.velocity-cmd", "float", "IN", 0.0, "z-pid-out")
    _add(f"{_MESA}.stepgen.00.counts", "s32", "OUT", 0, "")
    _add(f"{_MESA}.stepgen.01.position-fb", "float", "OUT", 0.0, "x-stepgen-fb")
    _add(f"{_MESA}.stepgen.01.velocity-cmd", "float", "IN", 0.0, "x-pid-out")
    _add(f"{_MESA}.stepgen.01.counts", "s32", "OUT", 0, "")

    # --- Spindle component ---
    _add("spindle.0.revs", "float", "IN", 0.0, "spindle-pos")
    _add("spindle.0.speed-in", "float", "IN", 13.33, "spindle-vel")
    _add("spindle.0.at-speed", "bit", "IN", True, "spindle-at-speed")

    # --- Debounce outputs ---
    _add("debounce.0.0.out", "bit", "OUT", False, "z-home")
    _add("debounce.0.3.out", "bit", "OUT", False, "x-home")
    _add("debounce.0.4.out", "bit", "OUT", False, "jog-z-minus")
    _add("debounce.0.5.out", "bit", "OUT", False, "jog-z-plus")
    _add("debounce.0.6.out", "bit", "OUT", False, "jog-x-minus")
    _add("debounce.0.7.out", "bit", "OUT", False, "jog-x-plus")
    _add("debounce.0.8.out", "bit", "OUT", False, "cycle-go-btn")
    _add("debounce.0.9.out", "bit", "OUT", False, "cycle-stop")

    return pins


class OfflinePinProvider(PinProvider):
    """Returns demo pin data for offline development.

    Demo data mirrors the actual machine's HAL configuration so that
    tree navigation, filtering, signal tracing, and watch list features
    can be tested without a LinuxCNC connection.
    """

    def __init__(self):
        self._pins = _build_demo_pins()
        self._lookup: Dict[str, PinInfo] = {p.name: p for p in self._pins}
        self._signal_index: Dict[str, List[PinInfo]] = {}
        for p in self._pins:
            if p.signal:
                self._signal_index.setdefault(p.signal, []).append(p)

    def get_all_pins(self) -> List[PinInfo]:
        return list(self._pins)

    def get_pin_value(self, pin_name: str):
        pin = self._lookup.get(pin_name)
        if pin is None:
            raise KeyError(f"HAL pin not found: {pin_name}")
        return pin.value

    def get_pin_info(self, pin_name: str) -> Optional[PinInfo]:
        return self._lookup.get(pin_name)

    def get_signal_pins(self, signal_name: str) -> List[PinInfo]:
        """Return all pins connected to a signal — enables signal tracing."""
        return self._signal_index.get(signal_name, [])

    def set_pin_value(self, pin_name: str, value) -> bool:
        """In offline mode, update the demo value (for testing UI flow)."""
        pin = self._lookup.get(pin_name)
        if pin is None:
            return False
        pin.value = value
        return True


# =============================================================================
# Factory
# =============================================================================

def get_pin_provider() -> PinProvider:
    """Get the appropriate pin provider for the current environment.

    Returns LivePinProvider if LinuxCNC is available, else OfflinePinProvider.
    """
    try:
        return LivePinProvider()
    except (ImportError, RuntimeError, Exception) as e:
        logger.info("Pin provider: using offline mode (%s)", e)
        return OfflinePinProvider()
