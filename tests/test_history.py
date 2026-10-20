"""
Unit tests for dropsort.history according to TRD Section 7.
"""

from dropsort.history import HistoryManager


def test_record_and_read_back(tmp_path):
    db_file = tmp_path / "test.db"
    history = HistoryManager(db_file)

    orig = tmp_path / "file.pdf"
    new = tmp_path / "Documents" / "file.pdf"

    move_id = history.record_move(orig, new)
    assert move_id == 1

    records = history.recent()
    assert len(records) == 1
    assert records[0]["id"] == 1
    assert records[0]["status"] == "moved"
    assert "timestamp" in records[0]


def test_undo_restores_original_path(tmp_path):
    db_file = tmp_path / "test.db"
    history = HistoryManager(db_file)

    downloads = tmp_path / "Downloads"
    docs = downloads / "Documents"
    downloads.mkdir(parents=True)
    docs.mkdir(parents=True)

    original_path = downloads / "assignment.pdf"
    sorted_path = docs / "assignment.pdf"
    sorted_path.write_text("PDF content", encoding="utf-8")

    move_id = history.record_move(original_path, sorted_path)

    success, msg = history.undo(move_id)
    assert success is True
    assert original_path.exists()
    assert not sorted_path.exists()
    assert original_path.read_text(encoding="utf-8") == "PDF content"

    # Status must be updated to 'undone'
    rec = history.get_record(move_id)
    assert rec["status"] == "undone"


def test_undo_when_original_name_is_taken_uses_a_rename(tmp_path):
    db_file = tmp_path / "test.db"
    history = HistoryManager(db_file)

    downloads = tmp_path / "Downloads"
    docs = downloads / "Documents"
    downloads.mkdir(parents=True)
    docs.mkdir(parents=True)

    original_path = downloads / "data.csv"
    sorted_path = docs / "data.csv"
    sorted_path.write_text("sorted data", encoding="utf-8")

    move_id = history.record_move(original_path, sorted_path)

    # In the meantime, another file with the exact original name was placed in Downloads!
    original_path.write_text("newly created file with same name", encoding="utf-8")

    success, msg = history.undo(move_id)
    assert success is True
    # The undo should have created data (1).csv without overwriting data.csv!
    restored_collision_file = downloads / "data (1).csv"
    assert restored_collision_file.exists()
    assert restored_collision_file.read_text(encoding="utf-8") == "sorted data"
    assert original_path.read_text(encoding="utf-8") == "newly created file with same name"


def test_undo_when_file_is_missing_fails_cleanly(tmp_path):
    db_file = tmp_path / "test.db"
    history = HistoryManager(db_file)

    downloads = tmp_path / "Downloads"
    docs = downloads / "Documents"
    downloads.mkdir(parents=True)
    docs.mkdir(parents=True)

    original_path = downloads / "deleted.pdf"
    sorted_path = docs / "deleted.pdf"
    # Do NOT create sorted_path (simulate deleted file)

    move_id = history.record_move(original_path, sorted_path)

    success, msg = history.undo(move_id)
    assert success is False
    assert "no longer exists" in msg

    # Status should be marked 'failed'
    rec = history.get_record(move_id)
    assert rec["status"] == "failed"


def test_undo_already_undone(tmp_path):
    db_file = tmp_path / "test.db"
    history = HistoryManager(db_file)

    downloads = tmp_path / "Downloads"
    docs = downloads / "Documents"
    downloads.mkdir(parents=True)
    docs.mkdir(parents=True)

    original_path = downloads / "test.txt"
    sorted_path = docs / "test.txt"
    sorted_path.write_text("txt", encoding="utf-8")

    move_id = history.record_move(original_path, sorted_path)
    success1, _ = history.undo(move_id)
    assert success1 is True

    # Attempting to undo again should return False
    success2, msg2 = history.undo(move_id)
    assert success2 is False
    assert "already been undone" in msg2


def test_two_phase_commit_workflow(tmp_path):
    db_file = tmp_path / "test.db"
    history = HistoryManager(db_file)

    orig = tmp_path / "doc.txt"
    new = tmp_path / "Documents" / "doc.txt"

    # 1. Pending before move
    move_id = history.record_pending_move(orig, new)
    assert history.get_record(move_id)["status"] == "pending"

    # 2. Confirm move
    history.confirm_move(move_id, new)
    assert history.get_record(move_id)["status"] == "moved"

    # 3. Fail move workflow
    fail_id = history.record_pending_move(orig, new)
    history.fail_move(fail_id, note="Permission Denied")
    rec = history.get_record(fail_id)
    assert rec["status"] == "failed"
    assert rec["note"] == "Permission Denied"


def test_crash_recovery_case1_move_finished_before_crash(tmp_path):
    """Case 1: File is at new_path and not original_path -> Mark 'moved' so Undo works."""
    db_file = tmp_path / "test.db"
    history = HistoryManager(db_file)

    orig = tmp_path / "Downloads" / "report.pdf"
    new = tmp_path / "Downloads" / "Documents" / "report.pdf"
    new.parent.mkdir(parents=True, exist_ok=True)
    new.write_text("pdf data", encoding="utf-8")  # File landed at destination

    # Simulate pending row left behind by crash
    move_id = history.record_pending_move(orig, new)

    # Re-initialize HistoryManager to simulate app restart
    restarted_history = HistoryManager(db_file)
    record = restarted_history.get_record(move_id)
    assert record["status"] == "moved"

    # Undo must still work
    success, msg = restarted_history.undo(move_id)
    assert success is True
    assert orig.exists()


def test_crash_recovery_case2_interrupted_before_move(tmp_path):
    """Case 2: File still exists at original_path -> Mark 'failed' with note."""
    db_file = tmp_path / "test.db"
    history = HistoryManager(db_file)

    orig = tmp_path / "Downloads" / "interrupted.txt"
    orig.parent.mkdir(parents=True, exist_ok=True)
    orig.write_text("still at source", encoding="utf-8")
    new = tmp_path / "Downloads" / "Documents" / "interrupted.txt"

    move_id = history.record_pending_move(orig, new)

    # Restart app
    restarted_history = HistoryManager(db_file)
    record = restarted_history.get_record(move_id)
    assert record["status"] == "failed"
    assert record["note"] == "Interrupted before move completed"


def test_crash_recovery_case3_file_missing_in_both(tmp_path):
    """Case 3: File missing at both original and destination -> Mark 'failed' with note."""
    db_file = tmp_path / "test.db"
    history = HistoryManager(db_file)

    orig = tmp_path / "Downloads" / "vanished.txt"
    new = tmp_path / "Downloads" / "Documents" / "vanished.txt"

    move_id = history.record_pending_move(orig, new)

    # Restart app
    restarted_history = HistoryManager(db_file)
    record = restarted_history.get_record(move_id)
    assert record["status"] == "failed"
    assert record["note"] == "File missing after interruption"
