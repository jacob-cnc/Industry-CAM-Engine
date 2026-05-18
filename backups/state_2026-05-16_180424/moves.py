"""Tool move definitions for Industry CAM Engine.

Defines the atomic unit of the toolpath — a single machine movement.
Zero external dependencies.
"""

from dataclasses import dataclass
from enum import Enum


class MoveType(Enum):
    """G-code motion type."""
    RAPID = "rapid"         # G00
    FEED = "feed"           # G01
    ARC_CW = "arc_cw"      # G02
    ARC_CCW = "arc_ccw"     # G03


class PassType(Enum):
    """Which phase of machining this move belongs to."""
    FACE = "face"
    ROUGH = "rough"
    CLEANUP = "cleanup"
    FINISH = "finish"
    TRANSITION = "transition"


@dataclass(frozen=True)
class ToolMove:
    """A single machine movement — the atomic unit of the toolpath.

    Coordinates:
        x: End X in DIAMETER (inches)
        z: End Z in inches
        feed: Feed rate (inches/rev). 0 for rapids.
        radius: Arc radius (signed: +CW G02, -CCW G03). 0 for linear moves.
        center_i: Arc center X offset (DIAMETER, incremental from start)
        center_k: Arc center Z offset (inches, incremental from start)
    """
    move_type: MoveType
    x: float
    z: float
    feed: float = 0.0
    radius: float = 0.0
    center_i: float = 0.0
    center_k: float = 0.0
    pass_type: PassType = PassType.ROUGH
    pass_index: int = 0
