# DropShelf: Smart Desktop Downloads Organizer

DropShelf watches your Downloads folder and sorts every new file into the right place, with one-click undo.

---

## Features

- **Live Event-Driven Watcher:** Uses OS-level file notification APIs via `watchdog` to detect new files immediately without polling.
- **Smart Category Sorting:** Default sorting rules for Documents, Spreadsheets, Presentations, Images, Videos, Audio, Archives, Installers, and Other.
- **Custom Rules Engine:** Priority keyword rules (e.g., "contains invoice -> Finance/Invoices") that evaluate before file-type rules.
- **Write Stability & Anti-Corruption Guard:** Waits until downloading files (or slow browser downloads) are completely finished before moving.
- **Non-Destructive Collision Resolution:** Never overwrites files. If `report.pdf` exists, the incoming file becomes `report (1).pdf`.
- **Skip Incomplete Downloads:** Ignores temporary partial downloads (`.crdownload`, `.part`, `.tmp`, etc.).
- **Live Activity Log & Rollback:** SQLite-backed audit trail with one-click **Undo** to restore files to their exact original locations.
- **Dynamic Folder Selection:** "Change Folder..." button to easily switch between folders (e.g. `C:\Users\YourName\Downloads` or a dedicated test folder).
- **On-Demand Organization:** "Organize Existing Files" button to clean up files already sitting in the folder.

---

## Project Structure

```text
dropshelf/
├── __init__.py      # Package initialization and version metadata
├── config.py        # Configuration loading, default rules, and path resolution
├── history.py       # SQLite audit trail, WAL mode configuration, and undo manager
├── mover.py         # Safe file moves, auto-collision renaming, and rollback logic
├── rules.py         # Rule engine for extension mapping and priority keyword rules
├── stability.py     # Write-stability verification and active file-lock probing
├── ui.py            # Tkinter GUI, queue polling, and activity table
└── watcher.py       # Watchdog observer, event filtration, and thread pool dispatch
```

---

## How It Works

DropShelf coordinates filesystem monitoring, concurrent worker execution, and non-blocking UI rendering through several key architectural components:

| Mechanism | Implementation in DropShelf |
|---|---|
| **Kernel Event Notifications** | Subscribes to OS filesystem events (`ReadDirectoryChangesW` on Windows, `inotify` on Linux, `FSEvents` on macOS) via `watchdog.Observer`, eliminating CPU-intensive polling loops. |
| **Event-Driven Architecture** | The watcher thread remains suspended until the OS kernel signals a directory event, minimizing background resource consumption. |
| **File Metadata Verification** | Inspects filesystem metadata (`os.stat`: `st_size`, `st_mtime_ns`) across consecutive intervals to verify write operations are complete before moving. |
| **File Lock Probing** | Tests file access by opening in append mode (`open(path, 'ab')`) and validating rename permissions (`os.rename(path, path)`). Active downloads hold sharing locks (`ERROR_SHARING_VIOLATION`), preventing premature moves. |
| **Concurrency Model** | Separates responsibilities across threads: the Tkinter main thread handles the GUI, a background daemon thread handles watchdog events, and a bounded `ThreadPoolExecutor` processes file moves. |
| **Race Condition Mitigation** | Protects against race conditions between browser download writers and move workers using metadata stability verification combined with file lock tests. |
| **Thread Synchronization** | Background workers pass UI updates to the main thread through a thread-safe `queue.Queue`, which the Tkinter event loop polls periodically via `root.after()`. |
| **Durable State Storage** | Uses a local SQLite database configured with Write-Ahead Logging (`WAL` mode) to maintain a durable move history for rollback operations across restarts. |

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
1. The app launches idle, displaying your default watched folder (e.g. `C:\Users\YourName\Downloads`).
2. *(Optional)* Click **Change Folder...** to select any other directory to watch.
3. Click **Start Watching** to begin monitoring.
4. Drop or download a sample file (e.g. `quarterly_report.pdf` into `C:\Users\YourName\Downloads`). Within ~2 seconds of download completion, it is moved to `C:\Users\YourName\Downloads\Documents\quarterly_report.pdf`.
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

## Known Limitations

1. **Same-Type Classification**: Files sharing an extension (e.g., work reports vs bank statements) both route to `Documents` unless an explicit keyword rule is configured.
2. **Substring Matching in Custom Rules**: Custom rules use case-insensitive substring checks. A rule for `"OS"` will match names containing those letters (e.g., `PHOTOS.jpg`, `BIOS.bin`).
3. **Broken External Shortcuts**: Moving a file changes its filesystem location; browser download bars, recent file lists, or desktop shortcuts pointing to the original path will not automatically follow the move.
4. **Files Held by Active Processes**: Files with exclusive locks held by other software (e.g., Word documents currently being edited) cannot be moved. After 3 retries, DropShelf leaves them in place for later sorting.
5. **Active Monitoring Only While Running**: DropShelf is an application-space process, not an OS service. Files downloaded while the app is closed remain in the folder until "Organize Existing Files" is clicked.
6. **Network/Download Stalls**: If a browser download stalls longer than the configured stability timeout and releases all OS file locks during the stall, the file may appear stable and be moved prematurely.
