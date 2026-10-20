# Starter prompt for Antigravity

Copy everything below the line into Antigravity. Put `prd.md` and `trd.md` in the project folder first.

---

You are building **DropSort**, a small desktop app that watches a folder (Downloads by default) and automatically moves each new file into the right subfolder, with a live activity log and undo. It is my Operating Systems case study project for Mumbai University, and I will present it live to my mentor, so it must be reliable, simple and easy for me to explain.

## Step 0: Read first, then ask your doubts

1. Read `prd.md` and `trd.md` in full. They are the source of truth for scope, behavior, structure and tests.
2. **Before writing any code, ask me all your doubts and wait for my answers.** Ask them in one numbered list. Do not guess on anything unclear, and do not continue until I reply.

## What to build

- Python 3.11+, `watchdog` for file events, Tkinter with `ttk` for the UI, SQLite for undo history, `rules.json` for rules, `pytest` for tests.
- Follow the project structure and module specs in `trd.md` exactly.
- Two screens only: Main (path, Start/Stop, status, Organize existing files, activity log, Undo) and Rules (add and delete custom rules).
- Keep the UI plain and minimal. Default `ttk` theme, clear spacing, no decorative extras.

## Rules you must follow

- Build only what is in the PRD scope. Do not add features from the out-of-scope list.
- Keep the code simple and readable. Add short comments where an OS concept is used (file event, thread, queue, file lock), because I need to explain them.
- Never touch the real Downloads folder during development or tests. All tests use temporary folders.
- Never overwrite a file. Never move a file that is still being written. Never recurse into subfolders.
- Tkinter widgets are only touched from the main thread. The watcher side talks to the UI through a `queue.Queue`.

## Build in milestones

After each milestone, run the tests, tell me what passed, and then continue.

1. Project setup, `config.py`, `rules.py`, with tests
2. `mover.py` and `stability.py`, with tests
3. `history.py` with undo, with tests
4. `watcher.py` with the full pipeline, plus the integration test
5. `ui.py` and `main.py`
6. README with install steps, how to run, and a short section on the OS concepts used

## Testing and verification

- Run the full test suite after every milestone and again at the end.
- Fix every failure before moving on. Do not skip or delete failing tests.
- At the end, launch the app against a temporary test folder, drop in sample files (including a slowly written file, a duplicate name, and a `.crdownload` file) and confirm sorting, collision rename, skipping and undo all work.
- Then walk through the manual checklist in `trd.md` section 7 and tell me which items you verified and which I need to check myself.
- Give me a final summary: what was built, test results, and anything incomplete.

## Git

- Do **not** commit or push to GitHub on your own.
- When everything works and tests pass, **ask me before pushing** and wait for my confirmation.
