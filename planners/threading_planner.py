"""Threading planner for Industry CAM Engine.

Computes G76 threading cycle parameters from user inputs.
The planner validates and derives the cycle parameters — the G-code writer
emits the actual G76 line since LinuxCNC handles the multi-pass synchronized
motion internally.

Imports from: models/
"""

import math
from typing import List, Tuple

from models.program import ThreadingParams
from models.stock import StockDef
from models.moves import ToolMove, MoveType, PassType
from models.constants import TOLERANCE


class ThreadingPlanner:
    """Compute and validate G76 threading cycle parameters.

    LinuxCNC's G76 handles:
    - Spindle-synchronized motion (encoder feedback)
    - Multi-pass infeed with degression
    - Compound slide angle (flank/radial infeed)
    - Spring passes at full depth
    - Entry/exit chamfers

    Our job: validate inputs, compute derived values, produce approach/retract
    moves for the graph, and pass parameters to the G-code writer.
    """

    def plan(self, params: ThreadingParams, stock: StockDef) -> List[ToolMove]:
        """Generate approach/retract moves for threading visualization.

        The actual threading motion is a G76 cycle (emitted by gcode_writer).
        This method produces:
        1. Rapid to threading start position
        2. A synthetic FEED move representing the thread path (for graph display)
        3. Rapid retract

        The G-code writer uses ThreadingParams directly for the G76 line.

        Returns:
            List of ToolMove for graph visualization and move tracking.
        """
        self._validate(params, stock)

        moves = []
        is_id = params.is_internal

        # Safe X: retract position between threading passes
        # OD: stock OD + clearance
        # ID: pilot hole - clearance (toward centerline)
        if is_id:
            safe_x = max(0.0, stock.pilot_hole_dia - 0.050)
            thread_start_x = params.major_diameter
        else:
            safe_x = stock.diameter + 0.050
            thread_start_x = params.major_diameter

        # Approach: rapid to safe X at start Z
        moves.append(ToolMove(
            move_type=MoveType.RAPID,
            x=safe_x,
            z=params.start_z,
            pass_type=PassType.THREADING,
        ))

        # Rapid to thread major diameter at start Z
        moves.append(ToolMove(
            move_type=MoveType.RAPID,
            x=thread_start_x,
            z=params.start_z,
            pass_type=PassType.THREADING,
        ))

        # Synthetic feed move representing the thread path (for graph display)
        # This shows the thread extent on the visualization
        moves.append(ToolMove(
            move_type=MoveType.FEED,
            x=thread_start_x,
            z=params.end_z,
            feed=params.pitch,  # pitch as "feed" for display context
            pass_type=PassType.THREADING,
        ))

        # Retract to safe X
        moves.append(ToolMove(
            move_type=MoveType.RAPID,
            x=safe_x,
            z=params.end_z,
            pass_type=PassType.THREADING,
        ))

        # Rapid back to start Z at safe X
        moves.append(ToolMove(
            move_type=MoveType.RAPID,
            x=safe_x,
            z=params.start_z,
            pass_type=PassType.THREADING,
        ))

        return moves

    def compute_g76_params(self, params: ThreadingParams) -> dict:
        """Compute the G76 word values from ThreadingParams.

        Returns dict with keys matching G76 words:
            P: pitch (distance per revolution)
            Z: final Z position
            I: thread peak offset (taper amount, 0 for parallel)
            J: initial cut depth (first pass)
            K: full thread depth
            R: depth degression (1.0=constant, 2.0=constant area)
            Q: compound slide angle (degrees * 10 for LinuxCNC)
            H: spring passes
            E: taper distance per thread (0 for parallel)
            L: chamfer threads (in number of threads at exit)
        """
        # Full thread depth (K word) — already computed in params
        full_depth = params.thread_depth

        # Initial cut depth (J word)
        if params.first_pass_depth > 0:
            first_depth = params.first_pass_depth
        else:
            # Auto-compute: first pass depth from constant-area formula
            # depth_1 = full_depth * sqrt(1/num_passes)
            first_depth = full_depth * math.sqrt(1.0 / params.num_passes)

        # Compound angle (Q word) — determines infeed direction
        compound_angle = self._get_compound_angle(params.infeed_method)

        # Thread peak offset (I word) — for tapered threads (NPT)
        # I = change in radius over the thread length
        # Positive = toward spindle (ID taper), Negative = away (OD taper)
        if params.taper_amount != 0.0:
            thread_length = abs(params.start_z - params.end_z)
            # taper_amount is in diameter per inch. I word is radius change over full length.
            peak_offset = (params.taper_amount * thread_length) / 2.0
            if not params.is_internal:
                peak_offset = -peak_offset  # OD external taper: negative
        else:
            peak_offset = 0.0

        return {
            "P": params.pitch,
            "Z": params.end_z,
            "I": peak_offset,
            "J": first_depth,
            "K": full_depth,
            "R": params.degression,
            "Q": compound_angle,
            "H": params.spring_passes,
            "E": 0.0,  # Taper distance per thread (we use I for full taper)
            "L": params.chamfer_threads,
        }

    def compute_pass_depths(self, params: ThreadingParams) -> List[float]:
        """Compute cumulative infeed depths for each pass.

        Uses constant-area (sqrt) progression by default (degression=2.0):
            depth[n] = full_depth * sqrt(n / num_passes)

        Returns:
            List of cumulative depths (len = num_passes).
        """
        full_depth = params.thread_depth
        n = params.num_passes
        degression = params.degression

        if degression <= 1.0:
            # Constant depth per pass
            step = full_depth / n
            return [step * (i + 1) for i in range(n)]
        else:
            # Constant area (sqrt progression)
            return [full_depth * math.sqrt((i + 1) / n) for i in range(n)]

    def _get_compound_angle(self, infeed_method: str) -> float:
        """Return compound slide angle in degrees for the infeed method."""
        angles = {
            "radial": 0.0,
            "flank": 29.5,
            "modified_flank": 30.0,
            "alternating": 29.5,  # LinuxCNC G76 doesn't support alternating directly
        }
        return angles.get(infeed_method, 29.5)

    def _validate(self, params: ThreadingParams, stock: StockDef) -> None:
        """Validate threading parameters. Raises on invalid inputs."""
        if params.pitch <= 0:
            raise ValueError(f"Thread pitch must be positive, got {params.pitch}")
        if params.thread_depth <= 0:
            raise ValueError(f"Thread depth must be positive, got {params.thread_depth}")
        if params.num_passes < 1:
            raise ValueError(f"Number of passes must be >= 1, got {params.num_passes}")
        if params.start_z <= params.end_z:
            raise ValueError(
                f"Start Z ({params.start_z}) must be greater than end Z ({params.end_z})"
            )
        if not params.is_internal and params.major_diameter > stock.diameter:
            raise ValueError(
                f"Thread major diameter ({params.major_diameter}) exceeds "
                f"stock diameter ({stock.diameter})"
            )
        # Check max threading speed (pitch * RPM = Z velocity)
        z_velocity = params.pitch * params.spindle_rpm / 60.0  # inches/second
        if z_velocity > 1.5:  # Our Z max velocity from INI
            raise ValueError(
                f"Threading Z velocity ({z_velocity:.2f} in/s) exceeds machine "
                f"max (1.5 in/s). Reduce RPM or use finer pitch."
            )
