"""Tool Table Serializer — .tbl file I/O for ToolCardData.

Implements the LinuxCNC-compatible .tbl format with metadata in comments:
    T<n> P<n> X<offset> Z<offset> D<nose_dia> I<front_angle> J<back_angle> Q<orient> ;<metadata>

Metadata is stored as pipe-delimited key=value pairs in the comment field:
    type=turning_rh|insert=CNMG|blade=0.000|desc=CNMG 432 roughing

Key conventions:
    - X offset in file is DIAMETER; ToolCardData stores RADIUS (×2 on save, ÷2 on load)
    - D field is nose DIAMETER (nose_radius × 2 on save, ÷ 2 on load)
    - Offsets use 6 decimal places; angles use 1 decimal place
    - Wear offsets (x_wear, z_wear) are NOT stored — they are GUI-only
    - P (pocket) is always equal to T (tool number) for QCTP

Zero Qt dependencies — pure data layer.
"""

import os
import re
import shutil
from typing import List, Optional

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

    Converts internal radius values to diameter for the file format.
    Preserves 6 decimal places for offsets, 1 decimal place for angles.

    Args:
        tool: A ToolCardData instance to serialize.

    Returns:
        A single line string in .tbl format (no trailing newline).
    """
    # Convert radius → diameter for X offset and nose radius
    x_diameter = tool.x_offset * 2.0
    nose_diameter = tool.nose_radius * 2.0

    # Format numeric fields
    x_str = f"{x_diameter:+.6f}"
    z_str = f"{tool.z_offset:+.6f}"
    d_str = f"{nose_diameter:.6f}"
    i_str = f"{tool.front_angle:.1f}"
    j_str = f"{tool.back_angle:.1f}"

    # Build metadata comment
    type_key = _TYPE_TO_KEY.get(tool.tool_type, "custom")
    blade_str = f"{tool.blade_width:.3f}"
    metadata = f"type={type_key}|insert={tool.insert_code}|blade={blade_str}|desc={tool.description}"

    # Assemble the line
    line = (
        f"T{tool.tool_number} P{tool.tool_number} "
        f"X{x_str} Z{z_str} D{d_str} "
        f"I{i_str} J{j_str} Q{tool.orientation} "
        f";{metadata}"
    )
    return line


# ---------------------------------------------------------------------------
# Deserialization
# ---------------------------------------------------------------------------

# Regex to parse a .tbl line
_LINE_PATTERN = re.compile(
    r"T(\d+)\s+P(\d+)\s+"
    r"X([+\-]?\d+\.?\d*)\s+"
    r"Z([+\-]?\d+\.?\d*)\s+"
    r"D(\d+\.?\d*)\s+"
    r"I(\d+\.?\d*)\s+"
    r"J(\d+\.?\d*)\s+"
    r"Q(\d+)"
    r"(?:\s*;(.*))?$"
)


def deserialize_tool(line: str) -> ToolCardData:
    """Parse a single .tbl format line into a ToolCardData.

    Converts diameter values from file to radius for internal storage.
    Applies defaults for missing metadata fields.

    Args:
        line: A single line from a .tbl file.

    Returns:
        A ToolCardData instance.

    Raises:
        ValueError: If the line does not match the expected format.
    """
    line = line.strip()
    match = _LINE_PATTERN.match(line)
    if not match:
        raise ValueError(f"Malformed tool table line: {line!r}")

    tool_number = int(match.group(1))
    # pocket = int(match.group(2))  # Not stored separately; always == tool_number
    x_diameter = float(match.group(3))
    z_offset = float(match.group(4))
    nose_diameter = float(match.group(5))
    front_angle = float(match.group(6))
    back_angle = float(match.group(7))
    orientation = int(match.group(8))
    comment = match.group(9) or ""

    # Convert diameter → radius
    x_offset = x_diameter / 2.0
    nose_radius = nose_diameter / 2.0

    # Parse metadata from comment
    metadata = _parse_metadata(comment)

    # Apply defaults for missing metadata
    tool_type = _KEY_TO_TYPE.get(metadata.get("type", ""), "Turning RH")
    insert_code = metadata.get("insert", "CNMG")
    blade_width = _safe_float(metadata.get("blade", ""), 0.0)
    description = metadata.get("desc", "")

    return ToolCardData(
        tool_number=tool_number,
        tool_type=tool_type,
        insert_code=insert_code,
        orientation=orientation,
        description=description,
        nose_radius=nose_radius,
        front_angle=front_angle,
        back_angle=back_angle,
        x_offset=x_offset,
        z_offset=z_offset,
        x_wear=0.0,
        z_wear=0.0,
        blade_width=blade_width,
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
    lines = [serialize_tool(tool) for tool in tools]
    content = "\n".join(lines) + "\n" if lines else ""

    # Write atomically: write to a temp file in the same directory, then rename
    dir_path = os.path.dirname(path) or "."
    os.makedirs(dir_path, exist_ok=True)
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(content)
    # Replace the original file
    if os.path.exists(path):
        os.replace(tmp_path, path)
    else:
        os.rename(tmp_path, path)


def load_tool_table(path: str) -> List[ToolCardData]:
    """Load tools from a .tbl file.

    Skips blank lines and malformed lines (logs a warning but does not raise).

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
            if not stripped:
                continue
            try:
                tool = deserialize_tool(stripped)
                tools.append(tool)
            except ValueError:
                # Skip malformed lines
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
    shutil.copy2(source_path, backup_path)
    return backup_path
