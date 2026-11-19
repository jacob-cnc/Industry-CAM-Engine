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
            raise ValueError(
                f"Finish cutting passes must be a whole number of 1 or more. "
                f"Got: {self.passes!r}")
        if not isfinite(self.feed) or self.feed <= 0:
            raise ValueError(
                f"Finish feed must be a positive number of inches per revolution. "
                f"Got: {self.feed!r}")

    @staticmethod
    def doc_from_allowance(allowance: float, passes: int) -> float:
        if type(passes) is not int or passes < 1:
            raise ValueError(
                f"Finish cutting passes must be a whole number of 1 or more. "
                f"Got: {passes!r}")
        if not isfinite(allowance) or allowance < 0:
            raise ValueError(
                f"Finish allowance must be zero or a positive diameter. Got: {allowance!r}")
        if allowance == 0 and passes > 1:
            raise ValueError(
                f"{passes} finish cutting passes need material to divide between them, "
                "but the finish allowance is zero. Set an allowance, or use 1 pass.")
        return allowance / passes
