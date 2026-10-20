"""
Rule matching engine for DropSort / DockShelf.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def destination_for(filename: str, rules: dict[str, Any]) -> str | None:
    """
    Determines the destination subfolder for a given filename based on rules.

    Priority:
    1. Ignore list: returns None if the extension matches ignore_extensions.
    2. Custom rules: first matching case-insensitive 'contains' rule wins.
    3. Type rules: matched by file extension (case-insensitive).
    4. Fallback folder: returned when no custom or type rule matches.

    Args:
        filename: Name or path of the candidate file.
        rules: Active rules dictionary.

    Returns:
        Subfolder relative path as a string, or None if the file should be skipped.
    """
    path = Path(filename)
    basename = path.name

    # Extract extension without leading dot (lowercase)
    ext = path.suffix.lstrip(".").lower()

    # 1. Ignore list check
    raw_ignore = rules.get("ignore_extensions", [])
    ignore_set = {str(item).lstrip(".").lower() for item in raw_ignore if item}
    if ext and ext in ignore_set:
        return None

    # 2. Custom rules check (first match wins, case-insensitive substring on filename)
    name_lower = basename.lower()
    for rule in rules.get("custom_rules", []):
        contains_str = rule.get("contains", "").strip().lower()
        target_folder = rule.get("folder", "").strip()
        if contains_str and target_folder and contains_str in name_lower:
            return target_folder

    # 3. Type rules check (case-insensitive extension match)
    type_rules = rules.get("type_rules", {})
    if ext:
        for folder_name, extensions in type_rules.items():
            ext_list = [str(e).lstrip(".").lower() for e in extensions]
            if ext in ext_list:
                return folder_name

    # 4. Fallback folder
    return rules.get("fallback_folder", "Other")
