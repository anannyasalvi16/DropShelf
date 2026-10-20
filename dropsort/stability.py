"""
File stability checker for DropSort / DockShelf.
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)


def wait_until_stable(
    path: Path,
    interval: float = 0.5,
    stable_checks: int = 3,
    timeout: float = 300.0,
) -> bool:
    """
    Decides whether a file has finished being written by another process (e.g. browser).

    OS Concepts applied:
    - File Metadata & Attributes: Uses stat() to check file size (st_size) and last modified
      time (st_mtime_ns) to verify whether writes are still actively occurring.
    - File Locking / In-Use Detection: On Windows, attempts to open the file in append
      binary mode ('ab'). If the operating system or browser holds an exclusive write lock,
      Windows raises PermissionError (ERROR_SHARING_VIOLATION), indicating active download.
    - Race Condition Prevention: Prevents premature moves while write buffers are flushing.

    Args:
        path: Path to the candidate file.
        interval: Time in seconds between polling checks.
        stable_checks: Number of consecutive identical checks required to declare stability.
        timeout: Maximum duration in seconds to wait before giving up.

    Returns:
        True if the file is stable and ready to move, False if missing or timed out.
    """
    path = Path(path)
    start_time = time.monotonic()
    consecutive_matches = 0
    last_stat: tuple[int, int] | None = None

    while True:
        # Check if total waiting duration exceeded timeout
        if time.monotonic() - start_time > timeout:
            logger.warning("File stability check timed out for %s", path)
            return False

        # If file does not exist, it was removed or deleted by another process
        if not path.is_file():
            return False

        try:
            # Query OS file metadata
            stat_res = path.stat()
            current_stat = (stat_res.st_size, stat_res.st_mtime_ns)

            # On Windows: Check if file is locked or in use by another process
            if sys.platform == "win32":
                try:
                    with open(path, "ab"):
                        pass
                    # Probe whether another process holds an open file handle without FILE_SHARE_DELETE.
                    # On Windows, attempting to rename an actively open file raises PermissionError (WinError 32).
                    import os
                    os.rename(path, path)
                except (PermissionError, OSError):
                    # File is currently locked or in use by another process (e.g. browser writing)
                    consecutive_matches = 0
                    time.sleep(interval)
                    continue

            # Check if metadata matches previous check
            if last_stat is not None and current_stat == last_stat:
                consecutive_matches += 1
                if consecutive_matches >= stable_checks:
                    return True
            else:
                consecutive_matches = 1
                last_stat = current_stat

        except (FileNotFoundError, PermissionError, OSError):
            # Transient OS error while file is being created or closed
            consecutive_matches = 0

        time.sleep(interval)
