"""Simulated Tuning Data Provider — Offline development support.

Generates time-varying fake data for PID error, encoder positions,
stepgen feedback, and spindle RPM so the tuning tab can be fully
tested on Windows without a LinuxCNC connection.

The simulation produces realistic-looking data:
    - Following error: sine wave + gaussian noise (~±0.0002")
    - Encoder positions: slow linear drift (simulates axis motion)
    - PID output: proportional to simulated error
    - Spindle RPM: random walk around 800 RPM
    - Stepgen feedback: tracks encoder with small mechanical lag

Usage:
    provider = SimulatedTuningProvider()
    provider.tick()  # call at 50ms intervals
    x_err = provider.get_following_error('x')
    data = provider.get_snapshot()
"""

import math
import random
from dataclasses import dataclass
from typing import Dict


@dataclass
class TuningSnapshot:
    """Complete snapshot of all tuning-relevant values.

    All positions in inches (radius for X). Errors in inches.
    """
    x_following_error: float = 0.0
    z_following_error: float = 0.0
    x_commanded: float = 0.0
    z_commanded: float = 0.0
    x_encoder: float = 0.0
    z_encoder: float = 0.0
    x_stepgen: float = 0.0
    z_stepgen: float = 0.0
    x_pid_output: float = 0.0
    z_pid_output: float = 0.0
    spindle_rpm: float = 0.0
    spindle_velocity: float = 0.0  # rev/sec
    spindle_position: float = 0.0  # total revolutions
    x_velocity: float = 0.0
    z_velocity: float = 0.0


class SimulatedTuningProvider:
    """Generates realistic fake tuning data for offline development.

    Simulates a closed-loop stepper system with:
    - Periodic axis motion (move 2s, dwell 1s)
    - Following error with frequency content matching real servo behavior
    - Encoder noise at the 5µm resolution level
    - Spindle RPM drift (manual spindle, no VFD)

    Call tick() at 50ms intervals. Read data via get_snapshot() or
    individual getters.
    """

    def __init__(self, tick_interval_ms: int = 50):
        self._dt = tick_interval_ms / 1000.0
        self._t = 0  # tick counter

        # Axis state
        self._x_cmd = 1.0    # start at 1" radius (2" diameter)
        self._z_cmd = -2.0   # start 2" from chuck face
        self._x_enc = 1.0
        self._z_enc = -2.0
        self._x_vel = 0.0
        self._z_vel = 0.0

        # Spindle
        self._spindle_rpm = 800.0
        self._spindle_revs = 0.0

        # Simulation parameters
        self._error_amplitude = 0.00015   # base error (inches)
        self._noise_sigma = 0.00002       # encoder noise std dev
        self._drift_rate = 0.5            # axis motion speed (in/sec)
        self._rpm_walk_sigma = 3.0        # RPM random walk step

        # Motion state machine
        self._moving = False
        self._move_phase = 0.0

    def tick(self):
        """Advance simulation by one time step."""
        self._t += 1
        t_sec = self._t * self._dt

        # Motion pattern: move for 2s, dwell for 1s, repeat
        cycle_pos = t_sec % 3.0
        self._moving = cycle_pos < 2.0

        if self._moving:
            # Sinusoidal velocity profile (smooth accel/decel)
            phase = (cycle_pos / 2.0) * math.pi
            vel_factor = math.sin(phase)

            # Alternate direction every cycle
            direction = 1 if (int(t_sec / 3.0) % 2 == 0) else -1

            self._x_vel = self._drift_rate * 0.3 * vel_factor * direction
            self._z_vel = self._drift_rate * vel_factor * direction

            self._x_cmd += self._x_vel * self._dt
            self._z_cmd += self._z_vel * self._dt
        else:
            self._x_vel = 0.0
            self._z_vel = 0.0

        # Encoder tracks command with servo lag
        lag_factor = 0.88 if self._moving else 0.96
        self._x_enc += (self._x_cmd - self._x_enc) * lag_factor
        self._z_enc += (self._z_cmd - self._z_enc) * lag_factor

        # Spindle RPM random walk (manual spindle, no closed-loop)
        self._spindle_rpm += random.gauss(0, self._rpm_walk_sigma)
        self._spindle_rpm = max(200, min(2500, self._spindle_rpm))
        self._spindle_revs += (self._spindle_rpm / 60.0) * self._dt

    def get_following_error(self, axis: str) -> float:
        """Return simulated following error for an axis.

        Args:
            axis: 'x' or 'z'

        Returns:
            Following error in inches (typically ±0.0002")
        """
        # Base oscillation at different frequencies per axis
        if axis == 'x':
            freq = 0.07
            phase = 0.0
        else:
            freq = 0.05
            phase = 1.2

        base = self._error_amplitude * math.sin(self._t * freq + phase)

        # Higher-frequency component when moving (servo chasing command)
        if self._moving:
            base += self._error_amplitude * 0.6 * math.sin(self._t * 0.25 + phase)

        # Gaussian noise (encoder quantization + electrical)
        noise = random.gauss(0, self._noise_sigma)

        return base + noise

    def get_pid_output(self, axis: str) -> float:
        """Simulated PID velocity output (in/sec)."""
        error = self.get_following_error(axis)
        # P=1000 response, clamped to MAX_OUTPUT
        output = error * 1000.0
        return max(-2.5, min(2.5, output))

    def get_encoder_position(self, axis: str) -> float:
        """Simulated linear encoder position (inches, radius for X)."""
        return self._x_enc if axis == 'x' else self._z_enc

    def get_commanded_position(self, axis: str) -> float:
        """Simulated commanded position (inches, radius for X)."""
        return self._x_cmd if axis == 'x' else self._z_cmd

    def get_stepgen_position(self, axis: str) -> float:
        """Simulated stepgen feedback (slightly different from encoder)."""
        enc = self.get_encoder_position(axis)
        # Mechanical compliance offset
        return enc + random.gauss(0, 0.000008)

    def get_velocity(self, axis: str) -> float:
        """Simulated axis velocity (in/sec)."""
        return self._x_vel if axis == 'x' else self._z_vel

    def get_spindle_rpm(self) -> float:
        return self._spindle_rpm

    def get_spindle_velocity(self) -> float:
        """Rev/sec (what the HAL encoder pin reports)."""
        return self._spindle_rpm / 60.0

    def get_spindle_position(self) -> float:
        """Total revolutions."""
        return self._spindle_revs

    def get_snapshot(self) -> TuningSnapshot:
        """Return a complete snapshot of all tuning values."""
        return TuningSnapshot(
            x_following_error=self.get_following_error('x'),
            z_following_error=self.get_following_error('z'),
            x_commanded=self.get_commanded_position('x'),
            z_commanded=self.get_commanded_position('z'),
            x_encoder=self.get_encoder_position('x'),
            z_encoder=self.get_encoder_position('z'),
            x_stepgen=self.get_stepgen_position('x'),
            z_stepgen=self.get_stepgen_position('z'),
            x_pid_output=self.get_pid_output('x'),
            z_pid_output=self.get_pid_output('z'),
            spindle_rpm=self.get_spindle_rpm(),
            spindle_velocity=self.get_spindle_velocity(),
            spindle_position=self.get_spindle_position(),
            x_velocity=self.get_velocity('x'),
            z_velocity=self.get_velocity('z'),
        )

    # ------------------------------------------------------------------
    # Test helpers
    # ------------------------------------------------------------------

    def set_error_amplitude(self, amplitude: float):
        """Adjust error amplitude (for testing alarm thresholds)."""
        self._error_amplitude = amplitude

    def set_moving(self, moving: bool):
        """Force motion state (for testing)."""
        self._moving = moving

    def inject_fault(self, axis: str, magnitude: float = 0.01):
        """Inject a large following error spike (simulates a fault)."""
        if axis == 'x':
            self._x_enc -= magnitude
        else:
            self._z_enc -= magnitude
