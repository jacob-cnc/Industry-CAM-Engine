"""Filter cascade logic for tool type → orientation/insert filtering.

When the user changes the Tool Type dropdown, the UI calls these functions
to get the valid options for orientation and insert code dropdowns. If the
current selection is not in the returned list, the UI resets to the first
valid option.

Zero Qt dependencies — pure data layer.
"""

from typing import List

from pipeline.tool_card_data import TYPE_ORIENTATIONS, TYPE_INSERTS


def get_valid_orientations(tool_type: str) -> List[int]:
    """Return valid orientations for the given tool type.

    Returns empty list for unknown types.
    """
    return TYPE_ORIENTATIONS.get(tool_type, [])


def get_valid_inserts(tool_type: str) -> List[str]:
    """Return valid insert codes for the given tool type.

    Returns empty list for unknown types.
    """
    return TYPE_INSERTS.get(tool_type, [])
