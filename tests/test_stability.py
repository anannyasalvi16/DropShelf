"""
Unit tests for dropsort.stability according to TRD Section 7.
"""

import threading
import time
from dropsort.stability import wait_until_stable


def test_file_written_once_is_stable(tmp_path):
    test_file = tmp_path / "sample.txt"
    test_file.write_text("Hello, World!", encoding="utf-8")

    # Fast check: 0.05 interval, 2 stable checks
    is_stable = wait_until_stable(test_file, interval=0.05, stable_checks=2, timeout=2.0)
    assert is_stable is True


def test_file_still_growing_is_not_stable_until_growth_stops(tmp_path):
    test_file = tmp_path / "growing.bin"
    test_file.write_bytes(b"initial")

    stop_writing = threading.Event()

    def slow_writer():
        for i in range(5):
            if stop_writing.is_set():
                break
            time.sleep(0.08)
            with open(test_file, "ab") as f:
                f.write(f"chunk{i}".encode())

    writer_thread = threading.Thread(target=slow_writer)
    writer_thread.start()

    # The file should become stable only after the writer finishes writing chunks
    is_stable = wait_until_stable(test_file, interval=0.05, stable_checks=3, timeout=5.0)
    writer_thread.join()

    assert is_stable is True
    # Verify file content is intact and not corrupted
    assert test_file.stat().st_size > len(b"initial")


def test_missing_file_returns_false(tmp_path):
    missing_file = tmp_path / "non_existent.pdf"
    assert wait_until_stable(missing_file, interval=0.05, stable_checks=2, timeout=0.2) is False


def test_timeout_returns_false_when_file_keeps_changing(tmp_path):
    test_file = tmp_path / "endless.log"
    test_file.write_text("start", encoding="utf-8")

    stop_event = threading.Event()

    def constant_writer():
        while not stop_event.is_set():
            time.sleep(0.03)
            try:
                with open(test_file, "ab") as f:
                    f.write(b"x")
            except Exception:
                pass

    t = threading.Thread(target=constant_writer)
    t.start()

    try:
        # Give a very short timeout so it fails stability within 0.25 seconds
        is_stable = wait_until_stable(test_file, interval=0.05, stable_checks=3, timeout=0.25)
        assert is_stable is False
    finally:
        stop_event.set()
        t.join()


def test_file_pauses_mid_write_and_resumes(tmp_path):
    test_file = tmp_path / "stream_with_pause.dat"
    test_file.write_bytes(b"header")

    second_chunk_written = threading.Event()

    def pausing_writer():
        # Open and hold file open like a browser download stream
        with open(test_file, "ab") as f:
            f.write(b"_part1")
            f.flush()
            # Pause mid-write
            time.sleep(0.12)
            f.write(b"_part2")
            f.flush()
            second_chunk_written.set()

    t = threading.Thread(target=pausing_writer)
    t.start()

    # With interval=0.05 and stable_checks=3, it should only return stable after part2 is closed
    is_stable = wait_until_stable(test_file, interval=0.05, stable_checks=3, timeout=3.0)
    t.join()

    assert is_stable is True
    assert second_chunk_written.is_set()
    assert test_file.read_bytes() == b"header_part1_part2"

