"""Abstract interface for LinuxCNC backend communication.

Defines the contract between the GUI and the machine control layer.
All GUI code programs against this interface — never against linuxcnc directly.

The interface is designed around polling (call update() each cycle) rather
than callbacks, matching LinuxCNC's stat.poll() pattern.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# =============================================================================
# State Enums
# =============================================================================

class InterpState(Enum):
    """LinuxCNC interpreter state."""
    IDLE = "idle"
    READING = "reading"
    PAUSED = "paused"
    WAITING = "waiting"


class TaskMode(Enum):
    """LinuxCNC task mode."""
    MANUAL = "manual"
    AUTO = "auto"
    MDI = "mdi"


class TaskState(Enum):
    """LinuxCNC task state."""
    ESTOP = "estop"
    ESTOP_RESET = "estop_reset"
    OFF = "off"
    ON = "on"


class HomingState(Enum):
    """Per-axis homing state."""
    NOT_HOMED = "not_homed"
    HOMING = "homing"
    HOMED = "homed"


class SpindleDirection(Enum):
    """Spindle rotation direction."""
    STOPPED = "stopped"
    FORWARD = "forward"
    REVERSE = "reverse"


# =============================================================================
# State Dataclasses
# =============================================================================

@dataclass(frozen=True)
class AxisState:
    """Current state of a single axis.

    Coordinates:
        position: Current position in user units (X = diameter, Z = inches)
        velocity: Current velocity (inches/sec)
        commanded: Commanded position (where motion controller wants to be)
        following_error: Difference between commanded and actual
        homed: Whether this axis has been homed
        at_limit: Whether a soft limit is active
        enabled: Whether the axis amplifier is enabled
    """
    position: float = 0.0
    velocity: float = 0.0
    commanded: float = 0.0
    following_error: float = 0.0
    homed: HomingState = HomingState.NOT_HOMED
    at_limit: bool = False
    enabled: bool = False
    min_limit: float = 0.0
    max_limit: float = 0.0


@dataclass(frozen=True)
class SpindleState:
    """Current spindle state."""
    speed: float = 0.0              # Actual RPM from encoder
    commanded_speed: float = 0.0    # Commanded RPM (S word)
    direction: SpindleDirection = SpindleDirection.STOPPED
    at_speed: bool = False
    override: float = 1.0           # 0.0–2.0 multiplier


@dataclass(frozen=True)
class MachineState:
    """Complete snapshot of machine state — updated each poll cycle.

    This is the single object the GUI reads to update all displays.
    Immutable (frozen) so it can be safely passed between threads.
    """
    # Task state
    task_state: TaskState = TaskState.OFF
    task_mode: TaskMode = TaskMode.MANUAL
    interp_state: InterpState = InterpState.IDLE

    # Axes
    x: AxisState = field(default_factory=AxisState)
    z: AxisState = field(default_factory=AxisState)

    # Spindle
    spindle: SpindleState = field(default_factory=SpindleState)

    # Overrides
    feed_override: float = 1.0      # 0.0–2.0 multiplier
    rapid_override: float = 1.0     # 0.0–1.0 multiplier

    # Program
    program_file: str = ""
    current_line: int = 0
    motion_line: int = 0

    # Active G-codes (modal state)
    active_gcodes: str = ""         # e.g., "G20 G90 G95 G54"
    active_mcodes: str = ""         # e.g., "M3 M8"

    # Tool
    tool_in_spindle: int = 0
    tool_offset_x: float = 0.0     # diameter
    tool_offset_z: float = 0.0

    # Flags
    estop_active: bool = False
    machine_on: bool = False
    all_homed: bool = False
    optional_stop: bool = False
    block_delete: bool = False
    flood_on: bool = False
    mist_on: bool = False

    # Error/message
    error_message: str = ""


# =============================================================================
# Abstract Backend Interface
# =============================================================================

class HALBackend(ABC):
    """Abstract interface for machine control communication.

    Implementations:
        LiveBackend — real LinuxCNC connection via linuxcnc module
        MockBackend — offline simulation for Windows development

    Usage pattern (in GUI timer callback):
        backend.poll()
        state = backend.state
        # Update DRO, status indicators, etc. from state
    """

    @property
    @abstractmethod
    def state(self) -> MachineState:
        """Current machine state snapshot (read after poll())."""
        ...

    @property
    @abstractmethod
    def connected(self) -> bool:
        """Whether the backend is connected to LinuxCNC."""
        ...

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------

    @abstractmethod
    def poll(self) -> None:
        """Poll LinuxCNC for updated state.

        Call this once per GUI timer cycle (typically 100ms).
        After calling, read self.state for the latest snapshot.
        """
        ...

    # ------------------------------------------------------------------
    # Mode Control
    # ------------------------------------------------------------------

    @abstractmethod
    def set_mode_manual(self) -> bool:
        """Switch to manual mode. Returns True on success."""
        ...

    @abstractmethod
    def set_mode_mdi(self) -> bool:
        """Switch to MDI mode. Returns True on success."""
        ...

    @abstractmethod
    def set_mode_auto(self) -> bool:
        """Switch to auto mode. Returns True on success."""
        ...

    # ------------------------------------------------------------------
    # E-Stop & Power
    # ------------------------------------------------------------------

    @abstractmethod
    def estop_reset(self) -> bool:
        """Reset E-stop. Returns True on success."""
        ...

    @abstractmethod
    def machine_on(self) -> bool:
        """Turn machine on (after E-stop reset). Returns True on success."""
        ...

    @abstractmethod
    def machine_off(self) -> bool:
        """Turn machine off. Returns True on success."""
        ...

    # ------------------------------------------------------------------
    # Homing
    # ------------------------------------------------------------------

    @abstractmethod
    def home_axis(self, axis: int) -> bool:
        """Home a single axis (0=X, 1=Z). Returns True on success."""
        ...

    @abstractmethod
    def home_all(self) -> bool:
        """Home all axes in sequence. Returns True on success."""
        ...

    @abstractmethod
    def unhome_axis(self, axis: int) -> bool:
        """Unhome a single axis. Returns True on success."""
        ...

    # ------------------------------------------------------------------
    # Jogging
    # ------------------------------------------------------------------

    @abstractmethod
    def jog_continuous(self, axis: int, direction: float, velocity: float) -> bool:
        """Start continuous jog on an axis.

        Args:
            axis: 0=X, 1=Z
            direction: +1.0 or -1.0
            velocity: Jog speed in inches/sec

        Returns True on success.
        """
        ...

    @abstractmethod
    def jog_increment(self, axis: int, direction: float, velocity: float, distance: float) -> bool:
        """Jog an axis by a fixed increment.

        Args:
            axis: 0=X, 1=Z
            direction: +1.0 or -1.0
            velocity: Jog speed in inches/sec
            distance: Increment in inches (always positive, direction sets sign)

        Returns True on success.
        """
        ...

    @abstractmethod
    def jog_stop(self, axis: int) -> bool:
        """Stop jogging on an axis. Returns True on success."""
        ...

    # ------------------------------------------------------------------
    # MDI
    # ------------------------------------------------------------------

    @abstractmethod
    def mdi_command(self, command: str) -> bool:
        """Execute an MDI command (e.g., "G0 X1.0 Z0.5").

        Switches to MDI mode if needed. Returns True on success.
        """
        ...

    # ------------------------------------------------------------------
    # Spindle (informational — manual spindle, no VFD)
    # ------------------------------------------------------------------

    @abstractmethod
    def spindle_forward(self, rpm: float) -> bool:
        """Command spindle forward (M3). For encoder sync, not motor control."""
        ...

    @abstractmethod
    def spindle_reverse(self, rpm: float) -> bool:
        """Command spindle reverse (M4). For encoder sync, not motor control."""
        ...

    @abstractmethod
    def spindle_stop(self) -> bool:
        """Command spindle stop (M5)."""
        ...

    # ------------------------------------------------------------------
    # Overrides
    # ------------------------------------------------------------------

    @abstractmethod
    def set_feed_override(self, value: float) -> bool:
        """Set feed override (0.0–2.0). Returns True on success."""
        ...

    @abstractmethod
    def set_rapid_override(self, value: float) -> bool:
        """Set rapid override (0.0–1.0). Returns True on success."""
        ...

    @abstractmethod
    def set_spindle_override(self, value: float) -> bool:
        """Set spindle override (0.25–1.5). Returns True on success."""
        ...

    # ------------------------------------------------------------------
    # Program Control
    # ------------------------------------------------------------------

    @abstractmethod
    def program_open(self, path: str) -> bool:
        """Open a G-code program file. Returns True on success."""
        ...

    @abstractmethod
    def program_run(self, start_line: int = 0) -> bool:
        """Run the loaded program from a line. Returns True on success."""
        ...

    @abstractmethod
    def program_pause(self) -> bool:
        """Pause program execution. Returns True on success."""
        ...

    @abstractmethod
    def program_resume(self) -> bool:
        """Resume paused program. Returns True on success."""
        ...

    @abstractmethod
    def program_stop(self) -> bool:
        """Stop program execution. Returns True on success."""
        ...

    # ------------------------------------------------------------------
    # Tool
    # ------------------------------------------------------------------

    @abstractmethod
    def tool_change(self, tool_number: int) -> bool:
        """Request tool change (Tn M6). Returns True on success."""
        ...

    # ------------------------------------------------------------------
    # Touch-off / WCS
    # ------------------------------------------------------------------

    @abstractmethod
    def touch_off(self, axis: int, value: float, system: int = 1) -> bool:
        """Touch off an axis (set WCS offset).

        Args:
            axis: 0=X, 1=Z
            value: The value to set at current position (X in diameter)
            system: G54=1, G55=2, etc.

        Returns True on success.
        """
        ...
