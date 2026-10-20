# DropSort: Product Requirements Document

## 1. Summary

DropSort is a small desktop app that watches a folder (Downloads by default) and automatically moves each new file into the right subfolder. It shows a live activity log and lets the user undo any move.

It is built as the Operating Systems case study project for Mumbai University (TE IT). The OS concepts are not simulated. The app uses real file system events, real file operations, and runs as a background process with a separate UI thread.

## 2. Problem

Almost everyone's Downloads folder is a mess. PDFs, installers, screenshots, assignments and zip files pile up together, and finding one file means scrolling through hundreds. Sorting by hand is boring, so nobody does it.

## 3. Goal

Keep the Downloads folder organized without the user doing anything, and never lose or corrupt a file while doing it.

## 4. Target users

- Students with assignments, notes and installers mixed together
- Anyone who downloads files daily and hates a cluttered folder

## 5. Scope

### In scope (v1)

| # | Feature | Notes |
|---|---|---|
| 1 | Live watcher | Detects new files in the watched folder as soon as they appear |
| 2 | Sort by file type | Default rules: Documents, Spreadsheets, Presentations, Images, Videos, Audio, Archives, Installers, Other |
| 3 | Custom rules | "If filename contains X, move to folder Y". Custom rules run before type rules |
| 4 | Activity log | Live list: time, file name, from, to |
| 5 | Undo | One click moves a file back to where it came from |
| 6 | Duplicate name handling | `report.pdf` becomes `report (1).pdf`. Never overwrite |
| 7 | Skip incomplete downloads | Ignore `.crdownload`, `.part`, `.tmp`, `.download`, `.opdownload` and files still growing |
| 8 | Organize existing files | One button to sort everything already sitting in the folder (useful for the demo) |
| 9 | Start and stop | A single toggle to pause watching |

### Out of scope (do not build)

- Cloud sync, accounts, or any network feature
- AI or content-based classification
- Watching multiple folders
- Recursive sorting of subfolders
- Mobile app
- Weekly reports, auto-delete rules, dark mode (only if everything above is finished and tested)

## 6. User flow

1. User opens DropSort and sees the watched folder path (default: their Downloads folder).
2. User presses **Start**. Status shows "Watching".
3. A file lands in Downloads. Within about 2 seconds of the download finishing it moves into its subfolder, and a row appears in the activity log.
4. User can select a row and press **Undo** to move it back.
5. User can open **Rules**, add a custom rule, and see it apply to the next file.
6. User can press **Organize existing files** to sort what is already there.

## 7. Screens (keep it minimal)

1. **Main screen:** watched folder path, Start/Stop toggle, status text, Organize existing files button, activity log table with an Undo button
2. **Rules screen:** list of custom rules, add and delete rule

Two screens only. Plain, simple layout. No decoration for its own sake.

## 8. Safety requirements (non-negotiable)

- Only touch files directly inside the watched folder. Never recurse, never touch folders.
- Never overwrite an existing file. Always rename on collision.
- Never move a file that is still being written.
- Every move is recorded so it can be undone.
- If a move fails (permission denied, file in use), log it, skip it and retry later. Never crash.
- All tests must run on temporary folders only, never on the real Downloads folder.

## 9. OS concepts covered (for the viva)

| OS concept | Where it appears |
|---|---|
| File system and directory structure | Folder tree the files are sorted into |
| File attributes and metadata | Extension, size and modified time drive the rules and the stability check |
| File operations | Move, rename, create directory, undo |
| File system event notification | Watcher uses inotify (Linux), ReadDirectoryChangesW (Windows), FSEvents (macOS) through the `watchdog` library |
| File permissions and locking | Handling "permission denied" and files held open by another process |
| Process and background service | The watcher runs continuously in the background |
| Threads and concurrency | Watcher thread and UI thread, communicating through a thread-safe queue |
| Race conditions | Moving a file that the browser is still writing, and how the stability check prevents it |

## 10. Viva questions and short answers

- **Which OS concept is this?** File system management and file system event notification.
- **How does it know a file arrived?** The OS notifies our watcher of directory events, so we do not keep checking the folder.
- **Why not check the folder every second?** Polling wastes CPU. Event notification wakes the program only when something changes.
- **What if the file is still downloading?** We ignore temp extensions and wait until size and modified time stop changing.
- **Why two threads?** The watcher must keep listening while the UI stays responsive. They share a queue so no data is corrupted.
- **What if two files have the same name?** We rename the new one with a number instead of overwriting.

## 11. Live demo script (about 2 minutes)

1. Show a messy Downloads folder.
2. Press **Start**. Say "it is now watching this folder."
3. Drag in 5 mixed files. They move within a couple of seconds and the log updates.
4. Press **Undo** on one. It jumps back.
5. Add a custom rule live (for example "name contains CNS goes to College/CNS"), drop a matching file, show it landing in the right place.
6. Drop two files with the same name to show the auto-rename.

## 12. Success criteria

- A file dropped into the watched folder is sorted correctly within 3 seconds of it being complete
- A file that is still being written is never moved early
- No file is ever lost, overwritten or corrupted in any test
- Undo restores the exact original location and name
- App runs for 30 minutes without crashing or high CPU use
- All automated tests pass

## 13. Known limitations

1. **Same-type classification**: All files sharing an extension (e.g., academic assignment PDF vs financial receipt PDF) route to the same category (`Documents`) unless a custom keyword rule is created.
2. **Substring matching in custom rules**: Custom rules use case-insensitive substring matching. A rule for `"OS"` will match words containing those characters (e.g., `PHOTOS.jpg`, `BIOS.bin`).
3. **Broken browser/shortcut paths**: Moving a file changes its directory path. Browser "Show in folder" buttons or desktop shortcuts pointing to the original location are not automatically updated.
4. **Files locked by active processes**: Files held with exclusive locks by other programs (e.g., video editing software or word processors) cannot be moved until closed. After 3 retries, they are skipped and left in place.
5. **No background sorting while closed**: DropShelf is a desktop application, not an OS daemon or kernel driver. Files downloaded while the app is closed remain unsorted until the app is launched and "Organize Existing Files" is clicked.
6. **Prolonged download stalls**: If a download stalls longer than the stability timeout and the downloading application completely releases its write lock during the stall, the file may be treated as complete.
