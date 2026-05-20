"""Live backend connecting to LinuxCNC via the Python API.

This module is only importable on Linux with LinuxCNC installed.
The factory (hal/factory.py) handles the import guard.

Wraps linuxcnc.stat, linuxcnc.command, and linuxcnc.error_channel
into the HALBackend interface.

Also creates a userspace HAL component for compound slide muxing.
"""

import logging
import importlib.util as _ilu
import linuxcnc

# Load system hal.so explicitly so the project's hal/ package in PYTHONPATH
# doesn't shadow it. Only available inside the LinuxCNC RT environment.
try:
    _spec = _ilu.spec_from_file_location(
        "hal_sys", "/usr/lib/python3/dist-packages/hal.py"
    )
    hal_module = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(hal_module)
except Exception:
    hal_module = None
del _ilu, _spec

logger = logging.getLogger(__name__)

from hal.interface import (
    HALBackend, MachineState, AxisState, SpindleState,
    InterpState, TaskMode, TaskState, HomingState, SpindleDirection,
)
from hal.constants import (
    X_MIN_LIMIT, X_MAX_LIMIT,
    Z_MIN_LIMIT, Z_MAX_LIMIT,
)


# LinuxCNC constant mappings
_TASK_STATE_MAP = {
    linuxcnc.STATE_ESTOP: TaskState.ESTOP,
    linuxcnc.STATE_ESTOP_RESET: TaskState.ESTOP_RESET,
    linuxcnc.STATE_OFF: TaskState.OFF,
    linuxcnc.STATE_ON: TaskState.ON,
}

_TASK_MODE_MAP = {
    linuxcnc.MODE_MANUAL: TaskMode.MANUAL,
    linuxcnc.MODE_AUTO: TaskMode.AUTO,
    linuxcnc.MODE_MDI: TaskMode.MDI,
}

_INTERP_MAP = {
    linuxcnc.INTERP_IDLE: InterpState.IDLE,
    linuxcnc.INTERP_READING: InterpState.READING,
    linuxcnc.INTERP_PAUSED: InterpState.PAUSED,
    linuxcnc.INTERP_WAITING: InterpState.WAITING,
}


class LiveBackend(HALBackend):
    """Real LinuxCNC backend using the Python API.

    Connects to the running LinuxCNC instance via NML shared memory.
    Requires LinuxCNC to be running (launched via INI file).

    Also creates a userspace HAL component 'compound-slide' with pins
    for MPG count reading and compound jog output.
    """

    def __init__(self):
        self._stat = linuxcnc.stat()
        self._cmd = linuxcnc.command()
        self._error = linuxcnc.error_channel()
        self._state = MachineState()
        self._connected = False

        # MPG encoder counts (read from HAL pins each poll cycle)
        self._mpg_x_counts = 0
        self._mpg_z_counts = 0

        # Create compound-slide HAL component
        self._hal_comp = None
        try:
            self._hal_comp = hal_module.component("compound-slide")
            # Input pins — MPG encoder counts fed from postgui.hal
            self._hal_comp.newpin("mpg-x-in", hal_module.HAL_S32, hal_module.HAL_IN)
            self._hal_comp.newpin("mpg-z-in", hal_module.HAL_S32, hal_module.HAL_IN)
            self._hal_comp.newpin("jog-scale", hal_module.HAL_FLOAT, hal_module.HAL_IN)
            # Control pins — written by GUI, read by HAL for mux selection
            self._hal_comp.newpin("compound-enable", hal_module.HAL_BIT, hal_module.HAL_OUT)
            self._hal_comp.newpin("compound-angle", hal_module.HAL_FLOAT, hal_module.HAL_OUT)
            # Output pins — decomposed jog counts written by GUI
            self._hal_comp.newpin("x-jog-counts", hal_module.HAL_S32, hal_module.HAL_OUT)
            self._hal_comp.newpin("z-jog-counts", hal_module.HAL_S32, hal_module.HAL_OUT)
            # MPG scale select pins — drive mux4.jogscale-*.sel0/sel1 via postgui.hal
            self._hal_comp.newpin("mpg-scale-sel0", hal_module.HAL_BIT, hal_module.HAL_OUT)
            self._hal_comp.newpin("mpg-scale-sel1", hal_module.HAL_BIT, hal_module.HAL_OUT)
            self._hal_comp.ready()
            # Default to index 1 = 0.001" per MPG click (sel0=1, sel1=0)
            self._hal_comp["mpg-scale-sel0"] = True
            self._hal_comp["mpg-scale-sel1"] = False
        except Exception:
            # If component already exists or HAL not ready, continue without it
            self._hal_comp = None

        try:
            self._stat.poll()
            self._connected = True
        except linuxcnc.error:
            self._connected = False

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def state(self) -> MachineState:
        return self._state

    @property
    def connected(self) -> bool:
        return self._connected

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------

    def poll(self) -> None:
        """Poll LinuxCNC stat channel and rebuild state snapshot.

        Also reads MPG encoder counts from the compound-slide HAL component
        pins for use by the compound slide feature.
        """
        try:
            self._stat.poll()
            self._connected = True
        except linuxcnc.error:
            self._connected = False
            return

        # Read MPG counts from HAL component pins
        if self._hal_comp is not None:
            try:
                self._mpg_x_counts = self._hal_comp["mpg-x-in"]
                self._mpg_z_counts = self._hal_comp["mpg-z-in"]
            except Exception:
                pass

        # Check error channel — drain all queued messages per cycle
        error_msg = ""
        while True:
            err = self._error.poll()
            if not err:
                break
            kind, text = err
            error_msg = text
            logger.error("LinuxCNC error [%s]: %s", kind, text)

        # Log state transitions to help diagnose unexpected E-STOP
        current_raw_state = self._stat.task_state
        if not hasattr(self, '_last_raw_state'):
            self._last_raw_state = current_raw_state
            logger.info("Initial machine state: %s", current_raw_state)
        elif current_raw_state != self._last_raw_state:
            state_names = {
                linuxcnc.STATE_ESTOP: "ESTOP",
                linuxcnc.STATE_ESTOP_RESET: "ESTOP_RESET",
                linuxcnc.STATE_OFF: "OFF",
                linuxcnc.STATE_ON: "ON",
            }
            logger.info("State transition: %s → %s",
                        state_names.get(self._last_raw_state, self._last_raw_state),
                        state_names.get(current_raw_state, current_raw_state))
            self._last_raw_state = current_raw_state

        s = self._stat

        # Task state
        task_state = _TASK_STATE_MAP.get(s.task_state, TaskState.OFF)
        task_mode = _TASK_MODE_MAP.get(s.task_mode, TaskMode.MANUAL)
        interp_state = _INTERP_MAP.get(s.interp_state, InterpState.IDLE)

        # Axis positions (joint-based for 2-axis lathe)
        # Joint 0 = X, Joint 1 = Z
        x_pos = s.actual_position[0]  # X in diameter (lathe mode)
        z_pos = s.actual_position[2]  # Z in inches (index 2 in XYZ tuple)

        x_cmd = s.joint[0]["output"] if len(s.joint) > 0 else 0.0
        z_cmd = s.joint[1]["output"] if len(s.joint) > 1 else 0.0

        x_ferr = s.joint[0]["ferror_current"] if len(s.joint) > 0 else 0.0
        z_ferr = s.joint[1]["ferror_current"] if len(s.joint) > 1 else 0.0

        x_homed = HomingState.HOMED if s.homed[0] else HomingState.NOT_HOMED
        z_homed = HomingState.HOMED if s.homed[1] else HomingState.NOT_HOMED

        x_enabled = s.joint[0]["enabled"] if len(s.joint) > 0 else False
        z_enabled = s.joint[1]["enabled"] if len(s.joint) > 1 else False

        x_axis = AxisState(
            position=x_pos,
            velocity=s.joint[0]["velocity"] if len(s.joint) > 0 else 0.0,
            commanded=x_cmd,
            following_error=x_ferr,
            homed=x_homed,
            at_limit=bool(s.limit[0]) if hasattr(s, "limit") else False,
            enabled=x_enabled,
            min_limit=X_MIN_LIMIT,
            max_limit=X_MAX_LIMIT,
        )

        z_axis = AxisState(
            position=z_pos,
            velocity=s.joint[1]["velocity"] if len(s.joint) > 1 else 0.0,
            commanded=z_cmd,
            following_error=z_ferr,
            homed=z_homed,
            at_limit=bool(s.limit[1]) if hasattr(s, "limit") else False,
            enabled=z_enabled,
            min_limit=Z_MIN_LIMIT,
            max_limit=Z_MAX_LIMIT,
        )

        # Spindle
        sp = s.spindle[0] if len(s.spindle) > 0 else {}
        spindle_speed = sp.get("speed", 0.0)
        spindle_dir_val = sp.get("direction", 0)
        if spindle_dir_val > 0:
            spindle_dir = SpindleDirection.FORWARD
        elif spindle_dir_val < 0:
            spindle_dir = SpindleDirection.REVERSE
        else:
            spindle_dir = SpindleDirection.STOPPED

        spindle = SpindleState(
            speed=abs(spindle_speed),
            commanded_speed=abs(sp.get("speed_cmd", sp.get("commanded", spindle_speed))),
            direction=spindle_dir,
            at_speed=bool(sp.get("at_speed", False)),
            override=sp.get("override", 1.0),
        )

        # Active G-codes
        gcodes = " ".join(f"G{g/10:.0f}" for g in s.gcodes if g > 0)
        mcodes = " ".join(f"M{m}" for m in s.mcodes if m > 0)

        all_homed = all(s.homed[i] for i in range(2))

        self._state = MachineState(
            task_state=task_state,
            task_mode=task_mode,
            interp_state=interp_state,
            x=x_axis,
            z=z_axis,
            spindle=spindle,
            feed_override=s.feedrate,
            rapid_override=s.rapidrate,
            program_file=s.file or "",
            current_line=s.current_line,
            motion_line=s.motion_line,
            active_gcodes=gcodes,
            active_mcodes=mcodes,
            tool_in_spindle=s.tool_in_spindle,
            tool_offset_x=s.tool_offset[0],
            tool_offset_z=s.tool_offset[2],
            estop_active=(task_state == TaskState.ESTOP),
            machine_on=(task_state == TaskState.ON),
            all_homed=all_homed,
            optional_stop=bool(s.optional_stop),
            block_delete=bool(s.block_delete),
            flood_on=bool(s.flood),
            mist_on=bool(s.mist),
            error_message=error_msg,
        )

    # ------------------------------------------------------------------
    # Mode Control
    # ------------------------------------------------------------------

    def _ensure_mode(self, mode) -> bool:
        """Switch to mode if not already there. Returns True on success."""
        self._stat.poll()
        if self._stat.task_mode == mode:
            return True
        if self._stat.interp_state != linuxcnc.INTERP_IDLE:
            return False
        self._cmd.mode(mode)
        return True

    def set_mode_manual(self) -> bool:
        return self._ensure_mode(linuxcnc.MODE_MANUAL)

    def set_mode_mdi(self) -> bool:
        return self._ensure_mode(linuxcnc.MODE_MDI)

    def set_mode_auto(self) -> bool:
        return self._ensure_mode(linuxcnc.MODE_AUTO)

    # ------------------------------------------------------------------
    # E-Stop & Power
    # ------------------------------------------------------------------

    def estop_reset(self) -> bool:
        logger.info("estop_reset: sending STATE_ESTOP_RESET")
        try:
            self._cmd.state(linuxcnc.STATE_ESTOP_RESET)
            logger.info("estop_reset: command accepted")
            return True
        except linuxcnc.error as e:
            logger.error("estop_reset: FAILED — %s", e)
            return False

    def machine_on(self) -> bool:
        logger.info("machine_on: sending STATE_ON")
        try:
            self._cmd.state(linuxcnc.STATE_ON)
            logger.info("machine_on: command accepted")
            return True
        except linuxcnc.error as e:
            logger.error("machine_on: FAILED — %s", e)
            return False

    def machine_off(self) -> bool:
        logger.info("machine_off: sending STATE_OFF")
        try:
            self._cmd.state(linuxcnc.STATE_OFF)
            logger.info("machine_off: command accepted")
            return True
        except linuxcnc.error as e:
            logger.error("machine_off: FAILED — %s", e)
            return False

    # ------------------------------------------------------------------
    # Homing
    # ------------------------------------------------------------------

    def home_axis(self, axis: int) -> bool:
        try:
            if not self._ensure_mode(linuxcnc.MODE_MANUAL):
                return False
            self._cmd.home(axis)
            return True
        except linuxcnc.error:
            return False

    def home_all(self) -> bool:
        try:
            if not self._ensure_mode(linuxcnc.MODE_MANUAL):
                return False
            self._cmd.home(-1)  # -1 = home all
            return True
        except linuxcnc.error:
            return False

    def unhome_axis(self, axis: int) -> bool:
        try:
            if not self._ensure_mode(linuxcnc.MODE_MANUAL):
                return False
            self._cmd.unhome(axis)
            return True
        except linuxcnc.error:
            return False

    # ------------------------------------------------------------------
    # Jogging
    # ------------------------------------------------------------------

    def _machine_is_on(self) -> bool:
        """Return True only if machine is in STATE_ON (safe to jog)."""
        return self._stat.task_state == linuxcnc.STATE_ON

    def jog_continuous(self, axis: int, direction: float, velocity: float) -> bool:
        try:
            if not self._machine_is_on():
                return False
            if not self._ensure_mode(linuxcnc.MODE_MANUAL):
                return False
            vel = abs(velocity) * (1.0 if direction > 0 else -1.0)
            self._cmd.jog(linuxcnc.JOG_CONTINUOUS, False, axis, vel)
            return True
        except linuxcnc.error:
            return False

    def jog_increment(self, axis: int, direction: float, velocity: float, distance: float) -> bool:
        try:
            if not self._machine_is_on():
                return False
            if not self._ensure_mode(linuxcnc.MODE_MANUAL):
                return False
            vel = abs(velocity)
            dist = abs(distance) * (1.0 if direction > 0 else -1.0)
            self._cmd.jog(linuxcnc.JOG_INCREMENT, False, axis, vel, dist)
            return True
        except linuxcnc.error:
            return False

    def jog_stop(self, axis: int) -> bool:
        try:
            if not self._machine_is_on():
                return False
            self._cmd.jog(linuxcnc.JOG_STOP, False, axis)
            return True
        except linuxcnc.error:
            return False

    # ------------------------------------------------------------------
    # MDI
    # ------------------------------------------------------------------

    def mdi_command(self, command: str) -> bool:
        try:
            if not self._ensure_mode(linuxcnc.MODE_MDI):
                return False
            self._cmd.mdi(command)
            self._cmd.wait_complete()
            return True
        except linuxcnc.error:
            return False

    # ------------------------------------------------------------------
    # Spindle
    # ------------------------------------------------------------------

    def spindle_forward(self, rpm: float) -> bool:
        try:
            if not self._ensure_mode(linuxcnc.MODE_MDI):
                return False
            self._cmd.mdi(f"M3 S{rpm:.0f}")
            self._cmd.wait_complete()
            return True
        except linuxcnc.error:
            return False

    def spindle_reverse(self, rpm: float) -> bool:
        try:
            if not self._ensure_mode(linuxcnc.MODE_MDI):
                return False
            self._cmd.mdi(f"M4 S{rpm:.0f}")
            self._cmd.wait_complete()
            return True
        except linuxcnc.error:
            return False

    def spindle_stop(self) -> bool:
        try:
            if not self._ensure_mode(linuxcnc.MODE_MDI):
                return False
            self._cmd.mdi("M5")
            self._cmd.wait_complete()
            return True
        except linuxcnc.error:
            return False

    # ------------------------------------------------------------------
    # Overrides
    # ------------------------------------------------------------------

    def set_feed_override(self, value: float) -> bool:
        try:
            self._cmd.feedrate(value)
            return True
        except linuxcnc.error:
            return False

    def set_rapid_override(self, value: float) -> bool:
        try:
            self._cmd.rapidrate(value)
            return True
        except linuxcnc.error:
            return False

    def set_spindle_override(self, value: float) -> bool:
        try:
            self._cmd.spindleoverride(value, 0)
            return True
        except linuxcnc.error:
            return False

    # ------------------------------------------------------------------
    # Program Control
    # ------------------------------------------------------------------

    def program_open(self, path: str) -> bool:
        try:
            if not self._ensure_mode(linuxcnc.MODE_AUTO):
                return False
            self._cmd.program_open(path)
            return True
        except linuxcnc.error:
            return False

    def program_run(self, start_line: int = 0) -> bool:
        try:
            if not self._ensure_mode(linuxcnc.MODE_AUTO):
                return False
            self._cmd.auto(linuxcnc.AUTO_RUN, start_line)
            return True
        except linuxcnc.error:
            return False

    def program_pause(self) -> bool:
        try:
            self._cmd.auto(linuxcnc.AUTO_PAUSE)
            return True
        except linuxcnc.error:
            return False

    def program_resume(self) -> bool:
        try:
            self._cmd.auto(linuxcnc.AUTO_RESUME)
            return True
        except linuxcnc.error:
            return False

    def program_stop(self) -> bool:
        try:
            self._cmd.abort()
            return True
        except linuxcnc.error:
            return False

    # ------------------------------------------------------------------
    # Tool
    # ------------------------------------------------------------------

    def tool_change(self, tool_number: int) -> bool:
        try:
            if not self._ensure_mode(linuxcnc.MODE_MDI):
                return False
            self._cmd.mdi(f"T{tool_number} M6")
            self._cmd.wait_complete(60)  # Tool change may wait for operator
            self._cmd.mdi("G43")
            self._cmd.wait_complete()
            return True
        except linuxcnc.error:
            return False

    # ------------------------------------------------------------------
    # Touch-off
    # ------------------------------------------------------------------

    def touch_off(self, axis: int, value: float, system: int = 1) -> bool:
        """Touch off using G10 L20.

        Args:
            axis: 0=X, 1=Z
            value: Value at current position (X in diameter)
            system: 1=G54, 2=G55, etc.
        """
        try:
            if not self._ensure_mode(linuxcnc.MODE_MDI):
                return False
            axis_letter = "X" if axis == 0 else "Z"
            self._cmd.mdi(f"G10 L20 P{system} {axis_letter}{value:.6f}")
            self._cmd.wait_complete()
            return True
        except linuxcnc.error:
            return False

    # ------------------------------------------------------------------
    # Compound Slide HAL Pins
    # ------------------------------------------------------------------

    def set_compound_enable(self, enabled: bool):
        """Set the compound-enable HAL pin.

        When enabled, postgui.hal routes the compound-slide component's
        output jog-counts to the joints instead of raw MPG counts.

        Args:
            enabled: True to enable compound slide muxing.
        """
        if self._hal_comp is not None:
            try:
                self._hal_comp["compound-enable"] = enabled
            except Exception:
                pass

    def set_compound_angle(self, angle: float):
        """Set the compound-angle HAL pin (informational, for HAL scope).

        Args:
            angle: Current compound angle in degrees.
        """
        if self._hal_comp is not None:
            try:
                self._hal_comp["compound-angle"] = angle
            except Exception:
                pass

    def set_compound_jog_counts(self, x_counts: int, z_counts: int):
        """Write decomposed jog counts to the compound-slide HAL output pins.

        These are the final jog counts that get routed to the joints
        when compound mode is active.

        Args:
            x_counts: Cumulative X jog count output.
            z_counts: Cumulative Z jog count output.
        """
        if self._hal_comp is not None:
            try:
                self._hal_comp["x-jog-counts"] = x_counts
                self._hal_comp["z-jog-counts"] = z_counts
            except Exception:
                pass

    def set_mpg_scale_index(self, index: int):
        """Set the MPG jog increment via mux4 select pins.

        Index maps to JOG_INCREMENTS: 0=0.0001", 1=0.001", 2=0.01", 3=0.1"
        Drives compound-slide.mpg-scale-sel0/sel1, which postgui.hal routes
        to mux4.jogscale-x/z.sel0/sel1.

        Args:
            index: 0–3 selecting the jog increment.
        """
        if self._hal_comp is not None:
            try:
                self._hal_comp["mpg-scale-sel0"] = bool(index & 1)
                self._hal_comp["mpg-scale-sel1"] = bool((index >> 1) & 1)
            except Exception:
                pass
