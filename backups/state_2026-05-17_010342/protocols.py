"""Planner protocols for Industry CAM Engine.

Defines the interface that roughing strategy implementations must satisfy.
Both StaircasePlanner and OffsetContourPlanner implement this protocol.

Imports from: models/
"""

from typing import Protocol, List, TYPE_CHECKING

from models.results import TurningPass
from models.tool import ToolDef
from models.params import RoughingParams
from models.stock import StockDef
from models.profile import MachiningMode

if TYPE_CHECKING:
    from intervals.fiber import Fiber
    from geometry.zone_query import ZoneQueryAPI


class RoughingPlanner(Protocol):
    """Interface for roughing strategy implementations."""

    def plan(
        self,
        zone_query: 'ZoneQueryAPI',
        tool: ToolDef,
        params: RoughingParams,
        stock: StockDef,
        mode: MachiningMode,
    ) -> List[TurningPass]:
        """Generate roughing passes.

        Returns ordered list of passes ready for transition planning.
        """
        ...
