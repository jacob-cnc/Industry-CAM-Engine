"""Grooving and parting planner for Industry CAM Engine.

Generates radial plunge toolpaths for grooving and parting operations.
Grooving tools do NOT side-cut — for grooves wider than blade width,
multiple plunge positions are computed automatically.

Imports from: models/
"""

from typing import List

from models.program import GroovingParams
from models.stock import StockDef
from models.moves import ToolMove, MoveType, PassType
from models.constants import TOLERANCE


class GroovingPlanner:
    """Plans radial plunge grooving and parting operations.

    For each groove:
    1. Compute plunge Z positions (fills groove width with blade-width plunges)
    2. At each position: plunge radially to depth (with optional peck cycle)
    3. Retract between positions

    Parting is a special case: groove to near-centerline at a single Z.
    """

    def plan(self, params: GroovingParams, stock: StockDef) -> List[ToolMove]:
        """Generate grooving/parting moves.

        Returns:
            Ordered list of ToolMove (RAPID + FEED + DWELL for visualization/G-code).
        """
        self._validate(params, stock)

        moves = []
        is_id = params.is_internal

        # Safe X: retract position
        if is_id:
            safe_x = max(0.0, stock.pilot_hole_dia - 0.050)
        else:
            safe_x = stock.diameter + 0.050

        # Compute plunge Z positions to fill the groove width
        plunge_positions = self._compute_plunge_positions(
            params.z_start, params.z_end, params.blade_width
        )

        # For each plunge position, generate the plunge cycle
        for z_pos in plunge_positions:
            # Plunge Z is the LEFT edge of the blade at this position.
            # The blade occupies [z_pos, z_pos - blade_width].
            plunge_z = z_pos

            # Rapid to safe X at this Z
            moves.append(ToolMove(
                move_type=MoveType.RAPID,
                x=safe_x,
                z=plunge_z,
                pass_type=PassType.GROOVING,
            ))

            # Rapid X to just above the surface (clearance)
            clearance = 0.010  # 0.010" above the start surface
            if is_id:
                approach_x = params.start_diameter - clearance
            else:
                approach_x = params.start_diameter + clearance

            moves.append(ToolMove(
                move_type=MoveType.RAPID,
                x=approach_x,
                z=plunge_z,
                pass_type=PassType.GROOVING,
            ))

            # Generate plunge moves (single plunge or peck cycle)
            plunge_moves = self._make_plunge_moves(
                params, plunge_z, approach_x
            )
            moves.extend(plunge_moves)

            # Retract to safe X after plunge
            moves.append(ToolMove(
                move_type=MoveType.RAPID,
                x=safe_x,
                z=plunge_z,
                pass_type=PassType.GROOVING,
            ))

        return moves

    def _make_plunge_moves(
        self, params: GroovingParams, plunge_z: float, approach_x: float
    ) -> List[ToolMove]:
        """Generate radial plunge moves for one Z position.

        If peck disabled: single feed to full depth.
        If peck enabled: feed by peck_depth, retract peck_retract, repeat.
        """
        is_id = params.is_internal
        bottom_dia = params.bottom_diameter
        start_dia = params.start_diameter

        if not params.peck_enabled:
            # Single plunge to depth
            return [ToolMove(
                move_type=MoveType.FEED,
                x=bottom_dia,
                z=plunge_z,
                feed=params.feed,
                pass_type=PassType.GROOVING,
            )]

        # Peck cycle: incremental plunges with retracts
        moves = []
        peck_depth = params.peck_depth
        peck_retract = params.peck_retract

        if is_id:
            # ID: increasing diameter toward bore wall
            x_current = start_dia
            while x_current < bottom_dia - TOLERANCE:
                x_target = min(x_current + peck_depth, bottom_dia)
                # Feed to peck depth
                moves.append(ToolMove(
                    move_type=MoveType.FEED,
                    x=x_target,
                    z=plunge_z,
                    feed=params.feed,
                    pass_type=PassType.GROOVING,
                ))
                x_current = x_target
                # Retract if not at final depth
                if x_current < bottom_dia - TOLERANCE:
                    retract_x = x_current - peck_retract
                    moves.append(ToolMove(
                        move_type=MoveType.RAPID,
                        x=retract_x,
                        z=plunge_z,
                        pass_type=PassType.GROOVING,
                    ))
                    # Re-feed to previous depth (rapid back to where we were)
                    moves.append(ToolMove(
                        move_type=MoveType.RAPID,
                        x=x_current,
                        z=plunge_z,
                        pass_type=PassType.GROOVING,
                    ))
        else:
            # OD: decreasing diameter toward centerline
            x_current = start_dia
            while x_current > bottom_dia + TOLERANCE:
                x_target = max(x_current - peck_depth, bottom_dia)
                # Feed to peck depth
                moves.append(ToolMove(
                    move_type=MoveType.FEED,
                    x=x_target,
                    z=plunge_z,
                    feed=params.feed,
                    pass_type=PassType.GROOVING,
                ))
                x_current = x_target
                # Retract if not at final depth
                if x_current > bottom_dia + TOLERANCE:
                    retract_x = x_current + peck_retract
                    moves.append(ToolMove(
                        move_type=MoveType.RAPID,
                        x=retract_x,
                        z=plunge_z,
                        pass_type=PassType.GROOVING,
                    ))
                    # Re-feed to previous depth (rapid back to where we were)
                    moves.append(ToolMove(
                        move_type=MoveType.RAPID,
                        x=x_current,
                        z=plunge_z,
                        pass_type=PassType.GROOVING,
                    ))

        return moves

    def _compute_plunge_positions(
        self, z_start: float, z_end: float, blade_width: float
    ) -> List[float]:
        """Compute Z positions for plunge operations to fill the groove width.

        The blade sits at [z_pos - blade_width, z_pos] (extends in -Z from position).
        First plunge: blade left edge at z_start → z_pos = z_start
        Last plunge: blade right edge at z_end → z_pos = z_end + blade_width

        For grooves narrower than or equal to blade width: single plunge.
        For wider grooves: fill with adjacent plunges. The last plunge
        overlaps only as much as needed to reach z_end.

        Args:
            z_start: Left edge of groove (less negative Z)
            z_end: Right edge of groove (more negative Z)
            blade_width: Grooving insert width (inches)

        Returns:
            List of Z positions for each plunge (blade left edge at each position).
        """
        groove_width = z_start - z_end  # positive

        # Single plunge if groove fits within one blade width
        if groove_width <= blade_width + TOLERANCE:
            # Center the blade in the groove
            center_z = (z_start + z_end) / 2.0
            return [center_z + blade_width / 2.0]

        # Multiple plunges needed
        # First plunge: left edge of blade at z_start
        positions = [z_start]

        # Fill interior with full blade-width steps
        z_current = z_start - blade_width
        # The last plunge needs to have its right edge (z_pos - blade_width) at z_end
        last_position = z_end + blade_width

        while z_current > last_position + TOLERANCE:
            positions.append(z_current)
            z_current -= blade_width

        # Final position: ensures right edge of blade reaches z_end
        if abs(positions[-1] - last_position) > TOLERANCE:
            positions.append(last_position)

        return positions

    def _validate(self, params: GroovingParams, stock: StockDef) -> None:
        """Validate grooving parameters. Raises on invalid inputs."""
        if params.blade_width <= 0:
            raise ValueError(f"Blade width must be positive, got {params.blade_width}")
        if params.groove_depth <= 0:
            raise ValueError(f"Groove depth must be positive, got {params.groove_depth}")
        if params.feed <= 0:
            raise ValueError(f"Feed rate must be positive, got {params.feed}")
        if params.z_start <= params.z_end:
            raise ValueError(
                f"Z start ({params.z_start}) must be greater than Z end ({params.z_end})"
            )
        if not params.is_internal:
            if params.start_diameter > stock.diameter + TOLERANCE:
                raise ValueError(
                    f"Groove start diameter ({params.start_diameter}) exceeds "
                    f"stock diameter ({stock.diameter})"
                )
            if params.bottom_diameter < 0:
                raise ValueError(
                    f"Groove bottom diameter ({params.bottom_diameter:.4f}) would be "
                    f"below centerline. Reduce groove depth."
                )
        if params.groove_type == "parting" and not params.peck_enabled:
            depth_radius = params.groove_depth / 2.0
            if depth_radius > 0.5:
                raise ValueError(
                    "Parting depth > 0.5\" without peck mode enabled. "
                    "Enable peck for chip evacuation on deep parting cuts."
                )
