"""Keyboard offline Ask view; all task decisions stay in the existing server."""

import json
import queue
import sys
import threading
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

import typer

from panestria.cli.tui_client import LocalAskClient, TerminalUnavailable
from panestria.config_local import LocalApplicationRejected
from panestria.contracts.activity import ProjectActivity


def literal(value: str) -> str:
    # Curses is a terminal, so never send source/model escape, OSC, bidi or
    # control characters to it. Newlines are layout, not terminal commands.
    return "".join(c for c in value if c == "\n" or (c.isprintable() and unicodedata.category(c) != "Cf"))


def wrapped(value: str, width: int) -> list[str]:
    lines, current, cells = [], "", 0
    for char in literal(value):
        size = 0 if unicodedata.combining(char) else 2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1
        if char == "\n" or cells + size > width:
            lines.append(current)
            current, cells = "", 0
        if char != "\n":
            current += char
            cells += size
    return [*lines, current]


@dataclass
class TerminalView:
    connected: bool = False
    question: str = field(default="", repr=False)
    answer: str = field(default="", repr=False)
    sources: list[str] = field(default_factory=list, repr=False)
    request_id: str | None = None
    state: str = "No request submitted"
    notice: str = "Checking the local server. Start 'panestria local serve' separately if unavailable."
    editing: bool = False
    scroll: int = 0
    activity_active: bool = False
    activity_fresh: bool = False
    activity_received_at: float = 0.0
    activity: ProjectActivity | None = field(default=None, repr=False)


class AskTerminal:
    def __init__(self, client: LocalAskClient, *, metadata_only: bool = False):
        self.metadata_only = metadata_only
        self.client, self.view = client, TerminalView(activity_active=metadata_only)
        if metadata_only:
            self.view.notice = "Checking project metadata. Start 'panestria activity serve' separately if unavailable."
        self.generation = 0
        self.busy: set[str] = set()
        self.events: queue.Queue[tuple[int, str, dict[str, Any] | TerminalUnavailable]] = queue.Queue()
        self.closed = False

    def start(self, kind: str, operation: Callable[[], dict[str, Any]]) -> None:
        if self.closed or kind in self.busy:
            return
        generation = self.generation
        self.busy.add(kind)

        def work() -> None:
            try:
                result: dict[str, Any] | TerminalUnavailable = operation()
            except TerminalUnavailable as error:
                result = error
            except Exception:
                result = TerminalUnavailable("operation_unconfirmed_check_receipt")
            if not self.closed:
                self.events.put((generation, kind, result))

        # Bounded HTTP workers never own the server/model. Closing the terminal
        # does not wait on inference or claim to cancel an unconfirmed request.
        threading.Thread(target=work, daemon=True).start()

    def drain(self) -> None:
        while True:
            try:
                generation, kind, result = self.events.get_nowait()
            except queue.Empty:
                return
            if self.closed or generation != self.generation:
                continue
            self.busy.discard(kind)
            v = self.view
            if isinstance(result, TerminalUnavailable):
                if result.clear:
                    self.generation += 1
                    self.busy.clear()
                    self.view = TerminalView(
                        activity_active=self.metadata_only,
                        notice=result.code + "; view cleared. Correct setup and refresh.",
                    )
                else:
                    v.notice = result.code + "; no automatic retry. Refresh the receipt before new work."
                    if kind == "status":
                        v.connected = False
                    if kind == "activity":
                        v.activity_fresh = False
                        v.notice = result.code + "; snapshot unconfirmed. Refresh explicitly; no work was started."
                    if kind == "ask" and not result.uncertain:
                        v.request_id, v.state = None, "Not submitted"
                        v.notice = result.code + "; question was not sent. Check the server, then submit explicitly."
                continue
            if kind == "status":
                if not v.connected:
                    v.notice = "Connected to your offline Ask scope. F2/new: question; Enter: submit."
                v.connected = True
                continue
            if kind == "activity":
                v.activity = ProjectActivity.model_validate_json(json.dumps(result))
                v.activity_fresh = True
                v.activity_received_at = time.monotonic()
                v.notice = "Read-only canonical states; they do not certify checks, answers or release acceptance."
                continue
            observed = str(result["state"])
            if v.state in {"COMPLETED", "CANCELLED", "FAILED"} and observed != v.state:
                continue  # An older receipt cannot regress an already confirmed terminal state.
            v.state = observed
            if v.state == "COMPLETED" and kind == "ask" and "text" in result:
                v.answer = literal(result["text"])
                v.sources = [
                    literal(str(source.get("source_id", "unknown")))[:128]
                    for source in result.get("sources", [])
                    if isinstance(source, dict)
                ]
                v.notice = "Answer shown only in this terminal; it is not automatically saved."
            elif v.state in {"CANCELLED", "FAILED"}:
                v.answer = ""
                v.notice = "Server confirmed " + v.state + "."
            elif kind == "cancel":
                v.notice = "Server confirmed " + v.state + "; cancellation cannot undo completed work."
            elif kind == "receipt":
                v.notice = "Receipt refreshed. Unretained answer text cannot be recovered from a receipt."

    def submit(self) -> None:
        v = self.view
        if v.activity_active:
            return
        if not v.connected or "ask" in self.busy or not v.question.strip():
            v.notice = "Connect first; enter a question; allow only one submission at a time."
            return
        if v.request_id and v.state not in {"COMPLETED", "CANCELLED", "FAILED"}:
            v.notice = "Prior submission is unconfirmed. Refresh its receipt or cancel before starting another."
            return
        identity, question = str(uuid4()), v.question
        self.generation += 1
        self.busy.clear()
        v.sources = []
        v.request_id, v.answer, v.state, v.editing, v.scroll = (
            identity,
            "",
            "Awaiting server receipt (unconfirmed)",
            False,
            0,
        )
        v.notice = "Waiting for local inference. F6/c requests cancellation; no cloud fallback."
        self.start("ask", lambda: self.client.ask(identity, question))

    def close(self) -> None:
        self.closed = True
        self.generation += 1
        self.busy.clear()
        self.view = TerminalView(notice="Closed")
        while not self.events.empty():
            try:
                self.events.get_nowait()
            except queue.Empty:
                break

    def refresh(self) -> None:
        if self.view.activity_active:
            self.start("activity", self.client.activity)
            return
        self.start("status", self.client.status)
        if self.view.request_id:
            self.start("receipt", partial(self.client.receipt, self.view.request_id))

    def cancel(self) -> None:
        if self.view.activity_active:
            return  # The metadata pane offers no mutation, even for a current Ask.
        if self.view.request_id:
            self.start("cancel", partial(self.client.cancel, self.view.request_id))
            self.view.notice = "Cancellation requested, awaiting the server's decision."

    def toggle_activity(self) -> None:
        if self.metadata_only:
            return
        self.view.activity_active = not self.view.activity_active
        if self.view.activity_active:
            self.refresh()

    def run(self, screen: Any) -> None:
        import curses

        screen.keypad(True)
        screen.timeout(100)
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        self.refresh()
        checked, leaving = time.monotonic(), False

        def line(row: int, value: str) -> None:
            rows, cols = screen.getmaxyx()
            if 0 <= row < rows:
                try:
                    fitted = wrapped(value.replace("\n", " "), max(1, cols - 2))[0]
                    screen.addnstr(row, 1, fitted, max(0, cols - 2))
                except curses.error:
                    pass  # Small/wide-character edge: redraw on resize, never interpret content.

        try:
            while True:
                self.drain()
                v = self.view
                if not self.metadata_only and v.connected and time.monotonic() - checked >= 5:
                    self.start("status", self.client.status)
                    checked = time.monotonic()
                screen.erase()
                rows, cols = screen.getmaxyx()
                line(0, "Panestria | PROJECT TASKS | read only" if v.activity_active
                     else "Panestria | OFFLINE ASK | terminal view")
                if rows < 18 or cols < 64:
                    line(2, "Resize to at least 64 columns x 18 rows. F10 quits.")
                elif v.activity_active:
                    page = v.activity
                    line(1, f"Project: {self.client.config.project_id}")
                    fresh = v.activity_fresh and time.monotonic() - v.activity_received_at <= 15
                    line(2, "Snapshot: " + ("FRESH" if fresh else "UNCONFIRMED/STALE"))
                    line(3, "Observed: " + (page.observed_at.isoformat() if page else "not available"))
                    line(4, "! MODE     ID       CANONICAL STATE    A:active R:review H:held Build")
                    if page is None:
                        line(5, "No confirmed snapshot. F5 refreshes without asking a model.")
                    elif not page.entries:
                        line(5, "No activity in this configured project.")
                    else:
                        for offset, entry in enumerate(page.entries, 5):
                            held = "?" if entry.held_build_claims is None else str(entry.held_build_claims)
                            line(offset, f"{'!' if entry.needs_attention else ' '} {entry.workflow:8} "
                                 f"{str(entry.id)[:8]} {entry.canonical_state:18} "
                                 f"A:{entry.active_tasks} R:{entry.waiting_reviews} H:{held}")
                    line(rows - 5, "n: next page available" if page and page.next_cursor else "No further page")
                    line(rows - 4, "! needs attention; held claims never imply free capacity")
                    line(rows - 3, v.notice)
                    line(rows - 2, ("" if self.metadata_only else "F4/t Ask | ") +
                         "F5/r Refresh first page | n Next | F10/q Quit")
                    line(rows - 1, "States only; content and exact approvals stay in their separate review views.")
                else:
                    line(
                        1,
                        "Server: "
                        + ("CONNECTED" if v.connected else "UNAVAILABLE/CHECKING")
                        + " | "
                        + self.client.config.origin,
                    )
                    line(2, f"Project: {self.client.config.project_id} | Restricted/offline | Response not retained")
                    line(
                        4,
                        "Question [editing; Enter sends, Escape discards]"
                        if v.editing
                        else "Question [F2 / n to edit]",
                    )
                    line(5, v.question[-max(1, cols - 3) :] or "No question entered.")
                    line(7, "Request status: " + v.state)
                    line(8, "Request: " + (v.request_id or "none"))
                    line(9, "Context source IDs: " + (", ".join(v.sources) or "none included"))
                    answer = wrapped(v.answer or "No answer received.", max(1, cols - 3))
                    v.scroll = min(v.scroll, max(0, len(answer) - (rows - 15)))
                    line(10, "Answer [PgUp/PgDn scroll]")
                    for row, value in enumerate(answer[v.scroll : v.scroll + rows - 15], 11):
                        line(row, value)
                    line(rows - 3, v.notice)
                    line(rows - 2, "F2/n Question | F5/r Refresh | F6/c Cancel | F10/q Quit")
                    line(rows - 1, "F4/t Project tasks (read only). Build/research actions use their separate views.")
                screen.refresh()
                try:
                    key = screen.get_wch()
                except curses.error:
                    continue
                if key == curses.KEY_RESIZE:
                    continue
                if key == curses.KEY_F10:
                    key = "q"
                    v.editing = False
                if key == curses.KEY_F5:
                    self.refresh()
                    continue
                if key == curses.KEY_F4 and not v.editing:
                    self.toggle_activity()
                    continue
                if key == curses.KEY_F6:
                    self.cancel()
                    continue
                if v.editing:
                    if key in {"\n", "\r", curses.KEY_ENTER}:
                        self.submit()
                    elif key == "\x1b":
                        v.question, v.editing = "", False
                    elif key in {curses.KEY_BACKSPACE, "\x7f", "\b"}:
                        v.question = v.question[:-1]
                    elif isinstance(key, str) and literal(key) == key and key.isprintable():
                        if len((v.question + key).encode()) <= 4096:
                            v.question += key
                    continue
                if key == "t":
                    self.toggle_activity()
                    continue
                if v.activity_active and key != "q":
                    if key == "n" and v.activity and v.activity.next_cursor:
                        self.start("activity", partial(self.client.activity, v.activity.next_cursor))
                    elif key == "r":
                        self.refresh()
                    continue
                if key in {curses.KEY_F10, "q"}:
                    if "ask" in self.busy and not leaving:
                        v.notice = "Request may still run. F6/c cancels; press quit again to leave it unconfirmed."
                        leaving = True
                    else:
                        return
                elif key in {curses.KEY_F2, "n"}:
                    if "ask" not in self.busy:
                        v.question, v.editing = "", True
                        leaving = False
                elif key in {curses.KEY_F5, "r"}:
                    self.refresh()
                elif key in {curses.KEY_F6, "c"} and v.request_id:
                    self.cancel()
                elif key == curses.KEY_NPAGE:
                    v.scroll += max(1, rows - 15)
                elif key == curses.KEY_PPAGE:
                    v.scroll = max(0, v.scroll - max(1, rows - 15))
        finally:
            self.close()
            screen.erase()
            screen.refresh()


def tui_command(config: Annotated[Path, typer.Option("--config")]) -> None:
    """Open the keyboard offline Ask application; run the local server separately."""
    run_terminal(lambda: LocalAskClient(config))


def run_terminal(client: Callable[[], LocalAskClient], *, metadata_only: bool = False) -> None:
    try:
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            raise TerminalUnavailable("interactive_terminal_required")
        import curses

        terminal = AskTerminal(client(), metadata_only=metadata_only)
        try:
            curses.wrapper(terminal.run)
        finally:
            terminal.close()
    except KeyboardInterrupt:
        return
    except (TerminalUnavailable, LocalApplicationRejected) as error:
        reason = error.code
    except Exception:
        reason = "terminal_unavailable_check_setup"
    else:
        return
    typer.echo(json.dumps({"status": "UNAVAILABLE", "reason": reason}), err=True)
    raise typer.Exit(1)
