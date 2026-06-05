"""Models module — Pure data structures with zero external dependencies.

All dataclasses, enums, and constants used throughout the engine.
"""

from models.constants import (
    TOLERANCE, TOLERANCE_SQ, CENTER_ARC_RADIUS_TOLERANCE_INCH,
    RADIUS_TOLERANCE, DISPLAY_TOLERANCE, DENSIFICATION_ERROR,
    SHAPELY_COS_LIMIT, DISPLAY_COS_LIMIT, MAX_DENSIFICATION_DEPTH,
    MAX_DISPLAY_DEPTH,
)
from models.profile import (
    SegmentType, MachiningMode, CornerBreakType, CornerBreak,
    ProfileMove, ClosedProfile,
)
from models.stock import StockDef
from models.tool import (
    ToolOrientation, ToolDirection, ToolType, ToolDef,
)
from models.params import (
    RoughingStrategy, RoughingParams, FinishingParams,
)
from models.moves import (
    MoveType, PassType, ToolMove,
)
from models.transitions import (
    TransitionType, Transition,
)
from models.results import (
    SweptRegion, TurningPass, PlanResult,
)
from models.validation import (
    Severity, PipelineStatus, ValidationResult, PipelineResult,
)
from models.program import (
    ThreadingParams, GroovingParams, ProgramBlock,
)
