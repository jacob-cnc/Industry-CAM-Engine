"""Tool definition for Industry CAM Engine.

Defines tool geometry, orientation, and offsets.
Zero external dependencies.
"""

from dataclasses import dataclass
from enum import Enum


class ToolOrientation(Enum):
    """LinuxCNC tool orientation codes 1-9."""
    OD_FRONT_RIGHT = 1
    OD_FRONT_LEFT = 2
    OD_BACK_RIGHT = 3
    OD_BACK_LEFT = 4
    ID_FRONT_RIGHT = 5
    ID_FRONT_LEFT = 6
    ID_BACK_RIGHT = 7
    ID_BACK_LEFT = 8
    CENTER = 9


class ToolDirection(Enum):
    """Cutting direction — determines G41 vs G42."""
    RIGHT = "R"
    LEFT = "L"
    NEUTRAL = "N"


class ToolType(Enum):
    """Tool category — influences available insert shapes and orientations."""
    TURNING = "turning"
    BORING = "boring"
    THREADING = "threading"
    GROOVING = "grooving"


@dataclass(frozen=True)
class ToolDef:
    """Complete tool geometry definition — single source of truth.

    This dataclass flows from the tool table through the pipeline.
    TNR compensation is handled by LinuxCNC G41/G42 at runtime,
    not by the engine's coordinate computation.

    Coordinates:
        nose_radius: TNR in inches (radius)
        x_offset: X offset in DIAMETER (inches)
        z_offset: Z offset in inches
        x_wear: X wear compensation in DIAMETER (inches)
        z_wear: Z wear compensation in inches
    """
    tool_number: int
    nose_radius: float
    tip_angle: float             # Included angle (degrees)
    edge_length: float           # Cutting edge length (inches)
    orientation: ToolOrientation
    direction: ToolDirection
    tool_type: ToolType = ToolType.TURNING
    rotation: float = 0.0        # Tool rotation about tip (degrees, 0-360)
    description: str = ""
    x_offset: float = 0.0
    z_offset: float = 0.0
    x_wear: float = 0.0
    z_wear: float = 0.0
