"""Live backend connecting to LinuxCNC via the Python API.

This module is only importable on Linux with LinuxCNC installed.
The factory (hal/factory.py) handles the import guard.

Wraps linuxcnc.stat, linuxcnc.command, and linuxcnc.error_channel
into the HALBackend interface.

Also creates a userspace HAL component for compound slide muxing.
"""

import logging
import importlib.util as _ilu
import subprocess
import time
from typing import Tuple
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
            # Input pins — MPG encoder counts
            self._hal_comp.newpin("mpg-x-in", hal_module.HAL_S32, hal_module.HAL_IN)
            self._hal_comp.newpin("mpg-z-in", hal_module.HAL_S32, hal_module.HAL_IN)
            # Per-joint jog scales (from mux8) — compound converts path motion
            # to each joint's counts with that joint's own scale.
            self._hal_comp.newpin("x-jog-scale", hal_module.HAL_FLOAT, hal_module.HAL_IN)
            self._hal_comp.newpin("z-jog-scale", hal_module.HAL_FLOAT, hal_module.HAL_IN)
            # Gates joint/axis jog-enable FALSE while the jog-counts mux switches
            self._hal_comp.newpin("jog-inhibit", hal_module.HAL_BIT, hal_module.HAL_OUT)
            # Spindle feedback for display (netted to spindle-vel / spindle-at-speed)
            self._hal_comp.newpin("spindle-rps", hal_module.HAL_FLOAT, hal_module.HAL_IN)
            self._hal_comp.newpin("spindle-at-speed", hal_module.HAL_BIT, hal_module.HAL_IN)
            # Control pins — written by GUI
            self._hal_comp.newpin("compound-enable", hal_module.HAL_BIT, hal_module.HAL_OUT)
            self._hal_comp.newpin("compound-angle", hal_module.HAL_FLOAT, hal_module.HAL_OUT)
            # Output pins — decomposed jog counts written by GUI
            self._hal_comp.newpin("x-jog-counts", hal_module.HAL_S32, hal_module.HAL_OUT)
            self._hal_comp.newpin("z-jog-counts", hal_module.HAL_S32, hal_module.HAL_OUT)
            # MPG scale select pins — wired to mux8.jogscale-*.sel0/sel1/sel2 via _connect_scale_select_pins
            self._hal_comp.newpin("mpg-scale-sel0", hal_module.HAL_BIT, hal_module.HAL_OUT)
            self._hal_comp.newpin("mpg-scale-sel1", hal_module.HAL_BIT, hal_module.HAL_OUT)
            self._hal_comp.newpin("mpg-scale-sel2", hal_module.HAL_BIT, hal_module.HAL_OUT)
            self._hal_comp.ready()
            # Start inhibited: if a previous GUI instance died with compound
            # enabled, attaching our compound-enable=FALSE writer flips the mux
            # back to direct MPG — that count jump must be absorbed.
            self._hal_comp["jog-inhibit"] = True
            self._hal_comp["compound-enable"] = False
            # Default to index 1 = 0.001" per MPG click (sel0=1, sel1=0, sel2=0)
            self._hal_comp["mpg-scale-sel0"] = True
            self._hal_comp["mpg-scale-sel1"] = False
            self._hal_comp["mpg-scale-sel2"] = False
        except Exception:
            # If component already exists or HAL not ready, continue without it
            self._hal_comp = None

        self._compound_routing_ok = False
        if self._hal_comp is not None:
            self._connect_scale_select_pins()
            self._compound_routing_ok = self._connect_compound_routing()
            # Spindle feedback for the ribbon. Non-critical: on failure the
            # pins read 0 and the GUI shows 0 RPM.
            self._halcmd_net(["spindle-vel", "compound-slide.spindle-rps"])
            self._halcmd_net(["spindle-at-speed", "compound-slide.spindle-at-speed"])
            time.sleep(self._SWITCH_SETTLE_S)
            self._hal_comp["jog-inhibit"] = False

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
        try:
            while True:
                err = self._error.poll()
                if not err:
                    break
                kind, text = err
                error_msg = text
                logger.error("LinuxCNC error [%s]: %s", kind, text)
        except Exception as e:
            logger.warning("Error channel poll failed: %s", e)

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

        # Axis positions in active work coordinate system (G54 etc.)
        # actual_position is G53 machine coords; subtract offsets to get work coords.
        # Project convention: X is RADIUS in machine/HAL units and DIAMETER in the
        # GUI and G-code (G7). AxisState.position is documented as diameter and
        # every GUI consumer treats it that way, so convert here. (Before
        # 2026-11-08 this passed radius through, so the DRO showed radius.)
        x_pos = 2.0 * (s.actual_position[0] - s.g5x_offset[0]
                       - s.g92_offset[0] - s.tool_offset[0])
        z_pos = s.actual_position[2] - s.g5x_offset[2] - s.g92_offset[2] - s.tool_offset[2]

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

        # MEASURED speed from the spindle encoder (rev/s -> RPM) via HAL. The
        # stat "speed" is the COMMANDED speed (S word, 0 when LinuxCNC thinks
        # the spindle is off) — on this manual-spindle lathe the two differ,
        # e.g. after M6 stopped the commanded spindle (2026-11-08).
        measured_rpm, at_speed = 0.0, False
        if self._hal_comp is not None:
            try:
                measured_rpm = self._hal_comp["spindle-rps"] * 60.0
                at_speed = bool(self._hal_comp["spindle-at-speed"])
            except Exception:
                pass
        if abs(measured_rpm) >= 1.0:
            spindle_dir = (SpindleDirection.FORWARD if measured_rpm > 0
                           else SpindleDirection.REVERSE)

        spindle = SpindleState(
            speed=abs(measured_rpm),
            commanded_speed=abs(spindle_speed),
            direction=spindle_dir,
            at_speed=at_speed,
            override=sp.get("override", 1.0),
        )

        # Active G-codes
        # stat.gcodes: element 0 is the interpreter line number; the rest are
        # modal codes x10 (171 = G17.1, 0 = G0) or -1 when the group is unset.
        gcodes = " ".join(
            f"G{g // 10}" if g % 10 == 0 else f"G{g // 10}.{g % 10}"
            for g in s.gcodes[1:] if g >= 0
        )
        mcodes = " ".join(f"M{m}" for m in s.mcodes if m > 0)

        all_homed = all(s.homed[i] for i in range(2))

        self._state = MachineState(
            task_state=task_state,
            task_mode=task_mode,
            interp_state=interp_state,
            program_busy=self._program_busy(s),
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

    @staticmethod
    def _program_busy(s) -> bool:
        """AUTO program still has work: interpreter, task execution, motion
        queue, pause, or an executing NML command. Interp IDLE alone is not
        enough (it goes IDLE once the whole file is read, before motion ends)."""
        if s.task_mode != linuxcnc.MODE_AUTO:
            return False
        return (s.interp_state != linuxcnc.INTERP_IDLE
                or s.exec_state != linuxcnc.EXEC_DONE
                or s.queue > 0
                or bool(s.paused)
                or s.state == linuxcnc.RCS_EXEC)

    # ------------------------------------------------------------------
    # Mode Control
    # ------------------------------------------------------------------

    def _ensure_mode(self, mode) -> bool:
        """Switch to mode if not already there. Returns True on success."""
        self._stat.poll()
        if self._stat.task_mode == mode:
            return True
        if self._program_busy(self._stat):
            # Never interfere with an AUTO program that still has work queued
            return False
        if self._stat.interp_state != linuxcnc.INTERP_IDLE:
            # MDI stuck non-idle (e.g. after tool change) — safe to abort
            self._cmd.abort()
            self._cmd.wait_complete()
        self._cmd.mode(mode)
        self._cmd.wait_complete()   # as AXIS ensure_mode does
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
            self._ensure_mode(linuxcnc.MODE_MANUAL)
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
        """Open a program WITHOUT changing task mode.

        Matches stock AXIS (open_file_guts): the file is opened in the current
        mode and AUTO is entered only at cycle start (program_run). Switching
        to AUTO on load left the controller in AUTO, where LinuxCNC ignores MPG
        jog counts (bench 2026-11-08).
        """
        try:
            self._stat.poll()
            if (self._stat.interp_state != linuxcnc.INTERP_IDLE
                    or self._program_busy(self._stat)):
                return False   # never reload under a running/paused program
            self._cmd.task_plan_synch()
            self._cmd.wait_complete()
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
            self._ensure_mode(linuxcnc.MODE_MANUAL)
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
            # X value is DIAMETER: force G7 in the same block (see tools_tab)
            prefix = "G7 " if axis == 0 else ""
            self._cmd.mdi(f"{prefix}G10 L20 P{system} {axis_letter}{value:.6f}")
            self._cmd.wait_complete()
            self._ensure_mode(linuxcnc.MODE_MANUAL)
            return True
        except linuxcnc.error:
            return False

    # ------------------------------------------------------------------
    # Compound Slide HAL Pins
    # ------------------------------------------------------------------

    # Time to hold jog-inhibit before/after a mux switch. Servo period is 2 ms;
    # 20 ms gives ~10 servo cycles for motion to latch the new count value.
    _SWITCH_SETTLE_S = 0.02

    @property
    def compound_routing_available(self) -> bool:
        """True when every compound-slide net was attached at startup."""
        return self._hal_comp is not None and self._compound_routing_ok

    def set_compound_routing(self, enabled: bool) -> bool:
        """Switch joint jog-counts between direct MPG and compound output.

        Jump-free sequence: inhibit jog-enable, zero the compound outputs, flip
        the mux, wait, release. Motion keeps updating its previous-count copy
        while jog-enable is FALSE, so the discontinuity causes no motion.

        Blocks the caller for ~40 ms.

        Returns:
            True if the switch was performed.
        """
        if not self.compound_routing_available:
            return False
        comp = self._hal_comp
        try:
            comp["jog-inhibit"] = True
            time.sleep(self._SWITCH_SETTLE_S)
            comp["x-jog-counts"] = 0
            comp["z-jog-counts"] = 0
            comp["compound-enable"] = bool(enabled)
            time.sleep(self._SWITCH_SETTLE_S)
            return True
        except Exception as e:
            logger.error("compound routing switch failed: %s", e)
            return False
        finally:
            try:
                comp["jog-inhibit"] = False
            except Exception:
                pass

    def read_compound_inputs(self) -> Tuple[int, int, float, float]:
        """Fresh read of (mpg_x_counts, mpg_z_counts, x_jog_scale, z_jog_scale)."""
        if self._hal_comp is None:
            return (0, 0, 0.0, 0.0)
        c = self._hal_comp
        return (c["mpg-x-in"], c["mpg-z-in"], c["x-jog-scale"], c["z-jog-scale"])

    def get_machine_position(self) -> Tuple[float, float]:
        """(x_radius, z) commanded joint positions, machine units (fresh poll)."""
        self._stat.poll()
        return (self._stat.joint[0]["output"], self._stat.joint[1]["output"])

    def get_joint_limits(self) -> Tuple[float, float, float, float]:
        """(x_min, x_max, z_min, z_max) wheel-jog limits, machine units.

        Mirrors LinuxCNC: position limits when homed, otherwise a window of
        +/- full travel around the current position (see compound_router.jog_window).
        """
        from hal.compound_router import jog_window
        self._stat.poll()
        s = self._stat
        x = jog_window(bool(s.homed[0]), s.joint[0]["output"],
                       s.joint[0]["min_position_limit"], s.joint[0]["max_position_limit"])
        z = jog_window(bool(s.homed[1]), s.joint[1]["output"],
                       s.joint[1]["min_position_limit"], s.joint[1]["max_position_limit"])
        return (x[0], x[1], z[0], z[1])

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
        """Write cumulative compound jog counts to the HAL output pins.

        industry-cam.hal muxes these onto joint.N.jog-counts while
        compound-enable is TRUE.
        """
        if self._hal_comp is not None:
            try:
                self._hal_comp["x-jog-counts"] = x_counts
                self._hal_comp["z-jog-counts"] = z_counts
            except Exception:
                pass

    def _halcmd_net(self, net_args) -> bool:
        result = subprocess.run(["halcmd", "net"] + net_args,
                                capture_output=True, text=True)
        if result.returncode != 0:
            logger.warning("halcmd net %s failed: %s",
                           " ".join(net_args), result.stderr.strip())
            return False
        logger.info("HAL net established: %s", " ".join(net_args))
        return True

    def _connect_compound_routing(self) -> bool:
        """Attach compound-slide pins to the routing signals in industry-cam.hal.

        The signals already exist (declared with readers only); this adds the
        GUI as writer/reader. All nets must succeed or compound mode stays
        disabled — a partial chain could route counts without the inhibit gate.
        """
        # `halcmd net` silently CREATES a missing signal, so first prove the
        # routing exists in the loaded HAL (an older industry-cam.hal would
        # otherwise leave compound outputs connected to nothing while the raw
        # MPG still jogs its own axis).
        required = {
            "compound-jog-inhibit": "not.compound-jog-inhibit.in",
            "compound-enable": "mux-gen.00.sel-bit-00",
            "compound-x-jog": "mux-gen.00.in-s32-01",
            "compound-z-jog": "mux-gen.01.in-s32-01",
        }
        for sig, reader in required.items():
            out = subprocess.run(["halcmd", "show", "sig", sig],
                                 capture_output=True, text=True).stdout
            if reader not in out:
                logger.error("Compound-slide routing unavailable: HAL signal %s "
                             "is not connected to %s (old industry-cam.hal?)",
                             sig, reader)
                return False

        nets = [
            ["compound-jog-inhibit", "compound-slide.jog-inhibit"],
            ["compound-enable", "compound-slide.compound-enable"],
            ["compound-x-jog", "compound-slide.x-jog-counts"],
            ["compound-z-jog", "compound-slide.z-jog-counts"],
            ["mpg-x-counts", "compound-slide.mpg-x-in"],
            ["mpg-z-counts", "compound-slide.mpg-z-in"],
            ["mpg-x-scale", "compound-slide.x-jog-scale"],
            ["mpg-z-scale", "compound-slide.z-jog-scale"],
        ]
        ok = all([self._halcmd_net(n) for n in nets])
        if not ok:
            logger.error("Compound-slide routing unavailable (HAL nets failed); "
                         "normal MPG jogging is unaffected")
        return ok

    def _connect_scale_select_pins(self):
        """Wire compound-slide scale-select OUT pins to mux8 sel inputs and or2.

        Run here because the compound-slide component only exists once the GUI
        starts, and display_gui.sh is a plain DISPLAY program (no POSTGUI_HALFILE).
        Called once at startup after the component is ready.
        """
        nets = [
            ["mpg-scale-sel0",
             "compound-slide.mpg-scale-sel0",
             "mux8.jogscale-x.sel0", "mux8.jogscale-z.sel0"],
            ["mpg-scale-sel1",
             "compound-slide.mpg-scale-sel1",
             "mux8.jogscale-x.sel1", "mux8.jogscale-z.sel1",
             "or2.jog-vel-mode.in0"],
            ["mpg-scale-sel2",
             "compound-slide.mpg-scale-sel2",
             "mux8.jogscale-x.sel2", "mux8.jogscale-z.sel2",
             "or2.jog-vel-mode.in1"],
        ]
        for net_args in nets:
            result = subprocess.run(
                ["halcmd", "net"] + net_args,
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                logger.warning("halcmd net %s failed: %s",
                               " ".join(net_args), result.stderr.strip())
            else:
                logger.info("HAL net established: %s", " ".join(net_args))

        # Wire or2 output to jog-vel-mode pins
        vel_mode_net = [
            "jog-vel-mode-sig",
            "or2.jog-vel-mode.out",
            "joint.0.jog-vel-mode", "axis.x.jog-vel-mode",
            "joint.1.jog-vel-mode", "axis.z.jog-vel-mode",
        ]
        result = subprocess.run(
            ["halcmd", "net"] + vel_mode_net,
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            logger.warning("halcmd net %s failed: %s",
                           " ".join(vel_mode_net), result.stderr.strip())
        else:
            logger.info("HAL net established: %s", " ".join(vel_mode_net))

    def set_mpg_scale_index(self, index: int):
        """Set the MPG jog mode via mux8 select pins.

        Index maps to JOG_MODES:
            0 = 0.0002" position mode
            1 = 0.001"  position mode
            2 = Vel Slow
            3 = Vel Med
            4 = Vel Fast

        Drives compound-slide.mpg-scale-sel0/sel1/sel2, which are netted
        at startup to mux8.jogscale-x/z.sel0/sel1/sel2 and or2.jog-vel-mode.

        Args:
            index: 0–4 selecting the jog mode.
        """
        if self._hal_comp is not None:
            try:
                self._hal_comp["mpg-scale-sel0"] = bool(index & 1)
                self._hal_comp["mpg-scale-sel1"] = bool((index >> 1) & 1)
                self._hal_comp["mpg-scale-sel2"] = bool((index >> 2) & 1)
            except Exception:
                pass
