"""Tool Table Serializer — .tbl file I/O for ToolCardData.

Implements the LinuxCNC-compatible .tbl format with metadata in comments:
    T<n> P<n> X<offset> Z<offset> D<nose_dia> I<front_angle> J<back_angle> Q<orient> ;<metadata>

Metadata is stored as pipe-delimited key=value pairs in the comment field:
    type=turning_rh|insert=CNMG|blade=0.000|desc=CNMG 432 roughing

Key conventions:
    - X in file is applied RADIUS = geometry + wear; GUI entry/display is DIAMETER
    - D field is nose DIAMETER (nose_radius × 2 on save, ÷ 2 on load)
    - Offsets use 6 decimal places; angles use 1 decimal place
    - Wear split is versioned comment metadata; file X/Z remain authoritative totals
    - P (pocket) is always equal to T (tool number) for QCTP

Zero Qt dependencies — pure data layer.
"""

import os
import re
import shutil
import math
import tempfile
from urllib.parse import quote, unquote
from typing import List

from pipeline.tool_card_data import ToolCardData


# ---------------------------------------------------------------------------
# Type encoding: display name ↔ file key
# ---------------------------------------------------------------------------

_TYPE_TO_KEY = {
    "Turning RH": "turning_rh",
    "Turning LH": "turning_lh",
    "Boring Bar": "boring_bar",
    "Threading External": "threading_external",
    "Threading Internal": "threading_internal",
    "Grooving/Parting": "grooving_parting",
    "Knurling": "knurling",
    "Custom": "custom",
}

_KEY_TO_TYPE = {v: k for k, v in _TYPE_TO_KEY.items()}


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def serialize_tool(tool: ToolCardData) -> str:
    """Serialize a single tool to a .tbl format line.

    File X/Z are applied machine-unit totals, geometry plus wear.
    Preserves 6 decimal places for offsets, 1 decimal place for angles.

    Args:
        tool: A ToolCardData instance to serialize.

    Returns:
        A single line string in .tbl format (no trailing newline).
    """
    if tool.tool_number < 1 or tool.orientation not in range(1, 10):
        raise ValueError("Tool number must be positive and orientation must be Q1 through Q9.")
    # Only D is a diameter; X is a radius machine-unit offset.
    x_applied = tool.x_offset + tool.x_wear
    nose_diameter = tool.nose_radius * 2.0

    # Format numeric fields
    x_str = f"{x_applied:+.6f}"
    z_str = f"{tool.z_offset + tool.z_wear:+.6f}"
    d_str = f"{nose_diameter:.6f}"
    i_str = f"{tool.front_angle:.1f}"
    j_str = f"{tool.back_angle:.1f}"

    # Build metadata comment
    type_key = _TYPE_TO_KEY.get(tool.tool_type, "custom")
    blade_str = f"{tool.blade_width:.3f}"
    metadata = (
        f"ice=2|xwear={tool.x_wear:.9f}|zwear={tool.z_wear:.9f}|"
        f"type={type_key}|insert={quote(tool.insert_code, safe=' ')}|blade={blade_str}|"
        f"desc={quote(tool.description, safe=' ')}"
    )
    if not all(math.isfinite(v) for v in (x_applied, tool.z_offset + tool.z_wear,
            nose_diameter, tool.front_angle, tool.back_angle, tool.x_wear, tool.z_wear)):
        raise ValueError("Tool table values must be finite.")
    if len(metadata.encode("utf-8")) > 200:
        raise ValueError("Tool metadata is too long for a reliable LinuxCNC comment round-trip.")

    # Assemble the line
    line = (
        f"T{tool.tool_number} P{tool.tool_number} "
        f"X{x_str} Z{z_str} D{d_str} "
        f"I{i_str} J{j_str} Q{tool.orientation} "
        f";{metadata}"
    )
    # v2.9.6 emctool.h: CANON_TOOL_ENTRY_LEN is 256, including the
    # newline/terminator. Its rewrite pads T/P and prints six decimal angles.
    # Budget that (longer) form too, not just the application comment length.
    rewritten = (
        f"T{tool.tool_number:<3d} P{tool.tool_number:<3d} "
        f"D{nose_diameter:+f} X{x_applied:+f} Z{tool.z_offset + tool.z_wear:+f} "
        f"I{tool.front_angle:+f} J{tool.back_angle:+f} Q{tool.orientation} ;{metadata}\n"
    )
    if max(len((line + "\n").encode("utf-8")), len(rewritten.encode("utf-8"))) >= 256:
        raise ValueError("Tool entry exceeds LinuxCNC's 256-byte line/rewrite limit; shorten its description.")
    return line


# ---------------------------------------------------------------------------
# Deserialization
# ---------------------------------------------------------------------------

class LegacyToolTableError(ValueError):
    """An old application table contains X values with ambiguous units."""


def deserialize_tool(line: str, *, unversioned_x_units: str | None = None) -> ToolCardData:
    """Read LinuxCNC machine units, including reordered/omitted zero fields.

    X/Z are authoritative applied totals. Retained wear metadata is subtracted
    to recover geometry even after LinuxCNC G10 L1 rewrites the table.
    """
    numeric, _, comment = line.strip().partition(";")
    words = {}
    for token in numeric.split():
        match = re.fullmatch(r"([A-Z])([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?)", token, re.I)
        if not match:
            raise ValueError(f"Malformed tool table token: {token!r}")
        key, value = match.group(1).upper(), float(match.group(2))
        if key in words or not math.isfinite(value):
            raise ValueError("Duplicate or non-finite tool table field.")
        if key not in "TPXYZABCUVWDIJQ":
            raise ValueError(f"Unsupported tool table field: {key}")
        words[key] = value
    if "T" not in words or words["T"] < 1 or not words["T"].is_integer():
        raise ValueError("Tool table row requires a positive integer T number.")
    if any(value != 0 for key, value in words.items() if key in "YABCUVW"):
        raise ValueError("This two-axis tool editor cannot preserve nonzero extra-axis offsets.")
    if words.get("P", words["T"]) != words["T"]:
        raise ValueError("This QCTP editor requires pocket P equal to tool T; refusing to remap pockets.")
    if words.get("Q", 0) not in range(1, 10):
        raise ValueError("This lathe editor requires an orientation Q1 through Q9.")
    metadata = _parse_metadata(comment.strip())
    version = metadata.get("ice")
    applied_x, applied_z = words.get("X", 0.0), words.get("Z", 0.0)
    if unversioned_x_units not in (None, "radius", "diameter"):
        raise ValueError("Unversioned X units must be explicitly radius or diameter.")
    if version is None and applied_x != 0:
        if unversioned_x_units is None:
            raise LegacyToolTableError(
                "Unversioned tool table has nonzero X with ambiguous diameter/radius units. "
                "Back it up, explicitly load with unversioned_x_units='radius' or 'diameter' "
                "after reconciling with the machine, then save to versioned format."
            )
        if unversioned_x_units == "diameter":
            applied_x /= 2.0
    if version not in (None, "2"):
        raise ValueError(f"Unsupported tool metadata version: {version}")
    if version and not all(key in metadata for key in ("xwear", "zwear")):
        raise ValueError("Tool wear metadata is incomplete; refusing to guess the geometry/wear split.")
    x_wear = float(metadata["xwear"]) if version else 0.0
    z_wear = float(metadata["zwear"]) if version else 0.0
    if not math.isfinite(x_wear) or not math.isfinite(z_wear):
        raise ValueError("Wear values must be finite.")
    return ToolCardData(
        tool_number=int(words["T"]),
        tool_type=_KEY_TO_TYPE.get(metadata.get("type", ""), "Turning RH"),
        insert_code=unquote(metadata.get("insert", "CNMG")) if version else metadata.get("insert", "CNMG"),
        orientation=int(words.get("Q", 0)),
        description=unquote(metadata.get("desc", "")) if version else metadata.get("desc", comment.strip() if not metadata else ""),
        nose_radius=words.get("D", 0.0) / 2.0,
        front_angle=words.get("I", 0.0), back_angle=words.get("J", 0.0),
        x_offset=applied_x - x_wear, z_offset=applied_z - z_wear,
        x_wear=x_wear, z_wear=z_wear,
        blade_width=_safe_float(metadata.get("blade", ""), 0.0),
    )


def _parse_metadata(comment: str) -> dict:
    """Parse pipe-delimited key=value metadata from a comment string.

    Args:
        comment: The comment portion after the semicolon.

    Returns:
        Dictionary of metadata key-value pairs.
    """
    result = {}
    if not comment:
        return result
    for pair in comment.split("|"):
        if "=" in pair:
            key, _, value = pair.partition("=")
            result[key.strip()] = value
    return result


def _safe_float(value: str, default: float) -> float:
    """Convert a string to float, returning default on failure."""
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------

def save_tool_table(tools: List[ToolCardData], path: str) -> None:
    """Save a list of tools to a .tbl file.

    Each tool is serialized to one line. The file is written atomically
    (write to temp, then rename) to prevent corruption on crash.

    Args:
        tools: List of ToolCardData instances to save.
        path: Destination file path.
    """
    if len({tool.tool_number for tool in tools}) != len(tools):
        raise ValueError("Duplicate tool numbers are not allowed.")
    lines = [serialize_tool(tool) for tool in tools]
    content = "\n".join(lines) + "\n" if lines else ""

    # Write atomically: write to a temp file in the same directory, then rename
    dir_path = os.path.dirname(path) or "."
    os.makedirs(dir_path, exist_ok=True)
    descriptor, tmp_path = tempfile.mkstemp(prefix=".tool-table-", dir=dir_path)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def load_tool_table(path: str, *, unversioned_x_units: str | None = None) -> List[ToolCardData]:
    """Load tools from a .tbl file.

    Skips blank/comment/non-tool lines. A malformed real tool row or ambiguous
    nonzero legacy X stops loading rather than silently dropping an offset.
    unversioned_x_units is an explicit offline migration choice, never guessed.

    Args:
        path: Path to the .tbl file.

    Returns:
        List of ToolCardData instances parsed from valid lines.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    tools: List[ToolCardData] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith(";"):
                continue
            try:
                tool = deserialize_tool(stripped, unversioned_x_units=unversioned_x_units)
                if any(existing.tool_number == tool.tool_number for existing in tools):
                    raise ValueError(f"Duplicate tool number T{tool.tool_number}.")
                tools.append(tool)
            except (ValueError, KeyError):
                # Never silently drop a real tool or an ambiguous legacy row.
                if re.match(r"T\d", stripped, re.I):
                    raise
                continue
    return tools


def create_backup(source_path: str) -> str:
    """Create a .bak backup of the source file.

    Args:
        source_path: Path to the file to back up.

    Returns:
        The path to the created backup file.

    Raises:
        FileNotFoundError: If source_path does not exist.
    """
    if not os.path.exists(source_path):
        raise FileNotFoundError(f"Cannot back up non-existent file: {source_path}")
    backup_path = source_path + ".bak"
    suffix = 1
    while os.path.exists(backup_path):
        backup_path = source_path + f".bak.{suffix}"
        suffix += 1
    shutil.copy2(source_path, backup_path)
    return backup_path
