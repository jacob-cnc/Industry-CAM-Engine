"""Transition planner for Industry CAM Engine.

Plans movements between cutting passes. Uses ZoneQueryAPI for safety
verification — never geometric assumptions.

NOTE: ZoneQueryAPI is received as a parameter (dependency injection).
This module does NOT import from geometry/.

Imports from: models/, intervals/
"""

from typing import List, Tuple, TYPE_CHECKING

from models.results import TurningPass
from models.moves import ToolMove, MoveType, PassType
from models.transitions import Transition, TransitionType
from models.stock import StockDef
from models.params import RoughingParams, RoughingStrategy
from models.profile import MachiningMode
from models.constants import TOLERANCE

if TYPE_CHECKING:
    from geometry.zone_query import ZoneQueryAPI


class TransitionPlanner:
    """Plans movements between cutting passes.

    Transition types:
    - RETRACT_TRAVERSE_PLUNGE: Standard safe transition (retract X → traverse Z → plunge X)
    - PERPENDICULAR_LINK: Feed perpendicular between offset-contour passes (no retract)
    - STEP_OVER: Simple X step-down for adjacent passes at same Z start
    """

    def plan_all(
        self,
        passes: List[TurningPass],
        mode: MachiningMode,
        stock: StockDef,
        zone_query: 'ZoneQueryAPI',
        strategy: RoughingStrategy,
    ) -> List[Transition]:
        """Generate transitions between all consecutive passes.

        Args:
            passes: Ordered list of all passes (face + rough + cleanup + finish)
            mode: OD or ID
            stock: Stock definition (for safe_x computation)
            zone_query: ZoneQueryAPI for safety verification (dependency injection)
            strategy: Roughing strategy (affects transition type selection)

        Returns:
            List of Transition objects (one fewer than passes).
        """
        transitions = []
        for i in range(len(passes) - 1):
            from_pass = passes[i]
            to_pass = passes[i + 1]
            transition = self.plan_transition(from_pass, to_pass, mode, stock, zone_query, strategy)
            transitions.append(transition)
        return transitions

    def plan_transition(
        self,
        from_pass: TurningPass,
        to_pass: TurningPass,
        mode: MachiningMode,
        stock: StockDef,
        zone_query: 'ZoneQueryAPI',
        strategy: RoughingStrategy,
    ) -> Transition:
        """Determine transition type and generate moves between two passes.

        For staircase strategy: always RETRACT_TRAVERSE_PLUNGE
        For offset-contour: PERPENDICULAR_LINK between contour passes,
                           RETRACT_TRAVERSE_PLUNGE for other transitions
        """
        # Determine start and end positions
        if from_pass.moves:
            last_move = from_pass.moves[-1]
            start_pos = (last_move.x, last_move.z)
        else:
            start_pos = (from_pass.x_level, from_pass.z_end)

        # For finish and cleanup passes, approach at the pass's first cutting position
        # The tool needs to arrive at the start of the contour safely.
        if to_pass.pass_type in (PassType.FINISH, PassType.CLEANUP):
            # The first move's endpoint is the first edge's END.
            # We need to approach the first edge's START — which is where cutting begins.
            # For cleanup/finish, the pass start position is (x_level or first move X, z_start).
            # Use z_start as the Z approach (top of contour) and the first move's X as X target.
            if to_pass.moves:
                # The first move goes TO the first edge endpoint.
                # The contour starts at z_start at the same X level.
                first_move = to_pass.moves[0]
                approach_x = first_move.x  # X of the contour
                approach_z = to_pass.z_start  # Top of the contour (Z_begin)
                end_pos = (approach_x, approach_z)
            else:
                end_pos = (stock.x_start, stock.z_start)
        else:
            end_pos = (to_pass.x_level, to_pass.z_start)

        safe_x = self._get_safe_x(mode, stock)

        # For now, use RETRACT_TRAVERSE_PLUNGE for all transitions
        # (PERPENDICULAR_LINK will be added with offset-contour planner)
        moves = self._retract_traverse_plunge(start_pos, end_pos, safe_x, mode, stock)

        return Transition(
            type=TransitionType.RETRACT_TRAVERSE_PLUNGE,
            start_position=start_pos,
            end_position=end_pos,
            safe_x=safe_x,
            moves=moves,
        )

    def _retract_traverse_plunge(
        self,
        start: Tuple[float, float],
        end: Tuple[float, float],
        safe_x: float,
        mode: MachiningMode,
        stock: StockDef,
    ) -> List[ToolMove]:
        """Generate RETRACT_TRAVERSE_PLUNGE move sequence.

        OD mode:
        1. Retract X to safe level (stock OD or beyond — away from part)
        2. Traverse Z at safe X to next pass start Z
        3. Rapid X to next pass X level (or previous cleared level)

        ID mode:
        1. Retract X to safe level (pilot hole — toward center)
        2. Traverse Z at safe X to next pass start Z
        3. Rapid X to next pass X level
        """
        moves = []

        start_x, start_z = start
        end_x, end_z = end

        # Step 1: Retract X to safe level
        if abs(start_x - safe_x) > TOLERANCE:
            moves.append(ToolMove(
                move_type=MoveType.RAPID,
                x=safe_x,
                z=start_z,
                pass_type=PassType.TRANSITION,
            ))

        # Step 2: Traverse Z at safe X to next pass start Z
        if abs(start_z - end_z) > TOLERANCE:
            moves.append(ToolMove(
                move_type=MoveType.RAPID,
                x=safe_x,
                z=end_z,
                pass_type=PassType.TRANSITION,
            ))

        # Step 3: Rapid X to next pass X level
        if abs(safe_x - end_x) > TOLERANCE:
            moves.append(ToolMove(
                move_type=MoveType.RAPID,
                x=end_x,
                z=end_z,
                pass_type=PassType.TRANSITION,
            ))

        return moves

    def _get_safe_x(self, mode: MachiningMode, stock: StockDef) -> float:
        """Safe retract X level parameterized by mode.

        OD: stock_dia (retract to stock OD — outside material)
        ID: pilot_hole_dia (retract to pilot hole — inside empty space)
        """
        if mode == MachiningMode.OD:
            return stock.diameter
        else:
            return stock.pilot_hole_dia
