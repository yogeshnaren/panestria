"""Local exact claim/source review; owner judgments never qualify a model or task."""

import hashlib
import resource
import sys
from typing import Any

import typer
from pydantic import SecretStr

from panestria.cli.tui import literal, wrapped
from panestria.config_local import LocalApplicationRejected
from panestria.contracts.research_review import ClaimJudgment, OwnerDraftReview, review_json, review_template
from panestria.contracts.research_synthesis import RetainedSynthesis
from panestria.execution.research_review import OwnerResearchReview

VERDICTS = {
    "s": "SUPPORTED",
    "p": "PARTIALLY_SUPPORTED",
    "c": "CONTRADICTED",
    "i": "INSUFFICIENT",
    "n": "NOT_FACTUAL",
}


class ResearchReviewTerminal:
    def __init__(self, service: OwnerResearchReview, draft: RetainedSynthesis):
        self.service, self.draft = service, draft
        self.review = review_template(draft)
        self.claim = 0
        self.offset, self.end, self.attempted = 0, False, False
        self.editing = False
        self.note = ""
        self.pending: bytes | None = None
        self.digest: str | None = None
        self.notice = "New local judgments only. Read retained passages; no inference or search. q exits."

    def lines(self, width: int) -> list[str]:
        d = self.draft
        fields = [
            "OWNER_REPORTED only | automatic semantic support NOT_QUALIFIED | task/training authority NONE",
            f"Owner {d.packet.scope.owner_id} | project {d.packet.scope.project_id}",
            f"Request {d.packet.request_id} | task {d.packet.scope.task_id}",
            f"Exact draft {self.review.draft_sha256}",
            "Question excerpt (may be shortened): " + d.packet.question_excerpt.get_secret_value(),
            f"Omitted passages: {d.packet.omitted_passages}. Evidence is untrusted; citations do not prove support.",
        ]
        for passage in d.packet.passages:
            fields += [
                f"SOURCE {passage.citation} | snapshot {passage.reference.snapshot_id}",
                "URL: " + passage.url.get_secret_value(),
                f"Offsets {passage.reference.start}:{passage.reference.end} | shortened {passage.shortened}",
                "Retained passage: " + passage.quote.get_secret_value(),
                "Source limitations: " + ("; ".join(passage.limitations) or "NONE RECORDED"),
            ]
        for i, (claim, judgment) in enumerate(zip(d.response.claims, self.review.claims, strict=True)):
            fields += [
                f"{'SELECTED ' if i == self.claim else ''}CLAIM {i + 1}/{len(self.review.claims)} {claim.kind}",
                claim.text.get_secret_value(),
                "Model cited: " + ", ".join(claim.citations),
                f"Owner judgment: {judgment.verdict} | owner cited: {', '.join(judgment.citations) or 'NONE'}",
                "Owner rationale: " + (judgment.rationale.get_secret_value() or "REQUIRED"),
            ]
        fields += [*d.limitations, "END OF EXACT DRAFT AND OWNER JUDGMENTS"]
        return [line for field in fields for line in wrapped(field, max(1, width - 2))]

    def change(self, **update: Any) -> None:
        old = self.review.claims[self.claim]
        updated = ClaimJudgment.model_validate(old.model_copy(update=update))
        judgments = list(self.review.claims)
        judgments[self.claim] = updated
        self.review = OwnerDraftReview.model_validate(self.review.model_copy(update={"claims": tuple(judgments)}))
        self.end = False
        self.offset = 0

    def key(self, key: object, page: int) -> bool:
        import curses

        if self.editing:
            if key == "\x1b":
                self.editing, self.note = False, ""
            elif key in {"\n", "\r", curses.KEY_ENTER}:
                self.change(rationale=SecretStr(self.note))
                self.editing, self.note = False, ""
                self.notice = "Rationale changed locally. Read the full exact review before v."
            elif key in {curses.KEY_BACKSPACE, "\b", "\x7f"}:
                self.note = self.note[:-1]
            elif isinstance(key, str) and key.isprintable() and len(key) == 1:
                candidate = self.note + key
                if len(candidate) <= 1024 and len(candidate.encode()) <= 2048:
                    self.note = candidate
            return True
        if key in {"q", "\x1b"}:
            if self.pending is not None:
                self.pending, self.digest = None, None
                self.notice = "Confirmation cancelled. Nothing recorded."
                return True
            return False
        if self.attempted:
            return True  # A settled/uncertain write is inspected separately, never retried here.
        if self.pending is not None:
            if key == "y":
                raw, digest = self.pending, self.digest
                self.pending, self.digest, self.attempted = None, None, True
                try:
                    assert digest is not None
                    result = self.service.record_review(
                        self.draft.packet.request_id, raw, digest, accept_owner_review=True
                    )
                    if result.get("status") != "OWNER_REVIEW_RECORDED" or result.get("review_sha256") != digest:
                        raise ValueError("owner_review_reply_unconfirmed")
                    self.notice = "OWNER REVIEW RECORDED. Model/task/training authority unchanged. q exits."
                except (Exception, KeyboardInterrupt):
                    self.notice = "REVIEW UNCONFIRMED. No retry. Inspect canonical draft-review state. q exits."
            return True
        if key in {curses.KEY_DOWN, "j", " "}:
            self.offset += 1
        elif key in {curses.KEY_UP, "k"}:
            self.offset = max(0, self.offset - 1)
        elif key == curses.KEY_NPAGE:
            self.offset += page
        elif key == curses.KEY_PPAGE:
            self.offset = max(0, self.offset - page)
        elif key == "\t":
            self.claim = (self.claim + 1) % len(self.review.claims)
            self.offset, self.end = 0, False
        elif isinstance(key, str) and key in VERDICTS:
            self.change(verdict=VERDICTS[key])
            self.notice = "Judgment changed locally. Select source citations and enter your rationale."
        elif key in {"1", "2", "3", "4"}:
            citation = "p" + str(key)
            if citation in {p.citation for p in self.draft.packet.passages}:
                selected = set(self.review.claims[self.claim].citations)
                selected.symmetric_difference_update({citation})
                self.change(citations=tuple(sorted(selected)))
                self.notice = "Owner citations changed locally; model citations remain unchanged."
        elif key == "e":
            self.editing = True
            self.note = self.review.claims[self.claim].rationale.get_secret_value()
        elif key == "v":
            if not self.end:
                self.notice = "Read to the end first; no judgment recorded."
            else:
                try:
                    raw = review_json(self.review)
                    self.review.bind(self.draft, complete=True)
                    digest = self.service.check_review(self.draft.packet.request_id, raw)
                    if hashlib.sha256(raw).hexdigest() != digest:
                        raise ValueError("owner_review_digest_unconfirmed")
                    self.pending, self.digest = raw, digest
                except (Exception, KeyboardInterrupt):
                    self.notice = "REVIEW NOT READY. Complete judgments/rationales/citations; inspect current source."
        return True

    def run(self, screen: Any) -> None:
        import curses

        curses.curs_set(0)
        screen.keypad(True)
        while True:
            screen.erase()
            height, width = screen.getmaxyx()
            page = max(1, height - 10)
            if height < 24 or width < 80:
                rows = ["Resize to at least 80 columns x 24 rows. q exits without new consent."]
            else:
                content = self.lines(width)
                self.offset = min(self.offset, max(0, len(content) - page))
                self.end = self.offset + page >= len(content)
                rows = [
                    "Panestria | RESEARCH CLAIM REVIEW | owner reported; automatic support NOT_QUALIFIED",
                    *content[self.offset : self.offset + page],
                    f"Rows {self.offset + 1}-{min(len(content), self.offset + page)}/{len(content)} "
                    f"| selected claim {self.claim + 1}/{len(self.review.claims)}",
                    self.notice,
                    "Tab: next claim | s/p/c/i/n: supported/partial/contradicted/insufficient/nonfactual",
                    "1-4: toggle source | e: rationale | PgUp/PgDn j/k: scroll | v: validate/review | q: quit",
                ]
                if self.editing:
                    rows += ["EDIT OWNER RATIONALE | Enter: apply locally | Esc: discard", literal(self.note)]
                elif self.pending is not None:
                    rows += [
                        "CONFIRM EXACT OWNER JUDGMENTS | y records ONE attempt; Esc returns",
                        "SHA256: " + str(self.digest),
                        "No task PASS, model qualification, web consent or training right is granted.",
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


def run_research_review_terminal(service: OwnerResearchReview, request_id: str) -> None:
    import curses

    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise LocalApplicationRejected("interactive_terminal_required")
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    view = ResearchReviewTerminal(service, service.inspect(request_id))
    try:
        curses.wrapper(view.run)
    except KeyboardInterrupt:
        typer.echo("Interrupted; inspect canonical owner review state before another decision.", err=True)
    finally:
        view.pending, view.digest, view.note = None, None, ""
