"""DXF export module for Industry CAM Engine.

Generates layered DXF files from PlanResult data with full zone,
profile, stock, and toolpath visualization.

Coordinate convention:
    - All coordinates in RADIUS for X, INCHES for Z (matching CAD reference)
    - DXF units: millimeters (multiply inches by 25.4)

Toolpath chain-of-trust:
    - Toolpath geometry is derived from G-code round-trip (write → parse → DXF)
    - This ensures the DXF reflects what the machine will actually execute

Imports from: models/, outputs/ (gcode_writer, gcode_parser)
"""

from typing import List, Tuple

import ezdxf

from models.results import PlanResult
from models.moves import MoveType
from outputs.gcode_writer import GCodeWriter
from outputs.gcode_parser import parse as parse_gcode


# Conversion factor: inches to millimeters (DXF units)
_MM = 25.4

# Layer definitions: (name, color index)
_LAYERS = [
    ("PROFILE", 7),                 # White — profile boundary
    ("STOCK", 8),                   # Gray — stock boundary
    ("TOOLPATH_FEED", 3),           # Green — feed moves
    ("TOOLPATH_RAPID", 1),          # Red — rapid moves
    ("ZONES_FINISHED_PART", 4),     # Cyan
    ("ZONES_MTR", 1),               # Red
    ("ZONES_TRUE_FACE", 14),        # Light red
    ("ZONES_FIN_ALLOWANCE", 2),     # Yellow
]


def export(plan_result: PlanResult, path: str) -> None:
    """Export a complete layered DXF from a PlanResult.

    Includes profile, stock, toolpath (via G-code round-trip), and zone polygons.

    Args:
        plan_result: Immutable pipeline output containing all geometry data.
        path: Output file path for the .dxf file.
    """
    doc = _create_document()
    msp = doc.modelspace()

    # Draw zone polygons
    _draw_zone_polygons(msp, plan_result)

    # Draw stock boundary
    _draw_polygon(msp, plan_result.stock_boundary, "STOCK")

    # Draw profile from segments
    _draw_profile(msp, plan_result)

    # Toolpath via G-code round-trip (chain-of-trust)
    writer = GCodeWriter()
    gcode = writer.write(plan_result)
    _draw_toolpath_from_gcode(msp, gcode)

    # Origin marker
    msp.add_point((0, 0, 0), dxfattribs={"layer": "0"})

    doc.saveas(path)


def export_from_gcode(gcode_text: str, path: str) -> None:
    """Export a DXF containing only the toolpath from parsed G-code.

    Useful for Edit tab export where no PlanResult zones/profile are available.

    Args:
        gcode_text: Complete G-code program text.
        path: Output file path for the .dxf file.
    """
    doc = _create_document()
    msp = doc.modelspace()

    _draw_toolpath_from_gcode(msp, gcode_text)

    # Origin marker
    msp.add_point((0, 0, 0), dxfattribs={"layer": "0"})

    doc.saveas(path)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _create_document() -> ezdxf.document.Drawing:
    """Create a new DXF document with all required layers."""
    doc = ezdxf.new("R2010", setup=True)
    for name, color in _LAYERS:
        doc.layers.add(name, color=color)
    return doc


def _draw_polygon(
    msp,
    coords: List[Tuple[float, float]],
    layer: str,
) -> None:
    """Draw a closed polygon as connected line segments.

    Boundary data from PlanResult is in (x_diameter, z) format.
    Converts to (x_radius * MM, z * MM) for DXF output.
    """
    if not coords:
        return
    for i in range(len(coords)):
        j = (i + 1) % len(coords)
        x1_r = coords[i][0] / 2.0
        z1 = coords[i][1]
        x2_r = coords[j][0] / 2.0
        z2 = coords[j][1]
        msp.add_line(
            (x1_r * _MM, z1 * _MM, 0),
            (x2_r * _MM, z2 * _MM, 0),
            dxfattribs={"layer": layer},
        )


def _draw_zone_polygons(msp, pr: PlanResult) -> None:
    """Draw all zone boundary polygons."""
    _draw_polygon(msp, pr.finished_part_boundary, "ZONES_FINISHED_PART")
    _draw_polygon(msp, pr.material_to_rough_boundary, "ZONES_MTR")
    _draw_polygon(msp, pr.finish_allowance_boundary, "ZONES_FIN_ALLOWANCE")

    # True face zone: derived from stock and fin_allowance
    fin_r = pr.roughing_params.fin_allowance / 2.0
    true_face = [
        (0.0, fin_r),
        (pr.stock.diameter, fin_r),
        (pr.stock.diameter, pr.stock.z_start),
        (0.0, pr.stock.z_start),
    ]
    _draw_polygon(msp, true_face, "ZONES_TRUE_FACE")


def _draw_profile(msp, pr: PlanResult) -> None:
    """Draw the profile boundary from PlanResult.profile.segments.

    Profile segments are in DIAMETER for X. Convert to radius for DXF.
    """
    segments = pr.profile.segments
    for i in range(len(segments) - 1):
        seg = segments[i]
        next_seg = segments[i + 1]
        x1_r = seg.x / 2.0
        z1 = seg.z
        x2_r = next_seg.x / 2.0
        z2 = next_seg.z
        msp.add_line(
            (x1_r * _MM, z1 * _MM, 0),
            (x2_r * _MM, z2 * _MM, 0),
            dxfattribs={"layer": "PROFILE"},
        )


def _draw_toolpath_from_gcode(msp, gcode_text: str) -> None:
    """Parse G-code and draw toolpath moves on FEED/RAPID layers.

    This is the chain-of-trust path: the DXF reflects exactly what the
    machine will execute, derived from the G-code round-trip.
    """
    parsed_moves = parse_gcode(gcode_text)

    prev_x_r: float | None = None
    prev_z: float | None = None

    for move in parsed_moves:
        x_r = move.x / 2.0  # Diameter → radius
        z = move.z

        if prev_x_r is not None and prev_z is not None:
            # Skip zero-length moves
            if abs(x_r - prev_x_r) < 0.00001 and abs(z - prev_z) < 0.00001:
                prev_x_r = x_r
                prev_z = z
                continue

            # Layer selection based on move type
            if move.move_type == MoveType.RAPID:
                layer = "TOOLPATH_RAPID"
            else:
                layer = "TOOLPATH_FEED"

            msp.add_line(
                (prev_x_r * _MM, prev_z * _MM, 0),
                (x_r * _MM, z * _MM, 0),
                dxfattribs={"layer": layer},
            )

        prev_x_r = x_r
        prev_z = z
