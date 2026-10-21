"""Keyboard discovery of existing PUBLIC Builds through the scoped owner CLI."""

import json
import queue
import threading
from pathlib import Path
from typing import Any

from panestria.cli.build_tui import BuildReviewClient, BuildReviewTerminal


class BuildGoalBrowser:
    def __init__(self, config: Path):
        self.client = BuildReviewClient(config)
        self.rows: list[dict[str, Any]] = []
        self.events: queue.Queue[dict[str, Any] | None] = queue.Queue()
        self.busy, self.closed, self.selected = False, False, 0
        self.notice = "Read-only goal discovery. No worker is started."

    def refresh(self) -> None:
        if self.busy or self.closed:
            return
        self.rows, self.selected, self.busy = [], 0, True
        self.notice = "Reading scoped canonical goals."

        def read() -> None:
            try:
                value = self.client.request("goals", ())
            except Exception:
                value = None
            if not self.closed:
                self.events.put(value)

        threading.Thread(target=read, daemon=True).start()

    def close(self) -> None:
        self.closed, self.rows = True, []
        self.client.close()

    def run(self, screen: Any) -> None:
        import curses

        screen.keypad(True)
        screen.timeout(100)
        self.refresh()
        try:
            while True:
                while not self.events.empty():
                    value = self.events.get_nowait()
                    self.busy = False
                    self.rows = value["goals"] if value else []
                    self.notice = (
                        "Latest 32 PUBLIC Builds in this project. Select to review; no work starts."
                        if value
                        else "Goal list UNCONFIRMED; F5 refreshes. No automatic retry."
                    )
                screen.erase()
                rows, cols = screen.getmaxyx()

                def line(row: int, text: str, selected: bool = False, cols: int = cols) -> None:
                    try:
                        screen.addnstr(row, 1, text, max(1, cols - 3), curses.A_REVERSE if selected else 0)
                    except curses.error:
                        pass

                line(0, "Panestria | PUBLIC BUILD GOALS | local owner")
                if rows < 18 or cols < 80:
                    line(2, "Resize to at least 80 columns x 18 rows. q quits.")
                else:
                    line(1, "Opening a goal does not submit, accept a plan or approve a merge.")
                    if not self.rows and not self.busy:
                        line(
                            3, "No visible goals. Use the separate explicit plan stage/accept commands to create work."
                        )
                    visible = max(1, (rows - 7) // 3)
                    offset = (self.selected // visible) * visible
                    for i, goal in enumerate(self.rows[offset : offset + visible], offset):
                        y = 3 + (i - offset) * 3
                        line(y, f"{goal['status']} | {goal['goal_id']}", i == self.selected)
                        # Titles are untrusted repository/contract text. Escape controls and bidi.
                        line(y + 1, json.dumps(goal["title"], ensure_ascii=True))
                        line(
                            y + 2,
                            f"Running {goal['running_tasks']} | awaiting review {goal['waiting_reviews']}"
                            f" | {goal['created_at']}",
                        )
                    line(rows - 3, self.notice)
                    line(rows - 2, "Up/Down or j/k Select | Enter Review | F5 Refresh | q/F10 Quit")
                    line(rows - 1, "Read-only metadata. Goal progress and exact merge approval are separate views.")
                screen.refresh()
                try:
                    key = screen.get_wch()
                except curses.error:
                    continue
                if key in {"q", curses.KEY_F10}:
                    return
                if key == curses.KEY_F5:
                    self.refresh()
                elif key in {curses.KEY_DOWN, "j"} and self.rows:
                    self.selected = min(self.selected + 1, len(self.rows) - 1)
                elif key in {curses.KEY_UP, "k"}:
                    self.selected = max(self.selected - 1, 0)
                elif key in {"\n", "\r", curses.KEY_ENTER} and self.rows and not self.busy:
                    goal = self.rows[self.selected]
                    if not goal["review_available"]:
                        self.notice = "Proposed plan: separate exact plan acceptance is required; no worker started."
                        continue
                    review = BuildReviewTerminal(BuildReviewClient(self.client.config, goal["goal_id"]))
                    try:
                        review.run(screen)
                    finally:
                        review.close()
                    self.notice = "Returned from review. F5 refreshes the goal list; no implicit cancellation."
        finally:
            self.close()
            screen.erase()
            screen.refresh()
