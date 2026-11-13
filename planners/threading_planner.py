"""Threading planner (owner plan 2026-11-12, docs/handoffs/2026-11-12-threading-workflow-plan.md).

Field-driven threads: X start / X end (nominal major), Z start / Z end (Z end =
where the tool pulls out), pitch, passes, spring passes, starts, entry angle.
The depth comes from the standard / class (models/thread_data.py) as the
params' root offset.

    straight  -> LinuxCNC G76 (verified with rs274: tests/unit/test_g76_threading.py)
    taper     -> one G33 per pass (LinuxCNC's G76 cannot taper), with the same
                 pass depths, compound shift and spring passes as G76 makes

Retract (owner 2026-11-12): external max(X start, X end) + .020 (dia),
internal pilot - .005 (dia) - between passes and at the end, straight out in
X at Z end, then along Z.

Imports from: models/
"""

import math
from typing import List

from models.moves import MoveType, PassType, ToolMove
from models.program import ThreadingParams
from models.results import ThreadPass, ThreadPlan
from models.thread_data import FORMS, basic_depth

OD_RETRACT_DIA = 0.020          # above the nominal major (owner)
ID_RETRACT_DIA = 0.005          # below the pilot (owner)
SYNC_SPEED_MARGIN = 0.9         # Z speed headroom for spindle-speed variation
MAX_TAPER_DEG = 45.0
TOOL_ANGLE_TOLERANCE_DEG = 1.0


def first_cut_dia(depth_dia: float, passes: int, degression: float) -> float:
    """G76 J (diameter): K / N^(1/R), rounded UP to the program's .0001 with a
    small cushion - J is printed to 4 places, and a J rounded down makes
    LinuxCNC add a sliver pass beyond the N the user asked for."""
    n_passes = max(1, int(passes))
    r = degression if degression > 0 else 2.0
    return math.ceil(depth_dia / n_passes ** (1.0 / r) * 1e4 + 0.3) / 1e4


def pass_depths(depth: float, passes: int, degression: float) -> List[float]:
    """Radial depth of each cutting pass, as LinuxCNC's G76 makes them:
    d_n = J x n^(1/R) with J from first_cut_dia (so pass N reaches K), the
    last one clipped to K."""
    r = degression if degression > 0 else 2.0
    first = first_cut_dia(2.0 * depth, passes, r) / 2.0
    out = []
    n = 1
    while True:
        d = first * n ** (1.0 / r)
        if d >= depth - 1e-9:
            out.append(depth)
            return out
        out.append(d)
        n += 1


class ThreadingPlanner:
    """Plan a threading operation; never emits G-code (outputs/gcode_writer.py does)."""

    def plan_thread(self, params: ThreadingParams, z_max_velocity: float = 0.75,
                    z_max_accel: float = 2.0, tool=None) -> ThreadPlan:
        errors, warnings = [], []
        p = params
        internal = p.is_internal
        form_depth = basic_depth(p.form, p.pitch, internal) if p.form in FORMS else 0.0
        crest = (p.crest_at(p.x_start, form_depth), p.crest_at(p.x_end, form_depth))
        root = (p.root_at(p.x_start), p.root_at(p.x_end))
        depth = abs(root[0] - crest[0]) / 2.0
        starts = max(1, int(p.num_starts))
        lead = p.pitch * starts
        if internal:
            retract = p.pilot_dia - ID_RETRACT_DIA
        else:
            retract = max(p.x_start, p.x_end) + OD_RETRACT_DIA

        # --- checks (plan section 5) ---
        if p.pitch <= 0:
            errors.append("Thread pitch must be positive.")
        if p.num_passes < 1:
            errors.append("Number of passes must be at least 1.")
        if p.end_z >= p.start_z:
            errors.append(f"Z end ({p.end_z:.4f}) must be behind Z start ({p.start_z:.4f}): threads "
                          f"are cut toward the chuck (left-hand threads are not supported).")
        if internal:
            if p.pilot_dia <= 0:
                errors.append("Internal thread: enter the pilot (tap drill) diameter.")
            elif min(root) <= p.pilot_dia + 1e-9:
                errors.append(f"Internal thread: the pilot ({p.pilot_dia:.4f}) is not below the "
                              f"thread's major ({min(root):.4f}).")
        elif min(root) <= 0:
            errors.append("External thread: the root diameter would be below zero.")
        if depth <= 0 and not errors:
            errors.append("The thread has no depth (crest = root).")
        dz = abs(p.start_z - p.end_z)
        if p.is_taper and dz > 0:
            half_angle = math.degrees(math.atan2(abs(p.x_end - p.x_start) / 2.0, dz))
            if half_angle > MAX_TAPER_DEG:
                errors.append(f"Taper of {half_angle:.1f} deg is steeper than {MAX_TAPER_DEG:.0f} deg "
                              f"(G33 with the lead along X is not supported).")
        z_speed = lead * p.spindle_rpm / 60.0
        usable = SYNC_SPEED_MARGIN * z_max_velocity
        if z_speed > usable + 1e-12:
            max_rpm = int(usable * 60.0 / lead) if lead > 0 else 0
            errors.append(f"{p.spindle_rpm:.0f} RPM x lead {lead:.4f} needs Z at {z_speed:.3f} in/s; "
                          f"the Z limit (with {100 - SYNC_SPEED_MARGIN * 100:.0f}% margin) is "
                          f"{usable:.3f} in/s - use {max_rpm} RPM or less.")
        lead_in = z_speed ** 2 / (2.0 * z_max_accel) if z_max_accel > 0 else 0.0
        if 0.0 <= p.start_z < lead_in:
            warnings.append(f"Z start {p.start_z:.4f} is less than the {lead_in:.4f} lead-in Z needs "
                            f"to reach thread speed at {p.spindle_rpm:.0f} RPM (assuming the thread "
                            f"starts at the Z0 face).")
        if tool is not None and p.form in FORMS:
            want = FORMS[p.form][0]
            angle = float(getattr(tool, "tip_angle", want) or want)
            if abs(angle - want) > TOOL_ANGLE_TOLERANCE_DEG:
                warnings.append(f"T{tool.tool_number}'s {angle:g} deg insert does not match the "
                                f"{want:g} deg thread form.")
        if internal and not p.is_taper and not errors:
            # G76 retracts between passes up to the full depth past the drive line
            if retract - 2.0 * depth <= 0:
                errors.append(f"The bore is too small: G76 retracts to {retract - 2 * depth:.4f} "
                              f"between passes (below the centreline).")

        z_starts = tuple(p.start_z - k * p.pitch for k in range(starts))
        if errors:
            return ThreadPlan("g76" if not p.is_taper else "g33", retract, lead, z_starts, p.end_z,
                              crest, root, depth, errors=tuple(errors), warnings=tuple(warnings))

        if not p.is_taper:
            sign = 1.0 if internal else -1.0
            depth_dia = 2.0 * depth
            first_dia = first_cut_dia(depth_dia, p.num_passes, p.degression)
            g76 = {
                "P": lead, "Z": p.end_z,
                "I": crest[0] - retract,                      # crest from the drive line
                "J": first_dia, "K": depth_dia,
                "R": p.degression, "Q": p.entry_angle, "H": int(p.spring_passes),
                "E": 0.0, "L": 0,
                "X_drive": retract,
            }
            return ThreadPlan("g76", retract, lead, z_starts, p.end_z, crest, root, depth, g76=g76,
                              warnings=tuple(warnings))

        # --- taper: G33 passes ---
        slope = (p.x_end - p.x_start) / (p.end_z - p.start_z)          # dia per Z
        tan_q = math.tan(math.radians(p.entry_angle))
        sign = 1.0 if internal else -1.0                                 # into the material
        depths = pass_depths(depth, p.num_passes, p.degression)
        depths += [depth] * max(0, int(p.spring_passes))
        all_starts = []
        for z0 in z_starts:
            passes = []
            for d in depths:
                zs = z0 - d * tan_q
                xs = crest[0] + slope * (zs - p.start_z) + sign * 2.0 * d
                xe = crest[1] + sign * 2.0 * d
                passes.append(ThreadPass(xs, zs, xe, p.end_z))
            all_starts.append(tuple(passes))
        # A shallow pass that lies inside the retract X (internal: inside the
        # pilot hole; external: above major + .020) is in air - the moves to and
        # from the retract X stay out of the material, so it needs no check.
        return ThreadPlan("g33", retract, lead, z_starts, p.end_z, crest, root, depth,
                          passes=tuple(all_starts), warnings=tuple(warnings))

    def plan(self, params: ThreadingParams, z_max_velocity: float = 0.75) -> List[ToolMove]:
        """Moves for the graph: approach, the thread at full depth, retract."""
        tp = self.plan_thread(params, z_max_velocity)
        r = tp.retract_x
        z0, z1 = params.start_z, params.end_z
        return [
            ToolMove(MoveType.RAPID, r, z0, pass_type=PassType.THREADING),
            ToolMove(MoveType.RAPID, tp.root[0], z0, pass_type=PassType.THREADING),
            ToolMove(MoveType.FEED, tp.root[1], z1, feed=params.pitch, pass_type=PassType.THREADING),
            ToolMove(MoveType.RAPID, r, z1, pass_type=PassType.THREADING),
            ToolMove(MoveType.RAPID, r, z0, pass_type=PassType.THREADING),
        ]
