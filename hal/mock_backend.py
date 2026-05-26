"""Mock backend for offline development on Windows.

Simulates LinuxCNC responses with realistic state transitions.
Jog commands update position over time. MDI commands are parsed minimally.
No external dependencies beyond Python stdlib.
"""

import time
import math
from typing import Optional

from hal.interface import (
    HALBackend, MachineState, AxisState, SpindleState,
    InterpState, TaskMode, TaskState, HomingState, SpindleDirection,
)
from hal.constants import (
    X_MIN_LIMIT, X_MAX_LIMIT, X_HOME,
    Z_MIN_LIMIT, Z_MAX_LIMIT, Z_HOME,
    X_MAX_VELOCITY, Z_MAX_VELOCITY,
    SPINDLE_DEFAULT_RPM,
)


class MockBackend(HALBackend):
    """Offline mock backend for Windows development.

    Simulates:
        - Position tracking (jog updates position)
        - State machine (estop → on → homed)
        - Spindle encoder feedback (simulated RPM)
        - Mode switching
        - Soft limit enforcement

    Does NOT simulate:
        - Real motion dynamics (instant position updates)
        - Following error
        - Program execution (auto mode is a no-op)
    """

    def __init__(self):
        # Internal mutable state — start in ready-to-use state for offline dev
        self._task_state = TaskState.ON
        self._task_mode = TaskMode.MANUAL
        self._interp_state = InterpState.IDLE

        # Positions (diameter for X, inches for Z)
        self._x_pos = X_HOME
        self._z_pos = Z_HOME
        self._x_homed = HomingState.HOMED
        self._z_homed = HomingState.HOMED

        # Spindle
        self._spindle_speed = 0.0
        self._spindle_commanded = 0.0
        self._spindle_dir = SpindleDirection.STOPPED

        # Overrides
        self._feed_override = 1.0
        self._rapid_override = 1.0
        self._spindle_override = 1.0

        # Jog state
        self._jog_x_active = False
        self._jog_z_active = False
        self._jog_x_vel = 0.0
        self._jog_z_vel = 0.0
        self._last_poll_time = time.time()

        # Tool
        self._tool_in_spindle = 0

        # MPG encoder counts (simulated — increment via simulate_mpg_pulse())
        self._mpg_x_counts = 0
        self._mpg_z_counts = 0

        # Flags
        self._machine_on = True
        self._flood = False
        self._mist = False

        # Error
        self._error = ""

        # Cached state snapshot
        self._state = self._build_state()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def state(self) -> MachineState:
        return self._state

    @property
    def connected(self) -> bool:
        return True  # Mock is always "connected"

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------

    def poll(self) -> None:
        """Update positions based on active jogs, rebuild state snapshot."""
        now = time.time()
        dt = now - self._last_poll_time
        self._last_poll_time = now

        # Update positions from continuous jog
        if self._jog_x_active and self._machine_on:
            new_x = self._x_pos + self._jog_x_vel * dt
            self._x_pos = max(X_MIN_LIMIT, min(X_MAX_LIMIT, new_x))
            # Stop at limits
            if self._x_pos <= X_MIN_LIMIT or self._x_pos >= X_MAX_LIMIT:
                self._jog_x_active = False
                self._jog_x_vel = 0.0

        if self._jog_z_active and self._machine_on:
            new_z = self._z_pos + self._jog_z_vel * dt
            self._z_pos = max(Z_MIN_LIMIT, min(Z_MAX_LIMIT, new_z))
            if self._z_pos <= Z_MIN_LIMIT or self._z_pos >= Z_MAX_LIMIT:
                self._jog_z_active = False
                self._jog_z_vel = 0.0

        # Simulate spindle encoder (ramp to commanded speed)
        if self._spindle_dir != SpindleDirection.STOPPED:
            target = self._spindle_commanded * self._spindle_override
            diff = target - self._spindle_speed
            # Ramp at ~500 RPM/sec
            ramp = min(abs(diff), 500.0 * dt)
            self._spindle_speed += math.copysign(ramp, diff)
        else:
            # Coast down
            if self._spindle_speed > 0:
                self._spindle_speed = max(0.0, self._spindle_speed - 200.0 * dt)

        self._state = self._build_state()

    # ------------------------------------------------------------------
    # Mode Control
    # ------------------------------------------------------------------

    def set_mode_manual(self) -> bool:
        if self._task_state != TaskState.ON:
            return False
        self._task_mode = TaskMode.MANUAL
        return True

    def set_mode_mdi(self) -> bool:
        if self._task_state != TaskState.ON:
            return False
        self._task_mode = TaskMode.MDI
        return True

    def set_mode_auto(self) -> bool:
        if self._task_state != TaskState.ON:
            return False
        self._task_mode = TaskMode.AUTO
        return True

    # ------------------------------------------------------------------
    # E-Stop & Power
    # ------------------------------------------------------------------

    def estop_reset(self) -> bool:
        if self._task_state == TaskState.ESTOP:
            self._task_state = TaskState.ESTOP_RESET
            self._error = ""
            return True
        return False

    def machine_on(self) -> bool:
        if self._task_state == TaskState.ESTOP_RESET:
            self._task_state = TaskState.ON
            self._machine_on = True
            return True
        return False

    def machine_off(self) -> bool:
        self._task_state = TaskState.OFF
        self._machine_on = False
        self._jog_x_active = False
        self._jog_z_active = False
        return True

    # ------------------------------------------------------------------
    # Homing
    # ------------------------------------------------------------------

    def home_axis(self, axis: int) -> bool:
        if not self._machine_on:
            return False
        if axis == 0:
            self._x_homed = HomingState.HOMED
            self._x_pos = X_HOME
        elif axis == 1:
            self._z_homed = HomingState.HOMED
            self._z_pos = Z_HOME
        return True

    def home_all(self) -> bool:
        if not self._machine_on:
            return False
        self._x_homed = HomingState.HOMED
        self._x_pos = X_HOME
        self._z_homed = HomingState.HOMED
        self._z_pos = Z_HOME
        return True

    def unhome_axis(self, axis: int) -> bool:
        if axis == 0:
            self._x_homed = HomingState.NOT_HOMED
        elif axis == 1:
            self._z_homed = HomingState.NOT_HOMED
        return True

    # ------------------------------------------------------------------
    # Jogging
    # ------------------------------------------------------------------

    def jog_continuous(self, axis: int, direction: float, velocity: float) -> bool:
        if not self._machine_on or self._task_mode != TaskMode.MANUAL:
            return False
        vel = abs(velocity) * (1.0 if direction > 0 else -1.0)
        if axis == 0:
            self._jog_x_active = True
            self._jog_x_vel = vel
        elif axis == 1:
            self._jog_z_active = True
            self._jog_z_vel = vel
        return True

    def jog_increment(self, axis: int, direction: float, velocity: float, distance: float) -> bool:
        if not self._machine_on or self._task_mode != TaskMode.MANUAL:
            return False
        # Instant position update for mock (no motion dynamics)
        delta = abs(distance) * (1.0 if direction > 0 else -1.0)
        if axis == 0:
            new_x = self._x_pos + delta
            self._x_pos = max(X_MIN_LIMIT, min(X_MAX_LIMIT, new_x))
        elif axis == 1:
            new_z = self._z_pos + delta
            self._z_pos = max(Z_MIN_LIMIT, min(Z_MAX_LIMIT, new_z))
        return True

    def jog_stop(self, axis: int) -> bool:
        if axis == 0:
            self._jog_x_active = False
            self._jog_x_vel = 0.0
        elif axis == 1:
            self._jog_z_active = False
            self._jog_z_vel = 0.0
        return True

    # ------------------------------------------------------------------
    # MDI
    # ------------------------------------------------------------------

    def mdi_command(self, command: str) -> bool:
        if not self._machine_on:
            return False
        self._task_mode = TaskMode.MDI
        # Minimal parsing for touch-off and positioning
        cmd = command.strip().upper()
        if cmd.startswith("G10"):
            # Touch-off — just acknowledge
            return True
        # Parse G0/G1 for position updates
        if "X" in cmd:
            try:
                x_idx = cmd.index("X")
                x_str = ""
                for c in cmd[x_idx + 1:]:
                    if c in "0123456789.+-":
                        x_str += c
                    else:
                        break
                if x_str:
                    self._x_pos = max(X_MIN_LIMIT, min(X_MAX_LIMIT, float(x_str)))
            except (ValueError, IndexError):
                pass
        if "Z" in cmd:
            try:
                z_idx = cmd.index("Z")
                z_str = ""
                for c in cmd[z_idx + 1:]:
                    if c in "0123456789.+-":
                        z_str += c
                    else:
                        break
                if z_str:
                    self._z_pos = max(Z_MIN_LIMIT, min(Z_MAX_LIMIT, float(z_str)))
            except (ValueError, IndexError):
                pass
        return True

    # ------------------------------------------------------------------
    # Spindle
    # ------------------------------------------------------------------

    def spindle_forward(self, rpm: float) -> bool:
        self._spindle_commanded = rpm
        self._spindle_dir = SpindleDirection.FORWARD
        return True

    def spindle_reverse(self, rpm: float) -> bool:
        self._spindle_commanded = rpm
        self._spindle_dir = SpindleDirection.REVERSE
        return True

    def spindle_stop(self) -> bool:
        self._spindle_commanded = 0.0
        self._spindle_dir = SpindleDirection.STOPPED
        return True

    # ------------------------------------------------------------------
    # Overrides
    # ------------------------------------------------------------------

    def set_feed_override(self, value: float) -> bool:
        self._feed_override = max(0.0, min(2.0, value))
        return True

    def set_rapid_override(self, value: float) -> bool:
        self._rapid_override = max(0.0, min(1.0, value))
        return True

    def set_spindle_override(self, value: float) -> bool:
        self._spindle_override = max(0.25, min(1.5, value))
        return True

    # ------------------------------------------------------------------
    # Program Control (no-ops in mock)
    # ------------------------------------------------------------------

    def program_open(self, path: str) -> bool:
        return True

    def program_run(self, start_line: int = 0) -> bool:
        return self._machine_on

    def program_pause(self) -> bool:
        return True

    def program_resume(self) -> bool:
        return True

    def program_stop(self) -> bool:
        return True

    # ------------------------------------------------------------------
    # Tool
    # ------------------------------------------------------------------

    def tool_change(self, tool_number: int) -> bool:
        self._tool_in_spindle = tool_number
        return True

    # ------------------------------------------------------------------
    # Touch-off
    # ------------------------------------------------------------------

    def touch_off(self, axis: int, value: float, system: int = 1) -> bool:
        # In mock, just acknowledge — no real WCS math
        return True

    # ------------------------------------------------------------------
    # MPG Simulation (for compound slide testing)
    # ------------------------------------------------------------------

    def simulate_mpg_pulse(self, axis: str, counts: int):
        """Simulate MPG encoder pulses for testing.

        Args:
            axis: "x" or "z" — which MPG handwheel.
            counts: Number of encoder counts to add (signed).
        """
        if axis == "x":
            self._mpg_x_counts += counts
        elif axis == "z":
            self._mpg_z_counts += counts

    def set_compound_enable(self, enabled: bool):
        """Set compound-enable state (no-op in mock, no HAL pins)."""
        pass

    def set_compound_angle(self, angle: float):
        """Set compound angle (no-op in mock, no HAL pins)."""
        pass

    def set_compound_jog_counts(self, x_counts: int, z_counts: int):
        """Write compound jog counts (mock: apply as position delta).

        In mock mode, directly update position to simulate the effect
        of the HAL mux2 routing jog counts to the joints.
        """
        # In mock mode, the jog_increment fallback handles motion.
        # This method exists for interface compatibility.
        pass

    def set_mpg_scale_index(self, index: int):
        """Set MPG jog mode index (no-op in mock — no HAL mux8 pins)."""
        pass

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_state(self) -> MachineState:
        """Construct immutable state snapshot from mutable internals."""
        all_homed = (
            self._x_homed == HomingState.HOMED
            and self._z_homed == HomingState.HOMED
        )

        x_axis = AxisState(
            position=self._x_pos,
            velocity=self._jog_x_vel if self._jog_x_active else 0.0,
            commanded=self._x_pos,
            following_error=0.0,
            homed=self._x_homed,
            at_limit=(self._x_pos <= X_MIN_LIMIT or self._x_pos >= X_MAX_LIMIT),
            enabled=self._machine_on,
            min_limit=X_MIN_LIMIT,
            max_limit=X_MAX_LIMIT,
        )

        z_axis = AxisState(
            position=self._z_pos,
            velocity=self._jog_z_vel if self._jog_z_active else 0.0,
            commanded=self._z_pos,
            following_error=0.0,
            homed=self._z_homed,
            at_limit=(self._z_pos <= Z_MIN_LIMIT or self._z_pos >= Z_MAX_LIMIT),
            enabled=self._machine_on,
            min_limit=Z_MIN_LIMIT,
            max_limit=Z_MAX_LIMIT,
        )

        spindle = SpindleState(
            speed=self._spindle_speed,
            commanded_speed=self._spindle_commanded,
            direction=self._spindle_dir,
            at_speed=abs(self._spindle_speed - self._spindle_commanded) < 50,
            override=self._spindle_override,
        )

        return MachineState(
            task_state=self._task_state,
            task_mode=self._task_mode,
            interp_state=self._interp_state,
            x=x_axis,
            z=z_axis,
            spindle=spindle,
            feed_override=self._feed_override,
            rapid_override=self._rapid_override,
            tool_in_spindle=self._tool_in_spindle,
            estop_active=(self._task_state == TaskState.ESTOP),
            machine_on=self._machine_on,
            all_homed=all_homed,
            error_message=self._error,
        )
