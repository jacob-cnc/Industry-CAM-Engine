"""G-code parser for Industry CAM Engine.

Parses the engine's own G-code output back into a List[ToolMove].
Intentionally minimal — only handles the subset the writer emits.

Used for:
- Round-trip verification (write → parse → compare)
- Edit Tab preview (parse external .ngc → display)
- G-code to DXF conversion

Imports from: models/ only
"""

import re
from typing import List, Optional

from models.moves import ToolMove, MoveType, PassType


def parse(gcode_text: str) -> List[ToolMove]:
    """Parse G-code text into a List[ToolMove].

    Handles:
    - G00 (rapid), G01 (feed), G02 (CW arc), G03 (CCW arc) — modal
    - X, Z axis words (absolute, diameter mode)
    - I, K (incremental arc center) and R (radius) formats
    - F (feed rate, modal)
    - Comments (parentheses or semicolons — ignored for geometry)

    LinuxCNC interpretation rules:
    - G90 absolute mode assumed
    - I/K incremental from start point
    - Feed rate persists until changed

    Args:
        gcode_text: Complete G-code program as string

    Returns:
        List of ToolMove objects representing all motion commands.
    """
    moves = []
    current_mode: Optional[MoveType] = None
    current_x: Optional[float] = None
    current_z: Optional[float] = None
    current_feed: float = 0.0

    for line in gcode_text.splitlines():
        # Strip comments
        line = _strip_comments(line).strip()
        if not line:
            continue

        # Parse words from the line
        words = _parse_words(line)
        if not words:
            continue

        # Extract G-code mode changes
        g_code = _get_word(words, 'G')
        if g_code is not None:
            g_int = int(g_code)
            if g_int == 0:
                current_mode = MoveType.RAPID
            elif g_int == 1:
                current_mode = MoveType.FEED
            elif g_int == 2:
                current_mode = MoveType.ARC_CW
            elif g_int == 3:
                current_mode = MoveType.ARC_CCW
            # Other G-codes (G20, G40, G41, G42, G90, etc.) — skip, not motion

        # Extract axis words
        x_val = _get_word(words, 'X')
        z_val = _get_word(words, 'Z')
        f_val = _get_word(words, 'F')
        i_val = _get_word(words, 'I')
        k_val = _get_word(words, 'K')
        r_val = _get_word(words, 'R')

        # Update feed rate
        if f_val is not None:
            current_feed = f_val

        # If we have axis motion, create a move
        if x_val is not None or z_val is not None:
            # Apply modal values
            new_x = x_val if x_val is not None else current_x
            new_z = z_val if z_val is not None else current_z

            if new_x is None or new_z is None:
                continue  # Can't create move without position

            if current_mode is None:
                continue  # No motion mode set yet

            # Build the move
            feed = current_feed if current_mode != MoveType.RAPID else 0.0
            radius = 0.0
            center_i = 0.0
            center_k = 0.0

            if current_mode in (MoveType.ARC_CW, MoveType.ARC_CCW):
                if i_val is not None:
                    center_i = i_val
                if k_val is not None:
                    center_k = k_val
                if r_val is not None:
                    radius = r_val if current_mode == MoveType.ARC_CW else -r_val

            move = ToolMove(
                move_type=current_mode,
                x=new_x,
                z=new_z,
                feed=feed,
                radius=radius,
                center_i=center_i,
                center_k=center_k,
                pass_type=PassType.ROUGH,  # Parser doesn't know pass type
                pass_index=0,
            )
            moves.append(move)

            current_x = new_x
            current_z = new_z

    return moves


def _strip_comments(line: str) -> str:
    """Remove comments from a G-code line."""
    # Remove parenthetical comments
    line = re.sub(r'\([^)]*\)', '', line)
    # Remove semicolon comments
    idx = line.find(';')
    if idx >= 0:
        line = line[:idx]
    return line


def _parse_words(line: str) -> List[tuple]:
    """Parse G-code words from a line. Returns list of (letter, value) tuples."""
    words = []
    # Match letter followed by number (with optional sign and decimal)
    pattern = r'([A-Z])([+-]?\d*\.?\d+)'
    for match in re.finditer(pattern, line, re.IGNORECASE):
        letter = match.group(1).upper()
        value = float(match.group(2))
        words.append((letter, value))
    return words


def _get_word(words: List[tuple], letter: str) -> Optional[float]:
    """Get the value of a specific word letter from parsed words."""
    for w_letter, w_value in words:
        if w_letter == letter:
            return w_value
    return None
