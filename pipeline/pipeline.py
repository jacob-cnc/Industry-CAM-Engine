"""Pipeline orchestrator for Industry CAM Engine.

Wires all modules together in the correct execution order.
This is the single entry point for toolpath generation.

Imports from: all modules above in the dependency chain.
"""

import time
from dataclasses import replace
from typing import List, Tuple

from models.profile import ClosedProfile, MachiningMode
from models.stock import StockDef
from models.tool import ToolDef
from models.params import RoughingParams, FinishingParams, RoughingStrategy
from models.moves import ToolMove, MoveType, PassType
from models.results import PlanResult, TurningPass
from models.validation import ValidationResult, PipelineResult, PipelineStatus, Severity
from models.constants import TOLERANCE

from geometry.kernel_offset import record_join_fallbacks
from geometry.zone_builder import build_zones
from geometry.zone_query import ZoneQueryAPI
from geometry.contour_intersect import ContourIntersect


from planners.face_planner import FacePlanner
from planners.staircase_planner import StaircasePlanner
from planners.cleanup_planner import CleanupPlanner
from planners.finish_planner import FinishPlanner

from transitions.transition_planner import TransitionPlanner

from validation.nose_clearance import NoseClearance
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
    """Execute the full CAM pipeline (see _execute for the steps).

    Any sharp-join offset the kernel could only build with rounded joins
    during the run is reported to the operator as one WARNING (F4,
    owner 2026-11-12) instead of only a log line.
    """
    with record_join_fallbacks() as fallbacks:
        result = _execute(profile, stock, tool, roughing_params, finishing_params,
                          finish_tool, verify_roundtrip)
    return _with_join_fallback_note(result, fallbacks)


def _with_join_fallback_note(result: PipelineResult, fallbacks: List[str]) -> PipelineResult:
    """The result with one WARNING naming the offsets that used rounded joins."""
    if not fallbacks:
        return result
    kinds = sorted({w.split(" by ")[0] for w in fallbacks})
    note = ValidationResult(
        severity=Severity.WARNING, category="geometry",
        message=(f"The geometry kernel could not keep sharp corners on {len(fallbacks)} "
                 f"offset(s) ({', '.join(kinds)}) and used rounded corners there."),
        recommendation="Nothing to change unless sharp corners on those paths matter; "
                       "check the preview at convex corners.",
        consequence="At those convex corners the path stays exactly the offset distance "
                    "from the part (an arc) instead of running out to a sharp point. "
                    "No gouge; the part shape itself is unchanged.",
    )
    validations = list(result.validations) + [note]
    plan_result = result.plan_result
    if plan_result is not None:
        plan_result = replace(plan_result, validations=validations)
    status = (PipelineStatus.SUCCESS_WITH_WARNINGS
              if result.status == PipelineStatus.SUCCESS else result.status)
    return replace(result, plan_result=plan_result, validations=validations, status=status)


def _execute(
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
    finishing_params = replace(finishing_params, doc_dia=FinishingParams.doc_from_allowance(
        roughing_params.fin_allowance, finishing_params.passes))
    start_time = time.time()
    all_validations: List[ValidationResult] = []

    # Arcs that are two pieces (same-X arcs, arcs past their own X extreme) are
    # split here, so every later step sees <= one-quadrant entry arcs
    # (geometry/arc_entry.py). Idempotent: profile_from_fields already did it.
    from geometry.arc_entry import normalize_profile
    profile = normalize_profile(profile)

    # Step 1: Pre-planning validation
    pre_results = validate_profile(profile, stock)
    # Tool reach (geometry/tool_reach.py): what the insert can't reach is LEFT
    # UNCUT (owner decision 2026-11-11). The contour is replaced by the one the
    # tool can follow, each uncut region is reported as a warning with its X/Z
    # range and the inserts that would reach it, and planning runs unchanged on
    # that contour. Roughing and finishing tools both cut to it. Anything still
    # out of reach afterwards is an error (safety net).
    from geometry.tool_reach import make_reachable, reach_messages
    reach_tools = [tool] + ([finish_tool] if finish_tool is not None and finish_tool != tool else [])
    for rt in reach_tools:
        profile, uncut = make_reachable(profile, rt)
        for reg in uncut:
            pre_results.append(ValidationResult(
                severity=Severity.WARNING, category="tool_reach",
                message=reg.message,
                recommendation="Cut the uncut region in its own block with a tool that reaches it.",
                location=reg.line_from,
                outline=reg.outline,
            ))
        for msg in reach_messages(profile, rt):
            pre_results.append(ValidationResult(
                severity=Severity.ERROR, category="tool_reach", message=msg,
                recommendation="Cut this part of the contour in its own block with a tool "
                               "that reaches it, or change the contour.",
            ))
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
            nose_clearance=NoseClearance.build(zone_query, tool),
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
    finish_passes = finish_planner.plan(zone_query, finish_tool or tool, finishing_params, stock, profile.mode, profile, roughing_params.fin_allowance)

    # Step 8: Plan transitions
    all_passes = face_passes + roughing_passes + cleanup_passes + finish_passes
    transition_planner = TransitionPlanner()
    transitions = transition_planner.plan_all(
        all_passes, profile.mode, stock, zone_query, roughing_params.strategy
    )

    # Persist contour exits and incoming finish links so output uses validated
    # motion, including the final contour's exit before travel to park.
    for index, pass_obj in enumerate(all_passes):
        if pass_obj.pass_type in (PassType.CLEANUP, PassType.FINISH):
            pass_obj = replace(pass_obj, retract_moves=tuple(
                transition_planner.contour_retract(pass_obj, profile.mode, stock)))
            if pass_obj.pass_type == PassType.FINISH and index > 0:
                pass_obj = replace(pass_obj, approach_moves=tuple(transitions[index - 1].moves))
            all_passes[index] = pass_obj
    all_passes = _plan_comp_contours(all_passes, profile, stock, tool, finish_tool or tool,
                                     zone_query)
    cleanup_passes = [p for p in all_passes if p.pass_type == PassType.CLEANUP]
    finish_passes = [p for p in all_passes if p.pass_type == PassType.FINISH]

    # Step 9: Assemble complete move list
    tool_moves = _assemble_moves(all_passes, transitions)
    if all_passes and all_passes[-1].pass_type in (PassType.CLEANUP, PassType.FINISH):
        tool_moves.extend(all_passes[-1].retract_moves)

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
    """Zone boundary polyline, or [] if the zone has no extractable wire.

    For display-only zones (finish_allowance) that may be too thin to extract
    in some configurations (e.g. ID with a very small fin_allowance). This is
    NOT a fallback - the zone genuinely may not have a usable wire.
    Arcs are sampled on the kernel's arc (geometry.zone_query.boundary_polyline).
    """
    from geometry.zone_query import boundary_polyline
    return boundary_polyline(zone_query.boundary_wire_extraction(zone_name))


def _extract_zone_boundary(zone_query, zone_name):
    """Zone boundary as (x_dia, z) points from the kernel's wire (closed polygon).

    The ONLY path to zone polygon coordinates: no hand math, no fallback - if
    the kernel gives no edges, the pipeline raises. Arcs are sampled ON the
    kernel's arc (geometry.zone_query.boundary_polyline; until 2026-11-12 this
    function densified arcs itself and put points up to .118 in off an R.25 arc).
    """
    from geometry.zone_query import boundary_polyline
    edges = zone_query.boundary_wire_extraction(zone_name)
    if not edges:
        raise RuntimeError(
            f"boundary_wire_extraction('{zone_name}') returned no edges. "
            f"Zone construction may have failed. Do NOT create a hand-math fallback."
        )
    return boundary_polyline(edges)


def _plan_comp_contours(all_passes, profile, stock, tool, finish_tool, zone_query):
    """Every cleanup / finish pass with its cutter-comp plan
    (planners/comp_contour.py): entry, contour, lead-out, as the writer will
    emit them. Each pass starts where the writer is when it reaches it: the
    first cleanup / finish pass at its planned approach point (x_level,
    z_start), a later cleanup pass where the previous one ended (its lead-out
    end, if any), a later finish pass at the end of its planned link."""
    from planners.comp_contour import plan_comp_contour
    is_id = profile.mode == MachiningMode.ID
    face_at_z0 = bool(getattr(stock, "face_at_z0", False))

    def part_contains(p):
        return zone_query.contains("finished_part", p[0], p[1])

    def stock_contains(p):
        return zone_query.contains("stock", p[0], p[1])

    out = list(all_passes)
    cleanups = [i for i, p in enumerate(out) if p.pass_type == PassType.CLEANUP]
    finishes = [i for i, p in enumerate(out) if p.pass_type == PassType.FINISH]
    end = None
    for n, i in enumerate(cleanups):
        p = out[i]
        start = (out[cleanups[0]].x_level, out[cleanups[0]].z_start) if n == 0 else end
        plan = plan_comp_contour(p.moves, start, tool, is_id, stock.z_start, face_at_z0,
                                 "Cleanup move", part_contains, stock_contains)
        out[i] = replace(p, comp_contour=plan)
        end = _comp_contour_end(plan)
    for n, i in enumerate(finishes):
        p = out[i]
        if n == 0:
            start = (p.x_level, p.z_start)
        elif p.approach_moves:
            start = (p.approach_moves[-1].x, p.approach_moves[-1].z)
        else:
            continue                  # the writer refuses a finish pass without its link
        label = ("Spring pass (repeat final contour)" if p.is_spring_pass
                 else f"Finish cutting pass {n + 1}")
        plan = plan_comp_contour(p.moves, start, finish_tool, is_id, stock.z_start, face_at_z0,
                                 f"{label}: move", part_contains, stock_contains)
        out[i] = replace(p, comp_contour=plan)
    return out


def _comp_contour_end(plan):
    """Where the tool is after a planned comp contour (lead-out end if any)."""
    if plan.lead_out is not None:
        return plan.lead_out
    if plan.contour:
        return (plan.contour[-1].x, plan.contour[-1].z)
    return plan.start


def _compute_stock_boundary(stock: StockDef) -> List[Tuple[float, float]]:
    """Compute stock boundary rectangle coordinates (diameter, Z)."""
    if stock.mode == MachiningMode.OD:
        return [
            (0.0, stock.z_start),
            (stock.diameter, stock.z_start),
            (stock.diameter, stock.physical_z_end),
            (0.0, stock.physical_z_end),
        ]
    else:
        return [
            (stock.pilot_hole_dia, stock.z_start),
            (stock.diameter, stock.z_start),
            (stock.diameter, stock.physical_z_end),
            (stock.pilot_hole_dia, stock.physical_z_end),
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
            # Zero-length — skip unless it's a dwell (intentionally stationary).
            # Arcs below tolerance are dropped too: a turned profile never
            # contains a full circle, and sub-tolerance arcs are kernel noise
            # (e.g. the rounded join a fallback offset puts at a corner-break
            # kink), which would otherwise fail pre-output validation.
            if move.move_type != MoveType.DWELL:
                continue
        filtered.append(move)

    return filtered
