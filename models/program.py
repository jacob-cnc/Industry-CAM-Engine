"""Multi-block program data structures for Industry CAM Engine.

Defines threading, grooving, and program block types for the
multi-operation conversational programming system.

Zero external dependencies.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class ThreadingParams:
    """Parameters for a threading operation (G76 cycle).

    Thread geometry is computed from standard + designation lookup,
    but all fields are user-overridable.

    Coordinates:
        major_diameter: Thread major diameter (DIAMETER, inches)
        pitch: Distance per revolution (inches). Computed as 1/TPI for inch threads.
        thread_depth: Full thread depth (RADIUS, inches). Computed from standard formula.
        start_z: Z position where threading begins (inches)
        end_z: Z position where threading ends (inches, more negative)
        taper_amount: For NPT — taper per inch on diameter (inches/inch). 0 for parallel.
    """
    # Thread identification
    thread_standard: str        # "UNC", "UNF", "UNEF", "NPT", "Metric", "ACME"
    designation: str            # "1/2-13 UNC", "M10x1.5", etc. (display label)

    # Core geometry
    major_diameter: float       # Thread major OD (DIAMETER, inches)
    pitch: float                # Distance per revolution (inches)
    thread_depth: float         # Full thread depth (RADIUS, inches)

    # Z extent
    start_z: float              # Where threading begins (Z position)
    end_z: float                # Where threading ends (more negative Z)

    # Cycle parameters
    infeed_method: str          # "radial", "flank", "modified_flank", "alternating"
    num_passes: int             # Number of cutting passes (excluding spring passes)
    spring_passes: int          # Passes at full depth with no additional infeed
    chamfer_threads: float      # Pullout chamfer amount (0, 0.5, 1.0, 1.5 threads)

    # Mode
    is_internal: bool           # True = ID (bore) threading, False = OD (external)

    # Machine settings
    spindle_rpm: float
    tool_number: int

    # Advanced
    num_starts: int = 1         # Multi-start thread (lead = pitch * num_starts)
    taper_amount: float = 0.0   # NPT taper (inches per inch on diameter). 0 = parallel.
    first_pass_depth: float = 0.0  # J word: initial cut depth (0 = auto-compute)
    degression: float = 2.0     # R word: depth degression (2.0 = constant area / sqrt)


@dataclass(frozen=True)
class GroovingParams:
    """Parameters for a grooving or parting operation.

    Grooving is purely radial plunging — no side-cutting.
    For grooves wider than blade width, multiple plunge positions
    are computed automatically.

    Coordinates:
        z_start: Left edge of groove (less negative Z, closer to chuck)
        z_end: Right edge of groove (more negative Z, toward tailstock)
        groove_depth: Radial depth on DIAMETER (inches)
        start_diameter: OD at groove location (DIAMETER, inches)
        peck_depth: Per-peck radial infeed (DIAMETER, inches)
        peck_retract: Retract between pecks (DIAMETER, inches)
        blade_width: Grooving insert width (inches, along Z axis)
    """
    # Groove type
    groove_type: str            # "single", "multiple", "parting"
    is_internal: bool           # True = ID grooving, False = OD grooving

    # Geometry
    z_start: float              # Left edge Z (less negative)
    z_end: float                # Right edge Z (more negative)
    groove_depth: float         # Radial depth (DIAMETER, inches)
    start_diameter: float       # OD at groove location (DIAMETER, inches)

    # Peck cycle
    peck_enabled: bool
    peck_depth: float           # Per-peck radial infeed (DIAMETER, inches)
    peck_retract: float         # Retract between pecks (DIAMETER, inches)

    # Cutting parameters
    feed: float                 # Radial plunge feed (inches/rev)
    spindle_rpm: float
    tool_number: int
    blade_width: float          # Insert width (inches, along Z)

    @property
    def groove_width(self) -> float:
        """Total groove width along Z axis (always positive)."""
        return abs(self.z_start - self.z_end)

    @property
    def bottom_diameter(self) -> float:
        """Diameter at groove bottom."""
        if self.is_internal:
            return self.start_diameter + self.groove_depth
        else:
            return self.start_diameter - self.groove_depth


@dataclass
class ProgramBlock:
    """One operation in the multi-block program.

    Each block is self-contained with its own type, tool, and parameters.
    The block list defines the execution order.
    """
    block_id: int               # Unique ID for UI tracking (auto-assigned)
    block_type: str             # "od_profile", "id_profile", "threading_od",
                                # "threading_id", "grooving_od", "grooving_id", "parting"
    tool_number: int = 1        # Tool for this block
    enabled: bool = True        # Toggle on/off without deleting
    label: str = ""             # User-editable display name (auto-generated if empty)
    visible: bool = True        # Graph visibility toggle
    params_data: dict = field(default_factory=dict)  # Block-specific field state (segments, stock, etc.)

    @property
    def display_label(self) -> str:
        """Label shown in the block list UI."""
        if self.label:
            return self.label
        # Auto-generate from type
        type_labels = {
            "od_profile": "OD Profile",
            "id_profile": "ID Profile",
            "threading_od": "Threading OD",
            "threading_id": "Threading ID",
            "grooving_od": "Grooving OD",
            "grooving_id": "Grooving ID",
            "parting": "Parting",
        }
        return type_labels.get(self.block_type, self.block_type)

    @property
    def is_profile(self) -> bool:
        """True if this is a profile (turning) block."""
        return self.block_type in ("od_profile", "id_profile")

    @property
    def is_threading(self) -> bool:
        """True if this is a threading block."""
        return self.block_type in ("threading_od", "threading_id")

    @property
    def is_grooving(self) -> bool:
        """True if this is a grooving or parting block."""
        return self.block_type in ("grooving_od", "grooving_id", "parting")
