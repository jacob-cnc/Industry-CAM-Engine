"""Read back the stock the writer put in a program's header (outputs/gcode_writer.py).

The header is how a G-code file opened on its own (Run / Edit tab) says what
bar it was made for:

    ; Units: inch            (or "metric (mm)")
    ; Mode: OD               (or ID)
    ; === STOCK ===
    ; Diameter: 2.0000
    ; Z Start: 0.1000
    ; Z End: -1.0000
    ; Pilot Hole Dia: 2.8700 (ID only)
    ; Stock Face Z: 0.0000   (from 2026-11-13: Z Start may be approach only)

A program without this header (hand-written, another CAM) has no stock:
stock_from_header returns None and the caller says so - it is never guessed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

MM = 25.4


@dataclass(frozen=True)
class HeaderStock:
    mode_id: bool
    diameter: float          # inches
    z_start: float
    z_end: float
    pilot_hole_dia: float = 0.0
    face_z: Optional[float] = None   # "; Stock Face Z:" (programs from 2026-11-13 on)

    @property
    def face_known(self) -> bool:
        return self.face_z is not None

    def rect(self):
        """(r_in, r_out, z_back, z_front) of the bar, radius. As
        validation/cut_regions.stock_polygon: OD from the axis, ID from the
        pilot hole; front at the header's stock face, or for older programs
        without that line at Z start (never behind Z0); back at Z end."""
        r_in = self.pilot_hole_dia / 2.0 if self.mode_id else 0.0
        front = self.face_z if self.face_z is not None else max(self.z_start, 0.0)
        return (r_in, self.diameter / 2.0, self.z_end, front)


def _value(text: str, label: str) -> Optional[float]:
    m = re.search(rf"^\s*;\s*{re.escape(label)}:\s*([-+]?\d*\.?\d+)", text, re.M | re.I)
    return float(m.group(1)) if m else None


def stock_from_header(gcode: str) -> Optional[HeaderStock]:
    """The FIRST block's stock from the header, or None without one."""
    head = gcode.split("=== TOOL ===", 1)[0]
    if not re.search(r"^\s*;\s*===\s*STOCK\s*===", head, re.M | re.I):
        return None
    dia, z0, z1 = (_value(head, k) for k in ("Diameter", "Z Start", "Z End"))
    if dia is None or z0 is None or z1 is None or dia <= 0 or z1 >= max(z0, 0.0):
        return None
    mode = re.search(r"^\s*;\s*Mode:\s*(\w+)", head, re.M | re.I)
    mode_id = bool(mode and mode.group(1).upper() == "ID")
    pilot = _value(head, "Pilot Hole Dia") or 0.0
    if mode_id and not (0 < pilot < dia):
        return None
    scale = 1.0 / MM if re.search(r"^\s*;\s*Units:\s*metric", head, re.M | re.I) else 1.0
    face = _value(head, "Stock Face Z")
    return HeaderStock(mode_id, dia * scale, z0 * scale, z1 * scale, pilot * scale,
                       None if face is None else face * scale)
