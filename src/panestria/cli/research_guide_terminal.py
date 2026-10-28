"""Keyboard stage review; all side effects stay in existing canonical services."""

import resource
import sys
from typing import Any

from panestria.cli.tui import literal, wrapped
from panestria.config_local import LocalApplicationRejected
from panestria.execution.research_guide import OwnerResearchGuide
from panestria.kernel.errors import KernelDenied


class ResearchGuideTerminal:
    def __init__(self, service: OwnerResearchGuide, request_id: str):
        self.service, self.request_id = service, request_id
        self.step = service.prepare(request_id)
        self.offset, self.end, self.pending, self.stopped = 0, False, False, False
        self.notice = "Read the full stage review. v reviews exact action, y separately confirms. q exits."
        self.open_review = False

    def key(self, key: object, page: int) -> bool:
        import curses

        if key in {"q", "\x1b"}:
            if self.pending:
                self.pending = False
                self.notice = "Confirmation cancelled. No new action."
                return True
            return False
        if self.stopped:
            return True
        if self.pending:
            if key == "y":
                self.pending = False
                # One attempt only. Any unknown outcome ends this view; reopening
                # reads the original canonical intent, never guesses retry safety.
                self.stopped = True
                try:
                    action = self.service.execute(self.request_id, self.step)
                    if action == "REVIEW":
                        self.open_review = True
                        return False
                    self.step = self.service.prepare(self.request_id)
                    self.offset, self.end, self.stopped = 0, False, False
                    self.notice = "Stage returned. Read the NEXT stage before a separate decision. q exits."
                except (Exception, KeyboardInterrupt) as error:
                    reason = error.code if isinstance(error, KernelDenied) else "stage_outcome_unconfirmed"
                    self.notice = f"STOPPED: {reason}. No retry. Inspect canonical state before another decision."
            return True
        if key in {curses.KEY_DOWN, "j", " "}:
            self.offset += 1
        elif key in {curses.KEY_UP, "k"}:
            self.offset = max(0, self.offset - 1)
        elif key == curses.KEY_NPAGE:
            self.offset += page
        elif key == curses.KEY_PPAGE:
            self.offset = max(0, self.offset - page)
        elif key == "v":
            if self.step.action == "STOP":
                self.notice = "No safe action in this state. Inspect setup/canonical state; q exits."
            elif not self.end:
                self.notice = "Read to the end first. No action attempted."
            else:
                self.pending = True
        return True

    def run(self, screen: Any) -> None:
        import curses

        curses.curs_set(0)
        screen.keypad(True)
        while True:
            screen.erase()
            height, width = screen.getmaxyx()
            page = max(1, height - 9)
            if height < 24 or width < 80:
                rows = ["Resize to at least 80 columns x 24 rows. q exits without new consent."]
            else:
                content = [line for field in self.step.lines for line in wrapped(field, width - 2)]
                self.offset = min(self.offset, max(0, len(content) - page))
                self.end = self.offset + page >= len(content)
                rows = [
                    "Panestria | GUIDED RESEARCH | same canonical request | manual decisions",
                    *content[self.offset : self.offset + page],
                    f"Rows {self.offset + 1}-{min(len(content), self.offset + page)}/{len(content)}",
                    self.notice,
                    "PgUp/PgDn j/k: scroll | v: review exact action | q/Esc: leave/cancel",
                ]
                if self.pending:
                    rows += [
                        f"CONFIRM {self.step.action} | y makes ONE attempt; Esc cancels",
                        self.step.digest,
                        "This does not approve any later stage, policy change or task completion.",
                    ]
            for n, value in enumerate(rows[: height - 1]):
                try:
                    screen.addnstr(n, 0, literal(value), width - 1)
                except curses.error:
                    pass
            screen.refresh()
            key = screen.get_wch()
            if height < 24 or width < 80:
                if key in {"q", "\x1b"}:
                    return
            elif not self.key(key, page):
                return


def run_research_guide_terminal(service: OwnerResearchGuide, request_id: str) -> None:
    import curses

    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise LocalApplicationRejected("interactive_terminal_required")
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    view = ResearchGuideTerminal(service, request_id)
    curses.wrapper(view.run)
    if view.open_review:
        from panestria.cli.research_review_terminal import run_research_review_terminal

        run_research_review_terminal(service.review, request_id)
