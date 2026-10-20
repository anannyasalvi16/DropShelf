"""
Integration tests for dropsort.watcher according to TRD Section 7.
"""

import queue
import time
from pathlib import Path
from dropsort.config import ThreadSafeRulesManager, get_default_rules, save_rules
from dropsort.history import HistoryManager
from dropsort.watcher import FolderWatcher


def wait_until_condition(check_fn, timeout=5.0, step=0.05):
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        if check_fn():
            return True
        time.sleep(step)
    return False


def test_watcher_pipeline_integration(tmp_path):
    watch_dir = tmp_path / "Downloads"
    watch_dir.mkdir()
    rules_file = tmp_path / "rules.json"
    db_file = tmp_path / "test.db"

    rules = get_default_rules()
    rules["watch_folder"] = str(watch_dir)
    save_rules(rules, rules_file)

    rules_mgr = ThreadSafeRulesManager(rules_file)
    hist_mgr = HistoryManager(db_file)
    event_q = queue.Queue()

    # Fast stability for testing
    watcher = FolderWatcher(
        watch_folder=watch_dir,
        rules_manager=rules_mgr,
        history_manager=hist_mgr,
        event_queue=event_q,
        stability_interval=0.05,
        stability_checks=2,
        stability_timeout=3.0,
    )

    watcher.start()
    try:
        # Give watchdog observer thread a moment to register on Windows
        time.sleep(0.3)

        # 1. Create a PDF -> should move to Documents/
        pdf_file = watch_dir / "lecture.pdf"
        pdf_file.write_text("lecture notes", encoding="utf-8")

        assert wait_until_condition(lambda: (watch_dir / "Documents" / "lecture.pdf").exists(), timeout=4.0)
        assert not pdf_file.exists()

        # 2. Temp-extension file -> must be left alone in watch_dir!
        temp_file = watch_dir / "big_game.iso.crdownload"
        temp_file.write_bytes(b"downloading...")
        time.sleep(0.4)
        assert temp_file.exists()  # Kept in root, NOT moved!

        # 3. Two files with the same name -> both survive
        first_img = watch_dir / "photo.png"
        first_img.write_text("photo 1", encoding="utf-8")
        assert wait_until_condition(lambda: (watch_dir / "Images" / "photo.png").exists(), timeout=4.0)
        assert wait_until_condition(lambda: not first_img.exists(), timeout=2.0)
        time.sleep(0.15)

        second_img = watch_dir / "photo.png"
        second_img.write_text("photo 2", encoding="utf-8")
        assert wait_until_condition(lambda: (watch_dir / "Images" / "photo (1).png").exists(), timeout=4.0)

        assert (watch_dir / "Images" / "photo.png").read_text(encoding="utf-8") == "photo 1"
        assert (watch_dir / "Images" / "photo (1).png").read_text(encoding="utf-8") == "photo 2"

        # 4. Custom rule -> matches and moves to custom folder
        cns_file = watch_dir / "cns_security_report.docx"
        cns_file.write_text("security", encoding="utf-8")
        assert wait_until_condition(lambda: (watch_dir / "College" / "CNS" / "cns_security_report.docx").exists(), timeout=4.0)

    finally:
        watcher.stop()
        assert not watcher.is_running


def test_organize_existing(tmp_path):
    watch_dir = tmp_path / "Downloads"
    watch_dir.mkdir()
    rules_file = tmp_path / "rules.json"
    db_file = tmp_path / "test.db"

    rules = get_default_rules()
    rules["watch_folder"] = str(watch_dir)
    save_rules(rules, rules_file)

    rules_mgr = ThreadSafeRulesManager(rules_file)
    hist_mgr = HistoryManager(db_file)
    event_q = queue.Queue()

    # Pre-populate watch_dir BEFORE starting watcher
    (watch_dir / "sheet.xlsx").write_text("expenses", encoding="utf-8")
    (watch_dir / "song.mp3").write_text("audio track", encoding="utf-8")

    watcher = FolderWatcher(
        watch_folder=watch_dir,
        rules_manager=rules_mgr,
        history_manager=hist_mgr,
        event_queue=event_q,
        stability_interval=0.05,
        stability_checks=2,
    )

    watcher.start()
    try:
        # Trigger organize_existing on demand
        count = watcher.organize_existing()
        assert count == 2

        assert wait_until_condition(lambda: (watch_dir / "Spreadsheets" / "sheet.xlsx").exists(), timeout=4.0)
        assert wait_until_condition(lambda: (watch_dir / "Audio" / "song.mp3").exists(), timeout=4.0)
    finally:
        watcher.stop()


def test_duplicate_events_suppressed(tmp_path):
    """Assert that if both 'created' and 'moved' events fire for one download, it is only processed once."""
    watch_dir = tmp_path / "Downloads"
    watch_dir.mkdir()
    rules_file = tmp_path / "rules.json"
    db_file = tmp_path / "test.db"

    rules = get_default_rules()
    rules["watch_folder"] = str(watch_dir)
    save_rules(rules, rules_file)

    rules_mgr = ThreadSafeRulesManager(rules_file)
    hist_mgr = HistoryManager(db_file)
    event_q = queue.Queue()

    watcher = FolderWatcher(
        watch_folder=watch_dir,
        rules_manager=rules_mgr,
        history_manager=hist_mgr,
        event_queue=event_q,
        stability_interval=0.05,
        stability_checks=2,
    )

    test_file = watch_dir / "statement.pdf"
    test_file.write_text("statement data", encoding="utf-8")

    watcher.start()
    try:
        # Simulate OS firing both created and moved events concurrently for the same file
        watcher.handle_incoming_file(test_file)
        watcher.handle_incoming_file(test_file)

        assert wait_until_condition(lambda: (watch_dir / "Documents" / "statement.pdf").exists(), timeout=4.0)
        time.sleep(0.3)

        # Assert no duplicate 'statement (1).pdf' was created!
        assert not (watch_dir / "Documents" / "statement (1).pdf").exists()

        # Assert only ONE record exists in history
        records = [r for r in hist_mgr.recent() if "statement.pdf" in r["original_path"]]
        assert len(records) == 1
        assert records[0]["status"] == "moved"
    finally:
        watcher.stop()


def test_locked_file_exhausts_retries_and_leaves_file_untouched(tmp_path):
    """Assert that a permanently locked file retries 3 times, fails cleanly, and stays in place."""
    watch_dir = tmp_path / "Downloads"
    watch_dir.mkdir()
    rules_file = tmp_path / "rules.json"
    db_file = tmp_path / "test.db"

    rules = get_default_rules()
    rules["watch_folder"] = str(watch_dir)
    save_rules(rules, rules_file)

    rules_mgr = ThreadSafeRulesManager(rules_file)
    hist_mgr = HistoryManager(db_file)
    event_q = queue.Queue()

    watcher = FolderWatcher(
        watch_folder=watch_dir,
        rules_manager=rules_mgr,
        history_manager=hist_mgr,
        event_queue=event_q,
        stability_interval=0.05,
        stability_checks=2,
        stability_timeout=0.5,
    )

    locked_file = watch_dir / "locked_file.txt"
    locked_file.write_text("locked", encoding="utf-8")

    # Hold an exclusive lock on the file during the move
    with open(locked_file, "r+b") as hold_open:
        watcher.start()
        try:
            # Trigger pipeline
            watcher.handle_incoming_file(locked_file)
            time.sleep(1.0)

            # File must still exist untouched in the watch directory!
            assert locked_file.exists()
            assert not (watch_dir / "Documents" / "locked_file.txt").exists()
        finally:
            watcher.stop()

