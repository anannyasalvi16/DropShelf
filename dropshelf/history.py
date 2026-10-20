"""
SQLite undo history manager for DropShelf.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import DEFAULT_DB_PATH
from .mover import safe_move

logger = logging.getLogger(__name__)


class HistoryManager:
    """
    Manages persistent SQLite operation history and rollback/undo capabilities.

    OS Concepts applied:
    - Persistence vs Volatile State: History is written to non-volatile secondary storage
      (SQLite database file) rather than main memory, surviving application crashes and restarts.
    - Concurrency Control: SQLite access across worker threads and UI polling is serialized
      using threading.Lock and WAL (Write-Ahead Logging) journal mode to prevent database locks.
    - Atomic State Transitions: Database status updates ('moved' -> 'undone' / 'failed')
      guarantee consistent state following file system rollbacks.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = Path(db_path or DEFAULT_DB_PATH).resolve()
        self._lock = threading.Lock()
        self._init_db()
        self.recover_pending_moves()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        # Enable WAL journal mode for concurrent reads/writes
        conn.execute("PRAGMA journal_mode = WAL;")
        return conn

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS moves (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        original_path TEXT NOT NULL,
                        new_path TEXT NOT NULL,
                        status TEXT NOT NULL CHECK(status IN ('pending', 'moved', 'undone', 'failed')),
                        note TEXT
                    );
                    """
                )
                conn.commit()

                # Migration check: ensure 'note' column exists and 'pending' status is allowed
                cols = [row["name"] for row in conn.execute("PRAGMA table_info(moves);").fetchall()]
                if "note" not in cols:
                    try:
                        conn.execute("ALTER TABLE moves ADD COLUMN note TEXT;")
                        conn.commit()
                    except Exception:
                        pass

                # Verify CHECK constraint allows 'pending'
                try:
                    conn.execute("SAVEPOINT test_pending;")
                    conn.execute(
                        "INSERT INTO moves (timestamp, original_path, new_path, status, note) VALUES ('test', 'test', 'test', 'pending', 'test');"
                    )
                    conn.execute("ROLLBACK TO test_pending;")
                    conn.execute("RELEASE test_pending;")
                except sqlite3.IntegrityError:
                    # Old schema with restrictive CHECK constraint; migrate table
                    conn.execute("ALTER TABLE moves RENAME TO moves_old;")
                    conn.execute(
                        """
                        CREATE TABLE moves (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            timestamp TEXT NOT NULL,
                            original_path TEXT NOT NULL,
                            new_path TEXT NOT NULL,
                            status TEXT NOT NULL CHECK(status IN ('pending', 'moved', 'undone', 'failed')),
                            note TEXT
                        );
                        """
                    )
                    conn.execute(
                        """
                        INSERT INTO moves (id, timestamp, original_path, new_path, status, note)
                        SELECT id, timestamp, original_path, new_path, status, NULL FROM moves_old;
                        """
                    )
                    conn.execute("DROP TABLE moves_old;")
                    conn.commit()

    def record_pending_move(self, original_path: Path | str, new_path: Path | str) -> int:
        """
        Phase 1 of Two-Phase Move: Records an operation as 'pending' BEFORE file I/O begins.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO moves (timestamp, original_path, new_path, status, note)
                    VALUES (?, ?, ?, 'pending', NULL);
                    """,
                    (now_iso, str(Path(original_path).resolve()), str(Path(new_path).resolve())),
                )
                conn.commit()
                return cursor.lastrowid

    def confirm_move(self, move_id: int, final_path: Path | str) -> None:
        """
        Phase 2 of Two-Phase Move: Marks a pending operation as 'moved' after file I/O succeeds.
        """
        with self._lock:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    UPDATE moves
                    SET status = 'moved', new_path = ?, note = NULL
                    WHERE id = ?;
                    """,
                    (str(Path(final_path).resolve()), move_id),
                )
                conn.commit()

    def fail_move(self, move_id: int, note: str = "") -> None:
        """
        Marks an operation as 'failed' if file I/O could not be completed.
        """
        with self._lock:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    UPDATE moves
                    SET status = 'failed', note = ?
                    WHERE id = ?;
                    """,
                    (note, move_id),
                )
                conn.commit()

    def record_move(self, original_path: Path | str, new_path: Path | str) -> int:
        """Atomic helper for recording a completed move operation directly."""
        move_id = self.record_pending_move(original_path, new_path)
        self.confirm_move(move_id, new_path)
        return move_id

    def recover_pending_moves(self) -> list[dict[str, Any]]:
        """
        Startup Recovery for Interrupted Moves:
        Scans for rows that remained 'pending' due to an unexpected crash or power failure.
        - If file exists at new_path and NOT at original_path: move completed before crash -> mark 'moved'.
        - If file still exists at original_path: move never completed -> mark 'failed' with note.
        - If file exists at neither: file was lost/deleted -> mark 'failed' with note.
        """
        recovered = []
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT id, original_path, new_path FROM moves WHERE status = 'pending';"
                )
                pending_rows = [dict(row) for row in cursor.fetchall()]

                for row in pending_rows:
                    move_id = row["id"]
                    orig_p = Path(row["original_path"])
                    new_p = Path(row["new_path"])

                    if new_p.exists() and not orig_p.exists():
                        conn.execute(
                            "UPDATE moves SET status = 'moved', note = 'Recovered on startup' WHERE id = ?;",
                            (move_id,),
                        )
                        row["status"] = "moved"
                        row["note"] = "Recovered on startup"
                    elif orig_p.exists():
                        conn.execute(
                            "UPDATE moves SET status = 'failed', note = 'Interrupted before move completed' WHERE id = ?;",
                            (move_id,),
                        )
                        row["status"] = "failed"
                        row["note"] = "Interrupted before move completed"
                    else:
                        conn.execute(
                            "UPDATE moves SET status = 'failed', note = 'File missing after interruption' WHERE id = ?;",
                            (move_id,),
                        )
                        row["status"] = "failed"
                        row["note"] = "File missing after interruption"

                    recovered.append(row)

                if pending_rows:
                    conn.commit()
                    logger.info("Reconciled %s orphan pending moves on startup.", len(pending_rows))

        return recovered

    def recent(self, limit: int = 200) -> list[dict[str, Any]]:
        """Retrieves the most recent move records (newest first)."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT id, timestamp, original_path, new_path, status, note
                    FROM moves
                    ORDER BY id DESC
                    LIMIT ?;
                    """,
                    (limit,),
                )
                return [dict(row) for row in cursor.fetchall()]

    def get_record(self, move_id: int) -> dict[str, Any] | None:
        """Fetch a single record by ID."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT id, timestamp, original_path, new_path, status, note FROM moves WHERE id = ?;",
                    (move_id,),
                )
                row = cursor.fetchone()
                return dict(row) if row else None

    def undo(self, move_id: int) -> tuple[bool, str]:
        """
        Reverses a previously recorded move operation with extensive edge-case guards:
        - If file is missing or deleted at destination: marks 'failed' and reports clear message.
        - If original name in parent directory is taken: renames restored file using collision avoidance.
        - If original parent folder was deleted: recreates parent folder.
        - Never crashes on I/O or permissions failure.
        """
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT id, original_path, new_path, status FROM moves WHERE id = ?;",
                    (move_id,),
                )
                row = cursor.fetchone()
                if not row:
                    return False, f"Move record ID #{move_id} not found."

                rec = dict(row)
                if rec["status"] == "undone":
                    return False, f"Move #{move_id} has already been undone."
                if rec["status"] == "failed":
                    return False, f"Move #{move_id} is marked as failed and cannot be undone."
                if rec["status"] == "pending":
                    return False, f"Move #{move_id} was interrupted and is still pending."

                new_file = Path(rec["new_path"])
                original_file = Path(rec["original_path"])

                # Edge case 1: Destination file was moved, renamed, or deleted manually
                if not new_file.exists():
                    conn.execute(
                        "UPDATE moves SET status = 'failed', note = 'File missing at destination' WHERE id = ?;",
                        (move_id,),
                    )
                    conn.commit()
                    return False, f"Cannot undo: File no longer exists at destination ({new_file.name})."

                orig_parent = original_file.parent
                try:
                    # Edge case 2: Original folder was deleted
                    orig_parent.mkdir(parents=True, exist_ok=True)

                    # Edge case 3: Original file name is now taken -> safe_move handles collision automatically
                    restored_path = safe_move(new_file, orig_parent)
                    conn.execute(
                        "UPDATE moves SET status = 'undone', new_path = ?, note = NULL WHERE id = ?;",
                        (str(restored_path), move_id),
                    )
                    conn.commit()
                    return True, f"Restored {new_file.name} to {restored_path.parent.name}/{restored_path.name}"
                except Exception as exc:
                    logger.error("Failed to restore move #%s: %s", move_id, exc)
                    conn.execute(
                        "UPDATE moves SET status = 'failed', note = ? WHERE id = ?;",
                        (str(exc), move_id),
                    )
                    conn.commit()
                    return False, f"Undo failed: {exc}"
