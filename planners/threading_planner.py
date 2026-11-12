"""Threading planner for Industry CAM Engine.

Computes G76 threading cycle parameters from user inputs.
The planner validates and derives the cycle parameters — the G-code writer
emits the actual G76 line since LinuxCNC handles the multi-pass synchronized
motion internally.

Imports from: models/
"""

import math
from typing import List

from models.program import ThreadingParams
from models.stock import StockDef
from models.moves import ToolMove, MoveType, PassType


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

    # Drive line this far outside the crest (on DIAMETER; owner 2026-11-12,
    # same as the contour feed-in).
    DRIVE_LINE_CLEARANCE_DIA = 0.020
    # Retract / approach X this much further from the drive line (diameter).
    SAFE_X_EXTRA_DIA = 0.050

    def compute_g76_params(self, params: ThreadingParams) -> dict:
        """G76 words for LinuxCNC in G7 (DIAMETER mode), plus where the tool
        must be before and after the cycle.

        LinuxCNC (2.9 manual, G76): the drive line is the tool's X before the
        G76; I is the thread crest's offset FROM the drive line (negative =
        external, positive = internal); J and K are the first and full cut depth
        beyond the crest; in G7 I, J, K are DIAMETER values. P is the distance
        per spindle revolution - the LEAD (pitch x starts).

        Until 2026-11-12 the drive line was put ON the major diameter with I0
        (LinuxCNC: "In G76, I must not be 0"), J / K were radial values read as
        diameters (half-depth threads), an internal thread was approached at the
        MAJOR diameter (into the bore wall), and multi-start used the pitch as P.

        Returns the G76 words P Z I J K R Q H E L and (diameter, inches):
            X_drive   drive line: crest + .020 (external) / crest - .020 (internal)
            X_safe    approach / retract X, clear of the work
            crest     major Ø (external) / minor Ø = major - 2 x depth (internal)
            Z_start   where each start begins (list, one per start)
        """
        if params.taper_amount != 0.0:
            raise ValueError(
                "Tapered threads (e.g. NPT) are not supported: LinuxCNC's G76 cuts parallel "
                "threads only. Set the taper to 0, or cut the taper another way.")
        depth_dia = 2.0 * params.thread_depth                       # K: radial depth -> diameter
        if params.first_pass_depth > 0:
            first_dia = 2.0 * params.first_pass_depth
        else:
            # constant-area start: depth_1 = full_depth * sqrt(1/num_passes)
            first_dia = depth_dia * math.sqrt(1.0 / params.num_passes)
        compound_angle = self._get_compound_angle(params.infeed_method)
        c = self.DRIVE_LINE_CLEARANCE_DIA
        if params.is_internal:
            crest = params.major_diameter - depth_dia
            x_drive = crest - c
            peak_offset = +c
            x_safe = max(0.0, x_drive - self.SAFE_X_EXTRA_DIA)
        else:
            crest = params.major_diameter
            x_drive = crest + c
            peak_offset = -c
            x_safe = x_drive + self.SAFE_X_EXTRA_DIA
        starts = max(1, int(params.num_starts))
        lead = params.pitch * starts
        # Pull-out chamfer: LinuxCNC's exit taper (L2) over E along the drive line.
        exit_taper = max(0.0, params.chamfer_threads) * lead
        drive_len = abs(params.start_z - params.end_z)
        if exit_taper > drive_len / 2.0 + 1e-12:
            raise ValueError(
                f"The pull-out chamfer ({params.chamfer_threads:g} threads = {exit_taper:.4f}) is "
                f"longer than half the thread ({drive_len:.4f}); LinuxCNC refuses that. Use a "
                f"smaller chamfer or a longer thread.")
        return {
            "P": lead,
            "Z": params.end_z,
            "I": peak_offset,
            "J": first_dia,
            "K": depth_dia,
            "R": params.degression,
            "Q": compound_angle,
            "H": params.spring_passes,
            "E": exit_taper,
            "L": 2 if exit_taper > 0 else 0,
            "X_drive": x_drive,
            "X_safe": x_safe,
            "crest": crest,
            "Z_start": [params.start_z - k * params.pitch for k in range(starts)],
        }

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
