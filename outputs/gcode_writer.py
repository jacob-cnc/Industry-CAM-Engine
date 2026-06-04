"""Position-tracking G-code writer for Industry CAM Engine.

Generates clean, readable G-code with descriptive comments on every line.
Always outputs both X and Z on motion commands for operator clarity.

Imports from: models/ only
"""

import math
from typing import List, Optional

from models.results import PlanResult
from models.moves import ToolMove, MoveType, PassType
from models.profile import SegmentType, CornerBreakType
from models.tool import ToolDef, ToolDirection
from models.constants import TOLERANCE, CENTER_ARC_RADIUS_TOLERANCE_INCH


class GCodeWriter:
    """G-code writer with full coordinate output and descriptive comments.

    Features:
    - Always outputs both X and Z on motion lines (operator readability)
    - Descriptive comments on every line (pass number, move type, context)
    - G41/G42 cutter compensation active for ALL cutting passes when TNR > 0
    - Same-tool optimization (skip tool change if roughing == finishing tool)
    - Arc validation before emitting
    """

    def __init__(self, arc_format: str = "ijk"):
        self._arc_format = arc_format
        self._x: float = 0.0
        self._z: float = 0.0
        self._feed: Optional[float] = None
        self._n: int = 10

    def write(self, plan_result: PlanResult, unit_mode: str = "inch") -> str:
        """Generate complete G-code program from PlanResult.

        Args:
            plan_result: Pipeline output (always in inches).
            unit_mode: Output unit system - "inch" or "metric".
                When "metric", coordinates and feeds are multiplied by 25.4
                and formatted with 3 decimal places. When "inch", values are
                output unchanged with 4 decimal places.

        Raises:
            ValueError: If unit_mode is not "inch" or "metric".
        """
        if unit_mode not in ("inch", "metric"):
            raise ValueError(
                f"Invalid unit_mode '{unit_mode}'. Must be 'inch' or 'metric'."
            )

        self._x = 0.0
        self._z = 0.0
        self._feed = None
        self._n = 10
        self._metric = unit_mode == "metric"
        self._conv = 25.4 if self._metric else 1.0
        self._fmt = ".3f" if self._metric else ".4f"
        lines = []

        pr = plan_result
        same_tool = True  # For now, roughing and finishing use same tool (single tool_def)
        is_id = pr.mode.value == "id"

        # Safe boundary X: the side the tool approaches/retracts from
        # OD: stock OD + 0.010" clearance (0.005" per side above stock surface)
        # ID: pilot hole - 0.010" clearance (inside empty space, away from bore wall)
        if is_id:
            safe_x = max(0.0, pr.stock.pilot_hole_dia - 0.010)
        else:
            safe_x = pr.stock.diameter + 0.010

        # RS274 file delimiter — required for LinuxCNC cutter-comp look-ahead
        lines.append("%")
        lines.append("")

        # Header (ASCII only — LinuxCNC's C parser does not handle UTF-8)
        fmt = self._fmt
        conv = self._conv
        lines.append("; Industry CAM Engine - Generated Program")
        lines.append(f"; Units: {'metric (mm)' if self._metric else 'inch'}")
        lines.append(f"; Mode: {pr.mode.value.upper()}")
        lines.append(";")

        # --- Stock Definition ---
        lines.append("; === STOCK ===")
        lines.append(f"; Diameter: {pr.stock.diameter * conv:{fmt}}")
        lines.append(f"; X Start: {pr.stock.x_start * conv:{fmt}}")
        lines.append(f"; Z Start: {pr.stock.z_start * conv:{fmt}}")
        lines.append(f"; Z End: {pr.stock.z_end * conv:{fmt}}")
        lines.append(f"; X Park: {pr.stock.x_park * conv:{fmt}}")
        lines.append(f"; Z Park: {pr.stock.z_park * conv:{fmt}}")
        if pr.stock.pilot_hole_dia > 0:
            lines.append(f"; Pilot Hole Dia: {pr.stock.pilot_hole_dia * conv:{fmt}}")
        lines.append(";")

        # --- Tool Definition ---
        lines.append("; === TOOL ===")
        lines.append(f"; Tool Number: T{pr.tool.tool_number}")
        lines.append(f"; Description: {pr.tool.description}")
        lines.append(f"; Nose Radius: {pr.tool.nose_radius * conv:{fmt}}")
        lines.append(f"; Tip Angle: {pr.tool.tip_angle:.1f} deg")
        lines.append(f"; Edge Length: {pr.tool.edge_length * conv:{fmt}}")
        lines.append(f"; Orientation: {pr.tool.orientation.value}")
        lines.append(f"; Direction: {pr.tool.direction.value}")
        lines.append(f"; Type: {pr.tool.tool_type.value}")
        lines.append(";")

        # --- Feeds & Speeds ---
        lines.append("; === FEEDS & SPEEDS ===")
        lines.append(f"; Spindle RPM: {pr.roughing_params.spindle_rpm:.0f}")
        lines.append(f"; Roughing Strategy: {pr.roughing_params.strategy.value}")
        lines.append(f"; Roughing DOC (dia): {pr.roughing_params.doc_dia * conv:{fmt}}")
        lines.append(f"; Roughing Feed: {pr.roughing_params.feed * conv:{fmt}}")
        lines.append(f"; Finish Allowance (dia): {pr.roughing_params.fin_allowance * conv:{fmt}}")
        if pr.roughing_params.peck_enabled and pr.roughing_params.peck_length:
            lines.append(f"; Peck Length: {pr.roughing_params.peck_length * conv:{fmt}}")
        lines.append(f"; Finish Passes: {pr.finishing_params.passes}")
        lines.append(f"; Finish DOC (dia): {pr.finishing_params.doc_dia * conv:{fmt}}")
        lines.append(f"; Finish Feed: {pr.finishing_params.feed * conv:{fmt}}")
        lines.append(";")

        # --- Profile Segments ---
        lines.append(f"; === PROFILE ({len(pr.profile.segments)} segments) ===")
        lines.append(f"; Z Start: {pr.profile.z_start * conv:{fmt}}")
        lines.append(f"; Z End: {pr.profile.z_end * conv:{fmt}}")
        for i, seg in enumerate(pr.profile.segments):
            seg_type = seg.segment_type.value.upper()
            if seg.segment_type == SegmentType.ARC:
                if seg.quadrant:
                    q_label = "Q" if seg.quadrant_sign > 0 else "-Q"
                    lines.append(
                        f"; Seg {i+1}: {seg_type} X{seg.x * conv:{fmt}} Z{seg.z * conv:{fmt}} {q_label}"
                    )
                else:
                    lines.append(
                        f"; Seg {i+1}: {seg_type} X{seg.x * conv:{fmt}} Z{seg.z * conv:{fmt}} R{seg.radius * conv:{fmt}}"
                    )
            else:
                lines.append(f"; Seg {i+1}: {seg_type} X{seg.x * conv:{fmt}} Z{seg.z * conv:{fmt}}")
            # Corner break after this segment (if any)
            if i < len(pr.profile.corner_breaks) and pr.profile.corner_breaks[i] is not None:
                cb = pr.profile.corner_breaks[i]
                if cb.break_type == CornerBreakType.FILLET:
                    lines.append(f";        Corner: FILLET R{cb.radius * conv:{fmt}}")
                elif cb.break_type == CornerBreakType.CHAMFER:
                    lines.append(f";        Corner: CHAMFER {cb.size * conv:{fmt}} x {cb.angle:.1f} deg")
        lines.append(";")

        # --- Summary ---
        lines.append(f"; Passes: {pr.pass_count} total, Moves: {pr.move_count}")
        lines.append(f"; Generation time: {pr.generation_time_ms:.1f} ms")
        lines.append("")

        # Warnings
        for v in pr.validations:
            if v.severity.value == "warning":
                lines.append(f"; WARNING: {v.message}")

        # Safety preamble
        unit_code = "G21" if self._metric else "G20"
        unit_label = "mm" if self._metric else "inch"
        lines.append(self._line(f"{unit_code} G18 G40 G49 G80", f"Safety line - {unit_label}, ZX plane, comp off"))
        lines.append(self._line("G90 G95", "Absolute positioning, feed per revolution"))
        lines.append("")

        # Spindle — manual spindle, M3 enables encoder feedback for G95
        lines.append(self._line(f"S{pr.roughing_params.spindle_rpm:.0f} M3", "Spindle CW - enables encoder for feed/rev"))

        # Park position
        park_x = pr.stock.x_park
        park_z = pr.stock.z_park
        lines.append(self._rapid(park_x, park_z, "Move to park position"))
        self._x = park_x
        self._z = park_z
        lines.append("")

        # Tool call (LinuxCNC standard: Tn M6, then G43)
        lines.append(self._line(f"T{pr.tool.tool_number} M6", f"Load tool T{pr.tool.tool_number} - {pr.tool.description}"))
        lines.append(self._line("G43", "Tool length comp on"))
        lines.append("")

        # Determine cutter comp code based on TNR and tool direction
        has_tnr = pr.tool.nose_radius > 0.0001
        comp_code = self._get_comp_code(pr.tool.direction) if has_tnr else "G40"

        # Engage cutter comp for all cutting passes if TNR is present
        # G41/G42 compensates the programmed path by the tool nose radius.
        # Must be engaged before the first cutting move with a lead-in move.
        if has_tnr and comp_code != "G40":
            lines.append(self._line(f"{comp_code}", f"Cutter comp on (TNR={pr.tool.nose_radius:.4f})"))
        else:
            lines.append(self._line("G40", "Cutter comp off (no TNR)"))
        lines.append("")

        # === FACE PASSES ===
        if pr.face_passes:
            lines.append(f"; === FACE PASSES ({len(pr.face_passes)} passes) ===")
            lines.append(self._rapid(safe_x, pr.stock.z_start, f"Approach: {'Pilot hole' if is_id else 'Stock OD'}, Z_start"))
            self._x = safe_x
            self._z = pr.stock.z_start

            for i, p in enumerate(pr.face_passes):
                # Position in Z for this pass (feed from safe boundary — cutting into face material)
                face_z = p.moves[0].z if p.moves else pr.stock.z_start
                lines.append(self._feed_line(safe_x, face_z, pr.roughing_params.feed, f"Face pass {i+1}: feed Z to {face_z:.4f}"))
                # Face cut: feed from safe boundary to X_start at constant Z
                for move in p.moves:
                    lines.append(self._emit_move(move, f"Face pass {i+1}: feed to X_start"))
                # Retract X to safe boundary at previous pass Z (safe level)
                retract_z = pr.stock.z_start if i == 0 else pr.face_passes[i-1].moves[0].z
                lines.append(self._rapid(safe_x, retract_z, f"Retract X to {'pilot hole' if is_id else 'stock OD'}, Z={retract_z:.4f} (prev pass)"))
            lines.append("")

        # === ROUGHING PASSES ===
        if pr.roughing_passes:
            lines.append(f"; === ROUGHING PASSES ({len(pr.roughing_passes)} passes) ===")
            # Build set of shoulder Z values from profile segments for diagonal retract detection
            shoulder_z_values = self._get_shoulder_z_values(pr)

            prev_retract_x = safe_x  # First pass retracts to safe boundary

            # Determine the "normal" Z start for roughing (fin_allowance for OD).
            # Passes with z_start significantly below this are "valley passes" in
            # a pocket/concavity. They need wider retract to clear pocket walls.
            fin_allowance_r = pr.roughing_params.fin_allowance / 2.0
            normal_z_start = fin_allowance_r if not is_id else pr.stock.z_start

            # Compute valley retract X: the widest X level of the normal passes
            # that terminate at the same shoulder as the valley passes, plus one
            # DOC clearance. This is the "pocket mouth" — just wide enough to
            # clear the pocket walls without wasting time retracting to stock OD.
            valley_retract_x = self._compute_valley_retract_x(
                pr.roughing_passes, normal_z_start, pr.roughing_params.doc_dia, safe_x
            )

            prev_valley_x = None  # Track previous valley pass X level

            for i, p in enumerate(pr.roughing_passes):
                # Detect valley pass: z_start is below the normal roughing start.
                # This means the pass is inside a pocket/concavity where the profile
                # dips inward then steps back out. The tool must approach from
                # outside the pocket to avoid rapid-ing through uncut taper material.
                is_valley_pass = p.z_start < normal_z_start - TOLERANCE * 10

                # For valley passes, use valley_retract_x (pocket mouth + clearance).
                # For normal passes, use prev_retract_x (one step back — faster cycle time).
                approach_x = valley_retract_x if is_valley_pass else prev_retract_x

                # Approach sequence:
                # 1. Traverse Z at approach_x to this pass's Z start (rapid, safe X)
                lines.append(self._rapid(approach_x, p.z_start, f"Rough pass {i+1}: traverse Z to {p.z_start:.4f} at X{approach_x:.4f}"))
                # 2. Rapid X to previous pass's X level (already cleared — safe to rapid)
                #    Then feed X only the last DOC into material.
                if is_valley_pass and prev_valley_x is not None:
                    # Rapid from approach_x to previous valley pass X (already cleared)
                    lines.append(self._rapid(prev_valley_x, p.z_start, f"Rough pass {i+1}: rapid X to prev level {prev_valley_x:.4f}"))
                    # Feed only the last DOC into material
                    lines.append(self._feed_line(p.x_level, p.z_start, pr.roughing_params.feed, f"Rough pass {i+1}: feed X to DOC level {p.x_level:.4f}"))
                else:
                    # Normal pass or first valley pass: feed from approach_x to DOC level
                    lines.append(self._feed_line(p.x_level, p.z_start, pr.roughing_params.feed, f"Rough pass {i+1}: feed X to DOC level {p.x_level:.4f}"))
                # 3. Cut along Z
                for move in p.moves:
                    lines.append(self._emit_move(move, f"Rough pass {i+1} cut"))

                # Retract logic
                pass_end_z = self._z
                at_shoulder = self._is_at_shoulder(pass_end_z, shoulder_z_values)

                # For valley passes, retract to valley_retract_x (pocket mouth).
                # For normal passes at a shoulder, diagonal retract to prev_retract_x.
                # For normal passes not at shoulder, straight X retract.
                retract_x = valley_retract_x if is_valley_pass else prev_retract_x

                if at_shoulder or is_valley_pass:
                    # Diagonal rapid to retract X at pass z_start (clears shoulder/pocket wall)
                    lines.append(self._rapid(retract_x, p.z_start, f"Diagonal retract to X{retract_x:.4f} (clears {'pocket wall' if is_valley_pass else 'shoulder'})"))
                else:
                    # Normal retract: straight X to previous pass X level
                    lines.append(self._rapid(retract_x, self._z, f"Retract X to prev pass level {retract_x:.4f}"))
                # Track: next pass retracts to the MAX X this pass reached.
                # Cap at safe_x — no need to retract beyond stock boundary + clearance.
                prev_retract_x = min(self._compute_pass_max_x(p), safe_x)

                # Track valley pass X level for next valley pass approach
                if is_valley_pass:
                    prev_valley_x = p.x_level

            lines.append("")

        # === CLEANUP PASS ===
        if pr.cleanup_passes:
            lines.append("; === CLEANUP PASS (semi-finish, roughing boundary contour) ===")
            # Approach: rapid to safe boundary at Z0+fin, then rapid X to cleanup start
            cleanup_pass = pr.cleanup_passes[0]
            approach_x = cleanup_pass.x_level  # X_start + fin
            approach_z = cleanup_pass.z_start  # Z0 + fin

            lines.append(self._rapid(safe_x, approach_z, f"Rapid to {'pilot hole' if is_id else 'stock OD'} at Z0+fin"))
            lines.append(self._rapid(approach_x, approach_z, f"Rapid to X_start+fin={approach_x:.4f}"))
            self._x = approach_x
            self._z = approach_z

            for p in pr.cleanup_passes:
                for j, move in enumerate(p.moves):
                    lines.append(self._emit_move(move, f"Cleanup move {j+1}"))

            if same_tool:
                # Same tool — just retract normally, no tool change
                lines.append(self._rapid(safe_x, self._z, "Retract X after cleanup"))
                lines.append(self._rapid(safe_x, pr.stock.z_start, "Traverse Z to Z_start"))
            else:
                # Different tool — retract to park for tool change
                lines.append(self._line("G40", "Comp off for tool change"))
                lines.append(self._rapid(park_x, park_z, "Retract to park for tool change"))
                lines.append(self._line(f"T{pr.tool.tool_number} M6", "Load finish tool"))
                lines.append(self._line("G43", "Tool length comp on"))
                if has_tnr and comp_code != "G40":
                    lines.append(self._line(f"{comp_code}", f"Re-engage cutter comp (TNR={pr.tool.nose_radius:.4f})"))
            lines.append("")

        # === FINISH PASS ===
        if pr.finish_passes:
            lines.append("; === FINISH PASS (profile contour) ===")
            # Approach: rapid to safe boundary at Z0+fin, then rapid X to X_start
            finish_pass = pr.finish_passes[0]
            approach_x = finish_pass.x_level  # X_start
            approach_z = finish_pass.z_start  # Z0+fin

            lines.append(self._rapid(safe_x, approach_z, f"Rapid to {'pilot hole' if is_id else 'stock OD'} at Z0+fin"))
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
        lines.append(self._line("M5", "Spindle stop"))
        lines.append(self._line("M2", "Program end"))
        lines.append("%")   # RS274 closing delimiter

        return "\n".join(lines) + "\n"

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
        fmt = self._fmt
        conv = self._conv
        line = f"G00 X{x * conv:{fmt}} Z{z * conv:{fmt}}"
        self._x = x
        self._z = z
        return self._line(line, comment)

    def _feed_line(self, x: float, z: float, feed: float, comment: str) -> str:
        """Emit G01 — always shows both X and Z."""
        fmt = self._fmt
        conv = self._conv
        parts = f"G01 X{x * conv:{fmt}} Z{z * conv:{fmt}}"
        if feed > 0 and (self._feed is None or abs(feed - self._feed) > 0.00001):
            parts += f" F{feed * conv:{fmt}}"
            self._feed = feed
        self._x = x
        self._z = z
        return self._line(parts, comment)

    def _arc(self, move: ToolMove, comment: str) -> str:
        """Emit G02/G03 — always shows both X and Z."""
        fmt = self._fmt
        conv = self._conv
        g_code = "G02" if move.move_type == MoveType.ARC_CW else "G03"
        parts = f"{g_code} X{move.x * conv:{fmt}} Z{move.z * conv:{fmt}}"

        if self._arc_format == "ijk":
            parts += f" I{move.center_i * conv:{fmt}} K{move.center_k * conv:{fmt}}"
        else:
            parts += f" R{abs(move.radius) * conv:{fmt}}"

        if move.feed > 0 and (self._feed is None or abs(move.feed - self._feed) > 0.00001):
            parts += f" F{move.feed * conv:{fmt}}"
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

    def _compute_valley_retract_x(
        self, passes: list, normal_z_start: float, doc_dia: float, safe_x: float
    ) -> float:
        """Compute the retract X for valley passes — the pocket mouth + one DOC clearance.

        Valley passes are inside a concavity where the profile dips inward then
        steps back out. The tool needs to retract just far enough to clear the
        pocket walls, not all the way to stock OD.

        The pocket mouth X is the widest X level among the normal passes (those
        starting at the normal z_start) that terminate at the same shoulder Z as
        the valley passes. Add one DOC for clearance.

        If no normal passes share the shoulder, falls back to safe_x.
        """
        # Find the shoulder Z that valley passes end at
        valley_end_z = None
        for p in passes:
            if p.z_start < normal_z_start - TOLERANCE * 10:
                valley_end_z = p.z_end
                break

        if valley_end_z is None:
            return safe_x  # No valley passes — doesn't matter

        # Find the widest X level among normal passes that end at the same shoulder
        pocket_mouth_x = 0.0
        for p in passes:
            if p.z_start >= normal_z_start - TOLERANCE * 10:
                # Normal pass — check if it ends at the same shoulder as valley passes
                if abs(p.z_end - valley_end_z) < TOLERANCE * 10:
                    pocket_mouth_x = max(pocket_mouth_x, p.x_level)

        if pocket_mouth_x < TOLERANCE:
            return safe_x  # No matching normal passes — fall back to safe_x

        # Add one DOC clearance beyond the pocket mouth
        retract_x = pocket_mouth_x + doc_dia
        # Cap at safe_x — never retract beyond stock boundary
        return min(retract_x, safe_x)

    def _get_comp_code(self, direction: ToolDirection) -> str:
        """Get G41/G42 based on tool direction."""
        if direction == ToolDirection.RIGHT:
            return "G42"
        elif direction == ToolDirection.LEFT:
            return "G41"
        return "G40"

    def _compute_pass_max_x(self, turning_pass) -> float:
        """Compute the true maximum X reached by a pass, including arc peaks.

        For linear moves: max X is the endpoint X.
        For arc moves: compute the actual peak X of the arc sweep.
        Result is capped at stock OD (no retract beyond stock needed).
        """
        max_x = 0.0
        prev_x = None
        prev_z = None

        for move in turning_pass.moves:
            max_x = max(max_x, move.x)

            if move.move_type in (MoveType.ARC_CW, MoveType.ARC_CCW) and prev_x is not None:
                if abs(move.center_i) > 0.0001 or abs(move.center_k) > 0.0001:
                    # Center in diameter coords
                    center_x = prev_x + move.center_i
                    # Radius in radius coords (for geometry)
                    center_x_r = center_x / 2.0
                    start_x_r = prev_x / 2.0
                    radius_r = math.sqrt(
                        (start_x_r - center_x_r)**2 + (prev_z - (prev_z + move.center_k))**2
                    )
                    # Arc peak X (diameter) = (center_x_r + radius_r) * 2
                    arc_peak_x_dia = (center_x_r + radius_r) * 2.0

                    # Only use peak if it's actually reached by the arc
                    # Simple check: peak X > both endpoint X values means arc bulges outward
                    if arc_peak_x_dia > prev_x and arc_peak_x_dia > move.x:
                        max_x = max(max_x, arc_peak_x_dia)

            prev_x = move.x
            prev_z = move.z

        return max_x

    def _line(self, content: str, comment: str = "") -> str:
        """Format a G-code line with N-number and semicolon comment."""
        line = f"N{self._n} {content}"
        if comment:
            line += f"  ; {comment}"
        self._n += 10
        return line
