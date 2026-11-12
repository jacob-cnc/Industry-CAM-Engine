"""Stock material definition for Industry CAM Engine.

Defines the raw material dimensions and approach/park positions.
Zero external dependencies.
"""

from dataclasses import dataclass
from models.profile import MachiningMode


@dataclass(frozen=True)
class StockDef:
    """Stock material definition and approach/park positions.

    Coordinates:
        diameter: Stock OD in DIAMETER (inches)
        x_start: X approach position / True Face Zone inner boundary (DIAMETER)
        z_start: Z approach position / True Face Zone Z+ boundary (positive, e.g., 0.100)
        z_end: Derived operation cutting depth (inches, negative)
        back_face_z: Physical stock back face; None retains legacy operation extent.
        x_park: X park position (DIAMETER, safe retract)
        z_park: Z park position (inches, safe retract)
        pilot_hole_dia: ID mode pilot hole diameter. 0 = no pilot hole.
    """
    diameter: float
    x_start: float
    z_start: float
    z_end: float
    mode: MachiningMode = MachiningMode.OD
    x_park: float = 3.0
    z_park: float = 3.0
    pilot_hole_dia: float = 0.0
    back_face_z: float | None = None  # Physical stock back face; z_end is operation depth.
    # True when the operator's Z start said the face is already at Z0 (no stock in
    # front); z_start is then only approach clearance (model_builder._safe_z_start).
    face_at_z0: bool = False

    @property
    def physical_z_end(self) -> float:
        return self.z_end if self.back_face_z is None else self.back_face_z
