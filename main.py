"""
Main entry point for DropShelf desktop application.
"""

from __future__ import annotations

import logging
import sys
import tkinter as tk
from pathlib import Path

# Add project root to sys.path so 'dropsort' package is readily importable
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dropsort.config import DEFAULT_DB_PATH, DEFAULT_RULES_PATH, ThreadSafeRulesManager
from dropsort.history import HistoryManager
from dropsort.ui import MainWindow


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] (%(threadName)s) %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main() -> None:
    setup_logging()
    logger = logging.getLogger("main")
    logger.info("Initializing application...")

    rules_manager = ThreadSafeRulesManager(DEFAULT_RULES_PATH)
    history_manager = HistoryManager(DEFAULT_DB_PATH)

    root = tk.Tk()
    # Configure default styling
    root.tk_setPalette(background="#F0F0F0", foreground="#000000")

    app = MainWindow(root=root, rules_manager=rules_manager, history_manager=history_manager)

    logger.info("Starting Tkinter main event loop.")
    root.mainloop()


if __name__ == "__main__":
    main()
