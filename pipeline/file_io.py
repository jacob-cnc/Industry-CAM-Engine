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
    """Save via the canonical machine-unit serializer, including wear metadata."""
    from pipeline.tool_card_data import tool_def_to_tool_card
    from pipeline.tool_table_io import save_tool_table as save_cards
    save_cards([tool_def_to_tool_card(tool) for tool in tools], path)


def load_tool_table(path: str) -> List[ToolDef]:
    """Read through the same canonical serializer as the tool editor."""
    from pipeline.tool_card_data import tool_card_to_tool_def
    from pipeline.tool_table_io import load_tool_table as load_cards
    return [tool_card_to_tool_def(card) for card in load_cards(path)]


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
