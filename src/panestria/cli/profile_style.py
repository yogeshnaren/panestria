"""Explicit local keyboard style editor; only the existing API can save a revision."""

import resource
import sys
from pathlib import Path
from typing import Any

import typer

from panestria.cli.profile_client import ProfileClient, StyleSource
from panestria.cli.tui import literal
from panestria.cli.tui_client import TerminalUnavailable
from panestria.config_local import LocalApplicationRejected
from panestria.contracts.style import StyleProfile

_CHOICES = {
    "language": ("en", "es", "fr", "de", "hi", "zh"),
    "audience": ("general", "beginner", "technical"),
    "detail": ("concise", "balanced", "detailed"),
    "formatting": ("auto", "paragraphs", "bullets"),
    "tables": ("when-useful", "avoid"),
}


class StyleTerminal:
    def __init__(self, client: ProfileClient, source: StyleSource):
        self.client, self.source = client, source
        self.values = source.style.model_dump()
        self.approved = source.approved
        self.selected = 0
        self.review = False
        self.attempted = False
        self.notice = "Edit choices, then s to review. q exits without saving."

    def key(self, key: object) -> bool:
        import curses

        if key in ("q", "\x1b"):
            if self.review:
                self.review = False
                return True
            return False
        if self.attempted:
            return True  # One explicit write attempt; never retry an uncertain POST.
        if self.review:
            if key == "y":
                self.attempted = True
                self.review = False
                try:
                    receipt = self.client.save(self.source, StyleProfile.model_validate(self.values), self.approved)
                    self.notice = (
                        f"SAVED row version {receipt.row_version}. No inference or Ask selection started. q exits."
                    )
                except (TerminalUnavailable, ValueError):
                    self.notice = "SAVE UNCONFIRMED. No retry. Reopen exact profile/version to inspect. q exits."
                # Remove all wider profile plaintext as soon as the write ends.
                self.source = StyleSource(self.source.profile_id, self.source.key_id, self.source.row_version)
            return True
        if key in (curses.KEY_UP, "k"):
            self.selected = (self.selected - 1) % 6
        elif key in (curses.KEY_DOWN, "j", "\t"):
            self.selected = (self.selected + 1) % 6
        elif key in (curses.KEY_LEFT, curses.KEY_RIGHT, " ", "\n", "h", "l"):
            if self.selected == 5:
                self.approved = not self.approved
            else:
                name = tuple(_CHOICES)[self.selected]
                current = self.values[name]
                choices = tuple(dict.fromkeys((*_CHOICES[name], current)))
                step = -1 if key in (curses.KEY_LEFT, "h") else 1
                self.values[name] = choices[(choices.index(current) + step) % len(choices)]
        elif key == "s":
            self.review = True
        return True

    def run(self, screen: Any) -> None:
        import curses

        curses.curs_set(0)
        screen.keypad(True)
        while True:
            screen.erase()
            height, width = screen.getmaxyx()
            rows = [
                "Panestria encrypted style | RESTRICTED | local owner review",
                f"Profile {self.source.profile_id}",
                f"Row version {self.source.row_version if self.source.row_version is not None else 'NEW'}",
                "No model, key provisioning, service enablement or cloud export.",
                "",
                *[
                    f"{'>' if self.selected == n else ' '} {name}: {self.values[name]}"
                    for n, name in enumerate(_CHOICES)
                ],
                f"{'>' if self.selected == 5 else ' '} Local context approval: {'YES' if self.approved else 'NO'}",
                "",
                "Arrows/j/k: select | left/right/space: change | s: review | q: quit",
                self.notice,
            ]
            if self.review:
                rows += [
                    "",
                    "REVIEW: save this complete encrypted revision? Other fields/expiry remain unchanged.",
                    "The local-context choice changes only communication approval.",
                    "Press y to save once, Esc/q to return. No authority or quality is granted.",
                ]
            if height < 22 or width < 80:
                rows = ["Resize to at least 80 columns and 22 rows. q exits."]
            for n, text in enumerate(rows[: height - 1]):
                try:
                    screen.addnstr(n, 0, literal(text), width - 1)
                except curses.error:
                    pass
            screen.refresh()
            key = screen.get_wch()
            if height < 22 or width < 80:
                if key in ("q", "\x1b"):
                    return
                continue
            if not self.key(key):
                return


def run_style_terminal(
    config: Path, profile_id: str, key_id: str | None, expected_version: int | None, owner_review: bool
) -> None:
    import curses
    from uuid import UUID

    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise LocalApplicationRejected("interactive_terminal_required")
    if not owner_review or (key_id is None) == (expected_version is None):
        raise LocalApplicationRejected("explicit_style_create_or_exact_review_required")
    identity = str(UUID(profile_id))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    client = ProfileClient(config)
    if key_id is not None:
        client.scope()
        source = StyleSource(identity, str(UUID(key_id)), None)
    else:
        assert expected_version is not None
        source = client.source(identity, expected_version)
    try:
        curses.wrapper(StyleTerminal(client, source).run)
    except KeyboardInterrupt:
        # An interrupted write might have committed. Never submit it again here.
        typer.echo("Interrupted; inspect the exact profile/version before another save.", err=True)
