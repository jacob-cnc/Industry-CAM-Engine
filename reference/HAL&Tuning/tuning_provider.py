"""
Simulated Tuning Data Provider — Offline development support.

Generates time-varying fake data for PID error, encoder positions,
stepgen feedback, and spindle RPM so the tuning tab can be fully
tested on Windows without a LinuxCNC connection.

Usage:
    provider = SimulatedTuningProvider()
    # Call tick() on each timer interval (50ms recommended)
    provider.tick()
    x_err = provider.get_following_error('x')
    z_err = provider.get_following_error('z')
    rpm = provider.get_spindle_rpm()
"""

import math
import random


class SimulatedTuningProvider:
    """Generates realistic fake tuning data for offline development.

    Simulates:
    - Following error with sine wave + gaussian noise
    - Encoder positions with slow linear drift
    - PID output proportional to error
    - Spindle RPM with random walk
    - Stepgen position feedback tracking command with small lag
    """

    def __init__(self):
        self._t = 0  # tick counter
        self._dt = 0.05  # seconds per tick (50ms)

        # Simulated axis state
        self._x_pos = 0.0  # current X encoder position (inches, radius)
        self._z_pos = 0.0  # current Z encoder position (inches)
        self._x_cmd = 0.0  # commanded X position
        self._z_cmd = 0.0  # commanded Z position
        self._x_vel = 0.0  # X velocity command
        self._z_vel = 0.0  # Z velocity command

        # Spindle
        self._spindle_rpm = 800.0
        self._spindle_revs = 0.0

        # Simulation parameters (adjustable to test different scenarios)
        self._error_amplitude = 0.00015  # base following error amplitude (inches)
        self._noise_sigma = 0.00003  # gaussian noise std dev
        self._drift_rate = 0.001  # position drift rate (in/sec) for demo motion
        self._rpm_walk_sigma = 5.0  # RPM random walk step size

        # Motion simulation state
        self._moving = False
        self._move_timer = 0
        self._move_direction = 1

    def tick(self):
        """Advance simulation by one time step. Call at 50ms intervals."""
        self._t += 1

        # Simulate periodic motion (move for 2 sec, pause for 1 sec)
        cycle_pos = (self._t * self._dt) % 3.0
        self._moving = cycle_pos < 2.0

        if self._moving:
            # Slow drift to simulate axis movement
            direction = 1 if ((self._t // 60) % 2 == 0) else -1
            self._x_cmd += self._drift_rate * self._dt * direction * 0.5
            self._z_cmd += self._drift_rate * self._dt * direction

            # Encoder tracks command with small lag (simulates real servo behavior)
            self._x_pos += (self._x_cmd - self._x_pos) * 0.85
            self._z_pos += (self._z_cmd - self._z_pos) * 0.85
        else:
            # At rest — encoder settles toward command
            self._x_pos += (self._x_cmd - self._x_pos) * 0.95
            self._z_pos += (self._z_cmd - self._z_pos) * 0.95

        # Spindle RPM random walk
        self._spindle_rpm += random.gauss(0, self._rpm_walk_sigma)
        self._spindle_rpm = max(200, min(2000, self._spindle_rpm))
        self._spindle_revs += (self._spindle_rpm / 60.0) * self._dt

    def get_following_error(self, axis):
        """Return simulated following error for an axis.

        Args:
            axis: 'x' or 'z'

        Returns:
            Float — following error in inches (typically ±0.0002)
        """
        # Base oscillation at different frequencies per axis
        if axis == 'x':
            freq = 0.07
            phase = 0.0
        else:
            freq = 0.05
            phase = 1.2

        base = self._error_amplitude * math.sin(self._t * freq + phase)

        # Add higher-frequency component when moving (servo chasing)
        if self._moving:
            base += self._error_amplitude * 0.5 * math.sin(self._t * 0.3 + phase)

        # Gaussian noise (encoder quantization + electrical noise)
        noise = random.gauss(0, self._noise_sigma)

        return base + noise

    def get_pid_output(self, axis):
        """Return simulated PID velocity output (in/sec).

        Proportional to following error (mimics P-gain response).
        """
        error = self.get_following_error(axis)
        # Simulate P=1000, so output ≈ error * 1000 but clamped
        output = error * 1000.0
        max_out = 2.5  # matches MAX_OUTPUT in INI
        return max(-max_out, min(max_out, output))

    def get_encoder_position(self, axis):
        """Return simulated linear encoder position (inches).

        Args:
            axis: 'x' or 'z'
        """
        if axis == 'x':
            return self._x_pos
        else:
            return self._z_pos

    def get_commanded_position(self, axis):
        """Return simulated commanded position (inches)."""
        if axis == 'x':
            return self._x_cmd
        else:
            return self._z_cmd

    def get_stepgen_position(self, axis):
        """Return simulated stepgen position feedback.

        Slightly different from encoder (that's the whole point of closed-loop).
        """
        enc_pos = self.get_encoder_position(axis)
        # Stepgen tracks slightly differently due to mechanical compliance
        offset = random.gauss(0, 0.00001)
        return enc_pos + offset

    def get_spindle_rpm(self):
        """Return simulated spindle RPM."""
        return self._spindle_rpm

    def get_spindle_revs(self):
        """Return simulated spindle revolution count."""
        return self._spindle_revs

    def get_spindle_velocity(self):
        """Return spindle velocity in rev/sec (what the HAL pin reports)."""
        return self._spindle_rpm / 60.0

    def get_all_tuning_data(self):
        """Return a complete snapshot of all tuning-relevant values.

        Returns:
            Dict with all values needed by the tuning tab's live status section.
        """
        return {
            'x_ferror': self.get_following_error('x'),
            'z_ferror': self.get_following_error('z'),
            'x_cmd_pos': self.get_commanded_position('x'),
            'z_cmd_pos': self.get_commanded_position('z'),
            'x_enc_pos': self.get_encoder_position('x'),
            'z_enc_pos': self.get_encoder_position('z'),
            'x_pid_out': self.get_pid_output('x'),
            'z_pid_out': self.get_pid_output('z'),
            'x_stepgen_pos': self.get_stepgen_position('x'),
            'z_stepgen_pos': self.get_stepgen_position('z'),
            'spindle_rpm': self.get_spindle_rpm(),
            'spindle_revs': self.get_spindle_revs(),
        }

    def set_error_amplitude(self, amplitude):
        """Adjust simulated error amplitude (for testing alarm thresholds)."""
        self._error_amplitude = amplitude

    def set_moving(self, moving):
        """Force moving/stopped state (for testing)."""
        self._moving = moving
