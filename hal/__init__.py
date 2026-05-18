"""HAL abstraction layer for Industry CAM Engine.

Provides a unified interface to LinuxCNC (live) or mock data (offline).
The GUI never imports linuxcnc directly — it goes through this layer.

Usage:
    from hal import get_backend
    backend = get_backend()  # Returns LiveBackend or MockBackend
"""

from hal.interface import HALBackend, MachineState, AxisState, SpindleState
from hal.factory import get_backend

__all__ = [
    "get_backend",
    "HALBackend",
    "MachineState",
    "AxisState",
    "SpindleState",
]
