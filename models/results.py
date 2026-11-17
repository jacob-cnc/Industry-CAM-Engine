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
class SharpenedCorner:
    """A concave arc no larger than the nose radius, cut as the sharp corner
    of its neighbouring lines (owner 2026-11-10). Points (X dia, Z)."""
    radius: float
    corner: Tuple[float, float]


@dataclass(frozen=True)
class CompContour:
    """How one cleanup / finish contour is cut under cutter comp: entry,
    contour and lead-out, decided by planners/comp_contour.py; the G-code
    writer only emits it. Points are (X diameter, Z).

        comp_code   "G41" | "G42" | "G40" (no nose radius / neutral tool)
        nose_radius the tool's nose radius the decisions were made for
        feed        feed of the first contour move (entry and lead-out feed)
        start       contour start (approach artefacts at the pass head skipped)
        entry       end of the comp-off approach = start of the comp entry move
        z_clear     approach clearance Z (comp off)
        collinear   entry runs in line with a sloped first cut
        face_entry  OD face / centre entry: one nose radius before the start
        contour     the moves to cut (arc pieces re-joined, small concave arcs
                    sharpened)
        sharpened   the sharpened arcs (reported to the operator)
        lead_out    end of the comp lead-out move, or None (no material beyond)
    """
    comp_code: str
    nose_radius: float
    feed: float
    start: Tuple[float, float]
    entry: Tuple[float, float]
    z_clear: float
    collinear: bool
    face_entry: bool
    contour: Tuple[ToolMove, ...]
    sharpened: Tuple[SharpenedCorner, ...] = ()
    lead_out: Optional[Tuple[float, float]] = None


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
    is_spring_pass: bool = False
    retract_moves: Optional[Tuple[ToolMove, ...]] = None  # Planned exit, including terminal finish.
    approach_moves: Tuple[ToolMove, ...] = ()  # Pipeline-planned, validated incoming link.
    comp_contour: Optional[CompContour] = None  # Cleanup/finish: planned comp entry/contour/lead-out.


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


@dataclass(frozen=True)
class ThreadPass:
    """One synchronized threading pass (diameter X)."""
    x_start: float
    z_start: float
    x_end: float
    z_end: float


@dataclass(frozen=True)
class ThreadPlan:
    """A planned threading operation (planners/threading_planner.py).

    mode "g76": straight thread, LinuxCNC's G76 cycle with ``g76`` words.
    mode "g33": taper, one G33 per pass in ``passes`` (one list per start).
    Retract X: external max(X) + .020, internal pilot - .005 (owner 2026-11-12).
    """
    mode: str
    retract_x: float
    lead: float
    z_starts: tuple                    # one per start
    end_z: float
    crest: tuple                       # (at Z start, at Z end), diameter
    root: tuple                        # (at Z start, at Z end), diameter
    depth: float                       # radial, crest -> root at Z start
    g76: Optional[dict] = None
    passes: tuple = ()                 # tuple of tuples of ThreadPass, one per start
    errors: tuple = ()
    warnings: tuple = ()
