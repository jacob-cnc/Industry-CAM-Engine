"""Multi-block program data structures for Industry CAM Engine.

Defines threading, grooving, and program block types for the
multi-operation conversational programming system.

Zero external dependencies.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ThreadingParams:
    """A threading operation - field driven (owner plan 2026-11-12,
    docs/handoffs/2026-11-12-threading-workflow-plan.md).

    Diameters in inches. X start / X end are the NOMINAL MAJOR at Z start / Z end
    (equal = straight, different = taper). The cut depth is never typed: the
    thread data (models/thread_data.py) gives ``root_offset`` = root - X for the
    chosen standard and class (Custom: the form's basic depth), so

        external   crest = X              root = X + root_offset   (root_offset < 0)
        internal   crest = pilot (tap drill)  root = X + root_offset (>= 0)

    Z end is where the tool pulls out (no pull-out chamfer). RH only.
    """
    designation: str            # "1/4-20 UNC", "M6x1", ... or "Custom"
    thread_type: str            # "UNC", ..., "NPT" or "Custom"
    thread_class: str           # "2A", "6H", "2G", ... ("" for NPT / Custom)
    form: str                   # thread_data.FORMS key: "60", "acme", "tr", "npt"
    is_internal: bool
    x_start: float              # nominal major at Z start (DIAMETER)
    x_end: float                # nominal major at Z end (DIAMETER)
    start_z: float
    end_z: float                # where the tool pulls out
    pitch: float                # inches per thread
    root_offset: float          # root - X (DIAMETER), from the standard / class
    pilot_dia: float            # internal: the crest (tap drill); 0 for external
    num_passes: int
    spring_passes: int
    num_starts: int
    entry_angle: float          # compound infeed angle (G76 Q), degrees
    spindle_rpm: float
    tool_number: int
    degression: float = 2.0     # G76 R: 2.0 = constant area per pass (LinuxCNC)

    @property
    def is_taper(self) -> bool:
        return abs(self.x_end - self.x_start) > 1e-9

    @property
    def lead(self) -> float:
        return self.pitch * max(1, int(self.num_starts))

    def root_at(self, x: float) -> float:
        return x + self.root_offset

    def crest_at(self, x: float, form_depth: float) -> float:
        """Crest diameter where the nominal major is x. Internal straight threads
        use the pilot; internal tapers follow the root line (form depth)."""
        if not self.is_internal:
            return x
        if not self.is_taper:
            return self.pilot_dia
        return self.root_at(x) - 2.0 * form_depth


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
