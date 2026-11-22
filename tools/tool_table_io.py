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

from tools.tool_card_data import ToolCardData


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
    "Center Drill": "center_drill",
    "Spot Drill": "spot_drill",
    "Twist Drill": "twist_drill",
    "Reamer": "reamer",
    "Tap": "tap",
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
    if tool.tool_number < 1:
        raise ValueError(
            f"Tool number must be 1 or greater; this tool has T{tool.tool_number}.")
    if tool.orientation not in range(1, 10):
        raise ValueError(
            f"T{tool.tool_number}: orientation must be Q1 through Q9; got "
            f"Q{tool.orientation}. Set the tip orientation on the tool card.")
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
        + (f"iso={quote(tool.iso_code, safe='')}|" if tool.iso_code else "")
        + (f"ic={tool.ic:.4f}|" if tool.ic > 0 else "")
        # Drill metadata (D already carries the drill diameter = nose_radius*2).
        + (f"pointangle={tool.point_angle:.1f}|" if tool.point_angle else "")
        + (f"flute={tool.flute_length:.4f}|" if tool.flute_length else "")
        + (f"maxpeck={tool.max_peck:.4f}|" if tool.max_peck else "")
        + (f"pitch={tool.pitch:.5f}|" if tool.pitch else "")
        + f"desc={quote(tool.description, safe=' ')}"
    )
    _fields = {
        "X offset+wear": x_applied, "Z offset+wear": tool.z_offset + tool.z_wear,
        "nose diameter D": nose_diameter, "front angle I": tool.front_angle,
        "back angle J": tool.back_angle, "X wear": tool.x_wear, "Z wear": tool.z_wear,
    }
    _bad = [f"{name}={value}" for name, value in _fields.items() if not math.isfinite(value)]
    if _bad:
        raise ValueError(
            f"T{tool.tool_number}: these tool values are not real numbers: "
            + ", ".join(_bad) + ". Correct them on the tool card before saving.")
    _meta_len = len(metadata.encode("utf-8"))
    if _meta_len > 200:
        raise ValueError(
            f"T{tool.tool_number}: the description/insert/ISO text needs {_meta_len} bytes "
            "but only 200 fit in a LinuxCNC comment. Shorten the description by about "
            f"{_chars(_meta_len - 200)}.")

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
    _line_len = max(len((line + "\n").encode("utf-8")), len(rewritten.encode("utf-8")))
    if _line_len >= 256:
        raise ValueError(
            f"T{tool.tool_number}: the tool table row needs {_line_len} bytes including its "
            "line ending, but LinuxCNC stores only 255 and would truncate the rest the next "
            "time it rewrites the table (G10 L1), corrupting the row. Shorten the "
            f"description by about {_chars(_line_len - 255)}.")
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
            raise ValueError(
                f"{token!r} is not a tool table word - expected a letter followed by a "
                "number, like X-1.234 or Q3.")
        key, value = match.group(1).upper(), float(match.group(2))
        if key in words:
            raise ValueError(
                f"{key} appears twice in this row ({key}{_num(words[key])} and "
                f"{key}{_num(value)}); LinuxCNC would use only one of them.")
        if not math.isfinite(value):
            raise ValueError(f"{token!r} is not a real number.")
        if key not in "TPXYZABCUVWDIJQ":
            raise ValueError(
                f"{key} is not a LinuxCNC tool table word (expected one of "
                "T P X Y Z A B C U V W D I J Q).")
        words[key] = value
    if "T" not in words:
        raise ValueError("This row has no T word, so there is no tool number to load.")
    if words["T"] < 1 or not words["T"].is_integer():
        raise ValueError(
            f"T{_num(words['T'])} is not a usable tool number - it must be a whole "
            "number of 1 or greater.")
    _extra = sorted(f"{key}{_num(value)}" for key, value in words.items()
                    if key in "YABCUVW" and value != 0)
    if _extra:
        raise ValueError(
            f"T{int(words['T'])} has offsets on axes this two-axis lathe editor cannot "
            f"keep ({', '.join(_extra)}); saving would silently drop them. Edit this row "
            "in a text editor, or zero those words if the machine does not use them.")
    if words.get("P", words["T"]) != words["T"]:
        raise ValueError(
            f"T{int(words['T'])} sits in pocket P{_num(words['P'])}. This QCTP editor "
            "requires P to equal T and will not remap pockets; set "
            f"P{int(words['T'])} for this tool.")
    if words.get("Q", 0) not in range(1, 10):
        _q = f"Q{_num(words['Q'])}" if "Q" in words else "no Q word"
        raise ValueError(
            f"T{int(words['T'])} has {_q}; a lathe tool needs an orientation of Q1 "
            "through Q9 (see the orientation diagram on the Tools tab).")
    metadata = _parse_metadata(comment.strip())
    version = metadata.get("ice")
    applied_x, applied_z = words.get("X", 0.0), words.get("Z", 0.0)
    if unversioned_x_units not in (None, "radius", "diameter"):
        raise ValueError(
            f"unversioned_x_units={unversioned_x_units!r} is not a choice; pass "
            "'radius' or 'diameter' to say how an unversioned table's X is measured.")
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
        raise ValueError(
            f"T{int(words['T'])} was written by a newer tool editor (metadata ice={version}, "
            "this one reads ice=2). Update the application rather than loading this table.")
    if version:
        _missing = [key for key in ("xwear", "zwear") if key not in metadata]
        if _missing:
            raise ValueError(
                f"T{int(words['T'])} is missing its {' and '.join(_missing)} metadata, so the "
                "row's X/Z cannot be split back into geometry and wear. Re-enter this tool's "
                "wear on the Tools tab, or delete the ice=2 comment to load X/Z as pure "
                "geometry with zero wear.")
    try:
        x_wear = float(metadata["xwear"]) if version else 0.0
        z_wear = float(metadata["zwear"]) if version else 0.0
        bad_wear = not (math.isfinite(x_wear) and math.isfinite(z_wear))
    except ValueError:
        bad_wear = True
    if bad_wear:
        raise ValueError(
            f"T{int(words['T'])} has unusable wear metadata (xwear="
            f"{metadata.get('xwear')!r}, zwear={metadata.get('zwear')!r}); both must be "
            "real numbers. Re-enter this tool's wear on the Tools tab.")
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
        iso_code=unquote(metadata.get("iso", "")),
        ic=_safe_float(metadata.get("ic", ""), 0.0),
        point_angle=_safe_float(metadata.get("pointangle", ""), 0.0),
        flute_length=_safe_float(metadata.get("flute", ""), 0.0),
        max_peck=_safe_float(metadata.get("maxpeck", ""), 0.0),
        pitch=_safe_float(metadata.get("pitch", ""), 0.0),
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


def _chars(n: int) -> str:
    """'1 character' / '4 characters' - error text the owner reads should read."""
    return f"{n} character" + ("" if n == 1 else "s")


def _num(value: float) -> str:
    """Format a tool table number the way the file shows it (no trailing .0)."""
    return f"{value:g}"


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
    _seen, _dupes = set(), []
    for tool in tools:
        if tool.tool_number in _seen and tool.tool_number not in _dupes:
            _dupes.append(tool.tool_number)
        _seen.add(tool.tool_number)
    if _dupes:
        raise ValueError(
            "Two tools cannot share a number: "
            + ", ".join(f"T{n}" for n in sorted(_dupes))
            + f" {'appears' if len(_dupes) == 1 else 'appear'} more than once. "
            "Renumber or delete the duplicate before saving.")
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
        for number, line in enumerate(f, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith(";"):
                continue
            try:
                tool = deserialize_tool(stripped, unversioned_x_units=unversioned_x_units)
                if any(existing.tool_number == tool.tool_number for existing in tools):
                    raise ValueError(
                        f"T{tool.tool_number} is already defined earlier in this file; "
                        "two rows cannot describe the same tool.")
                tools.append(tool)
            except (ValueError, KeyError) as exc:
                # Never silently drop a real tool or an ambiguous legacy row. Say which
                # row of which file was rejected - the message is all the owner gets.
                if re.match(r"T\d", stripped, re.I):
                    # Keep LegacyToolTableError so callers can offer the units choice;
                    # anything else reads better to the owner as a plain ValueError.
                    kind = (LegacyToolTableError
                            if isinstance(exc, LegacyToolTableError) else ValueError)
                    raise kind(
                        f"{os.path.basename(path)} line {number} was not loaded: {exc}\n\n"
                        f"  {stripped}"
                    ) from exc
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
