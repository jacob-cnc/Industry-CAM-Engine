"""CompoundJogEngine — turns one MPG's counts into per-joint jog counts.

The compound-slide feature drives both joints from a single handwheel. The GUI
reads the selected MPG's raw encoder count, this engine decomposes each count
delta along the compound path (linear angle or arc), and the resulting
cumulative per-joint counts are written to ``compound-slide.x/z-jog-counts``,
which ``industry-cam.hal`` muxes onto ``joint.N.jog-counts`` while compound mode
is enabled.

Frame
-----
Everything here is in **machine joint coordinates**: X is radius (joint 0
units), Z is joint 1 units. That is the frame jog-counts act in, so:

* soft limits are the real joint limits (from LinuxCNC, not ``hal.constants``),
* behaviour does not depend on G7/G8, work offsets, or tool offsets.

Scaling
-------
LinuxCNC moves a joint by ``delta_counts * joint.N.jog-scale``. X and Z use
different jog scales (X radius units are half-size per count), so each axis's
output counts are computed with that axis's own scale. A single input count
travels ``travel_per_count`` along the path; the GUI passes the Z jog-scale,
which is the physical inches-per-count of the selected position increment.

The virtual position (``x_r``, ``z``) advances by the *quantized* motion that
was actually emitted, so it stays equal to where the joints' free planners are
headed and limit checks / arc re-projection use the true target.

No Qt, no HAL — fully testable in isolation.
"""

from dataclasses import dataclass
from typing import Optional, Tuple

from hal.compound_logic import CompoundArcLogic, CompoundLinearLogic, Limits


@dataclass(frozen=True)
class CompoundStep:
    """Result of one engine step that produced motion."""

    x_total: int          # cumulative X output counts since start()
    z_total: int          # cumulative Z output counts since start()
    x_counts: int         # X counts emitted this step
    z_counts: int         # Z counts emitted this step
    distance: float       # cumulative path distance (inches)


class CompoundJogEngine:
    """Converts selected-MPG count deltas into per-joint cumulative jog counts."""

    def __init__(self, limits: Limits):
        """
        Args:
            limits: (x_min_radius, x_max_radius, z_min, z_max) in machine
                joint coordinates — normally the joints' position limits.
        """
        self.limits: Limits = limits
        self.mode = "linear"
        self.angle_deg = 45.0
        self.linear = CompoundLinearLogic()
        self.arc = CompoundArcLogic()
        self.active = False
        self.x_r = 0.0
        self.z = 0.0
        self._last_counts = 0
        self._x_acc = 0.0
        self._z_acc = 0.0
        self.x_total = 0
        self.z_total = 0

    # ------------------------------------------------------------------

    def start(self, x_r: float, z: float, input_counts: int,
              mode: str = "linear", angle_deg: float = 45.0) -> None:
        """Begin a compound session at machine position (x_r, z).

        For arc mode, call ``self.arc.activate(...)`` with the same position
        before or after this; the engine only drives ``process_pulse``.
        """
        if mode not in ("linear", "arc"):
            raise ValueError(f"unknown compound mode {mode!r}")
        self.mode = mode
        self.angle_deg = angle_deg
        self.x_r = x_r
        self.z = z
        self._last_counts = input_counts
        self._x_acc = 0.0
        self._z_acc = 0.0
        self.x_total = 0
        self.z_total = 0
        self.linear.reset()
        self.active = True

    def stop(self) -> None:
        self.active = False

    # ------------------------------------------------------------------

    def _path_delta(self, count_delta: int, travel: float
                    ) -> Optional[Tuple[float, float]]:
        """Requested (dx_radius, dz) for this delta, or None if suppressed."""
        if self.mode == "arc":
            dx, dz, suppressed, _clamped = self.arc.process_pulse(
                count_delta, travel, self.x_r, self.z, self.limits)
            if suppressed or (dx == 0.0 and dz == 0.0):
                return None
            return dx, dz

        dx, dz = CompoundLinearLogic.decompose_pulse(
            count_delta, travel, abs(self.angle_deg))
        # Axis coupling by angle sign (operator convention, unchanged from the
        # original GUI implementation):
        #   positive angle: X-, Z+ per positive count  (e.g. +45 = OD chamfer)
        #   zero/negative:  X-, Z- per positive count  (e.g. -45 = ID chamfer)
        dx = -dx
        if self.angle_deg <= 0:
            dz = -dz
        _, _, suppressed = CompoundLinearLogic.check_soft_limits(
            self.x_r, self.z, dx, dz, self.limits)
        if suppressed:
            return None
        return dx, dz

    def step(self, input_counts: int, travel_per_count: float,
             x_scale: float, z_scale: float) -> Optional[CompoundStep]:
        """Process the selected MPG's current raw count.

        Args:
            input_counts: Current raw encoder count of the selected MPG.
            travel_per_count: Path distance per input count (inches).
            x_scale: joint.0.jog-scale (radius units per count).
            z_scale: joint.1.jog-scale (units per count).

        Returns:
            CompoundStep when new output counts were emitted, else None.
        """
        if not self.active:
            return None
        count_delta = input_counts - self._last_counts
        self._last_counts = input_counts
        if count_delta == 0:
            return None
        if x_scale <= 0.0 or z_scale <= 0.0 or travel_per_count <= 0.0:
            return None  # scales not wired — never emit motion blind

        delta = self._path_delta(count_delta, travel_per_count)
        if delta is None:
            return None
        dx, dz = delta

        if self.mode == "arc":
            self.arc.accumulate_distance(dx, dz)
            distance = self.arc.cumulative_distance
        else:
            self.linear.accumulate_distance(dx, dz)
            distance = self.linear.cumulative_distance

        self._x_acc += dx / x_scale
        self._z_acc += dz / z_scale
        x_counts = int(self._x_acc)   # truncates toward zero
        z_counts = int(self._z_acc)
        self._x_acc -= x_counts
        self._z_acc -= z_counts

        if x_counts == 0 and z_counts == 0:
            return None

        self.x_total += x_counts
        self.z_total += z_counts
        self.x_r += x_counts * x_scale
        self.z += z_counts * z_scale
        return CompoundStep(self.x_total, self.z_total,
                            x_counts, z_counts, distance)
