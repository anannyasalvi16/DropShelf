# DropSort: Technical Requirements Document

## 1. Stack

| Part | Choice | Why |
|---|---|---|
| Language | Python 3.11+ | Fast to build, strong file system support |
| File events | `watchdog` | Wraps the OS event APIs (inotify, ReadDirectoryChangesW, FSEvents) |
| UI | Tkinter with `ttk` | Ships with Python, real desktop feel, no extra dependency |
| Config | `rules.json` | Human readable, easy to edit |
| History | SQLite (`sqlite3`, standard library) | Reliable undo history that survives restarts |
| File operations | `pathlib`, `shutil` | Standard, cross-platform |
| Tests | `pytest` | Standard |
| Packaging (optional) | PyInstaller | Single `.exe` for the demo |

Primary target: Windows 10/11. Must also work on Linux and macOS without code changes.

## 2. Architecture

```
  OS file system
       |
       |  (events: file created / moved in)
       v
  Watcher thread (watchdog Observer)
       |
       v
  Stability checker  -->  Rule engine  -->  Mover  -->  History (SQLite)
       |                                       |
       +---------------> event queue <---------+
                              |
                              v
                        UI thread (Tkinter)
                      polls queue every 200 ms
```

Rules of the design:

- The UI thread never does file work. The watcher side never touches Tkinter widgets.
- All communication from the watcher side to the UI goes through one `queue.Queue`.
- The UI polls the queue with `root.after(200, ...)`.

## 3. Project structure

```
dropsort/
  main.py                  # entry point
  requirements.txt
  README.md
  dropsort/
    __init__.py
    config.py              # load and save rules.json, default rules, paths
    rules.py               # rule matching, returns destination folder for a file
    stability.py           # decides whether a file is finished being written
    mover.py               # safe move with collision handling
    history.py             # SQLite history, undo support
    watcher.py             # watchdog handler plus worker that runs the pipeline
    ui.py                  # Tkinter screens
  tests/
    test_rules.py
    test_stability.py
    test_mover.py
    test_history.py
    test_watcher_integration.py
```

## 4. Module specifications

### 4.1 config.py

- Default watched folder: the user's Downloads folder (`Path.home() / "Downloads"`).
- `rules.json` structure:

```json
{
  "watch_folder": "C:/Users/Ana/Downloads",
  "custom_rules": [
    { "contains": "CNS", "folder": "College/CNS" }
  ],
  "type_rules": {
    "Documents": ["pdf", "doc", "docx", "txt", "rtf"],
    "Spreadsheets": ["xls", "xlsx", "csv"],
    "Presentations": ["ppt", "pptx"],
    "Images": ["jpg", "jpeg", "png", "gif", "webp", "svg"],
    "Videos": ["mp4", "mkv", "mov", "avi"],
    "Audio": ["mp3", "wav", "m4a", "flac"],
    "Archives": ["zip", "rar", "7z", "tar", "gz"],
    "Installers": ["exe", "msi", "dmg", "pkg", "apk"]
  },
  "fallback_folder": "Other",
  "ignore_extensions": ["crdownload", "part", "tmp", "download", "opdownload"]
}
```

- Destination folders are created inside the watched folder, for example `Downloads/Documents`. A custom rule folder is also relative to the watched folder.
- If `rules.json` is missing or invalid, recreate it from defaults. Never crash.

### 4.2 rules.py

`def destination_for(filename: str, rules: dict) -> str | None`

- Return `None` if the extension is in `ignore_extensions`.
- Check custom rules first, in order. Case-insensitive "contains" match on the file name.
- Then check type rules by extension (case-insensitive).
- Otherwise return the fallback folder.

### 4.3 stability.py

`def wait_until_stable(path: Path, interval=0.5, stable_checks=3, timeout=300) -> bool`

- A file is stable when its size and modified time are unchanged for `stable_checks` consecutive checks.
- On Windows also try opening the file in append mode. If it raises `PermissionError`, the file is still in use, so keep waiting.
- Return `False` if the file vanishes or the timeout is hit.
- This function blocks, so it runs in a worker thread, never in the UI thread.

### 4.4 mover.py

`def safe_move(src: Path, dest_dir: Path) -> Path`

- Create `dest_dir` if needed.
- If a file with the same name exists in `dest_dir`, generate `name (1).ext`, `name (2).ext` and so on until free.
- Use `shutil.move`.
- Return the final destination path.
- Must never overwrite. Must raise a clear exception on failure so the caller can log and retry.

### 4.5 history.py

SQLite table `moves`:

| Column | Type |
|---|---|
| id | INTEGER PRIMARY KEY |
| timestamp | TEXT (ISO 8601) |
| original_path | TEXT |
| new_path | TEXT |
| status | TEXT (`moved`, `undone`, `failed`) |

Functions:

- `record_move(original, new)` returns the row id
- `recent(limit=200)` returns rows newest first
- `undo(move_id)`: if `new_path` still exists, move it back to `original_path`, using collision handling if `original_path` is now taken. Mark status `undone`. If `new_path` is gone, mark failed and report a clear message.

### 4.6 watcher.py

- A `watchdog` event handler reacts to `on_created` and `on_moved` (browsers often download to a temp name and rename on finish, so `on_moved` matters).
- Only handle events where the file is directly inside the watched folder. Ignore directories and anything in subfolders.
- Each valid event is submitted to a small `ThreadPoolExecutor` (max 4 workers). The worker does: check ignore list, wait until stable, find destination, safe move, record history, push a result message to the UI queue.
- Keep a set of paths currently being processed so the same file is never handled twice.
- On failure, push an error message to the queue and retry up to 3 times with a delay. After that, log as failed and move on.
- `start()` and `stop()` must be clean. `stop()` joins the observer and shuts down the executor.
- `organize_existing()` walks the top level of the watched folder once and runs the same pipeline on each file.

### 4.7 ui.py

- Main window: path label, Start/Stop button, status label, "Organize existing files" button, `ttk.Treeview` for the activity log, Undo button.
- Rules window: `ttk.Treeview` of custom rules, entry fields for text and folder, Add and Delete buttons. Saving writes `rules.json`, and the watcher reloads the rules.
- Queue messages are small dicts, for example `{"type": "moved", "name": ..., "from": ..., "to": ..., "id": ...}` and `{"type": "error", "name": ..., "message": ...}`.
- Plain, minimal look. Use the default `ttk` theme. Clear spacing, no clutter.

## 5. Concurrency rules

- Tkinter is not thread-safe. Only the main thread touches widgets.
- Worker threads only write to the queue and to SQLite. Use a new SQLite connection per thread, or `check_same_thread=False` guarded by a lock.
- Rules are read through a lock-protected getter so a rules update never races with a running move.

## 6. Error handling

| Situation | Behavior |
|---|---|
| Permission denied or file in use | Retry up to 3 times, then log failure and continue |
| File disappears before the move | Log as skipped |
| Destination folder cannot be created | Log the error, do not crash |
| Invalid `rules.json` | Restore defaults |
| Name collision | Rename with a number |
| Disk full or other OS error | Log the error, show it in the UI |

## 7. Test plan

All tests use `tmp_path`. No test ever touches the real Downloads folder.

| Test file | Cases |
|---|---|
| test_rules.py | each default type maps correctly; uppercase extensions; custom rule beats type rule; unknown extension goes to fallback; temp extensions return `None`; file with no extension |
| test_stability.py | file written once is stable; file still growing is not stable until growth stops; missing file returns `False`; timeout returns `False` |
| test_mover.py | basic move; collision creates `(1)`; second collision creates `(2)`; destination folder is created; source is gone afterwards; no overwrite ever |
| test_history.py | record and read back; undo restores original path; undo when original name is taken uses a rename; undo when the file is missing fails cleanly; status updates |
| test_watcher_integration.py | start watcher on a temp folder, create files, assert they land in the right subfolders; temp-extension files are left alone; a file written slowly is moved only after completion; two files with the same name both survive; stop() shuts down cleanly |

A manual checklist (run before the demo):

1. Real browser download of a large file: it is not moved until the download completes.
2. Drop 20 files at once: all sorted, none lost.
3. Undo several moves in a row.
4. Restart the app: history is still there.
5. Leave it running 30 minutes with the app idle: CPU stays near zero.

## 8. Non-functional requirements

- Idle CPU under 1%, because it is event driven and never polls the whole folder.
- Memory under 100 MB.
- Startup under 2 seconds.
- No network access at all.

## 9. Definition of done

- Every feature in the PRD works as described
- All pytest tests pass
- Manual checklist passes
- README explains install, run, and the OS concepts used
- No file loss in any scenario tested
