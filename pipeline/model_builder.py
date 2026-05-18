"""Model builder for Industry CAM Engine.

Converts raw UI field values into typed dataclasses.
This is the ONLY place where string→enum conversion and field validation happens.
No Qt imports — testable without a display.

Imports from: models/
"""

from typing import List, Tuple, Optional

from models.profile import (
    ClosedProfile, ProfileMove, SegmentType, MachiningMode,
    CornerBreak, CornerBreakType,
)
from models.stock import StockDef
from models.params import RoughingParams, FinishingParams, RoughingStrategy
from models.tool import ToolDef


def build_from_fields(
    segments: List[dict],
    stock_dia: float,
    x_start: float,
    z_start: float,
    z_end: float,
    mode: str,
    pilot_hole_dia: float,
    doc_dia: float,
    feed: float,
    strategy: str,
    fin_allowance: float,
    peck_enabled: bool,
    peck_length: Optional[float],
    spindle_rpm: float,
    finish_passes: int,
    finish_doc_dia: float,
    finish_feed: float,
    tool_def: ToolDef,
    x_park: float = 3.0,
    z_park: float = 3.0,
    corner_breaks: Optional[List[Optional[dict]]] = None,
) -> Tuple[ClosedProfile, StockDef, RoughingParams, FinishingParams]:
    """Convert raw UI field values into typed dataclasses.

    Args:
        segments: List of segment dicts [{"type": "line", "x": 1.0, "z": -0.5}, ...]
        stock_dia: Stock diameter (inches)
        x_start: X approach position (diameter)
        z_start: Z approach position (inches, positive)
        z_end: Z end position (inches, negative)
        mode: "od" or "id"
        pilot_hole_dia: Pilot hole diameter (0 if none)
        doc_dia: Depth of cut (diameter)
        feed: Feed rate (inches/rev)
        strategy: "staircase" or "offset_contour"
        fin_allowance: Finish allowance (diameter)
        peck_enabled: Whether peck roughing is active
        peck_length: Peck interval (inches) or None
        spindle_rpm: Spindle speed
        finish_passes: Number of finish passes
        finish_doc_dia: Finish DOC (diameter)
        finish_feed: Finish feed rate
        tool_def: ToolDef from tool table
        x_park: X park position (diameter)
        z_park: Z park position (inches)
        corner_breaks: Optional list of corner break dicts

    Returns:
        Tuple of (ClosedProfile, StockDef, RoughingParams, FinishingParams)

    Raises:
        ValueError: If required fields are missing or invalid
    """
    # Validate required fields
    if not segments:
        raise ValueError("At least one profile segment is required.")
    if stock_dia <= 0:
        raise ValueError(f"Stock diameter must be positive. Got: {stock_dia}")
    if doc_dia <= 0:
        raise ValueError(f"DOC must be positive. Got: {doc_dia}")
    if feed <= 0:
        raise ValueError(f"Feed rate must be positive. Got: {feed}")

    # Convert mode string to enum
    try:
        machining_mode = MachiningMode(mode.lower())
    except ValueError:
        raise ValueError(f"Invalid mode: '{mode}'. Must be 'od' or 'id'.")

    # Convert strategy string to enum
    try:
        roughing_strategy = RoughingStrategy(strategy.lower())
    except ValueError:
        raise ValueError(f"Invalid strategy: '{strategy}'. Must be 'staircase' or 'offset_contour'.")

    # Convert segment dicts to ProfileMove objects
    profile_moves = []
    for i, seg in enumerate(segments):
        seg_type_str = seg.get("type", "line").lower()
        try:
            seg_type = SegmentType(seg_type_str)
        except ValueError:
            raise ValueError(f"Segment {i+1}: invalid type '{seg_type_str}'. Must be 'line' or 'arc'.")

        x = seg.get("x", seg.get("x_dia", 0.0))
        z = seg.get("z", 0.0)
        radius = seg.get("radius", 0.0)

        profile_moves.append(ProfileMove(
            segment_type=seg_type,
            x=float(x),
            z=float(z),
            radius=float(radius),
        ))

    # Convert corner breaks
    breaks: List[Optional[CornerBreak]] = []
    if corner_breaks and len(corner_breaks) == len(profile_moves) - 1:
        for cb in corner_breaks:
            if cb is None or cb.get("type", "none") == "none":
                breaks.append(None)
            else:
                cb_type = CornerBreakType(cb["type"])
                breaks.append(CornerBreak(
                    break_type=cb_type,
                    radius=cb.get("radius", 0.0),
                    size=cb.get("size", 0.0),
                    angle=cb.get("angle", 45.0),
                ))
    else:
        # Default: no corner breaks
        breaks = [None] * max(0, len(profile_moves) - 1)

    # Build dataclasses
    profile = ClosedProfile(
        segments=profile_moves,
        corner_breaks=breaks,
        mode=machining_mode,
        z_start=0.0,  # Always 0 (finished face)
        z_end=z_end,
    )

    stock = StockDef(
        diameter=stock_dia,
        x_start=x_start,
        z_start=_safe_z_start(z_start, fin_allowance),
        z_end=z_end,
        mode=machining_mode,
        x_park=x_park,
        z_park=z_park,
        pilot_hole_dia=pilot_hole_dia,
    )

    roughing = RoughingParams(
        doc_dia=doc_dia,
        feed=feed,
        strategy=roughing_strategy,
        fin_allowance=fin_allowance,
        peck_enabled=peck_enabled,
        peck_length=peck_length,
        spindle_rpm=spindle_rpm,
    )

    finishing = FinishingParams(
        passes=finish_passes,
        doc_dia=finish_doc_dia,
        feed=finish_feed,
    )

    return profile, stock, roughing, finishing


def _safe_z_start(z_start: float, fin_allowance: float) -> float:
    """Ensure Z_start provides a safe approach without unnecessary face passes.

    If Z_start is at or below the finish allowance threshold (Z=0 + fin_allowance),
    there's no meaningful face material to remove. In that case, bump Z_start to
    fin_allowance + 0.050" to provide a safe rapid approach clearance without
    generating TFZ face passes.

    This lets the user set Z_start=0 to skip face passes while still getting
    a safe approach distance.

    Args:
        z_start: User-specified Z start (positive = above face)
        fin_allowance: Finish allowance in DIAMETER

    Returns:
        Adjusted z_start value
    """
    fin_allowance_radius = fin_allowance / 2.0
    threshold = fin_allowance_radius + 0.001  # Slightly above fin_allowance

    if z_start <= threshold:
        # No face material — provide safe approach clearance only
        return fin_allowance_radius + 0.050

    return z_start
