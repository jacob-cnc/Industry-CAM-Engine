"""INI File I/O — Regex-based load/save preserving comments and formatting.

LinuxCNC INI files have quirks that configparser doesn't handle well:
    - Inline comments (# after value)
    - Duplicate keys in different sections
    - Specific whitespace formatting operators expect

This module uses regex line-by-line parsing to read values and in-place
replacement to write them, preserving the original file structure.

Usage:
    values = load_ini_section("industry-cam.ini", "JOINT_0")
    save_ini_value("industry-cam.ini", "JOINT_0", "P", "1200.0")
"""

import os
import re
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def load_ini_section(ini_path: str, section_name: str) -> Dict[str, str]:
    """Load all key=value pairs from an INI section.

    Args:
        ini_path: Path to the INI file.
        section_name: Section name without brackets (e.g., 'JOINT_0').

    Returns:
        Dict of {key: value_string} for all keys in the section.
        Empty dict if file not found or section not found.
    """
    result = {}
    if not os.path.isfile(ini_path):
        logger.warning("INI file not found: %s", ini_path)
        return result

    in_section = False
    section_re = re.compile(r'^\[(.+)\]')
    kv_re = re.compile(r'^(\w+)\s*=\s*(.+?)(?:\s*#.*)?$')

    with open(ini_path, 'r') as f:
        for line in f:
            line = line.rstrip('\n')

            m = section_re.match(line)
            if m:
                if m.group(1) == section_name:
                    in_section = True
                elif in_section:
                    break  # Left our section
                else:
                    in_section = False
                continue

            if in_section:
                m = kv_re.match(line)
                if m:
                    result[m.group(1)] = m.group(2).strip()

    return result


def load_ini_value(ini_path: str, section_name: str, key: str) -> Optional[str]:
    """Load a single value from an INI section.

    Args:
        ini_path: Path to the INI file.
        section_name: Section name without brackets.
        key: The key to look up.

    Returns:
        Value as string, or None if not found.
    """
    section = load_ini_section(ini_path, section_name)
    return section.get(key)


def save_ini_value(ini_path: str, section_name: str, key: str, value: str) -> bool:
    """Update a single key=value in an INI file, preserving formatting.

    Replaces the value in-place using regex. If the key doesn't exist
    in the section, appends it at the end of the section.

    Args:
        ini_path: Path to the INI file.
        section_name: Section name without brackets.
        key: The INI key to update.
        value: New value as string.

    Returns:
        True on success, False if file not found.
    """
    if not os.path.isfile(ini_path):
        logger.error("Cannot save — INI file not found: %s", ini_path)
        return False

    with open(ini_path, 'r') as f:
        lines = f.readlines()

    section_re = re.compile(r'^\[(.+)\]')
    kv_re = re.compile(rf'^({re.escape(key)})\s*=\s*(.+?)(\s*#.*)?$')

    in_section = False
    found = False
    new_lines = []

    for line in lines:
        stripped = line.rstrip('\n')

        m = section_re.match(stripped)
        if m:
            if in_section and not found:
                # Key not found in section — append before leaving
                new_lines.append(f"{key} = {value}\n")
                found = True
            in_section = (m.group(1) == section_name)
            new_lines.append(line)
            continue

        if in_section and not found:
            m = kv_re.match(stripped)
            if m:
                # Preserve inline comment
                comment = m.group(3) or ''
                new_lines.append(f"{key} = {value}{comment}\n")
                found = True
                continue

        new_lines.append(line)

    # If section was the last one and key wasn't found
    if in_section and not found:
        new_lines.append(f"{key} = {value}\n")

    with open(ini_path, 'w') as f:
        f.writelines(new_lines)

    logger.info("INI: [%s] %s = %s", section_name, key, value)
    return True


def save_ini_section(ini_path: str, section_name: str,
                     values: Dict[str, str]) -> bool:
    """Save multiple key=value pairs to an INI section.

    Args:
        ini_path: Path to the INI file.
        section_name: Section name without brackets.
        values: Dict of {key: value_string} to write.

    Returns:
        True if all writes succeeded.
    """
    success = True
    for key, value in values.items():
        if not save_ini_value(ini_path, section_name, key, value):
            success = False
    return success
