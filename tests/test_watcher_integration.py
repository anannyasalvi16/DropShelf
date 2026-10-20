"""
Integration tests for dropsort.watcher.
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
        pdf_file = watch_dir / "report.pdf"
        pdf_file.write_text("quarterly report", encoding="utf-8")

        assert wait_until_condition(lambda: (watch_dir / "Documents" / "report.pdf").exists(), timeout=4.0)
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
        invoice_file = watch_dir / "client_invoice.docx"
        invoice_file.write_text("billing details", encoding="utf-8")
        assert wait_until_condition(lambda: (watch_dir / "Finance" / "Invoices" / "client_invoice.docx").exists(), timeout=4.0)

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


def test_change_watched_folder_while_watching(tmp_path):
    """
    Assert that dynamically changing the watched folder while watching:
    - Sorts new files created in the new watched folder.
    - Leaves files created in the old folder untouched.
    """
    folder_a = tmp_path / "DownloadsA"
    folder_a.mkdir()
    folder_b = tmp_path / "DownloadsB"
    folder_b.mkdir()

    rules_file = tmp_path / "rules.json"
    db_file = tmp_path / "test.db"

    rules = get_default_rules()
    rules["watch_folder"] = str(folder_a)
    save_rules(rules, rules_file)

    rules_mgr = ThreadSafeRulesManager(rules_file)
    hist_mgr = HistoryManager(db_file)
    event_q = queue.Queue()

    watcher = FolderWatcher(
        watch_folder=folder_a,
        rules_manager=rules_mgr,
        history_manager=hist_mgr,
        event_queue=event_q,
        stability_interval=0.05,
        stability_checks=2,
        stability_timeout=3.0,
    )

    watcher.start()
    assert watcher.is_running
    try:
        time.sleep(0.3)

        # Dynamically change the watched folder while watching is active
        watcher.set_watch_folder(folder_b)
        assert watcher.is_running
        assert watcher.watch_folder == folder_b.resolve()
        time.sleep(0.3)

        # Place a new file in the new folder
        new_file = folder_b / "sample_new.pdf"
        new_file.write_text("new folder doc", encoding="utf-8")

        # Place a file in the old folder
        old_file = folder_a / "sample_old.pdf"
        old_file.write_text("old folder doc", encoding="utf-8")

        # The new folder's file must be sorted into folder_b/Documents
        assert wait_until_condition(
            lambda: (folder_b / "Documents" / "sample_new.pdf").exists(),
            timeout=4.0,
        )
        assert not new_file.exists()

        # The old folder's file must NOT be sorted and must remain untouched in folder_a
        time.sleep(0.5)
        assert old_file.exists()
        assert not (folder_a / "Documents" / "sample_old.pdf").exists()
    finally:
        watcher.stop()


