"""Imports from: models/ only"""

from dataclasses import dataclass
from typing import List

from models.moves import MoveType, PassType, ToolMove
from models.results import PlanResult


@dataclass(frozen=True)
class SimMove:
    """A single animation frame position for playback simulation."""
    x_radius: float
    z: float
    move_type: str
    pass_type: str
    pass_index: int
    feed: float
    n_number: int


def export(plan_result: PlanResult) -> List[SimMove]:
    """Convert PlanResult tool_moves into a list of SimMove objects for playback animation.

    Each SimMove represents one animation frame position.
    x_radius is X/2 (diameter to radius conversion for display).
    n_number is sequential (10, 20, 30, ...).
    """
    sim_moves: List[SimMove] = []
    for i, move in enumerate(plan_result.tool_moves):
        sim_moves.append(SimMove(
            x_radius=move.x / 2.0,
            z=move.z,
            move_type=move.move_type.value,
            pass_type=move.pass_type.value,
            pass_index=move.pass_index,
            feed=move.feed,
            n_number=(i + 1) * 10,
        ))
    return sim_moves
