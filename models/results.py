"""Result data structures for Industry CAM Engine.

Defines TurningPass, SweptRegion, and the immutable PlanResult.
Zero external dependencies.
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple

from models.profile import ClosedProfile, MachiningMode
from models.stock import StockDef
from models.tool import ToolDef
from models.params import RoughingParams, FinishingParams
from models.moves import ToolMove, PassType


@dataclass(frozen=True)
class SweptRegion:
    """Material removed by a single pass.

    Coordinates (all DIAMETER for X, inches for Z):
        x_min: Inner X bound (diameter)
        x_max: Outer X bound (diameter)
        z_start: Z start (higher Z, toward face)
        z_end: Z end (lower Z, into workpiece)
    For offset-contour: inner/outer boundary as coordinate arrays (radius, Z).
    """
    x_min: float
    x_max: float
    z_start: float
    z_end: float
    inner_boundary: Optional[List[Tuple[float, float]]] = None
    outer_boundary: Optional[List[Tuple[float, float]]] = None


@dataclass(frozen=True)
class TurningPass:
    """A single roughing, cleanup, or finish pass.

    Coordinates:
        x_level: X diameter of this pass
        z_start: Z start (higher Z)
        z_end: Z end (lower Z)
    """
    x_level: float
    z_start: float
    z_end: float
    pass_index: int
    pass_type: PassType
    moves: List[ToolMove]
    swept_region: Optional[SweptRegion] = None


@dataclass(frozen=True)
class PlanResult:
    """Immutable output of pipeline.execute(). Feeds all output adapters.

    This dataclass carries EVERYTHING the graph, G-code writer, and exporters need.
    No output adapter should ever call back into the engine for additional data.
    """
    profile: ClosedProfile
    stock: StockDef
    tool: ToolDef
    roughing_params: RoughingParams
    finishing_params: FinishingParams
    mode: MachiningMode

    # Planned passes
    face_passes: List[TurningPass]
    roughing_passes: List[TurningPass]
    cleanup_passes: List[TurningPass]
    finish_passes: List[TurningPass]

    # Complete ordered toolpath
    tool_moves: List[ToolMove]

    # Zone boundary data (radius, Z coordinate pairs for graph adapter)
    finished_part_boundary: List[Tuple[float, float]]
    finish_allowance_boundary: List[Tuple[float, float]]
    material_to_rough_boundary: List[Tuple[float, float]]
    stock_boundary: List[Tuple[float, float]]
    profile_boundary: List[Tuple[float, float]]

    # Validation results
    validations: List['ValidationResult']
    warnings_overridden: bool = False

    # Finish tool (if different from roughing tool)
    finish_tool: Optional[ToolDef] = None

    # Metadata
    generation_time_ms: float = 0.0
    pass_count: int = 0
    move_count: int = 0
