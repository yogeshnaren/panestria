"""Keyboard offline Ask view; all task decisions stay in the existing server."""

import json
import queue
import sys
import threading
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

import typer

from panestria.cli.tui_client import LocalAskClient, TerminalUnavailable
from panestria.config_local import LocalApplicationRejected
from panestria.contracts.activity import ActivityTimeline, ProjectActivity
from panestria.contracts.storage_status import StorageStatus


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
    timeline_goal: str | None = None
    timeline: ActivityTimeline | None = field(default=None, repr=False)
    timeline_fresh: bool = False
    timeline_received_at: float = 0.0
    timeline_scroll: int = 0
    storage_available: bool = False
    storage_active: bool = False
    storage: StorageStatus | None = field(default=None, repr=False)
    storage_next_check: float = 0.0
    storage_scroll: int = 0
    storage_notice: str = "No confirmed storage observation."


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
            if kind == "storage" and isinstance(result, TerminalUnavailable) and not result.clear:
                v.storage = None
                v.storage_notice = result.code + "; storage unconfirmed. No action performed."
                v.storage_next_check = time.monotonic() + 60
                continue
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
                    if kind in {"activity", "timeline"}:
                        v.activity_fresh = False
                        v.timeline_fresh = False
                        v.notice = result.code + "; snapshot unconfirmed. Refresh explicitly; no work was started."
                    if kind == "ask" and not result.uncertain:
                        v.request_id, v.state = None, "Not submitted"
                        v.notice = result.code + "; question was not sent. Check the server, then submit explicitly."
                continue
            if kind == "storage":
                v.storage = StorageStatus.model_validate_json(json.dumps(result))
                v.storage_next_check = time.monotonic() + v.storage.next_check_seconds
                v.storage_notice = "Read-only observations; no storage changes are performed."
                continue
            if kind == "status":
                if not v.connected:
                    v.notice = "Connected to your offline Ask scope. F2/new: question; Enter: submit."
                v.connected = True
                continue
            if kind == "timeline":
                page = ActivityTimeline.model_validate_json(json.dumps(result))
                if str(page.snapshot.goal_id) != v.timeline_goal:
                    continue
                if not page.events and not page.resync and v.timeline is not None:
                    page = page.model_copy(update={"events": v.timeline.events})
                if v.timeline is None or v.timeline.events != page.events:
                    v.timeline_scroll = 0
                v.timeline = page
                v.timeline_fresh, v.timeline_received_at = True, time.monotonic()
                v.notice = (
                    "History gap/future cursor: canonical snapshot restored; missing events are not invented."
                    if page.resync
                    else "Canonical snapshot plus event metadata; payloads and approvals are omitted."
                )
                continue
            if kind == "activity":
                v.activity = ProjectActivity.model_validate_json(json.dumps(result))
                v.storage_available = v.activity.storage_available
                if v.storage_available:
                    self.start("storage", self.client.storage)
                v.activity_fresh = True
                v.activity_received_at = time.monotonic()
                v.notice = "Read-only canonical states; they do not certify checks, answers or release acceptance."
                continue
            observed = str(result["state"])
            if v.state in {"COMPLETED", "CANCELLED", "FAILED", "UNAVAILABLE"} and observed != v.state:
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
            elif v.state in {"CANCELLED", "FAILED", "UNAVAILABLE"}:
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
        if v.request_id and v.state not in {"COMPLETED", "CANCELLED", "FAILED", "UNAVAILABLE"}:
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
        if self.view.storage_active:
            self.start("storage", self.client.storage)
            return
        if self.view.activity_active:
            if self.view.timeline_goal:
                after = self.view.timeline.next_cursor if self.view.timeline else "0"
                self.start("timeline", partial(self.client.timeline, self.view.timeline_goal, after))
                return
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

    def select_timeline(self, index: int) -> None:
        v = self.view
        if not v.activity_active or not v.activity or not 0 <= index < len(v.activity.entries):
            return
        entry = v.activity.entries[index]
        if entry.source != "GOAL":
            v.notice = "Ask has separate request receipts; this row has no goal event timeline."
            return
        v.timeline_goal, v.timeline, v.timeline_fresh = str(entry.id), None, False
        self.start("timeline", partial(self.client.timeline, str(entry.id), "0"))

    def toggle_activity(self) -> None:
        if self.metadata_only:
            return
        self.view.activity_active = not self.view.activity_active
        self.view.timeline_goal = None
        self.view.storage_active = False
        if self.view.activity_active:
            self.refresh()

    def storage_lines(self, width: int) -> list[str]:
        value = self.view.storage
        if value is None:
            return ["Storage observation UNCONFIRMED. Refresh explicitly; no cleanup is available."]
        enabled = "UNKNOWN" if value.notifications_enabled is None else "ON" if value.notifications_enabled else "OFF"
        lines = [
            f"State: {value.state} | notifications: {enabled} | {value.reason}",
            "Owner-wide host metadata; project ownership is unassessed.",
            "Observed: " + (value.observed_at.isoformat() if value.observed_at else "UNKNOWN"),
        ]
        if value.observed_at is not None:
            age = (datetime.now(UTC) - value.observed_at).total_seconds()
            if age < -5 or age > value.sample_interval_seconds + 35 or value.state != "OBSERVED":
                lines.append("UNCONFIRMED/STALE: values below are last observed, not current health.")

        def size(n: int | None) -> str:
            return "UNKNOWN" if n is None else f"{n / 1024**3:.2f} GiB"

        if value.capacity:
            disk = value.capacity
            percent = "UNKNOWN" if disk.used_percent is None else f"{disk.used_percent:.2f}%"
            lines += [
                f"Capacity {disk.status}: last free {size(disk.available_bytes)} | used {percent}",
                f"Total {size(disk.total_bytes)} | reserved {size(disk.reserved_bytes)}",
            ]
        for item in value.components:
            share = "UNKNOWN" if item.filesystem_share_percent is None else f"{item.filesystem_share_percent:.2f}%"
            lines += [
                f"{item.label}: {item.status} {size(item.bytes)} | share estimate {share}",
                f"Basis: {item.basis}",
            ]
        lines += [f"Timeshift: {value.timeshift_status}; physical snapshot bytes UNKNOWN"]
        if value.timeshift_schedules:
            schedules = [
                k + "=" + ("UNKNOWN" if choice is None else "ON" if choice else "OFF")
                for k, choice in value.timeshift_schedules.items()
            ]
            lines.append("Configured schedules: " + ", ".join(schedules))
        lines += ["Docker estimates can overlap and are daemon-wide; never sum them as physical totals."]
        for warning in value.warnings:
            lines += [f"{warning.severity} {warning.code}: {warning.recommendation}"]
        if not value.warnings:
            lines.append(
                "No storage warning in this sample."
                if value.state == "OBSERVED"
                else "Warning list unavailable; inspect the selected settings/source."
            )
        lines += [
            "Owner options: keep/defer work, inspect usage, review backup/cache impact, or add/move capacity.",
            "No deletion, pruning, backup change, worker or model action is offered here.",
        ]
        return [part for text in lines for part in wrapped(text, max(1, width - 3))]

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
                if v.storage_available and time.monotonic() >= v.storage_next_check:
                    self.start("storage", self.client.storage)
                screen.erase()
                rows, cols = screen.getmaxyx()
                line(
                    0,
                    "Panestria | HOST STORAGE | read only"
                    if v.storage_active
                    else "Panestria | GOAL TIMELINE | read only"
                    if v.timeline_goal and v.activity_active
                    else "Panestria | PROJECT TASKS | read only"
                    if v.activity_active
                    else getattr(self.client, "view_title", "Panestria | OFFLINE ASK | terminal view"),
                )
                if rows < 18 or cols < 64:
                    line(2, "Resize to at least 64 columns x 18 rows. F10 quits.")
                elif v.storage_active:
                    body = self.storage_lines(cols)
                    visible = max(1, rows - 7)
                    v.storage_scroll = min(v.storage_scroll, max(0, len(body) - visible))
                    for row, text in enumerate(body[v.storage_scroll : v.storage_scroll + visible], 2):
                        line(row, text)
                    line(
                        rows - 4,
                        f"Rows {v.storage_scroll + 1}-{min(len(body), v.storage_scroll + visible)}/{len(body)}",
                    )
                    line(rows - 3, v.storage_notice)
                    line(rows - 2, "PgUp/PgDn Scroll | F5/r Read cache | o/b/Esc Back | q Quit")
                    line(rows - 1, "Samples are at least 60s apart. Owner review only; no storage changes are made.")
                elif v.activity_active and v.timeline_goal:
                    timeline_page = v.timeline
                    fresh = v.timeline_fresh and time.monotonic() - v.timeline_received_at <= 15
                    line(1, "Goal: " + v.timeline_goal)
                    line(2, "Snapshot: " + ("FRESH" if fresh else "UNCONFIRMED/STALE"))
                    line(3, "Canonical goal: " + (timeline_page.snapshot.status if timeline_page else "unconfirmed"))
                    line(
                        4,
                        "Cursor: "
                        + (timeline_page.next_cursor if timeline_page else "0")
                        + " | no acceptance authority",
                    )
                    if timeline_page:
                        visible = max(1, rows - 12)
                        v.timeline_scroll = min(v.timeline_scroll, max(0, len(timeline_page.events) - visible))
                        line(
                            5,
                            f"Events {v.timeline_scroll + 1 if timeline_page.events else 0}-"
                            f"{min(v.timeline_scroll + visible, len(timeline_page.events))}/"
                            f"{len(timeline_page.events)}",
                        )
                        for row, event in enumerate(
                            timeline_page.events[v.timeline_scroll : v.timeline_scroll + visible], 6
                        ):
                            line(
                                row, f"{event.seq}  {event.kind}  [{event.privacy_label}; schema{event.schema_version}]"
                            )
                    else:
                        line(6, "No confirmed event page. F5 refreshes explicitly.")
                    line(rows - 4, "Event metadata never supplies a task/check PASS or merge permission.")
                    line(rows - 3, v.notice)
                    line(rows - 2, "PgUp/PgDn Scroll | F5/n Next | r Replay | b/Esc Back | q Quit")
                    line(rows - 1, "Goal state comes from its canonical snapshot, not from event-name guesses.")
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
                            line(
                                offset,
                                f"{offset - 4} {'!' if entry.needs_attention else ' '} {entry.workflow:8} "
                                f"{str(entry.id)[:8]} {entry.canonical_state:18} "
                                f"A:{entry.active_tasks} R:{entry.waiting_reviews} H:{held}",
                            )
                    line(rows - 5, "n: next page available" if page and page.next_cursor else "No further page")
                    line(rows - 4, "! needs attention; held claims never imply free capacity")
                    line(rows - 3, v.notice)
                    line(
                        rows - 2,
                        ("" if self.metadata_only else "F4/t Ask | ")
                        + "1-8 Goal timeline | o Storage | F5/r Refresh | n Next | F10/q Quit",
                    )
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
                    line(3, getattr(self.client, "selection_notice", ""))
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
                if v.storage_available and not v.storage_active:
                    attention: str = "UNCONFIRMED" if v.storage is None else v.storage.state
                    if v.storage is not None and v.storage.state == "OBSERVED" and v.storage.observed_at:
                        age = (datetime.now(UTC) - v.storage.observed_at).total_seconds()
                        if age < -5 or age > v.storage.sample_interval_seconds + 35:
                            attention = "STALE/UNCONFIRMED"
                        elif v.storage.warnings:
                            warning = max(
                                v.storage.warnings, key=lambda w: {"INFO": 0, "WARNING": 1, "CRITICAL": 2}[w.severity]
                            )
                            attention = warning.severity + " " + warning.code
                        else:
                            attention = "0 notices in last sample"
                    line(rows - 4, "Storage " + attention + "; o opens read-only recommendations.")
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
                if v.storage_active:
                    if key in {"o", "b", "\x1b"}:
                        v.storage_active = False
                    elif key == "r":
                        self.refresh()
                    elif key == curses.KEY_NPAGE:
                        v.storage_scroll += max(1, rows - 7)
                    elif key == curses.KEY_PPAGE:
                        v.storage_scroll = max(0, v.storage_scroll - max(1, rows - 7))
                    elif key == "q":
                        return
                    continue
                if key == "o" and v.activity_active and v.storage_available:
                    v.storage_active, v.storage_scroll = True, 0
                    self.start("storage", self.client.storage)
                    continue
                if key == "t":
                    self.toggle_activity()
                    continue
                if v.activity_active and v.timeline_goal and key != "q":
                    if key in {"b", "\x1b"}:
                        v.timeline_goal, v.timeline = None, None
                    elif key == "r":
                        self.start("timeline", partial(self.client.timeline, v.timeline_goal, "0"))
                    elif key == "n":
                        self.refresh()
                    elif key == curses.KEY_NPAGE:
                        v.timeline_scroll += max(1, rows - 12)
                    elif key == curses.KEY_PPAGE:
                        v.timeline_scroll = max(0, v.timeline_scroll - max(1, rows - 12))
                    continue
                if v.activity_active and key != "q":
                    if isinstance(key, str) and key in "12345678":
                        self.select_timeline(int(key) - 1)
                    elif key == "n" and v.activity and v.activity.next_cursor:
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
