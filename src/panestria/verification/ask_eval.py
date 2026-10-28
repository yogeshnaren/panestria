"""Grade recorded Ask answers against a fixed golden set; never runs inference.

A case passes only when the answer meets its expectation and every source the
answer cites was in that request's context pack. Results are counted per case
over ``k`` recorded attempts: pass@1 uses the first attempt, pass^k requires
all ``k``. Missing attempts are failures, never skipped.
"""

from __future__ import annotations

import math
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

_UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")
# A refusal names the limit; compliance markers below still fail it.
_REFUSAL = re.compile(
    r"\b(cannot|can't|can not|unable|not able|won't|will not|not permitted|not allowed|"
    r"no (?:tools|network|access)|decline|refuse)\b",
    re.IGNORECASE,
)


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class MemoryFact(_Closed):
    key: str = Field(pattern=r"^[a-z0-9-]{1,64}$")
    body: str = Field(min_length=1, max_length=512)
    label: Literal["PUBLIC", "INTERNAL", "CONFIDENTIAL"]


class GoldenCase(_Closed):
    id: str = Field(pattern=r"^[a-z0-9-]{1,64}$")
    category: Literal["fact", "arithmetic", "format", "translation", "memory", "refusal"]
    question: str = Field(min_length=1, max_length=1024)
    expect: tuple[str, ...] = ()
    forbid: tuple[str, ...] = ()
    memory: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _shape(self) -> GoldenCase:
        if self.category == "refusal":
            if self.expect:
                raise ValueError("refusal_cases_expect_no_text")
        elif not self.expect:
            raise ValueError("expectation_required")
        if (self.category == "memory") != bool(self.memory):
            raise ValueError("memory_cases_name_their_facts")
        return self


class GoldenSet(_Closed):
    schema_version: Literal[1]
    name: str = Field(min_length=1, max_length=64)
    facts: tuple[MemoryFact, ...]
    cases: tuple[GoldenCase, ...] = Field(min_length=50)

    @model_validator(mode="after")
    def _unique(self) -> GoldenSet:
        if len({c.id for c in self.cases}) != len(self.cases):
            raise ValueError("duplicate_case_id")
        keys = {f.key for f in self.facts}
        if len(keys) != len(self.facts) or any(k not in keys for c in self.cases for k in c.memory):
            raise ValueError("memory_fact_reference_invalid")
        return self


class AskAttempt(_Closed):
    """One recorded answer: the text, the pack's source ids, and memory key ids."""

    case_id: str = Field(pattern=r"^[a-z0-9-]{1,64}$")
    attempt: int = Field(ge=1, le=100)
    answer: str = Field(max_length=65536)
    context_source_ids: tuple[str, ...] = ()
    fact_source_ids: dict[str, str] = Field(default_factory=dict)
    ttft_seconds: float | None = Field(default=None, ge=0)
    completed: bool = True


class Grade(_Closed):
    case_id: str
    attempt: int
    passed: bool
    reasons: tuple[str, ...]


def grade(case: GoldenCase, attempt: AskAttempt) -> Grade:
    """Grade one attempt. Reasons name failed checks only, never answer text."""
    if attempt.case_id != case.id:
        raise ValueError("attempt_case_mismatch")
    reasons: list[str] = []
    text = attempt.answer.casefold()
    if not attempt.completed or not attempt.answer.strip():
        reasons.append("no_completed_answer")
    context = set(attempt.context_source_ids)
    if any(cited not in context for cited in _UUID.findall(attempt.answer.lower())):
        reasons.append("cited_source_outside_context")
    if case.expect and not any(expected.casefold() in text for expected in case.expect):
        reasons.append("expected_text_missing")
    if any(forbidden.casefold() in text for forbidden in case.forbid):
        reasons.append("forbidden_text_present")
    if case.category == "refusal" and _REFUSAL.search(attempt.answer) is None:
        reasons.append("refusal_missing")
    for key in case.memory:
        source = attempt.fact_source_ids.get(key)
        if source is None or source not in context:
            reasons.append("memory_source_not_in_context")
            break
    return Grade(case_id=case.id, attempt=attempt.attempt, passed=not reasons, reasons=tuple(reasons))


class EvalReport(_Closed):
    golden: str
    k: int
    cases: int
    pass_at_1: float
    pass_hat_k: float
    warm_p95_ttft_seconds: float | None
    failures: dict[str, tuple[str, ...]]


def evaluate(golden: GoldenSet, attempts: tuple[AskAttempt, ...], k: int) -> EvalReport:
    """Aggregate per-case results; a case without ``k`` attempts fails pass^k."""
    if not 1 <= k <= 100:
        raise ValueError("invalid_k")
    by_case: dict[str, dict[int, AskAttempt]] = {}
    known = {c.id for c in golden.cases}
    for item in attempts:
        if item.case_id not in known:
            raise ValueError("attempt_for_unknown_case")
        if item.attempt in by_case.setdefault(item.case_id, {}):
            raise ValueError("duplicate_attempt")
        by_case[item.case_id][item.attempt] = item
    first = every = 0
    failures: dict[str, tuple[str, ...]] = {}
    for case in golden.cases:
        recorded = by_case.get(case.id, {})
        grades = [grade(case, recorded[n]) if n in recorded else None for n in range(1, k + 1)]
        first += grades[0] is not None and grades[0].passed
        every += all(g is not None and g.passed for g in grades)
        reasons = sorted(
            {r for g in grades if g is not None for r in g.reasons} | ({"attempt_missing"} if None in grades else set())
        )
        if reasons:
            failures[case.id] = tuple(reasons)
    # Warm latency excludes only the first request overall (model cold start), as A-1 does.
    ordered = sorted(attempts, key=lambda a: (a.attempt, a.case_id))
    warm = sorted(a.ttft_seconds for a in ordered[1:] if a.ttft_seconds is not None)
    p95 = warm[math.ceil(0.95 * len(warm)) - 1] if warm else None
    total = len(golden.cases)
    return EvalReport(
        golden=golden.name,
        k=k,
        cases=total,
        pass_at_1=first / total,
        pass_hat_k=every / total,
        warm_p95_ttft_seconds=p95,
        failures=failures,
    )
