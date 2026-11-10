"""Arc translation between the engine's internal moves and LinuxCNC G-code.

This is the ONLY place that maps an internal arc to G02/G03 + I, and back.
The writer (outputs/gcode_writer.py), the move parser
(outputs/gcode_parser.py) and the preview parser
(gui/components/sim_viewer.py) all go through it, so what the preview draws
is exactly what LinuxCNC runs.

Internal convention (planners, validators, material sim, graph adapter),
unchanged since the engine was written:
  * ToolMove.center_i is a DIAMETER offset (center X dia - start X dia).
  * MoveType.ARC_CW / ARC_CCW: ARC_CW sweeps COUNTER-clockwise on the
    Program/Run graph (Z to the right, X up); ARC_CCW sweeps clockwise.
    The names are historical; the geometry they describe is consistent
    everywhere inside the engine and the preview.

LinuxCNC 2.9 in G7 G18 (verified with its own interpreter, rs274, on the lathe
PC, 2026-11-10):
  * I is a RADIUS offset even in diameter mode (G7 scales X words only).
  * G02 sweeps clockwise with Z to the right and X up; G03 counter-clockwise.

So an internal ARC_CW is written as G03 and an internal ARC_CCW as G02, with
I = center_i / 2. Before this module existed the writer emitted G02 for
ARC_CW and the diameter offset as I: LinuxCNC then ran the mirror-image arc
around a centre twice as far out in X, and rejected most programs with
"radius to end of arc differs" or cutter-comp gouge errors.
"""

from models.moves import MoveType


def gcode_for_arc(move_type: MoveType) -> str:
    """Internal arc type -> LinuxCNC motion word."""
    if move_type == MoveType.ARC_CW:
        return "G03"
    if move_type == MoveType.ARC_CCW:
        return "G02"
    raise ValueError(f"not an arc move: {move_type}")


def arc_type_for_gcode(g: int) -> MoveType:
    """LinuxCNC G2/G3 -> internal arc type."""
    if g == 2:
        return MoveType.ARC_CCW
    if g == 3:
        return MoveType.ARC_CW
    raise ValueError(f"not an arc G-code: G{g}")


def i_word_from_center_i(center_i_dia: float) -> float:
    """Internal diameter offset -> LinuxCNC I word (radius offset)."""
    return center_i_dia / 2.0


def center_i_from_i_word(i_word: float) -> float:
    """LinuxCNC I word (radius offset) -> internal diameter offset."""
    return i_word * 2.0
