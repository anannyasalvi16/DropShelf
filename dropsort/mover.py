"""
Safe file moving and collision-handling module for DropSort / DockShelf.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


def safe_move(src: Path, dest_dir: Path) -> Path:
    """
    Safely moves a file from src to dest_dir without ever overwriting an existing file.

    OS Concepts applied:
    - File Operations & Directory Creation: Ensures destination directory exists using mkdir(parents=True).
    - Inode / Directory Entry Rename: Uses shutil.move which translates to os.replace / rename
      within the same filesystem or copy-and-unlink across filesystem boundaries.
    - Non-destructive Collision Resolution: Guarantees no existing file is overwritten by
      generating sequential conflict resolution names: 'name (1).ext', 'name (2).ext', etc.

    Args:
        src: Source file path.
        dest_dir: Destination folder directory path.

    Returns:
        Path of the final moved file.

    Raises:
        FileNotFoundError: If the source file does not exist.
        ValueError: If source is a directory.
        OSError: If permissions or disk errors prevent the move.
    """
    src_path = Path(src).resolve()
    dest_directory = Path(dest_dir).resolve()

    if not src_path.exists():
        raise FileNotFoundError(f"Source file not found: {src_path}")
    if src_path.is_dir():
        raise ValueError(f"Source must be a file, not a directory: {src_path}")

    # Ensure destination folder exists
    dest_directory.mkdir(parents=True, exist_ok=True)

    stem = src_path.stem
    suffix = src_path.suffix
    target = dest_directory / src_path.name

    # Collision resolution: never overwrite existing files
    counter = 1
    while target.exists():
        # Avoid moving onto itself if source and target are the same path
        if target.resolve() == src_path:
            return target

        if suffix:
            candidate_name = f"{stem} ({counter}){suffix}"
        else:
            candidate_name = f"{stem} ({counter})"
        target = dest_directory / candidate_name
        counter += 1

    try:
        shutil.move(str(src_path), str(target))
        logger.info("Successfully moved %s -> %s", src_path.name, target)
        return target
    except Exception as exc:
        logger.error("Failed to move %s to %s: %s", src_path, target, exc)
        raise
