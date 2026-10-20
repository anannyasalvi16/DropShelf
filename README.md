# DropShelf: Smart Desktop Downloads Organizer

An event-driven desktop utility designed to organize messy Downloads folders automatically into categorised subfolders with a live activity log and full undo support.

> Built as an **Operating Systems Case Study Project for Mumbai University (TE IT)**.

---

## Demo

<!-- DEMO GIF PLACEHOLDER -->
<!-- Replace with actual demo GIF when recorded: ![DropShelf Demo](docs/demo.gif) -->
> _[Demo GIF Placeholder: Live folder sorting, non-destructive auto-rename, and one-click Undo]_

---

## Features

- **Live Event-Driven Watcher:** Uses OS-level file notification APIs via `watchdog` to detect new files immediately without polling.
- **Smart Category Sorting:** Default sorting rules for Documents, Spreadsheets, Presentations, Images, Videos, Audio, Archives, Installers, and Other.
- **Custom Rules Engine:** Priority keyword rules (e.g., "contains CNS -> College/CNS") that evaluate before file-type rules.
- **Write Stability & Anti-Corruption Guard:** Waits until downloading files (or slow browser downloads) are completely finished before moving.
- **Non-Destructive Collision Resolution:** Never overwrites files. If `report.pdf` exists, the incoming file becomes `report (1).pdf`.
- **Skip Incomplete Downloads:** Ignores temporary partial downloads (`.crdownload`, `.part`, `.tmp`, etc.).
- **Live Activity Log & Rollback:** SQLite-backed audit trail with one-click **Undo** to restore files to their exact original locations.
- **Dynamic Folder Selection:** "Change Folder..." button to easily switch between folders (e.g. `C:\Users\Student\Downloads` or a dedicated test folder).
- **On-Demand Organization:** "Organize Existing Files" button to clean up files already sitting in the folder.

---

## Installation & Setup

### Prerequisites
- Python 3.11+ (Tested and verified on Python 3.14 on Windows 11)

### 1. Clone / Navigate to Project
```bash
git clone https://github.com/anannyasalvi16/DropShelf.git
cd DropShelf
```

### 2. Create and Activate Virtual Environment
On Windows (PowerShell):
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

On Linux / macOS:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

---

## How to Run the App

```bash
python main.py
```

### Quick Workflow
1. The app launches idle, displaying your default watched folder (e.g. `C:\Users\Student\Downloads`).
2. *(Optional)* Click **Change Folder...** to select any other directory to watch.
3. Click **Start Watching** to begin monitoring.
4. Drop or download a sample file (e.g. `lecture_notes.pdf` into `C:\Users\Student\Downloads`). Within ~2 seconds of download completion, it is moved to `C:\Users\Student\Downloads\Documents\lecture_notes.pdf`.
5. Select any completed move in the activity log and click **Undo Selected Move** to restore the file to its original location.
6. Click **Manage Rules...** to add custom keyword rules on the fly.
7. Click **Organize Existing Files** to sort all loose files currently in the directory.

---

## Running Automated Tests

Run the full pytest suite:
```bash
pytest -v
```
All tests use isolated temporary folders (`tmp_path`) and never touch your real Downloads directory.

---

## Operating Systems Concepts Explained (Viva Reference)

| OS Concept | How & Where It Appears in DropShelf |
|---|---|
| **File System Events & Notification** | Uses OS-level kernel hooks (`ReadDirectoryChangesW` on Windows, `inotify` on Linux, `FSEvents` on macOS) through `watchdog.Observer`. Avoids busy-waiting/polling. |
| **I/O Polling vs Event-Driven** | Polling the folder every second would waste CPU cycles and battery. OS event notifications wake the application process only when a directory change occurs. |
| **File Attributes & Metadata** | Queries inode/metadata (`os.stat`: `st_size`, `st_mtime_ns`) to detect active write streams and classify files. |
| **File Locking & In-Use Detection** | On Windows, attempts opening the file in append mode (`open(path, 'ab')`) and tests rename permission (`os.rename(path, path)`). An active download raises `PermissionError` (`ERROR_SHARING_VIOLATION`), ensuring incomplete files are never moved. |
| **Concurrency & Multithreading** | The application separates duties across threads: (1) Main UI Thread for Tkinter GUI, (2) Watchdog Observer thread, (3) Bounded `ThreadPoolExecutor` worker threads for file moves. |
| **Race Conditions** | A browser writing a file concurrently with a mover attempting to sort it represents a classical race condition. Solved via consecutive metadata stability checks and file lock probing. |
| **Thread Synchronization & Queues** | Tkinter widgets are not thread-safe and can only be modified from the main thread. Worker threads communicate with the UI via a thread-safe `queue.Queue` polled via `root.after(200, ...)`. |
| **Persistent vs Volatile State** | SQLite database with Write-Ahead Logging (`WAL` mode) stores undo history to secondary storage, surviving process termination and system reboots. |

---

## Viva Questions & Answers

1. **Q: Which major OS concepts does this project demonstrate?**
   * **A:** Filesystem management, kernel event notification, process/thread concurrency, file locking/sharing modes, and race condition prevention.
2. **Q: Why not use a `while True: sleep(1)` loop to check the folder?**
   * **A:** Polling consumes unnecessary CPU cycles and causes disk wear. Kernel event notification (`ReadDirectoryChangesW`) allows the process to sleep until the OS kernel signals a directory change.
3. **Q: How does the application avoid moving a file that is still downloading?**
   * **A:** It checks for known partial download extensions (like `.crdownload`) and requires consecutive unchanged file size and modified timestamps (`stat()`), plus verifying that no exclusive write lock is held by another process.
4. **Q: Why are worker threads needed if the watcher is already running?**
   * **A:** The stability check blocks while waiting for downloads to finish. If done on the watcher thread, subsequent events would be delayed. Offloading to a `ThreadPoolExecutor` keeps event ingestion non-blocking while keeping the Tkinter UI fluid.

---

## Known Limitations

1. **Same-Type Classification**: Files sharing an extension (e.g., college assignment PDFs vs bank statement PDFs) both route to `Documents` unless an explicit keyword rule is configured.
2. **Substring Matching in Custom Rules**: Custom rules use case-insensitive substring checks. A rule for `"OS"` will match names containing those letters (e.g., `PHOTOS.jpg`, `BIOS.bin`).
3. **Broken External Shortcuts**: Moving a file changes its filesystem location; browser download bars, recent file lists, or desktop shortcuts pointing to the original path will not automatically follow the move.
4. **Files Held by Active Processes**: Files with exclusive locks held by other software (e.g., Word documents currently being edited) cannot be moved. After 3 retries, DropShelf leaves them in place for later sorting.
5. **Active Monitoring Only While Running**: DropShelf is an application-space process, not an OS service. Files downloaded while the app is closed remain in the folder until "Organize Existing Files" is clicked.
6. **Network/Download Stalls**: If a browser download stalls longer than the configured stability timeout and releases all OS file locks during the stall, the file may appear stable and be moved prematurely.
