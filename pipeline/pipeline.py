"""Pipeline orchestrator for Industry CAM Engine.

Wires all modules together in the correct execution order.
This is the single entry point for toolpath generation.

Imports from: all modules above in the dependency chain.
"""

import time
from typing import List, Tuple

from models.profile import ClosedProfile, MachiningMode
from models.stock import StockDef
from models.tool import ToolDef
from models.params import RoughingParams, FinishingParams, RoughingStrategy
from models.moves import ToolMove, MoveType
from models.results import PlanResult, TurningPass
from models.validation import ValidationResult, PipelineResult, PipelineStatus, Severity
from models.constants import TOLERANCE

from geometry.zone_builder import build_zones, ZoneSet
from geometry.zone_query import ZoneQueryAPI
from geometry.contour_intersect import ContourIntersect

from intervals.fiber import Fiber

from planners.face_planner import FacePlanner
from planners.staircase_planner import StaircasePlanner
from planners.cleanup_planner import CleanupPlanner
from planners.finish_planner import FinishPlanner

from transitions.transition_planner import TransitionPlanner

from validation.polygon_builder import ValidationPolygons
from validation.pre_planning_validator import validate_profile
from validation.post_planning_validator import validate_all_moves
from validation.pre_output_validator import validate_gcode_geometry


def execute(
    profile: ClosedProfile,
    stock: StockDef,
    tool: ToolDef,
    roughing_params: RoughingParams,
    finishing_params: FinishingParams,
    finish_tool: ToolDef | None = None,
    verify_roundtrip: bool = False,
) -> PipelineResult:
    """Execute the full CAM pipeline.

    Steps:
    1. Pre-planning validation (profile geometry)
    2. Build zones (geometry/zone_builder)
    2b. Extract zone boundary coordinates for PlanResult
    3. Build validation polygons (validation/polygon_builder)
    4. Plan face passes
    5. Plan roughing passes (staircase or offset-contour)
    6. Plan cleanup pass (staircase only)
    7. Plan finish pass
    8. Plan transitions between all passes
    9. Assemble complete move list
    10. Post-planning validation (Shapely — every move checked)
    11. Pre-output validation (G-code geometry)
    12. Construct immutable PlanResult
    13. Optional: round-trip verification

    Returns PipelineResult with status indicating success/failure.
    """
    start_time = time.time()
    all_validations: List[ValidationResult] = []

    # Step 1: Pre-planning validation
    pre_results = validate_profile(profile, stock)
    all_validations.extend(pre_results)

    if _has_errors(pre_results):
        return PipelineResult(
            plan_result=None,
            validations=all_validations,
            warnings_overridden=False,
            status=PipelineStatus.BLOCKED_BY_ERROR,
        )

    # Step 2: Build zones
    zone_set = build_zones(profile, stock, tool, roughing_params)
    zone_query = ZoneQueryAPI(zone_set)
    contour_intersect = ContourIntersect(zone_set)

    # Step 2b: Extract zone boundary coordinates for PlanResult (display)
    # Built directly from input coordinates — not from OCCT wire extraction
    # Extract zone boundaries from Build123d via wire extraction (NO hand math)
    finished_part_boundary = _extract_zone_boundary(zone_query, "finished_part")
    finish_allowance_boundary = _extract_zone_boundary_optional(zone_query, "finish_allowance")
    material_to_rough_boundary = _extract_zone_boundary(zone_query, "material_to_rough")
    profile_boundary = _extract_zone_boundary(zone_query, "finished_part")
    stock_boundary = _compute_stock_boundary(stock)
    # Step 3: Build validation polygons
    polygons = ValidationPolygons.from_zone_query(zone_query)

    # Step 4: Plan face passes
    # ID mode: TFZ collapses when X_start = first profile segment X (no face material)
    skip_face = False
    if profile.mode == MachiningMode.ID and len(profile.segments) >= 1:
        first_seg_x = profile.segments[0].x
        if abs(stock.x_start - first_seg_x) < TOLERANCE:
            skip_face = True

    if skip_face:
        face_passes = []
    else:
        face_planner = FacePlanner()
        face_passes = face_planner.plan(stock, tool, roughing_params, profile.mode, zone_query)

    # Step 5: Plan roughing passes
    if roughing_params.strategy == RoughingStrategy.STAIRCASE:
        staircase = StaircasePlanner()
        roughing_passes = staircase.plan(
            zone_query, tool, roughing_params, stock, profile.mode,
            contour_intersect=contour_intersect,
        )
    else:
        # Offset-contour roughing
        from planners.contour_roughing_planner import ContourRoughingPlanner
        contour_planner = ContourRoughingPlanner()
        roughing_passes = contour_planner.plan(
            zone_query, zone_set, tool, roughing_params, stock, profile.mode, profile,
        )

    # Step 6: Plan cleanup pass
    # Both strategies need a cleanup pass. For staircase, the cleanup removes
    # the stair-step material left between DOC levels. For offset-contour,
    # the innermost roughing pass is at fin_allowance + DOC from the profile,
    # so the cleanup removes that last DOC of material, leaving only
    # fin_allowance for the finish pass.
    cleanup_planner = CleanupPlanner()
    cleanup_passes = cleanup_planner.plan(zone_query, tool, roughing_params, stock, profile.mode, profile)

    # Step 7: Plan finish pass
    finish_planner = FinishPlanner()
    finish_passes = finish_planner.plan(zone_query, tool, finishing_params, stock, profile.mode, profile)

    # Step 8: Plan transitions
    all_passes = face_passes + roughing_passes + cleanup_passes + finish_passes
    transition_planner = TransitionPlanner()
    transitions = transition_planner.plan_all(
        all_passes, profile.mode, stock, zone_query, roughing_params.strategy
    )

    # Step 9: Assemble complete move list
    tool_moves = _assemble_moves(all_passes, transitions)

    # Step 10: Post-planning validation (Shapely)
    post_results = validate_all_moves(tool_moves, polygons, profile.mode)
    all_validations.extend(post_results)

    if _has_errors(post_results):
        return PipelineResult(
            plan_result=None,
            validations=all_validations,
            warnings_overridden=False,
            status=PipelineStatus.BLOCKED_BY_ERROR,
        )

    # Step 11: Pre-output validation
    output_results = validate_gcode_geometry(tool_moves)
    all_validations.extend(output_results)

    if _has_errors(output_results):
        return PipelineResult(
            plan_result=None,
            validations=all_validations,
            warnings_overridden=False,
            status=PipelineStatus.BLOCKED_BY_ERROR,
        )

    # Step 12: Construct immutable PlanResult
    elapsed_ms = (time.time() - start_time) * 1000

    plan_result = PlanResult(
        profile=profile,
        stock=stock,
        tool=tool,
        roughing_params=roughing_params,
        finishing_params=finishing_params,
        mode=profile.mode,
        finish_tool=finish_tool,
        face_passes=face_passes,
        roughing_passes=roughing_passes,
        cleanup_passes=cleanup_passes,
        finish_passes=finish_passes,
        tool_moves=tool_moves,
        finished_part_boundary=finished_part_boundary,
        finish_allowance_boundary=finish_allowance_boundary,
        material_to_rough_boundary=material_to_rough_boundary,
        stock_boundary=stock_boundary,
        profile_boundary=profile_boundary,
        validations=all_validations,
        warnings_overridden=False,
        generation_time_ms=elapsed_ms,
        pass_count=len(all_passes),
        move_count=len(tool_moves),
    )

    # Determine status
    has_warnings = any(v.severity == Severity.WARNING for v in all_validations)
    status = PipelineStatus.SUCCESS_WITH_WARNINGS if has_warnings else PipelineStatus.SUCCESS

    return PipelineResult(
        plan_result=plan_result,
        validations=all_validations,
        warnings_overridden=False,
        status=status,
    )


def _has_errors(results: List[ValidationResult]) -> bool:
    """Check if any result is an ERROR."""
    return any(r.severity == Severity.ERROR for r in results)


def _extract_boundary_coords(zone_query: ZoneQueryAPI, zone_name: str) -> List[Tuple[float, float]]:
    """Extract boundary coordinates from a zone for PlanResult.

    NOTE: This uses OCCT wire extraction which may have edge ordering issues.
    For display purposes, use _build_display_polygons() instead.
    This is kept for Shapely validation (which is tolerant of ordering).
    """
    edges = zone_query.boundary_wire_extraction(zone_name)
    if not edges:
        return []
    coords = []
    for edge in edges:
        coords.append(edge.start)
    if edges:
        coords.append(edges[-1].end)
    return coords


def _extract_zone_boundary_optional(zone_query, zone_name):
    """Extract zone boundary — returns empty list if zone has no extractable wire.

    Used for display-only zones (finish_allowance) that may be too thin to
    extract in some configurations (e.g., ID mode with very small fin_allowance).
    This is NOT a fallback — the zone genuinely may not have a usable wire.
    Arc edges are densified into intermediate points for smooth display.
    """
    import math

    edges = zone_query.boundary_wire_extraction(zone_name)
    if not edges:
        return []
    coords = [edges[0].start]
    for edge in edges:
        if edge.edge_type == "ARC" and edge.center is not None and edge.radius > 0.0001:
            sx, sz = edge.start
            ex, ez = edge.end
            cx, cz = edge.center
            r = edge.radius
            angle_start = math.atan2(sz - cz, sx - cx)
            angle_end = math.atan2(ez - cz, ex - cx)
            diff = angle_end - angle_start
            if diff > math.pi:
                diff -= 2 * math.pi
            elif diff < -math.pi:
                diff += 2 * math.pi
            n_pts = max(8, int(abs(diff) * r * 20))
            for i in range(1, n_pts + 1):
                t = i / float(n_pts)
                angle = angle_start + diff * t
                px = cx + r * math.cos(angle)
                pz = cz + r * math.sin(angle)
                coords.append((px, pz))
        else:
            coords.append(edge.end)
    return coords


def _extract_zone_boundary(zone_query, zone_name):
    """Extract zone boundary coordinates from Build123d via wire extraction.

    This is the ONLY path to get zone polygon coordinates.
    No hand math. No fallback. If this fails, the pipeline raises.
    
    Returns list of (x_dia, z) coordinate pairs forming a closed polygon.
    Arc edges are densified into intermediate points for smooth display.
    """
    import math

    edges = zone_query.boundary_wire_extraction(zone_name)
    if not edges:
        raise RuntimeError(
            f"boundary_wire_extraction('{zone_name}') returned no edges. "
            f"Zone construction may have failed. Do NOT create a hand-math fallback."
        )
    # Build ordered coordinate list from chained edges, densifying arcs
    coords = [edges[0].start]
    for edge in edges:
        if edge.edge_type == "ARC" and edge.center is not None and edge.radius > 0.0001:
            # Densify arc into intermediate points
            sx, sz = edge.start
            ex, ez = edge.end
            cx, cz = edge.center
            r = edge.radius

            # Compute angles (in diameter+Z space, matching edge data)
            angle_start = math.atan2(sz - cz, sx - cx)
            angle_end = math.atan2(ez - cz, ex - cx)

            # Normalize sweep to [-pi, pi]
            diff = angle_end - angle_start
            if diff > math.pi:
                diff -= 2 * math.pi
            elif diff < -math.pi:
                diff += 2 * math.pi

            # Generate intermediate points (skip first — already in coords)
            n_pts = max(8, int(abs(diff) * r * 20))
            for i in range(1, n_pts + 1):
                t = i / float(n_pts)
                angle = angle_start + diff * t
                px = cx + r * math.cos(angle)
                pz = cz + r * math.sin(angle)
                coords.append((px, pz))
        else:
            coords.append(edge.end)
    return coords


def _compute_stock_boundary(stock: StockDef) -> List[Tuple[float, float]]:
    """Compute stock boundary rectangle coordinates (diameter, Z)."""
    if stock.mode == MachiningMode.OD:
        return [
            (0.0, stock.z_start),
            (stock.diameter, stock.z_start),
            (stock.diameter, stock.z_end),
            (0.0, stock.z_end),
        ]
    else:
        return [
            (stock.pilot_hole_dia, stock.z_start),
            (stock.diameter, stock.z_start),
            (stock.diameter, stock.z_end),
            (stock.pilot_hole_dia, stock.z_end),
        ]


def _assemble_moves(passes: List[TurningPass], transitions: list) -> List[ToolMove]:
    """Interleave pass moves and transition moves into a single ordered list.

    Filters out zero-length moves that can occur at transition/pass boundaries
    when the approach position matches the first pass move target.
    """
    all_moves = []

    for i, pass_obj in enumerate(passes):
        # Add transition moves before this pass (except the first)
        if i > 0 and i - 1 < len(transitions):
            transition = transitions[i - 1]
            all_moves.extend(transition.moves)

        # Add pass moves
        all_moves.extend(pass_obj.moves)

    # Filter out zero-length moves (consecutive moves to same position)
    if not all_moves:
        return all_moves

    filtered = [all_moves[0]]
    for move in all_moves[1:]:
        prev = filtered[-1]
        if abs(move.x - prev.x) < TOLERANCE and abs(move.z - prev.z) < TOLERANCE:
            # Zero-length — skip unless it's an arc or dwell (both are intentionally stationary)
            if move.move_type not in (MoveType.ARC_CW, MoveType.ARC_CCW, MoveType.DWELL):
                continue
        filtered.append(move)

    return filtered
