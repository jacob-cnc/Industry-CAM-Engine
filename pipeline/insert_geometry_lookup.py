"""Insert Geometry Lookup — maps insert codes to front/back cutting edge angles.

Each entry maps an ISO insert designation (or special insert type) to a
(front_angle, back_angle) tuple in degrees. These angles are used for
cutter compensation calculations and orientation graphic rendering.
"""

from typing import Dict, Tuple

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
