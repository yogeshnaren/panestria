"""AI-P2c: Ask answers are graded, citations checked, and pass^k counted honestly."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from panestria.cli.main import app
from panestria.verification.ask_eval import AskAttempt, GoldenCase, GoldenSet, evaluate, grade

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "tests/fixtures/ask/golden-v1.json"


def golden() -> GoldenSet:
    return GoldenSet.model_validate_json(GOLDEN.read_bytes())


def test_ai_p2c_golden_set_is_large_balanced_and_well_formed():
    cases = golden().cases
    assert len(cases) >= 50
    categories = {case.category for case in cases}
    assert categories == {"fact", "arithmetic", "format", "translation", "memory", "refusal"}
    assert sum(case.category == "refusal" for case in cases) >= 5
    assert sum(case.category == "memory" for case in cases) >= 5
    # Recallable facts must be indexable: restricted text is never in full-text search.
    assert {fact.label for fact in golden().facts} <= {"PUBLIC", "INTERNAL", "CONFIDENTIAL"}


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"id": "x", "category": "fact", "question": "q"}, "expectation_required"),
        ({"id": "x", "category": "refusal", "question": "q", "expect": ("no",)}, "refusal_cases_expect_no_text"),
        ({"id": "x", "category": "memory", "question": "q", "expect": ("a",)}, "memory_cases_name_their_facts"),
    ],
)
def test_ai_p2c_case_shapes_are_enforced(change, reason):
    with pytest.raises(ValidationError, match=reason):
        GoldenCase.model_validate(change)


def case(**changes):
    return GoldenCase.model_validate({"id": "c", "category": "fact", "question": "q", "expect": ("Paris",), **changes})


def attempt(answer, n=1, **changes):
    return AskAttempt.model_validate({"case_id": "c", "attempt": n, "answer": answer, **changes})


def test_ai_p2c_expected_forbidden_and_empty_answers():
    assert grade(case(), attempt("The capital is paris.")).passed
    assert grade(case(), attempt("Lyon")).reasons == ("expected_text_missing",)
    assert grade(case(forbid=("lyon",)), attempt("Paris, not Lyon")).reasons == ("forbidden_text_present",)
    assert "no_completed_answer" in grade(case(), attempt("  ")).reasons
    assert "no_completed_answer" in grade(case(), attempt("Paris", completed=False)).reasons


def test_ai_p2c_citations_must_come_from_the_context_pack():
    inside, outside = str(uuid4()), str(uuid4())
    assert grade(case(), attempt(f"Paris [{inside}]", context_source_ids=(inside,))).passed
    failed = grade(case(), attempt(f"Paris [{outside}]", context_source_ids=(inside,)))
    assert failed.reasons == ("cited_source_outside_context",)


def test_ai_p2c_refusals_and_memory_sources():
    refusal = GoldenCase(id="c", category="refusal", question="q", forbid=("enabled cloud",))
    assert grade(refusal, attempt("I cannot enable cloud; I have no network.")).passed
    assert grade(refusal, attempt("Done.")).reasons == ("refusal_missing",)
    assert "forbidden_text_present" in grade(refusal, attempt("I can't, but I enabled cloud anyway.")).reasons
    memory = case(category="memory", expect=("PostgreSQL",), memory=("db",))
    source = str(uuid4())
    assert grade(memory, attempt("PostgreSQL", context_source_ids=(source,), fact_source_ids={"db": source})).passed
    assert grade(memory, attempt("PostgreSQL", fact_source_ids={"db": source})).reasons == (
        "memory_source_not_in_context",
    )


def test_ai_p2c_pass_at_1_pass_hat_k_and_missing_attempts():
    base = golden()
    first, second = base.cases[0], base.cases[1]
    good = {first.id: first.expect[0], second.id: second.expect[0]}
    attempts = [
        AskAttempt(case_id=first.id, attempt=n, answer=good[first.id], ttft_seconds=0.1 * n) for n in (1, 2, 3)
    ] + [
        AskAttempt(case_id=second.id, attempt=1, answer=good[second.id], ttft_seconds=0.5),
        AskAttempt(case_id=second.id, attempt=2, answer="wrong", ttft_seconds=0.6),
    ]
    report = evaluate(base, tuple(attempts), k=3)
    assert report.cases == len(base.cases)
    assert report.pass_at_1 == pytest.approx(2 / len(base.cases))
    assert report.pass_hat_k == pytest.approx(1 / len(base.cases))
    assert set(report.failures[second.id]) == {"attempt_missing", "expected_text_missing"}
    assert report.failures[base.cases[2].id] == ("attempt_missing",)
    assert report.warm_p95_ttft_seconds == pytest.approx(0.6)
    with pytest.raises(ValueError, match="duplicate_attempt"):
        evaluate(base, (attempts[0], attempts[0]), k=1)
    with pytest.raises(ValueError, match="attempt_for_unknown_case"):
        evaluate(base, (AskAttempt(case_id="unknown", attempt=1, answer="x"),), k=1)


def test_ai_p2c_cli_grades_recorded_results(tmp_path):
    base = golden()
    lines = [
        AskAttempt(
            case_id=item.id, attempt=1, answer=item.expect[0] if item.expect else "I cannot do that."
        ).model_dump_json()
        for item in base.cases
        if item.category != "memory"
    ]
    results = tmp_path / "results.jsonl"
    results.write_text("\n".join(lines) + "\n")
    shown = CliRunner().invoke(
        app, ["metrics", "ask-eval", "--golden", str(GOLDEN), "--results", str(results), "--k", "1"]
    )
    assert shown.exit_code == 0, shown.output
    report = json.loads(shown.stdout)
    memory = sum(item.category == "memory" for item in base.cases)
    assert report["pass_at_1"] == pytest.approx((len(base.cases) - memory) / len(base.cases))
    assert all(base_id.startswith("memory-") for base_id in report["failures"])
    results.write_text("not json\n")
    refused = CliRunner().invoke(app, ["metrics", "ask-eval", "--golden", str(GOLDEN), "--results", str(results)])
    assert refused.exit_code == 1 and "ask_eval_input_invalid" in refused.output
