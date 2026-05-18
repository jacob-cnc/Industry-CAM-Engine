"""Face planner for Industry CAM Engine.

Plans face passes to remove the True Face Zone.
OD: Feed from Stock OD toward X_start, stepping Z by DOC from Z_start toward Z=0+fin_allowance
ID: Feed from Pilot Hole toward X_start, stepping Z by DOC from Z_start toward Z=0+fin_allowance

Imports from: models/, intervals/ (Fiber not needed — face is rectangular)
"""

from typing import List, TYPE_CHECKING

from models.results import TurningPass, SweptRegion
from models.moves import ToolMove, MoveType, PassType
from models.tool import ToolDef
from models.params import RoughingParams
from models.stock import StockDef
from models.profile import MachiningMode
from models.constants import TOLERANCE

if TYPE_CHECKING:
    from geometry.zone_query import ZoneQueryAPI


class FacePlanner:
    """Plans face passes to remove the True Face Zone.

    Face passes cut along the X axis (radial direction) at constant Z levels,
    stepping Z from Z_start toward Z=0+fin_allowance.

    OD mode: Feed from Stock OD → X_start (decreasing X)
    ID mode: Feed from Pilot Hole → X_start (increasing X)
    """

    def plan(
        self,
        stock: StockDef,
        tool: ToolDef,
        params: RoughingParams,
        mode: MachiningMode,
        zone_query: 'ZoneQueryAPI',
    ) -> List[TurningPass]:
        """Generate face passes.

        Returns:
            List of TurningPass objects for the face zone, ordered from Z_start toward Z=0.
        """
        doc_radius = params.doc_dia / 2.0
        fin_allowance_radius = params.fin_allowance / 2.0
        stock_radius = stock.diameter / 2.0
        x_start_radius = stock.x_start / 2.0

        # Face zone Z boundaries
        z_top = stock.z_start  # Start cutting from here (positive Z)
        z_bottom = fin_allowance_radius  # Stop here — leave fin_allowance for finish pass

        # Check if there's actually a face zone to cut
        if z_top - z_bottom < TOLERANCE:
            return []  # No face material to remove

        # Determine X boundaries for face passes
        if mode == MachiningMode.OD:
            # OD: cut from stock OD inward to X_start
            x_feed_start_dia = stock.diameter  # Start at stock OD
            x_feed_end_dia = stock.x_start     # End at X_start
        else:
            # ID: cut from pilot hole outward to X_start
            x_feed_start_dia = stock.pilot_hole_dia  # Start at pilot hole
            x_feed_end_dia = stock.x_start           # End at X_start

        # Check if there's X travel for face passes
        if abs(x_feed_start_dia - x_feed_end_dia) < TOLERANCE * 2:
            return []  # No face zone (X_start == stock boundary)

        # Generate Z levels for face passes (stepping from Z_start toward Z=0+fin_allowance)
        z_levels = []
        z_current = z_top
        while z_current - z_bottom > TOLERANCE:
            z_current -= doc_radius
            if z_current < z_bottom:
                z_current = z_bottom
            z_levels.append(z_current)

        # Create passes
        passes = []
        for i, z_level in enumerate(z_levels):
            # Each face pass is a single feed move across X at constant Z
            move = ToolMove(
                move_type=MoveType.FEED,
                x=x_feed_end_dia,
                z=z_level,
                feed=params.feed,
                pass_type=PassType.FACE,
                pass_index=i,
            )

            # Swept region for this face pass
            prev_z = z_levels[i - 1] if i > 0 else z_top
            swept = SweptRegion(
                x_min=min(x_feed_start_dia, x_feed_end_dia),
                x_max=max(x_feed_start_dia, x_feed_end_dia),
                z_start=prev_z,
                z_end=z_level,
            )

            turning_pass = TurningPass(
                x_level=z_level,  # For face passes, "level" is the Z position
                z_start=z_level,
                z_end=z_level,
                pass_index=i,
                pass_type=PassType.FACE,
                moves=[move],
                swept_region=swept,
            )
            passes.append(turning_pass)

        return passes
