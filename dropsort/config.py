"""
Configuration and rules management for DropSort / DockShelf.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Single constant for the application name.
# Renaming this one constant dynamically updates window titles and the SQLite database filename.
APP_NAME: str = "DropShelf"

# Project root directory (where main.py and rules.json reside)
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent

# Database and configuration file paths derived from APP_NAME
DEFAULT_DB_PATH: Path = PROJECT_ROOT / f"{APP_NAME.lower()}.db"
DEFAULT_RULES_PATH: Path = PROJECT_ROOT / "rules.json"


def get_default_watch_folder() -> str:
    """Returns the default Downloads folder path for the current OS user."""
    return str(Path.home() / "Downloads")


def get_default_rules() -> dict[str, Any]:
    """Returns the default rules dictionary conforming to TRD Section 4.1."""
    return {
        "watch_folder": get_default_watch_folder(),
        "custom_rules": [
            {"contains": "CNS", "folder": "College/CNS"}
        ],
        "type_rules": {
            "Documents": ["pdf", "doc", "docx", "txt", "rtf"],
            "Spreadsheets": ["xls", "xlsx", "csv"],
            "Presentations": ["ppt", "pptx"],
            "Images": ["jpg", "jpeg", "png", "gif", "webp", "svg"],
            "Videos": ["mp4", "mkv", "mov", "avi"],
            "Audio": ["mp3", "wav", "m4a", "flac"],
            "Archives": ["zip", "rar", "7z", "tar", "gz"],
            "Installers": ["exe", "msi", "dmg", "pkg", "apk"],
        },
        "fallback_folder": "Other",
        "ignore_extensions": ["crdownload", "part", "tmp", "download", "opdownload"],
        "stability_checks": 3,
        "stability_interval": 0.5,
    }


def _validate_rules_dict(rules: Any) -> bool:
    """Check if the rules object has the required keys and types."""
    if not isinstance(rules, dict):
        return False
    required_keys = ["watch_folder", "custom_rules", "type_rules", "fallback_folder", "ignore_extensions"]
    if not all(k in rules for k in required_keys):
        return False
    if not isinstance(rules["custom_rules"], list) or not isinstance(rules["type_rules"], dict):
        return False
    return True


def load_rules(path: Path | None = None) -> dict[str, Any]:
    """
    Load rules from JSON file.
    If the file is missing or invalid, recreate it from defaults. Never crash.
    """
    target_path = path or DEFAULT_RULES_PATH
    if not target_path.exists():
        logger.info("Rules file %s not found. Creating default rules.", target_path)
        defaults = get_default_rules()
        save_rules(defaults, target_path)
        return defaults

    try:
        with open(target_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not _validate_rules_dict(data):
            raise ValueError("Invalid rules format or missing required keys")
        # Ensure optional stability keys have safe defaults if omitted
        if "stability_checks" not in data or not isinstance(data["stability_checks"], int):
            data["stability_checks"] = 3
        if "stability_interval" not in data or not isinstance(data["stability_interval"], (int, float)):
            data["stability_interval"] = 0.5
        return data
    except Exception as exc:
        logger.warning("Error loading %s (%s). Restoring default rules.", target_path, exc)
        defaults = get_default_rules()
        save_rules(defaults, target_path)
        return defaults


def save_rules(rules: dict[str, Any], path: Path | None = None) -> None:
    """Save rules to JSON file with indentation."""
    target_path = path or DEFAULT_RULES_PATH
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(rules, f, indent=2)


class ThreadSafeRulesManager:
    """
    Thread-safe container for active rules.
    Guarantees that rule updates from the UI thread never race with
    rule lookups performed by background worker threads during moves.
    """

    def __init__(self, rules_path: Path | None = None) -> None:
        self._rules_path = rules_path or DEFAULT_RULES_PATH
        self._lock = threading.RLock()
        self._rules = load_rules(self._rules_path)

    @property
    def rules_path(self) -> Path:
        return self._rules_path

    def get_rules(self) -> dict[str, Any]:
        """Return a copy of the current rules under read-lock protection."""
        with self._lock:
            # Return deep-enough copy of structure
            return {
                "watch_folder": self._rules.get("watch_folder", get_default_watch_folder()),
                "custom_rules": [dict(r) for r in self._rules.get("custom_rules", [])],
                "type_rules": {k: list(v) for k, v in self._rules.get("type_rules", {}).items()},
                "fallback_folder": self._rules.get("fallback_folder", "Other"),
                "ignore_extensions": list(self._rules.get("ignore_extensions", [])),
                "stability_checks": self._rules.get("stability_checks", 3),
                "stability_interval": self._rules.get("stability_interval", 0.5),
            }

    def update_rules(self, new_rules: dict[str, Any]) -> None:
        """Update and persist new rules under write-lock protection."""
        with self._lock:
            save_rules(new_rules, self._rules_path)
            self._rules = new_rules

    def reload(self) -> dict[str, Any]:
        """Reload rules from disk under lock protection."""
        with self._lock:
            self._rules = load_rules(self._rules_path)
            return self.get_rules()
