"""Tool definition for Industry CAM Engine.

Defines tool geometry, orientation, and offsets.
Zero external dependencies.
"""

from dataclasses import dataclass
from enum import Enum


class ToolOrientation(Enum):
    """LinuxCNC tool orientation codes 1-9 (Q word).

    The member NAMES are legacy and do NOT describe LinuxCNC's meaning. Per the
    LinuxCNC 2.9.6 manual Fig 2.16 (front-tool lathe), the cutting corner
    relative to the nose centre is: 1 -X+Z, 2 -X-Z (RH OD turning),
    3 +X-Z (conventional boring bar), 4 +X+Z, 5 +Z, 6 -X, 7 -Z, 8 +X, 9 centre.
    Only the integer value is sent to LinuxCNC.
    """
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
        x_offset: CAM boundary X geometry offset in DIAMETER (inches)
        z_offset: Z offset in inches
        x_wear: CAM boundary X wear in DIAMETER (inches)
        ToolCardData stores X geometry/wear as radius and converts at this boundary.
        LinuxCNC tool.tbl stores their combined X total as RADIUS, not these values.
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
    # Cutting-edge angles from the tool table (I / J words, insert defaults from
    # pipeline/insert_geometry_lookup.py), degrees, in the tool's own frame:
    # measured from its feed direction (toward the chuck for a right-hand tool)
    # round toward the air side. CNMG in a 95 deg holder = 95 / 175. 0 / 0 =
    # unknown or round: the reach check (geometry/tool_reach.py) is skipped.
    front_angle: float = 0.0
    back_angle: float = 0.0
