"""Profile data structures for Industry CAM Engine.

Defines the user's profile geometry and machining mode.
Zero external dependencies.
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


class SegmentType(Enum):
    """Type of profile segment."""
    LINE = "line"
    ARC = "arc"


class MachiningMode(Enum):
    """OD (external) or ID (internal/bore) machining."""
    OD = "od"
    ID = "id"


class CornerBreakType(Enum):
    """Type of corner break between adjacent segments."""
    NONE = "none"
    FILLET = "fillet"
    CHAMFER = "chamfer"


@dataclass(frozen=True)
class CornerBreak:
    """Corner break at a profile vertex (between two adjacent segments).

    corner_breaks[k-1] is vertex Vk; V1 is the corner between the implied
    front face and segment 1. Equal-leg chamfers and fillets only (angle is
    not used by the geometry). Sizes are true geometric lengths (radius
    space), not diameter values.

    Geometry: OD -> geometry/corner_breaks_od.py (validated against an NX
    reference part); ID -> legacy code in geometry/zone_builder.py until an
    ID reference part validates it.
    """
    break_type: CornerBreakType
    radius: float = 0.0       # Fillet radius (inches). Used when type=FILLET.
    size: float = 0.0         # Chamfer size (inches along each segment). Used when type=CHAMFER.
    angle: float = 45.0       # Chamfer angle (degrees). Used when type=CHAMFER.


@dataclass(frozen=True)
class ProfileMove:
    """A single segment in the user's profile definition.

    Coordinates:
        x: End X position in DIAMETER (inches)
        z: End Z position in INCHES
        radius: Arc radius in RADIUS (inches), signed: +CW (G02), -CCW (G03). 0 for lines.
        quadrant: If True, this is a tangent-bounded quadrant arc (quarter ellipse).
                  The radius field is ignored and the arc is computed from endpoints.
    """
    segment_type: SegmentType
    x: float
    z: float
    radius: float = 0.0
    quadrant: bool = False
    quadrant_sign: int = 1  # +1 = convex (Q), -1 = concave (-Q)


@dataclass(frozen=True)
class ClosedProfile:
    """Complete user profile with closure segments appended at generation time.

    The user defines only the open profile (segments). Closure is computed
    automatically by geometry/zone_builder.py using stock parameters.

    corner_breaks has length = len(segments) - 1 (one per junction between segments).
    """
    segments: List[ProfileMove]
    corner_breaks: List[Optional[CornerBreak]]
    mode: MachiningMode
    z_start: float = 0.0    # Always 0.0 for the finished face (enforced by validation)
    z_end: float = 0.0      # Most negative Z (user input, negative value)
