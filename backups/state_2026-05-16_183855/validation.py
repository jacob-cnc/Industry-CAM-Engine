"""Validation result data structures for Industry CAM Engine.

Defines severity classification, validation results, and pipeline status.
Zero external dependencies.
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple

from models.results import PlanResult


class Severity(Enum):
    """Validation result severity — determines whether G-code generation is blocked."""
    ERROR = "error"       # Pipeline halts, no G-code generated
    WARNING = "warning"   # User prompted, can override and continue


class PipelineStatus(Enum):
    """Overall pipeline execution outcome."""
    SUCCESS = "success"
    SUCCESS_WITH_WARNINGS = "success_with_warnings"
    BLOCKED_BY_ERROR = "blocked_by_error"
    CANCELLED_BY_USER = "cancelled_by_user"


@dataclass(frozen=True)
class ValidationResult:
    """A single validation finding — error or warning.

    Attributes:
        severity: ERROR blocks generation, WARNING lets user decide
        category: "geometry", "safety", "tool_reach", "engagement", "thin_wall", "quality", "system"
        message: Machinist-readable description
        recommendation: Suggested fix (e.g., "Increase radius to at least 0.023")
        consequence: What happens if user proceeds (e.g., "Material may remain")
        location: (x_dia, z) where issue occurs
        pass_index: Which pass (if applicable)
        move_index: Which move within pass (if applicable)
    """
    severity: Severity
    category: str
    message: str
    recommendation: Optional[str] = None
    consequence: Optional[str] = None
    location: Optional[Tuple[float, float]] = None
    pass_index: Optional[int] = None
    move_index: Optional[int] = None


@dataclass(frozen=True)
class PipelineResult:
    """Top-level result from pipeline.execute()."""
    plan_result: Optional[PlanResult]
    validations: List[ValidationResult]
    warnings_overridden: bool
    status: PipelineStatus
