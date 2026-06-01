"""Graph adapter for Industry CAM Engine.

Converts PlanResult into PyQtGraph-ready coordinate arrays.
NOTE: This module does NOT import PyQtGraph or Qt.
It produces plain coordinate arrays and metadata that gui/ consumes.

Imports from: models/ only
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple, Optional, TYPE_CHECKING

import numpy as np

from models.results import PlanResult
from models.moves import ToolMove, MoveType, PassType
from models.profile import MachiningMode

if TYPE_CHECKING:
    from outputs.material_sim import MaterialSimData


@dataclass
class ZoneShading:
    """Polygon coordinate arrays for zone fill rendering."""
    zone_name: str
    x_coords: List[float]  # RADIUS
    z_coords: List[float]  # INCHES
    color_key: str          # Key into COLORS dict


@dataclass
class ToolpathSegment:
    """A contiguous segment of the toolpath with uniform move type."""
    x_coords: List[float]  # RADIUS
    z_coords: List[float]  # INCHES
    move_type: MoveType
    pass_type: PassType
    pass_index: int


@dataclass
class PlaybackFrame:
    """A single frame in animated playback."""
    move_index: int
    x: float  # RADIUS
    z: float  # INCHES
    pass_type: PassType
    n_number: int


@dataclass
class MaterialStateData:
    """Pre-computed material state coordinate arrays for rendering."""
    stock_x: np.ndarray          # Stock polygon X coordinates (radius)
    stock_z: np.ndarray          # Stock polygon Z coordinates (inches)
    pass_states: List            # List of pass state coordinate arrays
    final_x: List[np.ndarray]   # Final state X coordinates (one per component polygon, radius)
    final_z: List[np.ndarray]   # Final state Z coordinates (one per component polygon, inches)
    move_states: dict = field(default_factory=dict)  # {move_index: List[Tuple[np.ndarray, np.ndarray]]}


@dataclass
class GraphData:
    """Complete data package for PyQtGraph rendering.

    All X coordinates in RADIUS. All Z in INCHES.
    """
    zone_shadings: List[ZoneShading] = field(default_factory=list)
    toolpath_segments: List[ToolpathSegment] = field(default_factory=list)
    profile_line_x: List[float] = field(default_factory=list)  # RADIUS
    profile_line_z: List[float] = field(default_factory=list)  # INCHES
    stock_rect: Tuple[float, float, float, float] = (0, 0, 0, 0)  # (x_min_r, x_max_r, z_min, z_max)
    centerline_z_range: Tuple[float, float] = (0, 0)
    playback_frames: List[PlaybackFrame] = field(default_factory=list)
    warning_regions: List[Tuple[List[float], List[float]]] = field(default_factory=list)
    material_states: Optional[MaterialStateData] = None


def convert(plan_result: PlanResult, material_sim_data: Optional['MaterialSimData'] = None) -> GraphData:
    """Convert PlanResult into PyQtGraph-ready coordinate arrays.

    - Converts all X from DIAMETER to RADIUS (÷ 2.0)
    - Groups moves by type for color-coded rendering
    - Constructs playback frame sequence
    - Extracts zone boundaries as polygon coordinate arrays
    - Optionally serializes material simulation data into coordinate arrays

    Performance budget: < 50ms for typical profiles.
    """
    data = GraphData()

    # Stock rectangle (in radius)
    stock_x_max_r = plan_result.stock.diameter / 2.0
    data.stock_rect = (0.0, stock_x_max_r, plan_result.stock.z_end, plan_result.stock.z_start)
    data.centerline_z_range = (plan_result.stock.z_end, plan_result.stock.z_start)

    # Profile line (convert from diameter to radius)
    for coord in plan_result.profile_boundary:
        data.profile_line_x.append(coord[0] / 2.0)  # diameter to radius
        data.profile_line_z.append(coord[1])

    # Zone shadings (boundaries already in radius from zone_query)
    if plan_result.finished_part_boundary:
        data.zone_shadings.append(ZoneShading(
            zone_name="finished_part",
            x_coords=[c[0] / 2.0 for c in plan_result.finished_part_boundary],
            z_coords=[c[1] for c in plan_result.finished_part_boundary],
            color_key="graph_zone_finished",
        ))

    if plan_result.material_to_rough_boundary:
        data.zone_shadings.append(ZoneShading(
            zone_name="material_to_rough",
            x_coords=[c[0] / 2.0 for c in plan_result.material_to_rough_boundary],
            z_coords=[c[1] for c in plan_result.material_to_rough_boundary],
            color_key="graph_zone_material",
        ))

    # Finish allowance zone — thin band between profile and roughing boundary
    # Computed as keep_zone - finished_part in zone_builder
    if plan_result.finish_allowance_boundary and len(plan_result.finish_allowance_boundary) >= 3:
        data.zone_shadings.append(ZoneShading(
            zone_name="finish_allowance",
            x_coords=[c[0] / 2.0 for c in plan_result.finish_allowance_boundary],
            z_coords=[c[1] for c in plan_result.finish_allowance_boundary],
            color_key="graph_zone_allowance",
        ))


    # True Face Zone (simple rectangle from stock params)
    fin_r = plan_result.roughing_params.fin_allowance / 2.0
    stock_r = plan_result.stock.diameter / 2.0
    x_start_r = plan_result.stock.x_start / 2.0
    z_start = plan_result.stock.z_start
    if plan_result.mode == MachiningMode.OD:
        tf_x = [x_start_r, stock_r, stock_r, x_start_r]
        tf_z = [fin_r, fin_r, z_start, z_start]
    else:
        pilot_r = plan_result.stock.pilot_hole_dia / 2.0
        tf_x = [pilot_r, x_start_r, x_start_r, pilot_r]
        tf_z = [0.0, 0.0, z_start, z_start]

    if z_start > fin_r + 0.0001:  # Only show if there's actual face material
        data.zone_shadings.append(ZoneShading(
            zone_name="true_face",
            x_coords=tf_x,
            z_coords=tf_z,
            color_key="graph_zone_true_face",
        ))

    # Toolpath segments (group consecutive moves of same type)
    _build_toolpath_segments(plan_result.tool_moves, data)

    # Playback frames
    n_number = 10
    for i, move in enumerate(plan_result.tool_moves):
        data.playback_frames.append(PlaybackFrame(
            move_index=i,
            x=move.x / 2.0,  # diameter to radius
            z=move.z,
            pass_type=move.pass_type,
            n_number=n_number,
        ))
        n_number += 10

    # Material simulation data serialization
    if material_sim_data:
        data.material_states = _convert_material_sim(material_sim_data)

    return data


def convert_from_moves(moves: List[ToolMove]) -> GraphData:
    """Convert a raw move list (e.g., from gcode_parser) into GraphData.

    Used by Edit Tab preview and round-trip overlay.
    Simpler than full convert() — no zone data, just toolpath.
    """
    data = GraphData()
    _build_toolpath_segments(moves, data)

    # Playback frames
    n_number = 10
    for i, move in enumerate(moves):
        data.playback_frames.append(PlaybackFrame(
            move_index=i,
            x=move.x / 2.0,
            z=move.z,
            pass_type=move.pass_type,
            n_number=n_number,
        ))
        n_number += 10

    return data


def _convert_material_sim(material_sim_data: 'MaterialSimData') -> MaterialStateData:
    """Convert MaterialSimData into MaterialStateData coordinate arrays.

    Extracts pre-computed numpy arrays from the simulation data and packages
    them into the rendering-ready MaterialStateData structure.

    No Shapely operations here — all data arrives as pre-computed numpy arrays
    from material_sim.py.

    Args:
        material_sim_data: Pre-computed material simulation data from material_sim.compute().

    Returns:
        MaterialStateData with stock, pass_states, and final state coordinate arrays.
    """
    # Extract stock polygon coordinates (already numpy arrays)
    stock_x, stock_z = material_sim_data.stock_polygon

    # Pass through pass_states directly — they already contain coordinate arrays
    pass_states = material_sim_data.pass_states

    # Extract final state coordinate arrays (list of (x_arr, z_arr) tuples)
    final_x = [coords[0] for coords in material_sim_data.final_state]
    final_z = [coords[1] for coords in material_sim_data.final_state]

    return MaterialStateData(
        stock_x=stock_x,
        stock_z=stock_z,
        pass_states=pass_states,
        final_x=final_x,
        final_z=final_z,
        move_states=material_sim_data.move_states,
    )


def _build_toolpath_segments(moves: List[ToolMove], data: GraphData) -> None:
    """Group moves into ToolpathSegments by move type for color-coded rendering.
    
    Arc moves are densified into polylines for smooth display.
    """
    if not moves:
        return

    from geometry.adaptive_sampling import adaptive_densify_arc
    from models.constants import DISPLAY_COS_LIMIT, MAX_DISPLAY_DEPTH
    import math

    prev_x_r: Optional[float] = None
    prev_z: Optional[float] = None

    for move in moves:
        x_r = move.x / 2.0  # diameter to radius
        z = move.z

        if prev_x_r is not None and prev_z is not None:
            if move.move_type in (MoveType.ARC_CW, MoveType.ARC_CCW) and (
                    abs(move.center_i) > 0.0001 or abs(move.center_k) > 0.0001):
                # Densify arc for smooth display
                center_i_r = move.center_i / 2.0
                center_x_r = prev_x_r + center_i_r
                center_z = prev_z + move.center_k
                radius = math.sqrt(
                    (prev_x_r - center_x_r)**2 + (prev_z - center_z)**2)
                if radius > 0.0001:
                    # Pure G-code interpretation: G02 = CW in G18 = negative
                    # angular sweep in display coords. G03 = positive sweep.
                    is_cw = (move.move_type == MoveType.ARC_CW)
                    points = adaptive_densify_arc(
                        start=(prev_x_r, prev_z),
                        end=(x_r, z),
                        center=(center_x_r, center_z),
                        radius=radius,
                        cos_limit=DISPLAY_COS_LIMIT,
                        max_depth=MAX_DISPLAY_DEPTH,
                        is_cw=is_cw,
                    )
                    x_coords = [p[0] for p in points]
                    z_coords = [p[1] for p in points]
                else:
                    x_coords = [prev_x_r, x_r]
                    z_coords = [prev_z, z]
            else:
                x_coords = [prev_x_r, x_r]
                z_coords = [prev_z, z]

            segment = ToolpathSegment(
                x_coords=x_coords,
                z_coords=z_coords,
                move_type=move.move_type,
                pass_type=move.pass_type,
                pass_index=move.pass_index,
            )
            data.toolpath_segments.append(segment)

        prev_x_r = x_r
        prev_z = z
