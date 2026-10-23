"""One exact owner declaration decision after full local review; no execution."""

import resource
import sys
from pathlib import Path
from typing import Any, Literal

import typer

from panestria.cli.connection_client import ConnectionClient
from panestria.cli.tui import literal, wrapped
from panestria.cli.tui_client import TerminalUnavailable
from panestria.config_local import LocalApplicationRejected
from panestria.contracts.connections import ConnectionReviewView


def review_lines(source: ConnectionReviewView, width: int) -> list[str]:
    m = source.manifest
    fields = [
        "Declaration review only. Execution unavailable; no account or folder is connected.",
        f"Owner {m.owner_id} | project {m.project_id}",
        f"Proposal {source.proposal_id} | grant {source.grant_id}",
        f"Operation {source.operation} | expected version {source.expected_version} | state {source.state}",
        f"Connector {m.connector_ref} version {m.connector_version} | account reference {m.account_ref}",
        "Declared actions: "
        + ", ".join(f"{a}={'YES' if a in m.actions else 'NO'}" for a in ("read", "write", "send", "delete", "spend")),
        "Data classes: " + ", ".join(m.data_classes),
        "Origins: " + (", ".join(m.origins) or "NONE"),
        "Opaque root references (not live enrollment): " + (", ".join(m.root_refs) or "NONE"),
        f"Declared limits: {m.budget.max_calls} calls, {m.budget.max_bytes} bytes, "
        f"{m.budget.max_wall_seconds}s, USD {m.budget.max_cash_microusd / 1_000_000:.6f} cash cap",
        "Declaration expiry: " + m.expires_at.isoformat(),
        "Review expiry: " + source.review_expires_at.isoformat(),
        "Policy: " + source.policy_ref,
        "Configuration hash: " + m.configuration_sha256,
        "Claimed conformance hash (UNVERIFIED): " + (m.conformance_sha256 or "NONE"),
        "Effect digest: " + source.effect_digest,
        "Approval records a declaration only. It imports no chats, credentials or application permissions.",
        "A REVOKE approval records disconnection intent/state; this component starts/stops no external process.",
        "END OF EXACT DECLARATION",
    ]
    return [part for value in fields for part in wrapped(value, max(1, width - 2))]


class ConnectionTerminal:
    def __init__(self, client: ConnectionClient, source: ConnectionReviewView, current_policy_ref: str):
        self.client, self.source, self.current_policy_ref = client, source, current_policy_ref
        self.offset, self.end, self.attempted = 0, False, False
        self.choice: Literal["approve", "deny"] | None = None
        self.notice = (
            "Policy changed. Prepare a fresh proposal; this review cannot be decided."
            if source.policy_ref != current_policy_ref
            else "Scroll to the end before a/d. q exits without a decision."
        )

    def key(self, key: object, page_size: int) -> bool:
        import curses

        if key in {"q", "\x1b"}:
            if self.choice is not None:
                self.choice = None
                return True
            return False
        if self.attempted:
            return True  # An uncertain decision is inspected on a new explicit run, never retried.
        if self.choice is not None:
            if key == "y":
                self.attempted = True
                choice, self.choice = self.choice, None
                try:
                    result = self.client.decide(self.source, choice)
                    self.notice = f"RECORDED {result.decision}. Execution remains unavailable. q exits."
                except (TerminalUnavailable, ValueError, TypeError):
                    self.notice = "DECISION UNCONFIRMED. No retry. Reopen this proposal/grant to inspect. q exits."
            return True
        if key in {curses.KEY_DOWN, "j", " "}:
            self.offset += 1
        elif key in {curses.KEY_UP, "k"}:
            self.offset = max(0, self.offset - 1)
        elif key == curses.KEY_NPAGE:
            self.offset += page_size
        elif key == curses.KEY_PPAGE:
            self.offset = max(0, self.offset - page_size)
        elif key in {"a", "d"}:
            if self.source.policy_ref != self.current_policy_ref:
                self.notice = "Policy changed. Prepare a fresh exact proposal; no decision sent."
            elif self.source.state != "PENDING":
                self.notice = "This review is not pending. Inspect the current grant; no decision sent."
            elif not self.end:
                self.notice = "Read to the end first; no decision sent."
            else:
                self.choice = "approve" if key == "a" else "deny"
        return True

    def run(self, screen: Any) -> None:
        import curses

        curses.curs_set(0)
        screen.keypad(True)
        while True:
            screen.erase()
            height, width = screen.getmaxyx()
            page_size = max(1, height - 8)
            if height < 22 or width < 80:
                rows = ["Resize to at least 80 columns x 22 rows. q exits."]
            else:
                content = review_lines(self.source, width)
                self.offset = min(self.offset, max(0, len(content) - page_size))
                self.end = self.offset + page_size >= len(content)
                rows = [
                    "Panestria | CONNECTION DECLARATION | conformance UNVERIFIED",
                    *content[self.offset : self.offset + page_size],
                    f"Rows {self.offset + 1}-{min(len(content), self.offset + page_size)}/{len(content)}",
                    self.notice,
                    "PgUp/PgDn j/k: scroll | a: approve declaration | d: deny | q: quit",
                ]
                if self.choice is not None:
                    rows += [
                        f"CONFIRM {self.choice.upper()} exact declaration",
                        f"Digest: {self.source.effect_digest}",
                        "y sends ONE decision; Esc returns. No connector is enabled.",
                    ]
            for n, value in enumerate(rows[: height - 1]):
                try:
                    screen.addnstr(n, 0, literal(value), width - 1)
                except curses.error:
                    pass
            screen.refresh()
            key = screen.get_wch()
            if height < 22 or width < 80:
                if key in {"q", "\x1b"}:
                    return
            elif not self.key(key, page_size):
                return


def run_connection_terminal(config: Path, proposal_id: str) -> None:
    import curses

    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise LocalApplicationRejected("interactive_terminal_required")
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    client = ConnectionClient(config)
    policy = client.scope()
    terminal = ConnectionTerminal(client, client.preview(proposal_id), policy.policy_ref)
    try:
        curses.wrapper(terminal.run)
    except KeyboardInterrupt:
        typer.echo("Interrupted; inspect this exact proposal/grant before another decision.", err=True)
