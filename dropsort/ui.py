"""
Tkinter and ttk user interface for DropShelf.
"""

from __future__ import annotations

import logging
import queue
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from .config import APP_NAME, ThreadSafeRulesManager
from .history import HistoryManager
from .watcher import FolderWatcher

logger = logging.getLogger(__name__)


class RulesDialog(tk.Toplevel):
    """
    Dialog window for managing custom file sorting rules.
    Allows adding and deleting rules matching filenames by substring.
    """

    def __init__(self, parent: tk.Tk, rules_manager: ThreadSafeRulesManager) -> None:
        super().__init__(parent)
        self.rules_manager = rules_manager

        self.title(f"{APP_NAME} - Custom Rules")
        self.geometry("520x400")
        self.minsize(450, 320)
        self.transient(parent)
        self.grab_set()

        self._build_ui()
        self._load_rules()

    def _build_ui(self) -> None:
        padding_frame = ttk.Frame(self, padding="12")
        padding_frame.pack(fill=tk.BOTH, expand=True)

        header_label = ttk.Label(
            padding_frame,
            text="Custom rules take priority over file-type rules.\nFirst matching rule in the list applies.",
            font=("Segoe UI", 9),
        )
        header_label.pack(anchor=tk.W, pady=(0, 10))

        # Table of existing custom rules
        columns = ("contains", "folder")
        self.tree = ttk.Treeview(padding_frame, columns=columns, show="headings", height=8, selectmode="browse")
        self.tree.heading("contains", text="Filename Contains (Keyword)")
        self.tree.heading("folder", text="Destination Subfolder")
        self.tree.column("contains", width=180)
        self.tree.column("folder", width=240)

        scrollbar = ttk.Scrollbar(padding_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, in_=self.tree)

        # Input fields for adding a rule
        input_frame = ttk.LabelFrame(padding_frame, text="Add New Rule", padding="8")
        input_frame.pack(fill=tk.X, pady=(10, 0))

        ttk.Label(input_frame, text="Keyword:").grid(row=0, column=0, sticky=tk.W, padx=4, pady=4)
        self.contains_var = tk.StringVar()
        self.contains_entry = ttk.Entry(input_frame, textvariable=self.contains_var, width=18)
        self.contains_entry.grid(row=0, column=1, sticky=tk.W, padx=4, pady=4)

        ttk.Label(input_frame, text="Subfolder:").grid(row=0, column=2, sticky=tk.W, padx=4, pady=4)
        self.folder_var = tk.StringVar()
        self.folder_entry = ttk.Entry(input_frame, textvariable=self.folder_var, width=20)
        self.folder_entry.grid(row=0, column=3, sticky=tk.W, padx=4, pady=4)

        btn_add = ttk.Button(input_frame, text="Add Rule", command=self._add_rule)
        btn_add.grid(row=0, column=4, padx=(8, 0), pady=4)

        # Actions bar
        actions_frame = ttk.Frame(padding_frame)
        actions_frame.pack(fill=tk.X, pady=(10, 0))

        btn_delete = ttk.Button(actions_frame, text="Delete Selected Rule", command=self._delete_rule)
        btn_delete.pack(side=tk.LEFT)

        btn_close = ttk.Button(actions_frame, text="Close", command=self.destroy)
        btn_close.pack(side=tk.RIGHT)

    def _load_rules(self) -> None:
        for row in self.tree.get_children():
            self.tree.delete(row)

        rules = self.rules_manager.get_rules()
        for idx, rule in enumerate(rules.get("custom_rules", [])):
            self.tree.insert("", tk.END, iid=str(idx), values=(rule.get("contains", ""), rule.get("folder", "")))

    def _add_rule(self) -> None:
        keyword = self.contains_var.get().strip()
        folder = self.folder_var.get().strip()

        if not keyword or not folder:
            messagebox.showwarning("Incomplete Rule", "Please provide both a keyword and destination subfolder.", parent=self)
            return

        rules = self.rules_manager.get_rules()
        rules.setdefault("custom_rules", []).append({"contains": keyword, "folder": folder})
        self.rules_manager.update_rules(rules)

        self.contains_var.set("")
        self.folder_var.set("")
        self._load_rules()

    def _delete_rule(self) -> None:
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Select Rule", "Please select a rule from the table to delete.", parent=self)
            return

        idx = int(selected[0])
        rules = self.rules_manager.get_rules()
        custom_rules = rules.get("custom_rules", [])
        if 0 <= idx < len(custom_rules):
            custom_rules.pop(idx)
            rules["custom_rules"] = custom_rules
            self.rules_manager.update_rules(rules)
            self._load_rules()


class MainWindow:
    """
    Main application window for the DropShelf desktop interface.
    """

    def __init__(
        self,
        root: tk.Tk,
        rules_manager: ThreadSafeRulesManager,
        history_manager: HistoryManager,
    ) -> None:
        self.root = root
        self.rules_manager = rules_manager
        self.history_manager = history_manager

        self.event_queue: queue.Queue = queue.Queue()
        rules = self.rules_manager.get_rules()
        watch_folder = Path(rules.get("watch_folder", str(Path.home() / "Downloads")))

        self.watcher = FolderWatcher(
            watch_folder=watch_folder,
            rules_manager=self.rules_manager,
            history_manager=self.history_manager,
            event_queue=self.event_queue,
        )

        self.root.title(f"{APP_NAME} - Downloads Organizer")
        self.root.geometry("780x520")
        self.root.minsize(650, 420)

        self._build_ui()
        self._load_recent_history()

        # Handle window close gracefully
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Poll the thread-safe queue every 200ms
        self.root.after(200, self._poll_queue)

    def _build_ui(self) -> None:
        container = ttk.Frame(self.root, padding="14")
        container.pack(fill=tk.BOTH, expand=True)

        # 1. Top Panel: Watched path and Watcher controls
        top_frame = ttk.LabelFrame(container, text="Watched Folder", padding="10")
        top_frame.pack(fill=tk.X, pady=(0, 10))

        self.path_label = ttk.Label(
            top_frame,
            text=str(self.watcher.watch_folder),
            font=("Segoe UI", 9, "bold"),
            relief="groove",
            padding="6",
        )
        self.path_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))

        self.change_btn = ttk.Button(top_frame, text="Change Folder...", command=self._change_folder)
        self.change_btn.pack(side=tk.LEFT, padx=(0, 6))

        self.start_btn = ttk.Button(top_frame, text="Start Watching", command=self._toggle_watcher, width=15)
        self.start_btn.pack(side=tk.LEFT, padx=4)

        self.organize_btn = ttk.Button(
            top_frame, text="Organize Existing Files", command=self._organize_existing
        )
        self.organize_btn.pack(side=tk.LEFT, padx=4)

        # 2. Status Banner
        status_bar = ttk.Frame(container)
        status_bar.pack(fill=tk.X, pady=(0, 8))

        self.status_var = tk.StringVar(value="Status: Idle (Click 'Start Watching' to monitor)")
        status_display = ttk.Label(status_bar, textvariable=self.status_var, font=("Segoe UI", 9, "italic"))
        status_display.pack(side=tk.LEFT)

        btn_rules = ttk.Button(status_bar, text="Manage Rules...", command=self._open_rules_dialog)
        btn_rules.pack(side=tk.RIGHT)

        # 3. Activity Log Table
        log_frame = ttk.LabelFrame(container, text="Activity Log", padding="8")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        cols = ("id", "time", "file", "from", "to", "status")
        self.tree = ttk.Treeview(log_frame, columns=cols, show="headings", selectmode="browse")

        self.tree.heading("id", text="ID")
        self.tree.heading("time", text="Time")
        self.tree.heading("file", text="File Name")
        self.tree.heading("from", text="From")
        self.tree.heading("to", text="To")
        self.tree.heading("status", text="Status")

        self.tree.column("id", width=45, anchor=tk.CENTER)
        self.tree.column("time", width=80, anchor=tk.CENTER)
        self.tree.column("file", width=180)
        self.tree.column("from", width=120)
        self.tree.column("to", width=190)
        self.tree.column("status", width=75, anchor=tk.CENTER)

        scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 4. Bottom Controls: Undo
        bottom_frame = ttk.Frame(container)
        bottom_frame.pack(fill=tk.X)

        self.undo_btn = ttk.Button(bottom_frame, text="Undo Selected Move", command=self._undo_selected, width=20)
        self.undo_btn.pack(side=tk.LEFT)

        info_lbl = ttk.Label(bottom_frame, text="Select a completed move to restore the file to its original location.")
        info_lbl.pack(side=tk.LEFT, padx=10)

    def _change_folder(self) -> None:
        new_dir = filedialog.askdirectory(
            title="Select Folder to Watch",
            initialdir=str(self.watcher.watch_folder),
            parent=self.root,
        )
        if new_dir:
            selected_path = Path(new_dir).resolve()
            # Update and persist in rules.json
            rules = self.rules_manager.get_rules()
            rules["watch_folder"] = str(selected_path)
            self.rules_manager.update_rules(rules)

            # Update live watcher and GUI path label
            self.watcher.set_watch_folder(selected_path)
            self.path_label.configure(text=str(selected_path))
            self.status_var.set(f"Status: Watched folder updated to {selected_path}")
            messagebox.showinfo(
                "Watched Folder Changed",
                f"DropShelf is now watching:\n{selected_path}",
                parent=self.root,
            )

    def _toggle_watcher(self) -> None:
        if self.watcher.is_running:
            self.watcher.stop()
            self.start_btn.configure(text="Start Watching")
            self.status_var.set("Status: Stopped")
        else:
            self.watcher.start()
            self.start_btn.configure(text="Stop Watching")
            self.status_var.set("Status: Watching folder...")

    def _organize_existing(self) -> None:
        count = self.watcher.organize_existing()
        if count == 0:
            messagebox.showinfo("Organize Files", "No loose files found in the watched folder.", parent=self.root)
        else:
            self.status_var.set(f"Status: Queued {count} existing file(s) for sorting.")

    def _open_rules_dialog(self) -> None:
        RulesDialog(self.root, self.rules_manager)

    def _undo_selected(self) -> None:
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Undo", "Please select a row in the Activity Log to undo.", parent=self.root)
            return

        item = self.tree.item(selected[0])
        values = item["values"]
        move_id = int(values[0])

        success, msg = self.history_manager.undo(move_id)
        if success:
            self.status_var.set(f"Status: {msg}")
            messagebox.showinfo("Undo Successful", msg, parent=self.root)
        else:
            self.status_var.set(f"Status: {msg}")
            messagebox.showwarning("Undo Failed", msg, parent=self.root)

        self._load_recent_history()

    def _load_recent_history(self) -> None:
        for row in self.tree.get_children():
            self.tree.delete(row)

        records = self.history_manager.recent(limit=100)
        for rec in records:
            time_display = ""
            if rec.get("timestamp"):
                try:
                    dt = datetime.fromisoformat(rec["timestamp"])
                    time_display = dt.strftime("%H:%M:%S")
                except Exception:
                    time_display = str(rec["timestamp"])[:8]

            orig_path = Path(rec["original_path"])
            new_path = Path(rec["new_path"])

            self.tree.insert(
                "",
                tk.END,
                iid=str(rec["id"]),
                values=(
                    rec["id"],
                    time_display,
                    new_path.name,
                    orig_path.parent.name,
                    f"{new_path.parent.name}/{new_path.name}",
                    rec["status"],
                ),
            )

    def _poll_queue(self) -> None:
        """
        Polls the thread-safe queue.
        Guarantees that UI widget manipulation strictly occurs on Tkinter's main thread.
        """
        try:
            while True:
                msg = self.event_queue.get_nowait()
                msg_type = msg.get("type")

                if msg_type == "moved":
                    now_str = datetime.now().strftime("%H:%M:%S")
                    self.tree.insert(
                        "",
                        0,
                        iid=str(msg["id"]),
                        values=(
                            msg["id"],
                            now_str,
                            msg["name"],
                            msg["from"],
                            msg["to"],
                            "moved",
                        ),
                    )
                    self.status_var.set(f"Status: Sorted {msg['name']} -> {msg['to']}")

                elif msg_type == "status":
                    self.status_var.set(f"Status: {msg.get('status')}")

                elif msg_type == "error":
                    self.status_var.set(f"Error on {msg.get('name')}: {msg.get('message')}")
                    self._load_recent_history()

                self.event_queue.task_done()
        except queue.Empty:
            pass

        # Schedule next poll in 200ms
        self.root.after(200, self._poll_queue)

    def _on_close(self) -> None:
        if self.watcher.is_running:
            self.watcher.stop()
        self.root.destroy()
