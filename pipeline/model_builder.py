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
    stock_back_z: Optional[float] = None,
    finish_spring_pass: bool = False,
) -> Tuple[ClosedProfile, StockDef, RoughingParams, FinishingParams]:
    """Convert raw UI field values into typed dataclasses.

    Args:
        segments: List of segment dicts [{"type": "line", "x": 1.0, "z": -0.5}, ...]
        stock_dia: Stock diameter (inches)
        x_start: X approach position (diameter)
        z_start: Z approach position (inches, positive)
        z_end: Legacy argument retained for callers; contour geometry determines depth.
        stock_back_z: Optional physical stock back face, separate from operation depth.
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

    profile = profile_from_fields(segments, mode, corner_breaks)
    from geometry.zone_builder import contour_z_end
    from dataclasses import replace
    operation_z_end = contour_z_end(profile)
    profile = replace(profile, z_end=operation_z_end)

    from math import isfinite
    from models.constants import TOLERANCE
    if stock_back_z is not None and not isfinite(stock_back_z):
        raise ValueError("Stock back face must be finite.")
    if stock_back_z is not None and stock_back_z > operation_z_end + TOLERANCE:
        raise ValueError("Stock back face must be at or behind the operation Z End.")
    _check_stock_size(profile, stock_dia, pilot_hole_dia, fin_allowance)

    stock = StockDef(
        diameter=stock_dia,
        x_start=x_start,
        z_start=_safe_z_start(z_start, fin_allowance),
        z_end=operation_z_end,
        back_face_z=stock_back_z,
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
        doc_dia=FinishingParams.doc_from_allowance(fin_allowance, finish_passes),
        feed=finish_feed,
        spring_pass=finish_spring_pass,
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


def _check_stock_size(profile: ClosedProfile, stock_dia: float, pilot_hole_dia: float,
                      fin_allowance: float) -> None:
    """The stock must leave room for the finish allowance around the profile.

    OD: stock diameter > largest finished diameter + finish allowance (dia).
    ID: pilot hole (if any) < smallest finished bore - finish allowance.
    Otherwise the cleanup/finish contour, which runs one finish allowance
    outside the profile, falls outside the stock where the profile meets it,
    gets clipped into separate pieces, and generation fails with a kernel-
    level error ("Cleanup clipping did not produce one connected contour").
    Checked on the profile END POINTS (segment end diameters).
    """
    from models.constants import TOLERANCE
    pts = [(m.x, m.z) for m in profile.segments]
    if len(pts) < 2:
        return
    od = profile.mode == MachiningMode.OD
    if not od and pilot_hole_dia <= 0:
        return
    limit = stock_dia if od else pilot_hole_dia
    name = "stock diameter" if od else "pilot hole"
    fix = ("Increase Stock > Diameter" if od else "Reduce the pilot hole diameter")

    def outside(d):          # beyond the stock surface (no material there)
        return d > limit + TOLERANCE if od else d < limit - TOLERANCE

    def no_room(d):          # closer to the stock surface than the allowance
        return d >= limit - fin_allowance - TOLERANCE if od \
            else d <= limit + fin_allowance + TOLERANCE

    for d, z in pts:
        if outside(d):
            raise ValueError(
                f"The profile goes outside the stock: Ø{d:.4f} at Z {z:.4f} is beyond "
                f"the {name} Ø{limit:.4f}. {fix}, or check that point.")
    # A stretch running along the stock surface with more profile after it.
    # (Ending on the stock surface, e.g. a step out to the bar, is fine.)
    for k in range(1, len(pts) - 1):
        (d0, z0), (d1, z1) = pts[k - 1], pts[k]
        if no_room(d0) and no_room(d1):
            need = (f"larger than Ø{max(d0, d1) + fin_allowance:.4f}" if od
                    else f"smaller than Ø{min(d0, d1) - fin_allowance:.4f}")
            raise ValueError(
                f"The {name} is too {'small' if od else 'large'}. The profile runs along "
                f"Ø{d1:.4f} from Z {z0:.4f} to Z {z1:.4f}, within the finish allowance "
                f"({fin_allowance:.4f} on the diameter) of the {name} Ø{limit:.4f}, and "
                f"continues after it, so the finish/cleanup pass cannot follow it. "
                f"{fix}: it must be {need}.")


def profile_from_fields(segments: List[dict], mode: str, corner_breaks=None) -> ClosedProfile:
    """Parse a contour identically for preview, depth calculation, and generation."""
    machining_mode = MachiningMode(mode.lower())
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

        # Detect quadrant arc: "Q" (convex) or "-Q" (concave)
        radius_str = str(radius).strip().upper() if not isinstance(radius, (int, float)) else ""
        is_quadrant = radius_str in ("Q", "-Q")
        quadrant_sign = -1 if radius_str == "-Q" else 1
        if is_quadrant:
            radius_val = 0.0
        else:
            radius_val = float(radius)

        profile_moves.append(ProfileMove(
            segment_type=seg_type,
            x=float(x),
            z=float(z),
            radius=radius_val,
            quadrant=is_quadrant,
            quadrant_sign=quadrant_sign,
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
                    trim=cb.get("trim", "nx"),
                ))
    else:
        # Default: no corner breaks
        breaks = [None] * max(0, len(profile_moves) - 1)

    profile = ClosedProfile(
        segments=profile_moves,
        corner_breaks=breaks,
        mode=machining_mode,
        z_start=0.0,  # Always 0 (finished face)
        z_end=min(float(seg.get("z", 0.0)) for seg in segments),
    )

    return profile
