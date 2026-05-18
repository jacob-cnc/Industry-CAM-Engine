"""Transition definitions for Industry CAM Engine.

Defines typed movements between cutting passes.
Zero external dependencies.
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Tuple

from models.moves import ToolMove


class TransitionType(Enum):
    """Type of movement between passes."""
    RETRACT_TRAVERSE_PLUNGE = "retract_traverse_plunge"
    PERPENDICULAR_LINK = "perpendicular_link"
    STEP_OVER = "step_over"


@dataclass(frozen=True)
class Transition:
    """Movement between two cutting passes.

    Coordinates:
        start_position: (x_dia, z) where previous pass ended
        end_position: (x_dia, z) where next pass begins
        safe_x: Retract X level (DIAMETER). Stock OD for OD, pilot hole for ID.
    """
    type: TransitionType
    start_position: Tuple[float, float]
    end_position: Tuple[float, float]
    safe_x: float
    moves: List[ToolMove]
