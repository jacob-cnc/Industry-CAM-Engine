"""Live backend connecting to LinuxCNC via the Python API.

This module is only importable on Linux with LinuxCNC installed.
The factory (hal/factory.py) handles the import guard.

Wraps linuxcnc.stat, linuxcnc.command, and linuxcnc.error_channel
into the HALBackend interface.
"""

import linuxcnc

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
    """

    def __init__(self):
        self._stat = linuxcnc.stat()
        self._cmd = linuxcnc.command()
        self._error = linuxcnc.error_channel()
        self._state = MachineState()
        self._connected = False

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
        """Poll LinuxCNC stat channel and rebuild state snapshot."""
        try:
            self._stat.poll()
            self._connected = True
        except linuxcnc.error:
            self._connected = False
            return

        # Check error channel
        error_msg = ""
        err = self._error.poll()
        if err:
            kind, text = err
            error_msg = text

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
        spindle_speed = s.spindle[0]["speed"] if len(s.spindle) > 0 else 0.0
        spindle_dir_val = s.spindle[0]["direction"] if len(s.spindle) > 0 else 0
        if spindle_dir_val > 0:
            spindle_dir = SpindleDirection.FORWARD
        elif spindle_dir_val < 0:
            spindle_dir = SpindleDirection.REVERSE
        else:
            spindle_dir = SpindleDirection.STOPPED

        spindle = SpindleState(
            speed=abs(spindle_speed),
            commanded_speed=abs(s.spindle[0]["commanded"] if len(s.spindle) > 0 else 0.0),
            direction=spindle_dir,
            at_speed=bool(s.spindle[0]["at_speed"] if len(s.spindle) > 0 else False),
            override=s.spindle[0]["override"] if len(s.spindle) > 0 else 1.0,
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
        self._cmd.wait_complete()
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
        try:
            self._cmd.state(linuxcnc.STATE_ESTOP_RESET)
            self._cmd.wait_complete()
            return True
        except linuxcnc.error:
            return False

    def machine_on(self) -> bool:
        try:
            self._cmd.state(linuxcnc.STATE_ON)
            self._cmd.wait_complete()
            return True
        except linuxcnc.error:
            return False

    def machine_off(self) -> bool:
        try:
            self._cmd.state(linuxcnc.STATE_OFF)
            self._cmd.wait_complete()
            return True
        except linuxcnc.error:
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

    def jog_continuous(self, axis: int, direction: float, velocity: float) -> bool:
        try:
            if not self._ensure_mode(linuxcnc.MODE_MANUAL):
                return False
            vel = abs(velocity) * (1.0 if direction > 0 else -1.0)
            self._cmd.jog(linuxcnc.JOG_CONTINUOUS, False, axis, vel)
            return True
        except linuxcnc.error:
            return False

    def jog_increment(self, axis: int, direction: float, velocity: float, distance: float) -> bool:
        try:
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
