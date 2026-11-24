"""On-center axial drilling planner for Industry CAM Engine (spec: drilling-cycles).

Generates the explicit peck toolpath for a hole on the spindle centreline (X0),
fed along Z by a drill / spot drill / reamer held in the QCTP holder. The engine
emits these as G0 / G1 / G4 moves (NOT a G8x canned cycle): a canned cycle in the
G18 (XZ) plane drills along Y rather than Z, which is wrong for a lathe. Explicit
moves also round-trip through the simple parser and preview on any machine.

The drill geometry comes from the tool, matching the .tbl D-column convention:
    drill_diameter = 2 * tool.nose_radius     (D = drill diameter, nose_radius = D/2)
    point_angle    = tool.tip_angle           (e.g. 118 or 135 degrees)

Z convention: Z is negative toward the tailstock. ``z_start`` is the part face;
feeds go to more-negative Z. A drilling block is generated on the block-writer
path (like grooving / threading) and so bypasses the pipeline's Shapely gates;
this planner therefore validates its own geometry at plan time.

Imports from: models/ only.
"""

import math
from typing import List

from models.program import DrillingParams
from models.stock import StockDef
from models.tool import ToolDef
from models.moves import ToolMove, MoveType, PassType
from models.constants import TOLERANCE

# Rapid clearance left above the last cut depth when re-entering the hole between
# pecks (full-retract) or when backing off for a chip break (DIAMETER-independent,
# axial inches).
RAPID_CLEARANCE = 0.020


def tip_length(drill_diameter: float, point_angle: float) -> float:
    """Axial length of the conical drill point: (D/2) / tan(point_angle / 2).

    Returns 0.0 for a flat point (>= 180 deg) or an unknown/degenerate angle
    (<= 0 deg), so a reamer or flat-bottom tool adds no tip compensation.
    """
    if drill_diameter <= 0.0 or point_angle <= 0.0 or point_angle >= 180.0:
        return 0.0
    return (drill_diameter / 2.0) / math.tan(math.radians(point_angle / 2.0))


class DrillingPlanner:
    """Plan one on-center axial drilling operation; never emits G-code.

    ``plan`` returns an ordered list of ToolMove (RAPID / FEED / DWELL) at X0,
    which outputs/gcode_writer.write_drilling_block formats into G-code.
    """

    def plan(self, params: DrillingParams, tool: ToolDef,
             stock: StockDef) -> List[ToolMove]:
        """Generate the drilling move list (all at X diameter 0.0).

        Raises ValueError on unsafe geometry (see _validate).
        """
        drill_dia = 2.0 * tool.nose_radius
        point_angle = tool.tip_angle
        tl = tip_length(drill_dia, point_angle)

        z_final = self._final_depth(params, tl)
        self._validate(params, stock, drill_dia, z_final)

        moves: List[ToolMove] = []

        # Rapid to the centreline at the clearance plane.
        moves.append(ToolMove(MoveType.RAPID, x=0.0, z=params.r_plane,
                              pass_type=PassType.DRILLING))

        moves.extend(self._peck_moves(params, z_final))

        # Bottom dwell (DWELL carries its seconds in the move's feed field, which
        # outputs/gcode_writer._dwell reads as G04 P<seconds>).
        if params.dwell > 0.0:
            moves.append(ToolMove(MoveType.DWELL, x=0.0, z=z_final,
                                  feed=params.dwell, pass_type=PassType.DRILLING))

        # Retract to the clearance plane.
        moves.append(ToolMove(MoveType.RAPID, x=0.0, z=params.r_plane,
                              pass_type=PassType.DRILLING))
        return moves

    def _final_depth(self, params: DrillingParams, tl: float) -> float:
        """Z of the drill tip at the bottom of the hole (most negative).

        The tip is always ``tip_length`` deeper than the full-diameter shoulder.
            depth_to_tip (blind): the tip reaches z_start - depth.
            shoulder ref OR through-hole: the FULL DIAMETER reaches z_start - depth,
                so the tip goes one tip_length further.
        (A through hole wants full-diameter breakthrough, so it uses shoulder
        semantics regardless of depth_to_tip; this avoids double-counting the tip.)
        """
        base = params.z_start - params.depth
        if params.depth_to_tip and not params.through_hole:
            return base
        return base - tl

    def _peck_moves(self, params: DrillingParams, z_final: float) -> List[ToolMove]:
        """Feed moves from the clearance plane to z_final.

        No peck: a single FEED to z_final. Peck: repeated FEED of peck_increment
        with a retract between pecks — a full retract to r_plane (then rapid back
        to just above the last depth) for full_retract, or a small chip-break
        retract that stays in the hole otherwise.
        """
        feed = params.feed
        if not params.peck_enabled:
            return [ToolMove(MoveType.FEED, x=0.0, z=z_final, feed=feed,
                             pass_type=PassType.DRILLING)]

        moves: List[ToolMove] = []
        z_cur = params.r_plane
        while z_cur > z_final + TOLERANCE:
            z_next = max(z_cur - params.peck_increment, z_final)
            moves.append(ToolMove(MoveType.FEED, x=0.0, z=z_next, feed=feed,
                                  pass_type=PassType.DRILLING))
            z_cur = z_next
            if z_cur > z_final + TOLERANCE:          # more hole to go: retract
                if params.full_retract:
                    moves.append(ToolMove(MoveType.RAPID, x=0.0, z=params.r_plane,
                                          pass_type=PassType.DRILLING))
                    moves.append(ToolMove(MoveType.RAPID, x=0.0,
                                          z=z_cur + RAPID_CLEARANCE,
                                          pass_type=PassType.DRILLING))
                else:
                    moves.append(ToolMove(MoveType.RAPID, x=0.0,
                                          z=z_cur + RAPID_CLEARANCE,
                                          pass_type=PassType.DRILLING))
        return moves

    def _validate(self, params: DrillingParams, stock: StockDef,
                  drill_dia: float, z_final: float) -> None:
        """Reject unsafe drilling geometry. Raises ValueError with context.

        No silent fallback (architecture rule 1). Machine Z-travel limits are the
        GUI layer's responsibility (it holds the INI); this checks what the
        planner can know from the params, tool, and stock.
        """
        if params.feed <= 0.0:
            raise ValueError(f"Drill feed must be positive, got {params.feed}.")
        if params.depth <= 0.0:
            raise ValueError(f"Drill depth must be positive, got {params.depth}.")
        if params.peck_enabled and params.peck_increment <= 0.0:
            raise ValueError(
                f"Peck increment must be positive when pecking, got {params.peck_increment}."
            )
        if drill_dia <= 0.0:
            raise ValueError(
                "Drill diameter is zero: set the tool's nose radius (D/2) so the "
                "drill has a diameter."
            )
        if params.r_plane <= z_final + TOLERANCE:
            raise ValueError(
                f"Clearance plane Z={params.r_plane:.4f} is not above the hole bottom "
                f"Z={z_final:.4f}; feed would start below the material."
            )
        if drill_dia > stock.diameter + TOLERANCE:
            raise ValueError(
                f"Drill diameter {drill_dia:.4f} exceeds the stock diameter "
                f"{stock.diameter:.4f}; the on-center hole does not fit."
            )
        if not params.through_hole and z_final < stock.physical_z_end - TOLERANCE:
            raise ValueError(
                f"Blind hole bottom Z={z_final:.4f} is beyond the stock back face "
                f"Z={stock.physical_z_end:.4f}. Reduce the depth, or enable "
                f"through-hole if it is meant to break through."
            )
