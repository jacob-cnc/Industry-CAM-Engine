"""Material removal simulation engine.

Pre-computes material states for playback visualization.
Uses Shapely for polygon operations — same parameters as the validator.

Imports from: models/, geometry/ only (no GUI dependencies)
"""

import logging
import math
import time
from dataclasses import dataclass, field
from typing import List, Tuple, Optional
import numpy as np
from shapely.geometry import Polygon, MultiPolygon, GeometryCollection, box
from shapely.ops import unary_union
from shapely.validation import make_valid

logger = logging.getLogger(__name__)

from models.results import PlanResult, TurningPass, SweptRegion
from models.moves import ToolMove, MoveType, PassType
from models.stock import StockDef
from models.profile import MachiningMode
# --- Validator Agreement (Requirements 7.1, 7.2, 7.3, 7.4) ---
# These constants are the SAME ones used by validation/polygon_builder.py,
# ensuring geometric identity between the simulation and the validator:
#   SHAPELY_COS_LIMIT = 0.9999  (adaptive arc densification cosine limit)
#   MAX_DENSIFICATION_DEPTH = 12 (maximum recursion depth)
#   TOLERANCE = 0.0005 inches    (gouge/penetration threshold)
# Coordinate convention: RADIUS for X, INCHES for Z — same as polygon_builder.
# Arc center offsets: center_i is in DIAMETER (÷2 for radius), center_k in INCHES.
from models.constants import SHAPELY_COS_LIMIT, MAX_DENSIFICATION_DEPTH, TOLERANCE
from geometry.adaptive_sampling import adaptive_densify_arc


@dataclass
class PassState:
    """Pre-computed material state after a pass completes."""
    pass_index: int
    pass_type: PassType
    # Exterior ring(s) as coordinate arrays (radius, inches)
    polygons: List[Tuple[np.ndarray, np.ndarray]]  # [(x_arr, z_arr), ...]
    # Move index range this pass covers in tool_moves
    move_start: int
    move_end: int


@dataclass
class MaterialSimData:
    """Complete pre-computed material simulation data."""
    # Initial stock polygon coordinates (radius, inches)
    stock_polygon: Tuple[np.ndarray, np.ndarray]  # (x_arr, z_arr)
    # Ordered sequence of pass states
    pass_states: List[PassState]
    # Per-move material states for smooth interpolation
    # Key: move_index → polygon coordinate arrays
    move_states: dict  # {int: List[Tuple[np.ndarray, np.ndarray]]}
    # Final state (stock minus all passes)
    final_state: List[Tuple[np.ndarray, np.ndarray]]
    # Metadata
    mode: MachiningMode
    total_passes: int
    computation_time_ms: float = 0.0


def compute(plan_result: PlanResult) -> MaterialSimData:
    """Pre-compute all material removal states from a PlanResult.

    Performance budget: < 200ms for profiles with up to 30 passes.

    Iterates all TurningPass objects in order (face → roughing → cleanup → finish),
    computes the SweptRegion polygon for each, and performs sequential
    stock_polygon.difference(swept_region) to produce pass_states.
    """
    start = time.perf_counter()

    # Build the initial stock polygon
    stock_poly = _build_stock_polygon(plan_result.stock, plan_result.mode)
    stock_arrays = _polygon_to_arrays(stock_poly)
    stock_coords = stock_arrays[0] if stock_arrays else (np.array([]), np.array([]))

    # Collect all turning passes in execution order
    all_passes: List[TurningPass] = (
        list(plan_result.face_passes)
        + list(plan_result.roughing_passes)
        + list(plan_result.cleanup_passes)
        + list(plan_result.finish_passes)
    )

    # Sort by pass_index to ensure correct execution order
    all_passes.sort(key=lambda p: p.pass_index)

    total_passes = len(all_passes)

    # Handle zero-pass edge case
    if total_passes == 0:
        computation_time_ms = (time.perf_counter() - start) * 1000.0
        return MaterialSimData(
            stock_polygon=stock_coords,
            pass_states=[],
            move_states={},
            final_state=stock_arrays,
            mode=plan_result.mode,
            total_passes=0,
            computation_time_ms=computation_time_ms,
        )

    # Build a mapping from pass_index → (move_start, move_end) in tool_moves
    pass_move_ranges = _compute_pass_move_ranges(all_passes, plan_result.tool_moves)

    # Get tool nose radius from ToolDef
    tool_tnr = plan_result.tool.nose_radius

    # Sequential subtraction
    current_material = stock_poly
    pass_states: List[PassState] = []

    for turning_pass in all_passes:
        # Compute the swept region polygon for this pass
        swept_region = _compute_swept_region_polygon(
            turning_pass, tool_tnr, plan_result.mode
        )

        # Skip empty swept regions (no material to subtract)
        if swept_region.is_empty:
            logger.warning(
                "Pass %d has empty swept region; material unchanged",
                turning_pass.pass_index,
            )
            # Still record the pass state (material unchanged)
            polygons = _polygon_to_arrays(current_material)
            move_start, move_end = pass_move_ranges.get(
                turning_pass.pass_index, (0, 0)
            )
            pass_states.append(PassState(
                pass_index=turning_pass.pass_index,
                pass_type=turning_pass.pass_type,
                polygons=polygons,
                move_start=move_start,
                move_end=move_end,
            ))
            continue

        # Perform subtraction: current_material minus swept_region
        result = current_material.difference(swept_region)

        # Validate result — apply make_valid if needed
        if not result.is_valid:
            logger.warning(
                "Pass %d subtraction produced invalid polygon; applying make_valid()",
                turning_pass.pass_index,
            )
            result = make_valid(result)

        # Handle GeometryCollection results from make_valid() or difference()
        # Extract all Polygon components and create a MultiPolygon
        if isinstance(result, GeometryCollection) and not isinstance(result, (Polygon, MultiPolygon)):
            polygons_extracted = [
                g for g in result.geoms
                if isinstance(g, Polygon) and not g.is_empty
            ]
            if polygons_extracted:
                if len(polygons_extracted) == 1:
                    result = polygons_extracted[0]
                else:
                    result = MultiPolygon(polygons_extracted)
            else:
                # No polygon components — material fully removed
                logger.warning(
                    "Pass %d: make_valid() returned GeometryCollection with no polygons; "
                    "material fully removed",
                    turning_pass.pass_index,
                )
                result = Polygon()

        # MultiPolygon results are retained as-is — all component polygons
        # represent disconnected material regions and are valid for the next
        # iteration's .difference() call.
        current_material = result

        # Convert to coordinate arrays
        polygons = _polygon_to_arrays(current_material)

        # Get move range for this pass
        move_start, move_end = pass_move_ranges.get(
            turning_pass.pass_index, (0, 0)
        )

        pass_states.append(PassState(
            pass_index=turning_pass.pass_index,
            pass_type=turning_pass.pass_type,
            polygons=polygons,
            move_start=move_start,
            move_end=move_end,
        ))

    # Compute final_state as stock minus union of ALL swept regions (canonical definition)
    # This ensures geometric correctness: final = stock - union(all swept regions)
    all_swept_polygons: List[Polygon] = []
    for turning_pass in all_passes:
        swept = _compute_swept_region_polygon(
            turning_pass, tool_tnr, plan_result.mode
        )
        if not swept.is_empty:
            all_swept_polygons.append(swept)

    if all_swept_polygons:
        all_swept_union = unary_union(all_swept_polygons)
        final_poly = stock_poly.difference(all_swept_union)

        # Apply make_valid if the result is invalid
        if not final_poly.is_valid:
            logger.warning(
                "Final state polygon is invalid; applying make_valid()"
            )
            final_poly = make_valid(final_poly)

        # Handle GeometryCollection results from make_valid or difference
        if isinstance(final_poly, GeometryCollection) and not isinstance(
            final_poly, (Polygon, MultiPolygon)
        ):
            polygons_extracted = [
                g for g in final_poly.geoms
                if isinstance(g, Polygon) and not g.is_empty
            ]
            if polygons_extracted:
                if len(polygons_extracted) == 1:
                    final_poly = polygons_extracted[0]
                else:
                    final_poly = MultiPolygon(polygons_extracted)
            else:
                final_poly = Polygon()

        # Handle empty result (all material removed)
        if final_poly.is_empty:
            final_state: List[Tuple[np.ndarray, np.ndarray]] = []
        else:
            final_state = _polygon_to_arrays(final_poly)
    else:
        # No swept regions produced — final state is stock unchanged
        final_state = stock_arrays

    # Compute per-move material states for smooth interpolation (task 2.3)
    move_states = _compute_per_move_states(
        stock_poly=stock_poly,
        all_passes=all_passes,
        pass_states=pass_states,
        tool_moves=plan_result.tool_moves,
        tool_tnr=tool_tnr,
        mode=plan_result.mode,
    )

    computation_time_ms = (time.perf_counter() - start) * 1000.0

    if computation_time_ms > 200.0:
        logger.warning(
            "Material simulation computation took %.1fms (target < 200ms for ≤30 passes; "
            "total_passes=%d)",
            computation_time_ms,
            total_passes,
        )

    return MaterialSimData(
        stock_polygon=stock_coords,
        pass_states=pass_states,
        move_states=move_states,
        final_state=final_state,
        mode=plan_result.mode,
        total_passes=total_passes,
        computation_time_ms=computation_time_ms,
    )


def _compute_pass_move_ranges(
    all_passes: List[TurningPass],
    tool_moves: List[ToolMove],
) -> dict:
    """Compute move_start and move_end indices for each pass in tool_moves.

    Scans tool_moves to find the first and last index where
    ToolMove.pass_index matches each TurningPass.pass_index.

    Returns:
        Dict mapping pass_index → (move_start, move_end) indices into tool_moves.
    """
    # Build mapping: pass_index → (first_index, last_index)
    ranges: dict = {}

    for i, move in enumerate(tool_moves):
        pi = move.pass_index
        if pi not in ranges:
            ranges[pi] = (i, i)
        else:
            ranges[pi] = (ranges[pi][0], i)

    return ranges


def _compute_per_move_states(
    stock_poly: Polygon,
    all_passes: List[TurningPass],
    pass_states: List[PassState],
    tool_moves: List[ToolMove],
    tool_tnr: float,
    mode: MachiningMode,
) -> dict:
    """Compute per-move material states for smooth intra-pass interpolation.

    For each cutting move (FEED, ARC_CW, ARC_CCW) within a pass, computes
    the partial swept region up to that move's endpoint and subtracts it
    from the previous pass state (or stock if first pass).

    Rapid moves are skipped entirely — no entry in the returned dict.

    MVP approach:
    - Rectangular passes: clip the full swept region box to the Z extent
      traversed so far (box from z_end to current move's Z endpoint).
    - Arc passes: use the full pass swept region (partial arc clipping deferred).

    Args:
        stock_poly: The initial stock Shapely Polygon.
        all_passes: All TurningPass objects in execution order.
        pass_states: Pre-computed PassState list (one per pass).
        tool_moves: Complete ordered tool_moves from PlanResult.
        tool_tnr: Tool nose radius (inches).
        mode: OD or ID machining mode.

    Returns:
        Dict mapping move_index → List[Tuple[np.ndarray, np.ndarray]] coordinate arrays.
    """
    move_states: dict = {}

    # Reconstruct per-pass Shapely polygons for "previous material" tracking.
    # We need the actual Shapely polygon before each pass to subtract from.
    # Recompute by sequential subtraction (same as compute() but we keep the polys).
    prev_materials: List[Polygon] = []
    current_material = stock_poly
    for pass_idx, turning_pass in enumerate(all_passes):
        prev_materials.append(current_material)
        # Compute swept region for this pass
        swept = _compute_swept_region_polygon(turning_pass, tool_tnr, mode)
        if not swept.is_empty:
            result = current_material.difference(swept)
            if not result.is_valid:
                result = make_valid(result)
            current_material = result

    for pass_idx, turning_pass in enumerate(all_passes):
        # Material state BEFORE this pass
        prev_material = prev_materials[pass_idx]

        # Get the pass's swept region info
        region = turning_pass.swept_region
        if region is None:
            continue

        # Get the move range for this pass
        ps = pass_states[pass_idx] if pass_idx < len(pass_states) else None
        if ps is None:
            continue

        move_start = ps.move_start
        move_end = ps.move_end

        # Determine if this is a rectangular or arc pass
        is_rectangular = turning_pass.pass_type in (PassType.FACE, PassType.ROUGH)
        has_arcs = False
        if not is_rectangular:
            has_arcs = any(
                m.move_type in (MoveType.ARC_CW, MoveType.ARC_CCW)
                for m in turning_pass.moves
            )

        # For arc passes, compute the full swept region once (used as fallback)
        if has_arcs:
            full_swept = _compute_arc_swept_band(turning_pass.moves, tool_tnr)
            if full_swept.is_empty:
                full_swept = _build_rectangular_swept_polygon(region)
        else:
            full_swept = _build_rectangular_swept_polygon(region)

        # Rectangular bounds in radius coordinates
        x_min_r = region.x_min / 2.0
        x_max_r = region.x_max / 2.0
        z_start = region.z_start
        z_end = region.z_end

        # For arc passes: build centerline points incrementally to avoid O(n²)
        # recomputation. We accumulate points as we iterate through moves.
        arc_centerline_cache: List[Tuple[float, float]] = []
        arc_prev_x_r: Optional[float] = None
        arc_prev_z: Optional[float] = None

        # Iterate through moves in this pass's range
        for move_idx in range(move_start, move_end + 1):
            if move_idx >= len(tool_moves):
                break

            move = tool_moves[move_idx]

            # Skip rapid moves — no material removal
            if move.move_type == MoveType.RAPID:
                # Track position for arc passes
                if has_arcs:
                    arc_prev_x_r = move.x / 2.0
                    arc_prev_z = move.z
                continue

            # Only process cutting moves (FEED, ARC_CW, ARC_CCW)
            if move.move_type not in (MoveType.FEED, MoveType.ARC_CW, MoveType.ARC_CCW):
                # Track position for arc passes
                if has_arcs:
                    arc_prev_x_r = move.x / 2.0
                    arc_prev_z = move.z
                continue

            # Compute partial swept region up to this move's endpoint
            if is_rectangular or not has_arcs:
                if turning_pass.pass_type == PassType.FACE:
                    # Face pass: tool moves in X (from OD toward centerline),
                    # clip by X extent traversed so far
                    current_x_r = move.x / 2.0
                    # Tool moves from x_max_r (OD) toward x_min_r (centerline).
                    # Partial box spans from current X position to x_max_r (OD),
                    # representing material already traversed.
                    partial_x_min = current_x_r
                    partial_x_max = x_max_r

                    # Ensure we don't exceed the full region bounds
                    partial_x_min = max(partial_x_min, x_min_r)
                    partial_x_min = min(partial_x_min, x_max_r)

                    if partial_x_min >= partial_x_max or z_end >= z_start:
                        # Degenerate partial region (tool at OD, no X traversal yet)
                        # Skip — no meaningful partial removal to show
                        continue
                    else:
                        partial_swept = box(partial_x_min, z_end, partial_x_max, z_start)
                else:
                    # Roughing pass: tool moves in -Z, clip to Z extent traversed so far
                    # The current move's Z endpoint defines how far we've cut
                    current_z = move.z

                    # Build partial box from current_z to z_start
                    # z_start is the higher Z (toward face), z_end is lower Z
                    # As tool moves from z_start toward z_end, partial region grows
                    partial_z_min = min(current_z, z_start)
                    partial_z_max = max(current_z, z_start)

                    # Ensure we don't exceed the full region bounds
                    partial_z_min = max(partial_z_min, z_end)
                    partial_z_max = min(partial_z_max, z_start)

                    if partial_z_min >= partial_z_max or x_min_r >= x_max_r:
                        # Degenerate partial region — use full swept region
                        partial_swept = full_swept
                    else:
                        partial_swept = box(x_min_r, partial_z_min, x_max_r, partial_z_max)
            else:
                # Arc passes: compute cumulative swept band incrementally
                curr_x_r = move.x / 2.0
                curr_z = move.z

                # Initialize start position if needed
                if arc_prev_x_r is None:
                    # Look for a preceding move in the pass to get start position
                    for prev_idx in range(move_idx - 1, move_start - 1, -1):
                        if prev_idx < len(tool_moves):
                            arc_prev_x_r = tool_moves[prev_idx].x / 2.0
                            arc_prev_z = tool_moves[prev_idx].z
                            break
                    if arc_prev_x_r is None:
                        arc_prev_x_r = curr_x_r
                        arc_prev_z = curr_z

                # Add start point if centerline cache is empty
                if not arc_centerline_cache:
                    arc_centerline_cache.append((arc_prev_x_r, arc_prev_z))

                # Append points for this move to the cumulative centerline
                if move.move_type == MoveType.FEED:
                    arc_centerline_cache.append((curr_x_r, curr_z))
                elif move.move_type in (MoveType.ARC_CW, MoveType.ARC_CCW):
                    # Densify the arc into points
                    center_i_r = move.center_i / 2.0  # diameter → radius
                    center_k = move.center_k           # already inches

                    center_x = arc_prev_x_r + center_i_r
                    center_z = arc_prev_z + center_k

                    dx = arc_prev_x_r - center_x
                    dz = arc_prev_z - center_z
                    arc_radius = math.sqrt(dx * dx + dz * dz)

                    if arc_radius < 1e-9:
                        # Zero-radius arc — treat as linear
                        arc_centerline_cache.append((curr_x_r, curr_z))
                    else:
                        arc_points = adaptive_densify_arc(
                            start=(arc_prev_x_r, arc_prev_z),
                            end=(curr_x_r, curr_z),
                            center=(center_x, center_z),
                            radius=arc_radius,
                            cos_limit=SHAPELY_COS_LIMIT,
                            max_depth=MAX_DENSIFICATION_DEPTH,
                        )
                        # Skip the first point (already in centerline cache)
                        arc_centerline_cache.extend(arc_points[1:])

                # Update previous position for next iteration
                arc_prev_x_r = curr_x_r
                arc_prev_z = curr_z

                # Compute the partial swept band from accumulated centerline
                partial_swept = _compute_band_from_centerline(
                    arc_centerline_cache, tool_tnr
                )

                # If partial band computation fails, fall back to full swept
                if partial_swept.is_empty:
                    partial_swept = full_swept

            # Subtract partial swept region from previous pass material
            if partial_swept.is_empty:
                continue

            result = prev_material.difference(partial_swept)

            # Validate result
            if not result.is_valid:
                result = make_valid(result)

            # Convert to coordinate arrays
            arrays = _polygon_to_arrays(result)
            if arrays:
                move_states[move_idx] = arrays

    return move_states


def _build_stock_polygon(stock: StockDef, mode: MachiningMode) -> Polygon:
    """Construct the initial stock Shapely Polygon.

    OD mode: rectangle from x_start/2 to stock_diameter/2 (radius)
    ID mode: rectangle from pilot_hole_dia/2 to x_start/2 (radius)
    Z range: z_end to z_start

    All X coordinates are in RADIUS. Z in INCHES.
    Uses shapely.geometry.box(xmin, ymin, xmax, ymax) where:
        x-axis = X (radius)
        y-axis = Z (inches)

    Validator agreement (Req 7.2): Same coordinate convention as
    polygon_builder.py — RADIUS for X, INCHES for Z. The polygon_builder
    converts edge.start[0] / 2.0 (diameter → radius) identically to how
    this function converts stock dimensions / 2.0.

    Subtraction direction (verified for Requirements 9.1, 9.2):
        OD: stock outer boundary is at x_max (diameter/2). Swept regions
            remove material from this outer boundary inward toward the
            finished part (smaller X values).
        ID: stock inner bore boundary is at x_min (pilot_hole_dia/2).
            Swept regions remove material from this inner boundary outward
            toward the finished part (larger X values).
    The .difference() operation is direction-agnostic — correctness depends
    on the stock polygon X range being set correctly per mode (done below)
    and the SweptRegion bounds being mode-aware (handled by the planner).
    """
    z_min = stock.z_end
    z_max = stock.z_start

    if mode == MachiningMode.OD:
        # OD: material extends from near-part boundary outward to stock OD
        x_min = stock.x_start / 2.0   # radius (inner, near finished part)
        x_max = stock.diameter / 2.0   # radius (outer stock boundary)
    else:
        # ID: material extends from pilot hole bore inward to x_start
        x_min = stock.pilot_hole_dia / 2.0  # radius (inner bore boundary)
        x_max = stock.x_start / 2.0         # radius (outer, near finished part)

    return box(x_min, z_min, x_max, z_max)


def _compute_swept_region_polygon(
    turning_pass: TurningPass,
    tool_tnr: float,
    mode: MachiningMode,
) -> Polygon:
    """Compute the Shapely Polygon for a pass's swept material envelope.

    - Face/roughing passes: rectangular polygon from pass bounds
    - Cleanup/finish passes with arcs: curved band from TNR offset
      (delegates to _compute_arc_swept_band; falls back to rectangular
       if that returns an empty polygon or for linear-only passes)

    All X coordinates are converted from DIAMETER (SweptRegion convention)
    to RADIUS for the Shapely polygon, matching the validator convention.
    Z coordinates remain in INCHES.

    Mode handling (Requirements 9.1, 9.2):
        The SweptRegion bounds (x_min, x_max, z_start, z_end) are computed
        by the planner and are already mode-aware — OD swept regions cover
        the outer material being removed inward, ID swept regions cover the
        inner bore material being removed outward. This function simply
        converts those bounds to radius coordinates for Shapely; no
        additional mode-specific logic is needed here.

    Args:
        turning_pass: The TurningPass containing moves and swept_region bounds.
        tool_tnr: Tool nose radius (inches).
        mode: OD or ID machining mode.

    Returns:
        A valid Shapely Polygon representing the swept material envelope.
        Returns an empty Polygon if no SweptRegion data is available.
    """
    region = turning_pass.swept_region
    if region is None:
        logger.warning(
            "Pass %d has no SweptRegion data; returning empty polygon",
            turning_pass.pass_index,
        )
        return Polygon()

    # Determine if this is a face/roughing pass (always rectangular)
    if turning_pass.pass_type in (PassType.FACE, PassType.ROUGH):
        poly = _build_rectangular_swept_polygon(region)
    else:
        # Cleanup/finish passes: check for arc moves
        has_arcs = any(
            m.move_type in (MoveType.ARC_CW, MoveType.ARC_CCW)
            for m in turning_pass.moves
        )
        if has_arcs:
            # Delegate to arc swept band computation (task 1.3)
            poly = _compute_arc_swept_band(turning_pass.moves, tool_tnr)
            # Fall back to rectangular if arc computation returns empty
            if poly.is_empty:
                poly = _build_rectangular_swept_polygon(region)
        else:
            # Linear-only cleanup/finish — use rectangular bounds
            poly = _build_rectangular_swept_polygon(region)

    # Validate the polygon; apply make_valid if needed
    if not poly.is_valid:
        logger.warning(
            "SweptRegion polygon for pass %d is invalid; applying make_valid()",
            turning_pass.pass_index,
        )
        poly = make_valid(poly)

    return poly


def _build_rectangular_swept_polygon(region: SweptRegion) -> Polygon:
    """Build a rectangular Shapely Polygon from SweptRegion bounds.

    Converts x_min/x_max from DIAMETER to RADIUS (÷ 2.0).
    Uses shapely.geometry.box(xmin, ymin, xmax, ymax) where:
        x-axis = X (radius)
        y-axis = Z (inches)

    Validator agreement (Req 7.2): Diameter-to-radius conversion (÷2)
    matches polygon_builder._build_polygon() which does edge.start[0] / 2.0.

    Args:
        region: SweptRegion with x_min, x_max in diameter; z_start, z_end in inches.

    Returns:
        A rectangular Shapely Polygon in radius/inches coordinates.
    """
    x_min_radius = region.x_min / 2.0
    x_max_radius = region.x_max / 2.0
    # box(xmin, ymin, xmax, ymax) — Z axis: z_end < z_start
    return box(x_min_radius, region.z_end, x_max_radius, region.z_start)


def _compute_band_from_centerline(
    centerline_points: List[Tuple[float, float]],
    tnr: float,
) -> Polygon:
    """Compute a swept band polygon from accumulated centerline points.

    This is the incremental counterpart to _compute_arc_swept_band(). Instead
    of processing a full list of ToolMove objects, it takes pre-collected
    centerline points (already densified for arcs) and offsets them by TNR
    perpendicular to the local tangent to form the swept band polygon.

    Used by _compute_per_move_states() to build arc swept bands incrementally
    as each cutting move is processed, avoiding O(n²) recomputation.

    Args:
        centerline_points: List of (x_radius, z_inches) points along the
            toolpath centerline, accumulated up to the current move.
        tnr: Tool nose radius (inches).

    Returns:
        A Shapely Polygon representing the swept band, or an empty Polygon
        if fewer than 2 points or computation fails.
    """
    if len(centerline_points) < 2 or tnr <= 0.0:
        return Polygon()

    # Offset the centerline points inward and outward by TNR
    # perpendicular to the local tangent direction
    outer_points: List[Tuple[float, float]] = []
    inner_points: List[Tuple[float, float]] = []

    n = len(centerline_points)
    for idx in range(n):
        # Compute tangent direction at this point
        if idx == 0:
            tx = centerline_points[1][0] - centerline_points[0][0]
            tz = centerline_points[1][1] - centerline_points[0][1]
        elif idx == n - 1:
            tx = centerline_points[n - 1][0] - centerline_points[n - 2][0]
            tz = centerline_points[n - 1][1] - centerline_points[n - 2][1]
        else:
            tx = centerline_points[idx + 1][0] - centerline_points[idx - 1][0]
            tz = centerline_points[idx + 1][1] - centerline_points[idx - 1][1]

        # Normalize tangent
        t_len = math.sqrt(tx * tx + tz * tz)
        if t_len < 1e-12:
            if outer_points:
                outer_points.append(outer_points[-1])
                inner_points.append(inner_points[-1])
            continue

        tx /= t_len
        tz /= t_len

        # Perpendicular (normal) to tangent: rotate 90° CCW → (-tz, tx)
        nx = -tz
        nz = tx

        px = centerline_points[idx][0]
        pz = centerline_points[idx][1]

        outer_points.append((px + tnr * nx, pz + tnr * nz))
        inner_points.append((px - tnr * nx, pz - tnr * nz))

    if len(outer_points) < 2 or len(inner_points) < 2:
        return Polygon()

    # Construct closed polygon: outer forward + inner reversed
    ring = outer_points + list(reversed(inner_points))
    ring.append(ring[0])

    if len(ring) < 4:
        return Polygon()

    poly = Polygon(ring)

    if not poly.is_valid:
        poly = make_valid(poly)
        if isinstance(poly, Polygon):
            pass
        elif isinstance(poly, MultiPolygon):
            if poly.is_empty:
                return Polygon()
            largest = max(poly.geoms, key=lambda g: g.area)
            poly = largest
        else:
            if hasattr(poly, 'geoms'):
                polygons = [g for g in poly.geoms if isinstance(g, Polygon) and not g.is_empty]
                if polygons:
                    poly = max(polygons, key=lambda g: g.area)
                else:
                    return Polygon()
            else:
                return Polygon()

    if poly.is_empty:
        return Polygon()

    return poly


def _compute_arc_swept_band(
    moves: List[ToolMove],
    tnr: float,
) -> Polygon:
    """Compute swept band for arc-containing passes.

    Offsets the toolpath arc inward and outward by TNR perpendicular to
    the arc tangent, then closes the boundary into a polygon.
    Uses adaptive_densify_arc with SHAPELY_COS_LIMIT and MAX_DENSIFICATION_DEPTH.

    Validator agreement (Requirements 7.1, 7.2, 7.3, 7.4):
    - Same SHAPELY_COS_LIMIT (0.9999) and MAX_DENSIFICATION_DEPTH (12) as
      validation/polygon_builder.py → geometric identity guaranteed.
    - Same coordinate convention: RADIUS for X, INCHES for Z.
    - center_i is in DIAMETER (from toolpath planner) → divided by 2 for radius.
    - center_k is in INCHES (from toolpath planner) → used directly.
    - TNR is the same tool.nose_radius used by the planner to generate the path.
    - The resulting swept band must not penetrate finished_part_poly beyond TOLERANCE.

    For each arc move (ARC_CW, ARC_CCW):
    - Compute arc center from previous position + center_i/center_k offsets
    - NOTE: center_i is in DIAMETER — convert to radius (÷ 2.0)
    - center_k is already in inches
    - Densify the arc into points using adaptive_densify_arc
    - Offset each point inward and outward by TNR perpendicular to the tangent

    For linear moves (FEED): offset the line segment by TNR perpendicular.

    The polygon is constructed from outer offset points (forward) concatenated
    with inner offset points (reversed) to form a closed ring.

    Falls back to an empty polygon if no valid geometry can be constructed.

    Args:
        moves: List of ToolMove objects for the pass.
        tnr: Tool nose radius (inches) — same value used by the toolpath planner.

    Returns:
        A Shapely Polygon representing the swept band, or an empty Polygon
        if the computation fails or produces degenerate geometry.
    """
    if not moves or tnr <= 0.0:
        return Polygon()

    # Collect the centerline points from all cutting moves (FEED, ARC_CW, ARC_CCW)
    # We need to track the previous position to compute arc centers
    centerline_points: List[Tuple[float, float]] = []

    # Find the first move's start position by looking at the move before the first
    # cutting move, or use the first cutting move's implied start.
    # The first move's start is the previous move's endpoint.
    # We'll track prev_x (radius), prev_z (inches) as we iterate.
    prev_x_r: Optional[float] = None
    prev_z: Optional[float] = None

    for i, move in enumerate(moves):
        # Current endpoint in radius coordinates
        curr_x_r = move.x / 2.0  # diameter → radius
        curr_z = move.z

        if move.move_type in (MoveType.FEED, MoveType.ARC_CW, MoveType.ARC_CCW):
            # If we don't have a previous position yet, we need to find it
            # from the preceding move in the list (or skip this move)
            if prev_x_r is None:
                # First cutting move — add its start point
                # Look backward for a preceding move to get start position
                if i > 0:
                    prev_x_r = moves[i - 1].x / 2.0
                    prev_z = moves[i - 1].z
                else:
                    # No preceding move — skip, can't determine start
                    prev_x_r = curr_x_r
                    prev_z = curr_z
                    centerline_points.append((curr_x_r, curr_z))
                    continue

            # Add start point if centerline is empty
            if not centerline_points:
                centerline_points.append((prev_x_r, prev_z))

            if move.move_type == MoveType.FEED:
                # Linear move — just add the endpoint
                centerline_points.append((curr_x_r, curr_z))

            elif move.move_type in (MoveType.ARC_CW, MoveType.ARC_CCW):
                # Arc move — densify using adaptive_densify_arc
                # Validator agreement (Req 7.4): center_i/center_k offsets use the
                # same convention as the toolpath planner (finish_planner.py):
                #   center_i is in DIAMETER (incremental from start) → convert to radius (÷2)
                #   center_k is in INCHES (incremental from start Z) → no conversion
                # This matches how polygon_builder.py converts edge.center[0] / 2.0
                center_i_r = move.center_i / 2.0  # diameter → radius
                center_k = move.center_k           # already inches

                # Arc center = start position + offset
                center_x = prev_x_r + center_i_r
                center_z = prev_z + center_k

                # Compute arc radius from center to start
                dx = prev_x_r - center_x
                dz = prev_z - center_z
                arc_radius = math.sqrt(dx * dx + dz * dz)

                if arc_radius < 1e-9:
                    # Zero-radius arc — degenerate, treat as linear
                    logger.warning(
                        "Zero-radius arc detected at move %d; treating as linear",
                        i,
                    )
                    centerline_points.append((curr_x_r, curr_z))
                else:
                    # Densify the arc
                    # Validator agreement (Req 7.1): uses same SHAPELY_COS_LIMIT
                    # and MAX_DENSIFICATION_DEPTH as polygon_builder._build_polygon()
                    arc_points = adaptive_densify_arc(
                        start=(prev_x_r, prev_z),
                        end=(curr_x_r, curr_z),
                        center=(center_x, center_z),
                        radius=arc_radius,
                        cos_limit=SHAPELY_COS_LIMIT,
                        max_depth=MAX_DENSIFICATION_DEPTH,
                    )
                    # Skip the first point (already in centerline_points)
                    centerline_points.extend(arc_points[1:])

        # Update previous position for next iteration
        prev_x_r = curr_x_r
        prev_z = curr_z

    # Need at least 2 points to form a band
    if len(centerline_points) < 2:
        return Polygon()

    # Offset the centerline points inward and outward by TNR
    # perpendicular to the local tangent direction
    outer_points: List[Tuple[float, float]] = []
    inner_points: List[Tuple[float, float]] = []

    n = len(centerline_points)
    for idx in range(n):
        # Compute tangent direction at this point
        # Use forward difference, backward difference, or central difference
        if idx == 0:
            # Forward difference
            tx = centerline_points[1][0] - centerline_points[0][0]
            tz = centerline_points[1][1] - centerline_points[0][1]
        elif idx == n - 1:
            # Backward difference
            tx = centerline_points[n - 1][0] - centerline_points[n - 2][0]
            tz = centerline_points[n - 1][1] - centerline_points[n - 2][1]
        else:
            # Central difference
            tx = centerline_points[idx + 1][0] - centerline_points[idx - 1][0]
            tz = centerline_points[idx + 1][1] - centerline_points[idx - 1][1]

        # Normalize tangent
        t_len = math.sqrt(tx * tx + tz * tz)
        if t_len < 1e-12:
            # Degenerate tangent — use previous offset direction or skip
            if outer_points:
                # Reuse last offset
                outer_points.append(outer_points[-1])
                inner_points.append(inner_points[-1])
            continue

        tx /= t_len
        tz /= t_len

        # Perpendicular (normal) to tangent: rotate 90° CCW → (-tz, tx)
        # This gives the "left" normal. For a lathe toolpath going in -Z direction
        # with X as radius, "outward" (away from centerline) is toward larger X.
        # We use both directions and let the polygon construction handle it.
        nx = -tz
        nz = tx

        px = centerline_points[idx][0]
        pz = centerline_points[idx][1]

        # Outer offset (in the +normal direction)
        outer_points.append((px + tnr * nx, pz + tnr * nz))
        # Inner offset (in the -normal direction)
        inner_points.append((px - tnr * nx, pz - tnr * nz))

    # Need at least 2 points on each side to form a polygon
    if len(outer_points) < 2 or len(inner_points) < 2:
        return Polygon()

    # Construct closed polygon: outer forward + inner reversed
    ring = outer_points + list(reversed(inner_points))
    # Close the ring
    ring.append(ring[0])

    if len(ring) < 4:
        return Polygon()

    poly = Polygon(ring)

    # Validate and fix if needed
    if not poly.is_valid:
        logger.warning("Arc swept band polygon is invalid; applying make_valid()")
        poly = make_valid(poly)
        # make_valid can return GeometryCollection — extract polygon if so
        if isinstance(poly, Polygon):
            pass
        elif isinstance(poly, MultiPolygon):
            # Return the largest polygon
            if poly.is_empty:
                return Polygon()
            largest = max(poly.geoms, key=lambda g: g.area)
            poly = largest
        else:
            # GeometryCollection or other — try to extract polygons
            if hasattr(poly, 'geoms'):
                polygons = [g for g in poly.geoms if isinstance(g, Polygon) and not g.is_empty]
                if polygons:
                    poly = max(polygons, key=lambda g: g.area)
                else:
                    return Polygon()
            else:
                return Polygon()

    if poly.is_empty:
        return Polygon()

    return poly


def _polygon_to_arrays(poly) -> List[Tuple[np.ndarray, np.ndarray]]:
    """Convert a Shapely Polygon or MultiPolygon to coordinate arrays.

    Returns list of (x_array, z_array) tuples — one per component polygon.
    Handles MultiPolygon by returning all components.
    Handles GeometryCollection by extracting all Polygon components.
    Coordinates remain in RADIUS for X and INCHES for Z.

    Args:
        poly: A Shapely Polygon, MultiPolygon, or GeometryCollection instance.

    Returns:
        List of (x_ndarray, z_ndarray) tuples. Empty list if polygon is
        empty or invalid.
    """
    if poly is None or poly.is_empty:
        return []

    if isinstance(poly, MultiPolygon):
        result = []
        for geom in poly.geoms:
            coords = np.array(geom.exterior.coords)
            x_arr = coords[:, 0].copy()
            z_arr = coords[:, 1].copy()
            result.append((x_arr, z_arr))
        return result

    if isinstance(poly, Polygon):
        coords = np.array(poly.exterior.coords)
        x_arr = coords[:, 0].copy()
        z_arr = coords[:, 1].copy()
        return [(x_arr, z_arr)]

    # GeometryCollection — extract all Polygon components
    if isinstance(poly, GeometryCollection) and hasattr(poly, 'geoms'):
        result = []
        for geom in poly.geoms:
            if isinstance(geom, Polygon) and not geom.is_empty:
                coords = np.array(geom.exterior.coords)
                x_arr = coords[:, 0].copy()
                z_arr = coords[:, 1].copy()
                result.append((x_arr, z_arr))
        return result

    # Unsupported geometry type — return empty
    return []
