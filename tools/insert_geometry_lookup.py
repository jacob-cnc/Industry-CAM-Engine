"""Insert Geometry Lookup — maps insert codes to front/back cutting edge angles.

Each entry maps an ISO insert designation (or special insert type) to a
(front_angle, back_angle) tuple in degrees. These angles are used for
cutter compensation calculations and orientation graphic rendering.
"""

import re
from typing import Dict, Optional, Tuple

# Mapping of insert code → (front_angle_degrees, back_angle_degrees)
INSERT_GEOMETRY: Dict[str, Tuple[float, float]] = {
    "CNMG": (95.0, 175.0),
    "CCMT": (95.0, 175.0),
    "WNMG": (95.0, 175.0),
    "DNMG": (62.5, 117.5),
    "DCMT": (62.5, 117.5),
    "VNMG": (72.5, 107.5),
    "TNMG": (60.0, 120.0),
    "SNMG": (45.0, 135.0),
    "RCMT": (0.0, 0.0),
    "60° UN/Metric": (60.0, 120.0),
    "55° Whitworth": (62.5, 117.5),
    "ACME": (75.5, 104.5),
    "Grooving": (0.0, 0.0),
}


def get_angles(insert_code: str) -> Tuple[float, float]:
    """Return (front_angle, back_angle) for the given insert code.

    Args:
        insert_code: An ISO insert designation or special type name
                     (e.g. "CNMG", "60° UN/Metric", "Grooving").

    Returns:
        Tuple of (front_angle, back_angle) in degrees.

    Raises:
        KeyError: If insert_code is not found in INSERT_GEOMETRY.
    """
    return INSERT_GEOMETRY[insert_code]


# ---------------------------------------------------------------------------
# Insert body shape and size (tool-graphic plan 2026-11-13)
# ---------------------------------------------------------------------------

# Insert family (the editor's insert list) -> body shape for the screen graphic.
INSERT_SHAPE: Dict[str, str] = {
    "CNMG": "C", "CCMT": "C", "WNMG": "W", "DNMG": "D", "DCMT": "D", "VNMG": "V",
    "TNMG": "T", "SNMG": "S", "RCMT": "R",
    "60° UN/Metric": "thread", "55° Whitworth": "thread", "ACME": "thread",
    "Grooving": "groove",
}

# ISO 1832 metric size digits (cutting-edge length, mm) -> inscribed circle, mm.
# Only the common sizes; an unlisted one is "size unknown", never guessed.
_METRIC_IC_MM: Dict[str, Dict[str, float]] = {
    "C": {"06": 6.35, "09": 9.525, "12": 12.7, "16": 15.875, "19": 19.05},
    "D": {"07": 6.35, "11": 9.525, "15": 12.7},
    "V": {"11": 6.35, "16": 9.525, "22": 12.7},
    "T": {"11": 6.35, "16": 9.525, "22": 12.7, "27": 15.875},
    "S": {"09": 9.525, "12": 12.7, "15": 15.875, "19": 19.05},
    "W": {"06": 9.525, "08": 12.7},
}


def parse_iso_code(code: str) -> Optional[Tuple[str, float, float]]:
    """(shape letter, IC inches, nose radius inches) from a full ISO insert code,
    or None when the code doesn't carry a size.

    Inch (ANSI B212.4): CNMG432 -> IC 4/8" = .500, nose radius 2/64" = .03125.
    Metric (ISO 1832): CNMG120408 -> edge 12 mm (IC 12.7 mm), radius 0.8 mm.
    Round inserts: RCMT32 (inch, IC 3/8"), RCMT1204 (metric, 12 mm diameter).
    """
    c = (code or "").upper().replace(" ", "").replace("-", "")
    head = re.match(r"^([CDVTSWR])[A-Z]{3}([0-9T.]+)", c)
    if not head:
        return None
    shape, tok = head.group(1), head.group(2)
    if shape == "R":
        if re.fullmatch(r"\d{4}", tok[:4]) and len(tok) >= 4:      # metric: diameter mm
            d = int(tok[:2]) / 25.4
            return ("R", d, d / 2.0)
        if re.fullmatch(r"\d\d(\.5)?", tok):                    # inch: IC in 1/8"
            ic = int(tok[0]) / 8.0
            return ("R", ic, ic / 2.0) if ic > 0 else None
        return None
    m = re.fullmatch(r"(\d{2})([0-9T]\d)(\d{2})", tok[:6]) if len(tok) >= 6 else None
    if m:                                                          # metric
        ic_mm = _METRIC_IC_MM.get(shape, {}).get(m.group(1))
        if ic_mm is None:
            return None
        return (shape, ic_mm / 25.4, int(m.group(3)) / 10.0 / 25.4)
    m = re.fullmatch(r"(\d)(\d(?:\.5)?)(\d)", tok)
    if m and int(m.group(1)) > 0:                                  # inch
        return (shape, int(m.group(1)) / 8.0, int(m.group(3)) / 64.0)
    return None
