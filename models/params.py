"""Machining parameters for Industry CAM Engine.

Defines roughing and finishing parameter sets.
Zero external dependencies.
"""

from dataclasses import dataclass
from enum import Enum


class RoughingStrategy(Enum):
    """Roughing pass generation strategy."""
    STAIRCASE = "staircase"
    OFFSET_CONTOUR = "offset_contour"


@dataclass(frozen=True)
class RoughingParams:
    """Parameters controlling roughing pass generation.

    Coordinates:
        doc_dia: Depth of cut in DIAMETER per pass (inches)
        feed: Feed rate (inches/rev)
        fin_allowance: Finish allowance in DIAMETER (inches). Engine converts to radius for offset.
        peck_length: Peck interval along toolpath (inches). None if peck disabled.
        spindle_rpm: Spindle speed for dwell calculations and G-code header.
    """
    doc_dia: float
    feed: float
    strategy: RoughingStrategy
    fin_allowance: float = 0.005
    peck_enabled: bool = False
    peck_length: float | None = None
    spindle_rpm: float = 1200.0


@dataclass(frozen=True)
class FinishingParams:
    """Parameters controlling finish pass generation.

    Coordinates:
        doc_dia: Finish DOC in DIAMETER (inches)
        feed: Finish feed rate (inches/rev)
    """
    passes: int = 1
    doc_dia: float = 0.002
    feed: float = 0.003
