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

TYPE_ORIENTATIONS: Dict[str, List[int]] = {
    "Turning RH": [2, 1, 3, 4],
    "Turning LH": [4, 3, 1, 2],
    "Boring Bar": [8, 6, 5, 7],
    "Threading External": [2, 1],
    "Threading Internal": [6, 5],
    "Grooving/Parting": [2, 6, 1, 5],
    "Knurling": [9],
    "Custom": [1, 2, 3, 4, 5, 6, 7, 8, 9],
}

TYPE_INSERTS: Dict[str, List[str]] = {
    "Turning RH": ["CNMG", "CCMT", "WNMG", "DNMG", "DCMT", "VNMG", "TNMG", "SNMG", "RCMT"],
    "Turning LH": ["CNMG", "CCMT", "WNMG", "DNMG", "DCMT", "VNMG", "TNMG", "SNMG", "RCMT"],
    "Boring Bar": ["CCMT", "DCMT", "VNMG", "RCMT"],
    "Threading External": ["60° UN/Metric", "55° Whitworth", "ACME"],
    "Threading Internal": ["60° UN/Metric", "55° Whitworth", "ACME"],
    "Grooving/Parting": ["Grooving"],
    "Knurling": ["Custom"],
    "Custom": ["CNMG", "CCMT", "WNMG", "DNMG", "DCMT", "VNMG", "TNMG", "SNMG", "RCMT",
               "60° UN/Metric", "55° Whitworth", "ACME", "Grooving"],
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
        front_angle=0.0,   # Not derivable from tip_angle alone; user selects insert
        back_angle=0.0,
        x_offset=tool.x_offset / 2.0,   # diameter → radius
        z_offset=tool.z_offset,
        x_wear=tool.x_wear / 2.0,       # diameter → radius
        z_wear=tool.z_wear,
        blade_width=0.0,
    )
