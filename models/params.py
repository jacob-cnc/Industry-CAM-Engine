"""Machining parameters for Industry CAM Engine.

Defines roughing and finishing parameter sets.
Zero external dependencies.
"""

from dataclasses import dataclass
from math import isfinite
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
        doc_dia: Derived finish allowance / cutting passes, in DIAMETER (inches)
        feed: Finish feed rate (inches/rev)
        spring_pass: Repeat final contour once; excluded from cutting pass count
    """
    passes: int = 1
    doc_dia: float = 0.002  # Derived from allowance/passes at model/pipeline boundary.
    feed: float = 0.003
    spring_pass: bool = False

    def __post_init__(self):
        if type(self.passes) is not int or self.passes < 1:
            raise ValueError("Finish cutting passes must be a positive integer.")
        if not isfinite(self.feed) or self.feed <= 0:
            raise ValueError("Finish feed must be positive and finite.")

    @staticmethod
    def doc_from_allowance(allowance: float, passes: int) -> float:
        if type(passes) is not int or passes < 1:
            raise ValueError("Finish cutting passes must be a positive integer.")
        if not isfinite(allowance) or allowance < 0:
            raise ValueError("Finish allowance must be finite and nonnegative.")
        if allowance == 0 and passes > 1:
            raise ValueError("Multiple cutting passes require a positive finish allowance.")
        return allowance / passes
