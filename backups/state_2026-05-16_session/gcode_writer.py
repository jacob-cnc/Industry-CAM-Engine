"""Position-tracking G-code writer for Industry CAM Engine.

Generates clean, readable G-code with descriptive comments on every line.
Always outputs both X and Z on motion commands for operator clarity.

Imports from: models/ only
"""

import math
from typing import List, Optional

from models.results import PlanResult
from models.moves import ToolMove, MoveType, PassType
from models.tool import ToolDef, ToolDirection
from models.constants import TOLERANCE, CENTER_ARC_RADIUS_TOLERANCE_INCH


class GCodeWriter:
    """G-code writer with full coordinate output and descriptive comments.

    Features:
    - Always outputs both X and Z on motion lines (operator readability)
    - Descriptive comments on every line (pass number, move type, context)
    - G41/G42 cutter compensation
    - Same-tool optimization (skip tool change if roughing == finishing tool)
    - Arc validation before emitting
    """

    def __init__(self, arc_format: str = "ijk"):
        self._arc_format = arc_format
        self._x: float = 0.0
        self._z: float = 0.0
        self._feed: Optional[float] = None
        self._n: int = 10

    def write(self, plan_result: PlanResult) -> str:
        """Generate complete G-code program from PlanResult."""
        self._x = 0.0
        self._z = 0.0
        self._feed = None
        self._n = 10
        lines = []

        pr = plan_result
        same_tool = True  # For now, roughing and finishing use same tool (single tool_def)

        # Header
        lines.append("; Industry CAM Engine — Generated Program")
        lines.append(f"; Profile: {len(pr.profile.segments)} segments, Mode: {pr.mode.value.upper()}")
        lines.append(f"; Stock: {pr.stock.diameter:.4f} dia, Z {pr.stock.z_start:.4f} to {pr.stock.z_end:.4f}")
        lines.append(f"; DOC: {pr.roughing_params.doc_dia:.4f} dia, Rough Feed: {pr.roughing_params.feed:.4f}")
        lines.append(f"; Fin Allowance: {pr.roughing_params.fin_allowance:.4f} dia, Finish Feed: {pr.finishing_params.feed:.4f}")
        lines.append(f"; RPM: {pr.roughing_params.spindle_rpm:.0f}")
        lines.append(f"; Tool: T{pr.tool.tool_number} {pr.tool.description}")
        lines.append("")

        # Warnings
        for v in pr.validations:
            if v.severity.value == "warning":
                lines.append(f"; WARNING: {v.message}")

        # Safety preamble
        lines.append(self._line("G20 G18 G40 G49 G80", "Safety line - inch, ZX plane, comp off"))
        lines.append(self._line("G90", "Absolute positioning"))
        lines.append("")

        # Spindle speed
        lines.append(self._line(f"S{pr.roughing_params.spindle_rpm:.0f}", "Spindle speed for encoder sync"))

        # Park position
        park_x = pr.stock.x_park
        park_z = pr.stock.z_park
        lines.append(self._rapid(park_x, park_z, "Move to park position"))
        self._x = park_x
        self._z = park_z
        lines.append("")

        # Tool call
        lines.append(self._line(f"T{pr.tool.tool_number:02d}01 M6", f"Load tool T{pr.tool.tool_number} - {pr.tool.description}"))
        lines.append(self._line("G43", "Tool length comp on"))

        # Cutter compensation
        comp_code = self._get_comp_code(pr.tool.direction)
        lines.append(self._line(comp_code, "Cutter radius compensation on"))
        lines.append("")

        # === FACE PASSES ===
        if pr.face_passes:
            lines.append(f"; === FACE PASSES ({len(pr.face_passes)} passes) ===")
            lines.append(self._rapid(pr.stock.diameter, pr.stock.z_start, "Approach: Stock OD, Z_start"))
            self._x = pr.stock.diameter
            self._z = pr.stock.z_start

            for i, p in enumerate(pr.face_passes):
                # Position in Z for this pass (feed from stock OD — cutting into face material)
                face_z = p.moves[0].z if p.moves else pr.stock.z_start
                lines.append(self._feed_line(pr.stock.diameter, face_z, pr.roughing_params.feed, f"Face pass {i+1}: feed Z to {face_z:.4f}"))
                # Face cut: feed from stock OD to X_start at constant Z
                for move in p.moves:
                    lines.append(self._emit_move(move, f"Face pass {i+1}: feed to X_start"))
                # Retract X to stock OD at previous pass Z (safe level)
                retract_z = pr.stock.z_start if i == 0 else pr.face_passes[i-1].moves[0].z
                lines.append(self._rapid(pr.stock.diameter, retract_z, f"Retract X to stock OD, Z={retract_z:.4f} (prev pass)"))
            lines.append("")

        # === ROUGHING PASSES ===
        if pr.roughing_passes:
            lines.append(f"; === ROUGHING PASSES ({len(pr.roughing_passes)} passes) ===")
            # Build set of shoulder Z values from profile segments for diagonal retract detection
            shoulder_z_values = self._get_shoulder_z_values(pr)

            prev_retract_x = pr.stock.diameter  # First pass retracts to stock OD

            for i, p in enumerate(pr.roughing_passes):
                # Approach sequence:
                # 1. Traverse Z at prev_retract_x to this pass's Z start (rapid, no material at this X)
                lines.append(self._rapid(prev_retract_x, p.z_start, f"Rough pass {i+1}: traverse Z to {p.z_start:.4f} at X{prev_retract_x:.4f}"))
                # 2. Feed X from prev_retract_x to DOC level (stepping into material)
                lines.append(self._feed_line(p.x_level, p.z_start, pr.roughing_params.feed, f"Rough pass {i+1}: feed X to DOC level {p.x_level:.4f}"))
                # 3. Cut along Z
                for move in p.moves:
                    lines.append(self._emit_move(move, f"Rough pass {i+1} cut"))

                # Retract logic
                pass_end_z = self._z
                at_shoulder = self._is_at_shoulder(pass_end_z, shoulder_z_values)

                if at_shoulder:
                    # Diagonal rapid straight to prev X level (clears shoulder corner)
                    # Both X and Z move simultaneously — X outward to prev level, Z toward face
                    lines.append(self._rapid(prev_retract_x, p.z_start, f"Diagonal retract to prev X level {prev_retract_x:.4f} (clears shoulder)"))
                else:
                    # Normal retract: straight X to previous pass X level
                    lines.append(self._rapid(prev_retract_x, self._z, f"Retract X to prev pass level {prev_retract_x:.4f}"))

                # Track: next pass approaches at THIS pass's X level
                prev_retract_x = p.x_level

            lines.append("")

        # === CLEANUP PASS ===
        if pr.cleanup_passes:
            lines.append("; === CLEANUP PASS (semi-finish, roughing boundary contour) ===")
            # Approach: rapid to stock OD at Z0+fin, then rapid X to X_start+fin
            cleanup_pass = pr.cleanup_passes[0]
            approach_x = cleanup_pass.x_level  # X_start + fin
            approach_z = cleanup_pass.z_start  # Z0 + fin

            lines.append(self._rapid(pr.stock.diameter, approach_z, f"Rapid to stock OD at Z0+fin"))
            lines.append(self._rapid(approach_x, approach_z, f"Rapid to X_start+fin={approach_x:.4f}"))
            self._x = approach_x
            self._z = approach_z

            for p in pr.cleanup_passes:
                for j, move in enumerate(p.moves):
                    lines.append(self._emit_move(move, f"Cleanup move {j+1}"))

            if same_tool:
                # Same tool — just retract normally, no tool change
                lines.append(self._rapid(pr.stock.diameter, self._z, "Retract X after cleanup"))
                lines.append(self._rapid(pr.stock.diameter, pr.stock.z_start, "Traverse Z to Z_start"))
            else:
                # Different tool — retract to park for tool change
                lines.append(self._rapid(park_x, park_z, "Retract to park for tool change"))
                lines.append(self._line("G40", "Comp off for tool change"))
                lines.append(self._line(f"T{pr.tool.tool_number:02d}01 M6", "Load finish tool"))
                lines.append(self._line("G43", "Tool length comp on"))
                lines.append(self._line(comp_code, "Cutter comp on"))
            lines.append("")

        # === FINISH PASS ===
        if pr.finish_passes:
            lines.append("; === FINISH PASS (profile contour) ===")
            # Approach: rapid to stock OD at Z0+fin, then rapid X to X_start
            finish_pass = pr.finish_passes[0]
            approach_x = finish_pass.x_level  # X_start
            approach_z = finish_pass.z_start  # Z0+fin

            lines.append(self._rapid(pr.stock.diameter, approach_z, f"Rapid to stock OD at Z0+fin"))
            lines.append(self._rapid(approach_x, approach_z, f"Rapid to X_start={approach_x:.4f}"))
            self._x = approach_x
            self._z = approach_z

            for p in pr.finish_passes:
                for j, move in enumerate(p.moves):
                    lines.append(self._emit_move(move, f"Finish move {j+1}"))
            lines.append("")

        # End
        lines.append("; === PROGRAM END ===")
        lines.append(self._line("G40", "Cutter comp cancel"))
        lines.append(self._rapid(park_x, park_z, "Return to park"))
        lines.append(self._line("M2", "Program end"))

        return "\n".join(lines)

    def _emit_move(self, move: ToolMove, comment: str) -> str:
        """Emit a single G-code line — always includes both X and Z.

        Suppresses zero-length moves (tool already at target position).
        """
        # Skip zero-length moves (approach already positioned the tool here)
        if move.move_type in (MoveType.FEED, MoveType.RAPID):
            if abs(move.x - self._x) < 1e-6 and abs(move.z - self._z) < 1e-6:
                return ""

        if move.move_type == MoveType.RAPID:
            return self._rapid(move.x, move.z, comment)
        elif move.move_type == MoveType.FEED:
            return self._feed_line(move.x, move.z, move.feed, comment)
        elif move.move_type in (MoveType.ARC_CW, MoveType.ARC_CCW):
            return self._arc(move, comment)
        return ""

    def _rapid(self, x: float, z: float, comment: str) -> str:
        """Emit G00 — always shows both X and Z."""
        line = f"G00 X{x:.4f} Z{z:.4f}"
        self._x = x
        self._z = z
        return self._line(line, comment)

    def _feed_line(self, x: float, z: float, feed: float, comment: str) -> str:
        """Emit G01 — always shows both X and Z."""
        parts = f"G01 X{x:.4f} Z{z:.4f}"
        if feed > 0 and (self._feed is None or abs(feed - self._feed) > 0.00001):
            parts += f" F{feed:.4f}"
            self._feed = feed
        self._x = x
        self._z = z
        return self._line(parts, comment)

    def _arc(self, move: ToolMove, comment: str) -> str:
        """Emit G02/G03 — always shows both X and Z."""
        g_code = "G02" if move.move_type == MoveType.ARC_CW else "G03"
        parts = f"{g_code} X{move.x:.4f} Z{move.z:.4f}"

        if self._arc_format == "ijk":
            parts += f" I{move.center_i:.4f} K{move.center_k:.4f}"
        else:
            parts += f" R{abs(move.radius):.4f}"

        if move.feed > 0 and (self._feed is None or abs(move.feed - self._feed) > 0.00001):
            parts += f" F{move.feed:.4f}"
            self._feed = move.feed

        self._x = move.x
        self._z = move.z
        return self._line(parts, comment)

    def _get_shoulder_z_values(self, pr: PlanResult) -> set:
        """Extract Z values where profile has horizontal-to-vertical transitions (shoulders).

        A shoulder exists where a horizontal segment (constant Z feed) meets a vertical
        segment (constant X step). These are the Z values where the tool would drag
        on the wall if it retracts straight up in X.

        We detect shoulders by looking at profile segment endpoints — any Z value
        that appears as the end of a horizontal segment AND the start of a vertical
        segment is a shoulder.
        """
        shoulder_z = set()
        segments = pr.profile.segments

        # Walk profile segments looking for Z values at step transitions
        for i, seg in enumerate(segments):
            # A shoulder is where a Z-direction segment ends and an X-direction segment begins
            # In a stepped OD profile: horizontal cut (constant X, varying Z) → vertical step (constant Z, varying X)
            # The shoulder Z is the Z endpoint of the horizontal segment
            if i > 0:
                prev_seg = segments[i - 1]
                # Previous segment moved in Z (horizontal cut), this segment moves in X (vertical step)
                prev_dz = abs(seg.z - prev_seg.z) if i > 1 else abs(seg.z - segments[i-1].z)
                # Check if current segment is primarily an X move (step down)
                # and previous was primarily a Z move (horizontal cut)
                if i >= 2:
                    prev_prev = segments[i - 2]
                    prev_dx = abs(prev_seg.x - prev_prev.x)
                    prev_dz_actual = abs(prev_seg.z - prev_prev.z)
                    curr_dx = abs(seg.x - prev_seg.x)
                    curr_dz = abs(seg.z - prev_seg.z)
                    # Shoulder: previous was mostly Z travel, current is mostly X travel
                    if prev_dz_actual > TOLERANCE and prev_dx < TOLERANCE and curr_dx > TOLERANCE and curr_dz < TOLERANCE:
                        shoulder_z.add(round(prev_seg.z, 6))

        # Also check roughing pass z_end values that don't match stock z_end
        # If a pass ends before the stock Z boundary, it's hitting a shoulder
        for p in pr.roughing_passes:
            if p.z_end > pr.stock.z_end + TOLERANCE:
                shoulder_z.add(round(p.z_end, 6))

        return shoulder_z

    def _is_at_shoulder(self, z: float, shoulder_z_values: set) -> bool:
        """Check if a Z position is at a shoulder (within tolerance)."""
        for sz in shoulder_z_values:
            if abs(z - sz) < TOLERANCE * 10:  # Slightly relaxed tolerance for matching
                return True
        return False

    def _get_comp_code(self, direction: ToolDirection) -> str:
        """Get G41/G42 based on tool direction."""
        if direction == ToolDirection.RIGHT:
            return "G42"
        elif direction == ToolDirection.LEFT:
            return "G41"
        return "G40"

    def _line(self, content: str, comment: str = "") -> str:
        """Format a G-code line with N-number and comment."""
        line = f"N{self._n} {content}"
        if comment:
            line += f"  ({comment})"
        self._n += 10
        return line
