"""Keyboard review of one canonical PUBLIC Build; existing owner CLI owns effects."""

import copy
import json
import os
import queue
import select
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import typer

from panestria.cli.tui import wrapped


class BuildUnconfirmed(Exception):
    pass


class BuildReviewClient:
    def __init__(self, config: Path, goal: str | None = None):
        self.config, self.goal = config, str(UUID(goal)) if goal is not None else ""
        self.lock, self.closed = threading.Lock(), False
        self.active: subprocess.Popen[bytes] | None = None

    @staticmethod
    def stop(process: subprocess.Popen[bytes]) -> None:
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=2)
            except ProcessLookupError:
                process.wait(timeout=2)

    def close(self) -> None:
        with self.lock:
            self.closed = True
            process = self.active
        if process is not None:
            self.stop(process)

    def request(self, operation: str, arguments: tuple[str, ...]) -> dict[str, Any]:
        # No shell, model call, arbitrary CLI operation or implicit grant.
        if operation not in {"goals", "status", "progress", "approve", "cancel"}:
            raise BuildUnconfirmed
        command = [sys.executable, "-m", "panestria.cli.main", "build", operation, "--config", str(self.config)]
        deadline = time.monotonic() + (30 if operation in {"goals", "status", "progress"} else 65)
        with self.lock:
            if self.closed:
                raise BuildUnconfirmed
            process = subprocess.Popen(
                [*command, *arguments],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            self.active = process
        try:
            assert process.stdout is not None
            body = bytearray()
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise BuildUnconfirmed
                if not select.select([process.stdout], [], [], min(0.1, remaining))[0]:
                    continue
                chunk = os.read(process.stdout.fileno(), 65536)
                if not chunk:
                    break
                if len(body) + len(chunk) > 1024 * 1024:
                    raise BuildUnconfirmed
                body.extend(chunk)
            process.wait(timeout=max(0.001, deadline - time.monotonic()))
            value = json.loads(body)
            if process.returncode or not isinstance(value, dict):
                raise BuildUnconfirmed
            if operation == "status" and (value.get("goal_id") != self.goal or "task_state" not in value):
                raise BuildUnconfirmed
            if operation == "goals":
                from panestria.contracts.build_index import BuildGoalIndex

                BuildGoalIndex.model_validate_json(json.dumps(value))
            if operation == "progress":
                from panestria.contracts.progress import BuildProgress

                observed = BuildProgress.model_validate_json(json.dumps(value))
                if observed.goal_id != self.goal:
                    raise BuildUnconfirmed
            return value
        except (OSError, ValueError, subprocess.SubprocessError):
            raise BuildUnconfirmed from None
        finally:
            # Only the new session owned by this exact child. A committed
            # effect can survive response loss: killing is NOT cancellation.
            self.stop(process)
            if process.stdout is not None:
                process.stdout.close()
            with self.lock:
                if self.active is process:
                    self.active = None

    def status(self) -> dict[str, Any]:
        return self.request("status", (self.goal, "--diff"))


@dataclass
class ReviewView:
    snapshot: dict[str, Any] = field(default_factory=dict, repr=False)
    progress: dict[str, Any] = field(default_factory=dict, repr=False)
    frozen: dict[str, Any] = field(default_factory=dict, repr=False)
    mode: str = ""
    typed: str = ""
    page: int = 0
    scroll: int = 0
    notice: str = "Reading the canonical Build snapshot. No worker is started."


class BuildReviewTerminal:
    def __init__(self, client: BuildReviewClient):
        self.client, self.view = client, ReviewView()
        self.events: queue.Queue[tuple[str, dict[str, Any] | None]] = queue.Queue()
        self.busy, self.closed = "", False

    def start(self, operation: str, arguments: tuple[str, ...] = ()) -> None:
        if self.busy or self.closed:
            return
        self.busy = operation

        def run() -> None:
            try:
                result = self.client.status() if operation == "status" else self.client.request(operation, arguments)
            except Exception:
                result = None
            if not self.closed:
                self.events.put((operation, result))

        threading.Thread(target=run, daemon=True).start()

    def drain(self) -> None:
        while not self.events.empty():
            operation, value = self.events.get_nowait()
            if self.closed:
                continue
            self.busy = ""
            if operation == "progress":
                self.view.progress = value or {}
                self.view.notice = (
                    "Read-only progress snapshot; F5 discards views. Owner merge stays a separate decision."
                    if value
                    else "Progress UNCONFIRMED; existing merge review is unchanged. No automatic retry."
                )
            elif value is None:
                self.view = ReviewView(notice="UNCONFIRMED; view cleared. Refresh canonical state; no automatic retry.")
            elif operation == "status":
                self.view = ReviewView(snapshot=value, notice="Canonical snapshot; F5 refreshes. Tab changes view.")
            else:
                # Mutation receipts do not optimistically update the view. Read
                # the scoped canonical task again, including after cancellation.
                self.view = ReviewView(notice="Decision returned; reading canonical state.")
                self.start("status")

    def refresh(self) -> None:
        if not self.busy:
            self.view = ReviewView(notice="Refreshing; pending confirmation discarded.")
            self.start("status")

    def review(self, operation: str) -> None:
        v = self.view
        if self.busy or not v.snapshot:
            return
        approval = v.snapshot.get("approval", {})
        if operation == "approve" and (
            v.snapshot.get("task_state") != "WAITING_APPROVAL"
            or approval.get("state") != "PENDING"
            or approval.get("continuation_kind") != "MERGE"
        ):
            v.notice = "No pending exact merge approval in this snapshot. Refresh canonical state."
            return
        if operation == "cancel" and v.snapshot.get("task_state") in {"COMPLETED", "CANCELLED", "FAILED"}:
            v.notice = "Canonical task already ended; no cancellation sent."
            return
        v.frozen = copy.deepcopy(v.snapshot)
        v.mode, v.typed, v.page, v.scroll = operation, "", 2, 0
        v.notice = "Review the frozen preview, then type " + ("MERGE" if operation == "approve" else "CANCEL") + "."

    def confirm(self) -> None:
        v = self.view
        if self.busy or not v.mode or v.typed != ("MERGE" if v.mode == "approve" else "CANCEL"):
            return
        frozen, operation = v.frozen, v.mode
        arguments: tuple[str, ...]
        if operation == "approve":
            a = frozen["approval"]
            arguments = (a["approval_id"], a["effect_digest"], str(a["expected_version"]), str(uuid4()))
        else:
            arguments = (self.client.goal, str(frozen["row_version"]))
        self.view = ReviewView(notice="Decision unconfirmed until canonical receipt. F10 leaves it running.")
        self.start(operation, arguments)

    def close(self) -> None:
        self.closed = True
        self.view = ReviewView()
        self.client.close()

    def content(self) -> str:
        v = self.view
        data = v.frozen if v.mode else v.snapshot
        if v.page == 3:
            p = v.progress
            if not p:
                return "VERIFIED BUILD PROGRESS\nUNCONFIRMED; press p to inspect this goal's canonical plan."
            passed, total = p["required_checks_passed"], p["required_checks_total"]
            filled = min(20, 20 * passed // total) if total else 0
            repair = p["repair"]
            return (
                "VERIFIED BUILD PROGRESS\n"
                f"Final required checks [{'#' * filled}{'.' * (20 - filled)}] {passed}/{total}\n"
                f"Goal execution: {p['goal_status']}\nAttention: {p['attention_reason']}\n"
                f"Next: {p['next_action']}\n"
                f"Owner merge: {p['owner_merge']} | release acceptance: {p['release_acceptance']}\n"
                f"Plan versions: {repair['versions_used']} | remaining wall envelope: "
                f"{repair['wall_envelope_remaining_seconds']}s\n"
                f"Held claims: {repair['held_claims']} | UNKNOWN invocations: {repair['unknown_invocations']}\n"
                f"Repair model turns: {repair.get('planning_turns_used', '?')} | reserved: "
                f"{repair.get('planning_wall_charged_seconds', '?')}s | "
                f"unconfirmed: {repair.get('unconfirmed_planning_turns', '?')}\n"
                f"As-of event: {p['as_of_event_seq']} | original contract v{p['contract_version']}\n"
                "Check and milestone references (untrusted descriptions):\n"
                + json.dumps({k: p[k] for k in ("requirements", "non_goals", "plans")}, indent=2)
            )
        if v.page == 1:
            return "DIFF (untrusted text)\n" + str(data.get("diff", "No diff available."))
        if v.page == 2:
            return "EXACT OWNER REVIEW\n" + json.dumps(
                {
                    k: data.get(k)
                    for k in (
                        "goal_id",
                        "task_id",
                        "row_version",
                        "base_commit",
                        "candidate_commit",
                        "evidence_sha256",
                        "approval",
                    )
                },
                indent=2,
            )
        return "INDEPENDENT CHECKS\n" + json.dumps(data.get("checks", []), indent=2)

    def run(self, screen: Any) -> None:
        import curses

        screen.keypad(True)
        screen.timeout(100)
        self.start("status")
        leaving = False
        try:
            while True:
                self.drain()
                v = self.view
                screen.erase()
                rows, cols = screen.getmaxyx()

                def line(row: int, value: str, rows: int = rows, cols: int = cols) -> None:
                    if 0 <= row < rows:
                        try:
                            screen.addstr(row, 1, wrapped(value, max(1, cols - 3))[0])
                        except curses.error:
                            pass

                line(0, "Panestria | PUBLIC BUILD REVIEW | local owner")
                if rows < 18 or cols < 80:
                    line(2, "Resize to at least 80 columns x 18 rows. F10 quits.")
                else:
                    line(1, "Goal: " + self.client.goal)
                    line(2, "Canonical task: " + str(v.snapshot.get("task_state", "UNCONFIRMED")))
                    line(3, "Operation: " + (self.busy or "none") + " | Explicit refresh; snapshots can become stale.")
                    lines = wrapped(self.content(), cols - 3)
                    v.scroll = min(v.scroll, max(0, len(lines) - (rows - 10)))
                    for row, value in enumerate(lines[v.scroll : v.scroll + rows - 10], 5):
                        line(row, value)
                    line(rows - 4, ("Confirmation: " + v.typed) if v.mode else "No decision pending.")
                    line(rows - 3, v.notice)
                    line(rows - 2, "Tab Views | p Progress | PgUp/Dn | a Merge | c Cancel | F5 Refresh | F10 Quit")
                    line(rows - 1, "Existing owner CLI owns grants/checks/protected CAS. No model call or auto-submit.")
                screen.refresh()
                try:
                    key = screen.get_wch()
                except curses.error:
                    continue
                if key == curses.KEY_F10 or (key == "q" and not v.mode):
                    if self.busy in {"approve", "cancel"} and not leaving:
                        v.notice = "Decision may still complete. Press quit again to leave; refresh after reopening."
                        leaving = True
                    else:
                        return
                elif key == curses.KEY_F5:
                    self.refresh()
                elif key == curses.KEY_RESIZE:
                    continue
                elif key == "\t":
                    v.page, v.scroll = (v.page + 1) % 4, 0
                    if v.page == 3 and not v.mode and not v.progress:
                        self.start("progress", (self.client.goal,))
                elif key == curses.KEY_NPAGE:
                    v.scroll += max(1, rows - 10)
                elif key == curses.KEY_PPAGE:
                    v.scroll = max(0, v.scroll - max(1, rows - 10))
                elif v.mode:
                    if key in {"\n", "\r", curses.KEY_ENTER}:
                        self.confirm()
                    elif key == "\x1b":
                        v.mode, v.typed, v.frozen = "", "", {}
                        v.notice = "Confirmation discarded; no decision sent."
                    elif key in {curses.KEY_BACKSPACE, "\x7f", "\b"}:
                        v.typed = v.typed[:-1]
                    elif isinstance(key, str) and key.isascii() and key.isalpha() and len(v.typed) < 6:
                        v.typed += key
                elif key == "p":
                    if not self.busy:
                        v.page, v.scroll = 3, 0
                        self.start("progress", (self.client.goal,))
                elif key == "a":
                    self.review("approve")
                elif key == "c":
                    self.review("cancel")
        finally:
            self.close()
            screen.erase()
            screen.refresh()


def build_tui(config: Path, goal_id: str | None = None) -> None:
    try:
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            raise BuildUnconfirmed
        import curses

        terminal: Any
        if goal_id is None:
            from panestria.cli.build_browser import BuildGoalBrowser

            terminal = BuildGoalBrowser(config)
        else:
            terminal = BuildReviewTerminal(BuildReviewClient(config, goal_id))
        try:
            curses.wrapper(terminal.run)
        finally:
            terminal.close()
        return
    except KeyboardInterrupt:
        return
    except Exception:
        typer.echo(json.dumps({"status": "UNAVAILABLE", "reason": "build_terminal_unavailable_check_setup"}), err=True)
        raise typer.Exit(2) from None
