"""Tool card data model for the GUI tool geometry editor.

Defines ToolCardData (GUI-layer tool definition), type/insert/orientation
constants, and conversion functions between ToolCardData and pipeline ToolDef.

Zero Qt dependencies — pure data layer.
"""

from dataclasses import dataclass
from typing import List, Dict

from models.tool import ToolDef, ToolOrientation, ToolDirection, ToolType


# ---------------------------------------------------------------------------
# ToolCardData dataclass
# ---------------------------------------------------------------------------

@dataclass
class ToolCardData:
    """GUI-layer tool definition with all fields needed for the card display.

    Coordinates:
        x_offset: X geometry offset in RADIUS (inches) — displayed as diameter
        z_offset: Z geometry offset (inches)
        x_wear: X wear offset in RADIUS (inches) — displayed as diameter
        z_wear: Z wear offset (inches)
        nose_radius: Tool nose radius (inches)
        front_angle: Front cutting edge angle (degrees)
        back_angle: Back cutting edge angle (degrees)
        blade_width: Grooving blade width (inches), 0.0 for non-grooving
    """
    tool_number: int
    tool_type: str          # "Turning RH", "Turning LH", "Boring Bar", etc.
    insert_code: str        # "CNMG", "CCMT", "60° UN/Metric", etc.
    orientation: int        # Q1–Q9
    description: str
    nose_radius: float
    front_angle: float
    back_angle: float
    x_offset: float         # radius internally
    z_offset: float
    x_wear: float           # radius internally
    z_wear: float
    blade_width: float = 0.0
    iso_code: str = ""      # full ISO insert code, e.g. "CNMG432" (optional)
    ic: float = 0.0         # insert inscribed circle / blade length, inches; 0 = from iso_code


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TOOL_TYPES: List[str] = [
    "Turning RH",
    "Turning LH",
    "Boring Bar",
    "Threading External",
    "Threading Internal",
    "Grooving/Parting",
    "Knurling",
    "Custom",
]

# Valid LinuxCNC orientations (Q) per tool type, first = default. Per the
# LinuxCNC 2.9.6 manual Fig 2.16 for a FRONT-TOOL lathe, cutting corner relative
# to the nose centre: 1 -X+Z, 2 -X-Z, 3 +X-Z, 4 +X+Z, 5 +Z, 6 -X, 7 -Z, 8 +X,
# 9 centre. Reviewed 2026-11-08 (previous lists offered inside corners for OD
# tools, Q6 for internal threading, Q5 for grooving).
TYPE_ORIENTATIONS: Dict[str, List[int]] = {
    "Turning RH": [2, 6],          # 2 = corner toward chuck; 6 = neutral holder
    "Turning LH": [1, 6],          # 1 = corner toward tailstock; 6 = neutral
    # LinuxCNC Fig 2.16, front-tool lathe: Q3 = corner +X/-Z (conventional
    # boring bar cutting toward the chuck), Q4 = +X/+Z (back-boring toward the
    # tailstock), Q8 = straight +X. Was [8, 6, 5, 7] (Q5-8 are axis-aligned).
    "Boring Bar": [3, 4, 8],
    "Threading External": [6],     # symmetric insert pointing at the centreline
    "Threading Internal": [8],     # symmetric insert pointing at the bore wall
    "Grooving/Parting": [2, 1, 6], # OD blade: chuck-side, tailstock-side corner, centre
    "Knurling": [9],
    "Custom": [1, 2, 3, 4, 5, 6, 7, 8, 9],
}

TYPE_INSERTS: Dict[str, List[str]] = {
    "Turning RH": ["CNMG", "CCMT", "WNMG", "DNMG", "DCMT", "VNMG", "TNMG", "SNMG", "RCMT", "Custom"],
    "Turning LH": ["CNMG", "CCMT", "WNMG", "DNMG", "DCMT", "VNMG", "TNMG", "SNMG", "RCMT", "Custom"],
    "Boring Bar": ["CCMT", "DCMT", "VNMG", "RCMT", "Custom"],
    "Threading External": ["60° UN/Metric", "55° Whitworth", "ACME", "Custom"],
    "Threading Internal": ["60° UN/Metric", "55° Whitworth", "ACME", "Custom"],
    "Grooving/Parting": ["Grooving", "Custom"],
    "Knurling": ["Custom"],
    "Custom": ["CNMG", "CCMT", "WNMG", "DNMG", "DCMT", "VNMG", "TNMG", "SNMG", "RCMT",
               "60° UN/Metric", "55° Whitworth", "ACME", "Grooving", "Custom"],
}


# ---------------------------------------------------------------------------
# Conversion: ToolCardData ↔ ToolDef
# ---------------------------------------------------------------------------

# Mapping from GUI tool_type string to pipeline ToolType enum
_CARD_TYPE_TO_TOOL_TYPE: Dict[str, ToolType] = {
    "Turning RH": ToolType.TURNING,
    "Turning LH": ToolType.TURNING,
    "Boring Bar": ToolType.BORING,
    "Threading External": ToolType.THREADING,
    "Threading Internal": ToolType.THREADING,
    "Grooving/Parting": ToolType.GROOVING,
    "Knurling": ToolType.TURNING,
    "Custom": ToolType.TURNING,
}

# Mapping from GUI tool_type string to pipeline ToolDirection
_CARD_TYPE_TO_DIRECTION: Dict[str, ToolDirection] = {
    "Turning RH": ToolDirection.RIGHT,
    "Turning LH": ToolDirection.LEFT,
    "Boring Bar": ToolDirection.RIGHT,
    "Threading External": ToolDirection.NEUTRAL,
    "Threading Internal": ToolDirection.NEUTRAL,
    "Grooving/Parting": ToolDirection.NEUTRAL,
    "Knurling": ToolDirection.NEUTRAL,
    "Custom": ToolDirection.NEUTRAL,
}


def _tip_angle_from_angles(front_angle: float, back_angle: float) -> float:
    """Derive included tip angle from front and back cutting edge angles.

    The tip angle is the included angle at the tool nose — the angular span
    between the front and back cutting edges:
        tip_angle = back_angle - front_angle

    For a round insert (0, 0) this returns 0 (no angular tip).
    """
    if front_angle == 0.0 and back_angle == 0.0:
        return 0.0  # Round insert — no angular tip
    return back_angle - front_angle


def tool_card_to_tool_def(card: ToolCardData) -> ToolDef:
    """Convert GUI card data to pipeline ToolDef for CAM operations.

    Key conversions:
        - x_offset: ToolCardData stores RADIUS, ToolDef stores DIAMETER → multiply by 2
        - x_wear: ToolCardData stores RADIUS, ToolDef stores DIAMETER → multiply by 2
        - orientation: int → ToolOrientation enum
        - tool_type: string → ToolType enum
        - front/back angles → tip_angle (included angle)
    """
    return ToolDef(
        tool_number=card.tool_number,
        nose_radius=card.nose_radius,
        tip_angle=_tip_angle_from_angles(card.front_angle, card.back_angle),
        edge_length=0.0,  # Not tracked in GUI card
        orientation=ToolOrientation(card.orientation),
        direction=_CARD_TYPE_TO_DIRECTION.get(card.tool_type, ToolDirection.NEUTRAL),
        tool_type=_CARD_TYPE_TO_TOOL_TYPE.get(card.tool_type, ToolType.TURNING),
        rotation=0.0,
        description=card.description,
        x_offset=card.x_offset * 2.0,   # radius → diameter
        z_offset=card.z_offset,
        x_wear=card.x_wear * 2.0,       # radius → diameter
        z_wear=card.z_wear,
        front_angle=card.front_angle,
        back_angle=card.back_angle,
    )


# Reverse mapping: pipeline ToolType → default GUI tool_type string
_TOOL_TYPE_TO_CARD_TYPE: Dict[ToolType, str] = {
    ToolType.TURNING: "Turning RH",
    ToolType.BORING: "Boring Bar",
    ToolType.THREADING: "Threading External",
    ToolType.GROOVING: "Grooving/Parting",
}


def tool_def_to_tool_card(tool: ToolDef) -> ToolCardData:
    """Convert pipeline ToolDef to GUI card data.

    Applies defaults for GUI-only fields not present in ToolDef:
        - insert_code defaults to first valid insert for the derived tool type
        - front_angle/back_angle default to 0.0 (user should select insert to auto-fill)
        - blade_width defaults to 0.0

    Key conversions:
        - x_offset: ToolDef stores DIAMETER, ToolCardData stores RADIUS → divide by 2
        - x_wear: ToolDef stores DIAMETER, ToolCardData stores RADIUS → divide by 2
        - orientation: ToolOrientation enum → int
        - tool_type: ToolType enum + direction → string
    """
    # Determine GUI tool_type from pipeline ToolType + direction
    if tool.tool_type == ToolType.TURNING:
        if tool.direction == ToolDirection.LEFT:
            card_type = "Turning LH"
        else:
            card_type = "Turning RH"
    else:
        card_type = _TOOL_TYPE_TO_CARD_TYPE.get(tool.tool_type, "Custom")

    # Default insert code: first valid insert for the derived type
    valid_inserts = TYPE_INSERTS.get(card_type, ["CNMG"])
    default_insert = valid_inserts[0] if valid_inserts else "CNMG"

    return ToolCardData(
        tool_number=tool.tool_number,
        tool_type=card_type,
        insert_code=default_insert,
        orientation=tool.orientation.value,
        description=tool.description,
        nose_radius=tool.nose_radius,
        front_angle=tool.front_angle,   # 0 when unknown; user selects insert
        back_angle=tool.back_angle,
        x_offset=tool.x_offset / 2.0,   # diameter → radius
        z_offset=tool.z_offset,
        x_wear=tool.x_wear / 2.0,       # diameter → radius
        z_wear=tool.z_wear,
        blade_width=0.0,
    )


def insert_spec(card: ToolCardData):
    """InsertSpec for the true-scale graphic (tool-graphic plan 2026-11-13).

    Size: the IC field when set, else the IC read from a full ISO code
    (owner: both), else 0 = unknown (drawn at a nominal size, labelled).
    Body shape: the ISO code's shape letter, else the insert family's.
    """
    from models.tool import InsertSpec
    from tools.insert_geometry_lookup import INSERT_SHAPE, parse_iso_code
    iso = parse_iso_code(card.iso_code) if card.iso_code else None
    if card.tool_type == "Grooving/Parting" or card.insert_code == "Grooving":
        shape = "groove"
    elif iso:
        shape = iso[0]
    else:
        shape = INSERT_SHAPE.get(card.insert_code, "custom")
    ic = card.ic if card.ic > 0 else (iso[1] if iso and shape != "groove" else 0.0)
    return InsertSpec(orientation=card.orientation, nose_radius=card.nose_radius,
                      front_angle=card.front_angle, back_angle=card.back_angle,
                      shape=shape, ic=ic, blade_width=card.blade_width)


def iso_radius_mismatch(card: ToolCardData) -> str:
    """A note when the ISO code's nose radius differs from the table's D/2."""
    from tools.insert_geometry_lookup import parse_iso_code
    iso = parse_iso_code(card.iso_code) if card.iso_code else None
    if iso and iso[0] != "R" and abs(iso[2] - card.nose_radius) > 0.0005:
        return (f"{card.iso_code} has a {iso[2]:.4f} nose radius; the tool table has "
                f"{card.nose_radius:.4f}")
    return ""
