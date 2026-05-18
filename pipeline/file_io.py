"""File I/O operations for Industry CAM Engine.

Handles save/load for conversational JSON, tool table, G-code, and backups.
No Qt imports — testable without a display.

Imports from: models/
"""

import json
import os
import glob
from datetime import datetime
from typing import List

from models.tool import ToolDef, ToolOrientation, ToolDirection, ToolType


def save_conversational(data: dict, path: str) -> None:
    """Save conversational program as JSON.

    Writes with indent=2 for human readability.
    Updates 'modified' timestamp.
    """
    data["modified"] = datetime.now().isoformat()
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)


def load_conversational(path: str) -> dict:
    """Load conversational program from JSON.

    Returns raw dict — model_builder converts to dataclasses.
    Validates 'version' field for forward compatibility.
    """
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if "version" not in data:
        raise ValueError(f"Conversational file missing 'version' field: {path}")

    return data


def save_gcode(gcode_text: str, path: str) -> None:
    """Save G-code text to .ngc file."""
    with open(path, 'w', encoding='utf-8') as f:
        f.write(gcode_text)


def save_tool_table(tools: List[ToolDef], path: str) -> None:
    """Save tool table in LinuxCNC .tbl format.

    Format: T<num> P<pocket> X<offset_dia> Z<offset> D<tnr_dia> I<front> J<back> Q<orient> ;description
    """
    lines = ["; Tool Table — Industry CAM Engine"]
    lines.append("; T P X Z D I J Q ;Description")

    for tool in tools:
        tnr_dia = tool.nose_radius * 2.0
        line = (
            f"T{tool.tool_number} P{tool.tool_number} "
            f"X{tool.x_offset:+.6f} Z{tool.z_offset:+.6f} "
            f"D{tnr_dia:.6f} I0 J0 Q{tool.orientation.value} "
            f";{tool.description}"
        )
        lines.append(line)

    with open(path, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines) + "\n")


def load_tool_table(path: str) -> List[ToolDef]:
    """Load tool table from LinuxCNC .tbl format.

    Parses T, P, X, Z, D, Q fields and description after semicolon.
    """
    tools = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith(';'):
                continue

            # Extract description (after semicolon)
            description = ""
            if ';' in line:
                parts = line.split(';', 1)
                line = parts[0].strip()
                description = parts[1].strip()

            # Parse words
            words = {}
            for token in line.split():
                if len(token) >= 2 and token[0].isalpha():
                    letter = token[0].upper()
                    try:
                        value = float(token[1:])
                        words[letter] = value
                    except ValueError:
                        pass

            if 'T' not in words:
                continue

            tool_number = int(words.get('T', 1))
            x_offset = words.get('X', 0.0)
            z_offset = words.get('Z', 0.0)
            tnr_dia = words.get('D', 0.0)
            orientation_val = int(words.get('Q', 1))

            # Map orientation value to enum
            try:
                orientation = ToolOrientation(orientation_val)
            except ValueError:
                orientation = ToolOrientation.OD_FRONT_RIGHT

            tools.append(ToolDef(
                tool_number=tool_number,
                nose_radius=tnr_dia / 2.0,
                tip_angle=80.0,  # Default — not stored in .tbl
                edge_length=0.375,  # Default — not stored in .tbl
                orientation=orientation,
                direction=ToolDirection.RIGHT,  # Default
                description=description,
                x_offset=x_offset,
                z_offset=z_offset,
            ))

    return tools


def create_backup(source_path: str, backup_dir: str, max_backups: int = 5) -> str:
    """Create timestamped backup of a file.

    Filename: {stem}_{YYYY-MM-DD_HHMMSS}{suffix}
    Prunes oldest backups beyond max_backups.

    Returns the backup file path.
    """
    if not os.path.exists(source_path):
        raise FileNotFoundError(f"Source file not found: {source_path}")

    os.makedirs(backup_dir, exist_ok=True)

    # Generate backup filename
    stem = os.path.splitext(os.path.basename(source_path))[0]
    suffix = os.path.splitext(source_path)[1]
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    backup_name = f"{stem}_{timestamp}{suffix}"
    backup_path = os.path.join(backup_dir, backup_name)

    # Copy file
    with open(source_path, 'r', encoding='utf-8') as src:
        content = src.read()
    with open(backup_path, 'w', encoding='utf-8') as dst:
        dst.write(content)

    # Prune old backups
    pattern = os.path.join(backup_dir, f"{stem}_*{suffix}")
    existing = sorted(glob.glob(pattern))
    while len(existing) > max_backups:
        os.remove(existing.pop(0))

    return backup_path
