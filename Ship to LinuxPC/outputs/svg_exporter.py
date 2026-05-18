"""Imports from: models/ only"""

from typing import List, Tuple

from models.results import PlanResult
from models.moves import MoveType


# --- Zone fill colors (hex + opacity) ---
_ZONE_COLORS = {
    "finished_part": ("#4A7B9D", 0.4),
    "mtr": ("#C75050", 0.3),
    "finish_allowance": ("#E5A84D", 0.3),
}

# --- Stroke styles ---
_FEED_STROKE = "#5E9E91"
_RAPID_STROKE = "#C75050"
_PROFILE_STROKE = "#FFFFFF"
_STOCK_STROKE = "#6B7B8A"


def _boundary_to_radius_coords(
    boundary: List[Tuple[float, float]],
) -> List[Tuple[float, float]]:
    """Boundary points are already (radius, Z). Return as-is."""
    return boundary


def _svg_polygon(
    points: List[Tuple[float, float]],
    fill: str,
    opacity: float,
    width: float,
    height: float,
) -> str:
    """Generate an SVG polygon element.

    SVG coordinate system:
        - Horizontal axis: Z (left = positive Z, right = negative Z)
        - Vertical axis: X radius (bottom = 0, top = stock radius)

    We map:
        svg_x = width - (z - z_min) * scale  (but caller pre-transforms)
        svg_y = height - x_radius * scale     (but caller pre-transforms)

    Here we receive already-transformed SVG coordinates as (svg_x, svg_y).
    """
    pts_str = " ".join(f"{x:.4f},{y:.4f}" for x, y in points)
    return (
        f'  <polygon points="{pts_str}" '
        f'fill="{fill}" fill-opacity="{opacity}" '
        f'stroke="none" />\n'
    )


def _svg_polyline(
    points: List[Tuple[float, float]],
    stroke: str,
    stroke_width: float,
    dash: str = "",
) -> str:
    """Generate an SVG polyline element."""
    pts_str = " ".join(f"{x:.4f},{y:.4f}" for x, y in points)
    style = f'stroke="{stroke}" stroke-width="{stroke_width}" fill="none"'
    if dash:
        style += f' stroke-dasharray="{dash}"'
    return f'  <polyline points="{pts_str}" {style} />\n'


def export(plan_result: PlanResult, path: str) -> None:
    """Export a PlanResult as an SVG file with zone fills and toolpath.

    Coordinate mapping:
        - X (diameter) is converted to radius for vertical axis
        - Z maps to horizontal axis (positive Z on left, negative Z on right)
        - SVG Y-axis is inverted so bottom = 0 radius, top = max radius
    """
    # --- Determine extents from stock ---
    stock = plan_result.stock
    stock_radius = stock.diameter / 2.0
    z_min = stock.z_end  # most negative Z
    z_max = stock.z_start  # most positive Z (approach)

    z_range = z_max - z_min
    x_range = stock_radius  # 0 to stock_radius

    # SVG dimensions with padding
    padding = 10.0
    scale = 100.0  # pixels per inch
    svg_width = z_range * scale + 2 * padding
    svg_height = x_range * scale + 2 * padding

    def to_svg(z: float, x_radius: float) -> Tuple[float, float]:
        """Convert (Z, X_radius) to SVG (svg_x, svg_y).

        Horizontal: Z positive on left, negative on right.
        Vertical: radius 0 at bottom, stock_radius at top.
        """
        svg_x = padding + (z_max - z) * scale
        svg_y = padding + (stock_radius - x_radius) * scale
        return (svg_x, svg_y)

    def boundary_to_svg(
        boundary: List[Tuple[float, float]],
    ) -> List[Tuple[float, float]]:
        """Convert boundary list of (radius, Z) to SVG coords."""
        return [to_svg(z, r) for r, z in boundary]

    # --- Build SVG content ---
    lines: List[str] = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>\n')
    lines.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {svg_width:.2f} {svg_height:.2f}" '
        f'width="{svg_width:.2f}" height="{svg_height:.2f}">\n'
    )
    lines.append(
        f'  <rect width="{svg_width:.2f}" height="{svg_height:.2f}" fill="#1A1A2E" />\n'
    )

    # --- Zone polygons ---
    # Finished Part zone
    if plan_result.finished_part_boundary:
        svg_pts = boundary_to_svg(plan_result.finished_part_boundary)
        color, opacity = _ZONE_COLORS["finished_part"]
        lines.append(_svg_polygon(svg_pts, color, opacity, svg_width, svg_height))

    # Material To Rough (MTR) zone
    if plan_result.material_to_rough_boundary:
        svg_pts = boundary_to_svg(plan_result.material_to_rough_boundary)
        color, opacity = _ZONE_COLORS["mtr"]
        lines.append(_svg_polygon(svg_pts, color, opacity, svg_width, svg_height))

    # Finish Allowance zone
    if plan_result.finish_allowance_boundary:
        svg_pts = boundary_to_svg(plan_result.finish_allowance_boundary)
        color, opacity = _ZONE_COLORS["finish_allowance"]
        lines.append(_svg_polygon(svg_pts, color, opacity, svg_width, svg_height))

    # --- Stock boundary (gray dashed) ---
    if plan_result.stock_boundary:
        svg_pts = boundary_to_svg(plan_result.stock_boundary)
        lines.append(
            _svg_polyline(svg_pts, _STOCK_STROKE, 0.5, dash="4,3")
        )

    # --- Profile boundary (white solid) ---
    if plan_result.profile_boundary:
        svg_pts = boundary_to_svg(plan_result.profile_boundary)
        lines.append(_svg_polyline(svg_pts, _PROFILE_STROKE, 1.0))

    # --- Toolpath lines ---
    for move in plan_result.tool_moves:
        # Convert move endpoint from diameter to radius
        x_radius = move.x / 2.0
        svg_end = to_svg(move.z, x_radius)

        if move.move_type == MoveType.RAPID:
            # Rapid: red dashed thin line (single segment per move)
            # We draw each move as a dot-to-dot; collect consecutive rapids
            lines.append(
                f'  <circle cx="{svg_end[0]:.4f}" cy="{svg_end[1]:.4f}" '
                f'r="0.3" fill="{_RAPID_STROKE}" opacity="0.6" />\n'
            )
        # Feed moves drawn as connected path segments below

    # Draw feed moves as connected polylines (group consecutive feeds)
    feed_segments: List[List[Tuple[float, float]]] = []
    current_feed: List[Tuple[float, float]] = []

    for move in plan_result.tool_moves:
        x_radius = move.x / 2.0
        svg_pt = to_svg(move.z, x_radius)

        if move.move_type in (MoveType.FEED, MoveType.ARC_CW, MoveType.ARC_CCW):
            current_feed.append(svg_pt)
        else:
            if current_feed:
                feed_segments.append(current_feed)
                current_feed = []
            # Add rapid start point for next feed segment
            current_feed = [svg_pt]

    if current_feed and len(current_feed) > 1:
        feed_segments.append(current_feed)

    for segment in feed_segments:
        if len(segment) >= 2:
            lines.append(_svg_polyline(segment, _FEED_STROKE, 0.5))

    # Draw rapid moves as dashed lines between consecutive rapids
    rapid_segments: List[List[Tuple[float, float]]] = []
    current_rapid: List[Tuple[float, float]] = []

    for move in plan_result.tool_moves:
        x_radius = move.x / 2.0
        svg_pt = to_svg(move.z, x_radius)

        if move.move_type == MoveType.RAPID:
            current_rapid.append(svg_pt)
        else:
            if current_rapid:
                rapid_segments.append(current_rapid)
                current_rapid = []
            current_rapid = [svg_pt]

    if current_rapid and len(current_rapid) > 1:
        rapid_segments.append(current_rapid)

    for segment in rapid_segments:
        if len(segment) >= 2:
            lines.append(_svg_polyline(segment, _RAPID_STROKE, 0.3, dash="3,2"))

    # --- Close SVG ---
    lines.append("</svg>\n")

    # --- Write file ---
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)
