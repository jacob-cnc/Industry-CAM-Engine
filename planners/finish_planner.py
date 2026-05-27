"""Finish planner for Industry CAM Engine.

Plans the finish pass that traces the exact profile boundary.
The finish pass removes the fin_allowance left by roughing/cleanup.

The finish tool approaches from (X_start, Z_start) and traces the entire
profile contour — including face segments if defined.

IMPORTANT: Only traces the USER'S profile segments — NOT the closure segments.
Closure segments go through the finished part and must never be cut.

Imports from: models/
"""

from typing import List, TYPE_CHECKING

from models.results import TurningPass
from models.moves import ToolMove, MoveType, PassType
from models.tool import ToolDef
from models.params import FinishingParams
from models.stock import StockDef
from models.profile import ClosedProfile, ProfileMove, SegmentType, MachiningMode

if TYPE_CHECKING:
    from geometry.zone_query import ZoneQueryAPI


class FinishPlanner:
    """Plans the finish pass following the profile boundary exactly.

    The finish pass traces the user's profile segments ONLY (not closure).
    G41/G42 cutter compensation is active — coordinates are programmed to the
    exact profile, LinuxCNC offsets by TNR at runtime.
    """

    def plan(
        self,
        zone_query: 'ZoneQueryAPI',
        tool: ToolDef,
        finishing_params: FinishingParams,
        stock: StockDef,
        mode: MachiningMode,
        profile: ClosedProfile = None,
    ) -> List[TurningPass]:
        """Generate finish pass following the profile segments.

        Approach: rapid to (X_start, Z0+fin), feed to (X_start, Z0),
        then trace the full profile contour from segment[0] to segment[-1].

        Args:
            zone_query: ZoneQueryAPI (not used directly — profile comes from ClosedProfile)
            tool: Tool definition (finish tool)
            finishing_params: Finish parameters
            stock: Stock definition
            mode: OD or ID
            profile: The user's ClosedProfile (segments only, no closure)

        Returns:
            List containing one TurningPass (the finish contour pass).
        """
        if profile is None:
            return []

        segments = profile.segments
        if len(segments) < 2:
            return []

        # Z start for finish pass approach:
        # OD: Z0+fin (face passes cleared above this)
        # ID with no TFZ (X_start = first segment X): Z_start
        # ID with TFZ (X_start > first segment X): Z0+fin
        from models.constants import TOLERANCE
        import math

        if mode == MachiningMode.ID and abs(stock.x_start - segments[0].x) < TOLERANCE:
            approach_z = stock.z_start
        else:
            approach_z = 0.001  # fin_clearance (Z0+fin)

        # Build moves: first feed from approach to profile start, then trace ALL segments
        moves = []

        # First move: feed from (X_start, approach_z) to profile start (segment[0])
        first_seg = segments[0]
        moves.append(ToolMove(
            move_type=MoveType.FEED,
            x=first_seg.x,
            z=first_seg.z,
            feed=finishing_params.feed,
            pass_type=PassType.FINISH,
            pass_index=0,
        ))

        # Then trace from segment[0] to each subsequent segment endpoint
        prev_x_dia = segments[0].x
        prev_z = segments[0].z

        for i in range(1, len(segments)):
            seg = segments[i]

            if seg.segment_type == SegmentType.ARC and seg.radius != 0.0:
                if seg.radius > 0:
                    move_type = MoveType.ARC_CW
                else:
                    move_type = MoveType.ARC_CCW

                # Compute arc center from endpoints and radius
                center = self._find_arc_center(
                    prev_x_dia / 2.0, prev_z,
                    seg.x / 2.0, seg.z,
                    abs(seg.radius),
                    seg.radius < 0,
                )

                if center is not None:
                    center_x_r, center_z = center
                    center_i = (center_x_r - prev_x_dia / 2.0) * 2.0
                    center_k = center_z - prev_z
                else:
                    center_i = 0.0
                    center_k = 0.0

                moves.append(ToolMove(
                    move_type=move_type,
                    x=seg.x,
                    z=seg.z,
                    feed=finishing_params.feed,
                    radius=seg.radius,
                    center_i=center_i,
                    center_k=center_k,
                    pass_type=PassType.FINISH,
                    pass_index=0,
                ))
            else:
                moves.append(ToolMove(
                    move_type=MoveType.FEED,
                    x=seg.x,
                    z=seg.z,
                    feed=finishing_params.feed,
                    pass_type=PassType.FINISH,
                    pass_index=0,
                ))

            prev_x_dia = seg.x
            prev_z = seg.z

        if not moves:
            return []

        # x_level = X_start (approach X), z_start = approach Z for rapid
        # The G-code writer uses these for the approach sequence
        finish_pass = TurningPass(
            x_level=stock.x_start,
            z_start=approach_z,
            z_end=min(m.z for m in moves),
            pass_index=0,
            pass_type=PassType.FINISH,
            moves=moves,
            swept_region=None,
        )

        return [finish_pass]

    def _find_arc_center(
        self, x1_r: float, z1: float, x2_r: float, z2: float,
        radius: float, is_ccw: bool
    ) -> tuple:
        """Find arc center given two endpoints and radius.

        Uses sweep-direction test to pick the correct center from the two
        candidates. CW/CCW is from the user's screen POV (inverted Y axis:
        X increases downward). In data space, CW on screen = positive cross
        product of (start-center) x (end-center).

        Returns (center_x_radius, center_z) or None if no solution.
        """
        import math

        mx = (x1_r + x2_r) / 2.0
        mz = (z1 + z2) / 2.0

        dx = x2_r - x1_r
        dz = z2 - z1
        d = math.sqrt(dx**2 + dz**2)

        if d < 1e-10:
            return None

        h_sq = radius**2 - (d / 2.0)**2
        if h_sq < 0:
            h_sq = 0
        h = math.sqrt(h_sq)

        px = -dz / d
        pz = dx / d

        # Two candidate centers
        c1_x = mx + h * px
        c1_z = mz + h * pz
        c2_x = mx - h * px
        c2_z = mz - h * pz

        # Pick center based on sweep direction.
        # Graph: horizontal=Z, vertical=X_radius (inverted Y).
        # CW on screen = positive cross product in data space.
        # screen_cross = (x1-cx)*(z2-cz) - (z1-cz)*(x2-cx)
        def _screen_cw(cx, cz):
            cross = (x1_r - cx) * (z2 - cz) - (z1 - cz) * (x2_r - cx)
            return cross > 0

        # is_ccw=True means CCW on screen = NOT screen_cw
        if is_ccw:
            if not _screen_cw(c1_x, c1_z):
                return (c1_x, c1_z)
            else:
                return (c2_x, c2_z)
        else:
            if _screen_cw(c1_x, c1_z):
                return (c1_x, c1_z)
            else:
                return (c2_x, c2_z)
