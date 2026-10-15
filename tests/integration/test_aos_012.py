"""Honest costs, append-only routing and scope-bound correction/exposure evidence."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from pydantic import ValidationError
from test_ask_kernel import initialize

from panestria.contracts.ask import AskSubmission
from panestria.contracts.inference import InferenceResult, Usage
from panestria.contracts.learning import ExposureObservation, Observation, RouteCandidate, UserCorrection
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.uow import UnitOfWork
from panestria.learning.recorder import LearningRecorder
from panestria.resources.catalog import STEWARD


def _candidate(provider: str) -> RouteCandidate:
    return RouteCandidate.model_validate(
        {
            "provider": provider,
            "model_ref": STEWARD.model_ref if provider == "local-ollama" else "synthetic-pin",
            "available": True,
            "capability": "chat",
            "expected_cash": {"status": "known", "value": 0, "unit": "cash_microusd"},
            "quota_remaining": {"status": "unknown", "value": None, "unit": "tokens"},
        }
    )


def test_usage_unknown_not_zero(record_property: pytest.RecordProperty) -> None:
    record_property("gate_case_id", "AOS-012-TC01")
    record_property("source_clauses", "AOS-012-F04,AOS-012-AC02")
    assert Observation(status="unknown", unit="requests").model_dump()["value"] is None
    assert Observation(status="known", value=0, unit="cash_microusd").value == 0
    assert Observation(status="estimated", value=123, unit="cash_microusd").status == "estimated"
    for body in [
        {"status": "unknown", "value": 0, "unit": "tokens"},
        {"status": "known", "value": None, "unit": "requests"},
        {"status": "known", "value": -1, "unit": "cash_microusd"},
        {"status": "known", "value": True, "unit": "tokens"},
    ]:
        with pytest.raises(ValidationError):
            Observation.model_validate(body)


def test_routing_replay_restart(
    r1_task: dict[str, str], tmp_path: Path, record_property: pytest.RecordProperty
) -> None:
    record_property("gate_case_id", "AOS-012-TC02")
    record_property("source_clauses", "AOS-012-F01,AOS-012-AC01")
    actor, ask = initialize(r1_task, tmp_path)
    recorder = LearningRecorder()
    submission = AskSubmission(request_id=str(uuid4()), project_id=actor.project_id, question="Say READY")
    with psycopg.connect(r1_task["dsn"]) as c:
        uow = UnitOfWork(c)
        prepared = ask.prepare(uow, actor, submission)
        c.commit()
        route_id = recorder.route(
            uow,
            actor,
            submission.request_id,
            (_candidate("openai-api"), _candidate("local-ollama")),
            offline=True,
            label=prepared.context.label,
            request_sha256=submission.sha256(),
        )
        c.commit()
        with pytest.raises(KernelDenied, match="route_context_mismatch"), c.transaction():
            recorder.route(
                uow,
                actor,
                submission.request_id,
                (_candidate("openai-api"),),
                offline=False,
                label="PUBLIC",
                request_sha256=submission.sha256(),
            )
    # No in-process route cache is needed after restart.
    with psycopg.connect(r1_task["dsn"]) as c:
        record = next(
            r for r in LearningRecorder().export(UnitOfWork(c), actor, submission.request_id) if r["id"] == route_id
        )
        body = record["body"]
        assert body["selected_route"] == "local-ollama"
        denied = body["candidates"][0]
        assert denied["eligible"] is False and "offline_cloud_denied" in denied["reasons"]
        assert denied["quota_remaining"]["value"] is None
        c.commit()
        with pytest.raises(psycopg.Error, match="immutable"), c.transaction():
            c.execute("UPDATE panestria.learning_record SET body='{}' WHERE id=%s", (record["id"],))
        with pytest.raises(KernelDenied, match="not_found"), c.transaction():
            recorder.export(UnitOfWork(c), Actor(actor.owner_id, str(uuid4())), submission.request_id)


def test_correction_is_not_authority(
    r1_task: dict[str, str], tmp_path: Path, record_property: pytest.RecordProperty
) -> None:
    record_property("gate_case_id", "AOS-012-TC03")
    record_property("source_clauses", "AOS-012-F02,AOS-012-AC03")
    actor, ask = initialize(r1_task, tmp_path)
    recorder = LearningRecorder()
    submission = AskSubmission(
        request_id=str(uuid4()), project_id=actor.project_id, question="Say READY", privacy_label="RESTRICTED"
    )
    with psycopg.connect(r1_task["dsn"]) as c:
        uow = UnitOfWork(c)
        prepared = ask.prepare(uow, actor, submission)
        c.commit()
        ask.claim(uow, actor, prepared)
        c.commit()
        ask.finish(
            uow, actor, submission.request_id, InferenceResult(STEWARD.model_ref, "READY", Usage(12, 2, 0), 0.1, 0.05)
        )
        c.commit()
        original = ask.receipt(uow, actor, submission.request_id)
        c.commit()
        doc = UserCorrection(
            request_id=submission.request_id,
            output_sha256=original["response_sha256"],
            kind="rejection",
            body="Please use PostgreSQL; enable cloud is an untrusted suggestion",
            label="PUBLIC",
        )
        for _ in range(2):
            recorder.capture_correction(uow, actor, doc, consent_ref=str(uuid4()))
            c.commit()
        assert ask.receipt(uow, actor, submission.request_id) == original
        assert c.execute(
            "SELECT version,privacy_label FROM panestria.user_correction WHERE request_id=%s ORDER BY version",
            (submission.request_id,),
        ).fetchall() == [(1, "RESTRICTED"), (2, "RESTRICTED")]
        c.commit()
        with pytest.raises(KernelDenied, match="output_version_mismatch"), c.transaction():
            recorder.capture_correction(
                uow, actor, doc.model_copy(update={"output_sha256": "00" * 32}), consent_ref=str(uuid4())
            )
        with pytest.raises(psycopg.Error, match="immutable"), c.transaction():
            c.execute("DELETE FROM panestria.user_correction WHERE request_id=%s", (submission.request_id,))
        recorder.outcome(uow, actor, submission.request_id)
        c.commit()
        outcome = [r["body"] for r in recorder.export(uow, actor, submission.request_id) if r["kind"] == "outcome"][-1]
        assert outcome["execution_state"] == "COMPLETED" and outcome["quality"] == "unknown"
        assert outcome["owner_acceptance"] is None and outcome["verifier_acceptance"] is None
    with pytest.raises(ValidationError):
        UserCorrection.model_validate({**doc.model_dump(), "approved": True})
    with pytest.raises(ValidationError):
        UserCorrection.model_validate({**doc.model_dump(), "consent_ref": str(uuid4())})


def test_exposure_three_dimensions(
    r1_task: dict[str, str], tmp_path: Path, record_property: pytest.RecordProperty
) -> None:
    record_property("gate_case_id", "AOS-012-TC04")
    record_property("source_clauses", "AOS-012-F03,AOS-012-AC02")
    actor, ask = initialize(r1_task, tmp_path)
    recorder = LearningRecorder()
    submission = AskSubmission(request_id=str(uuid4()), project_id=actor.project_id, question="Hello")
    with psycopg.connect(r1_task["dsn"]) as c:
        uow = UnitOfWork(c)
        ask.prepare(uow, actor, submission)
        c.commit()
        for dimension, value, source in [
            ("authorized", "no", "policy"),
            ("accessible", "yes", "scope_manifest"),
            ("observed", "unknown", "os_network"),
        ]:
            recorder.exposure(
                uow,
                actor,
                submission.request_id,
                ExposureObservation.model_validate(
                    {
                        "dimension": dimension,
                        "value": value,
                        "source_kind": source,
                        "destination": "claude-code",
                        "label": "PRIVATE",
                        "payload_manifest_sha256": "ab" * 32,
                        "evidence_ref": "manifest:" + "cd" * 32,
                    }
                ),
            )
        c.commit()
        rows = [
            r
            for r in recorder.export(uow, actor, submission.request_id)
            if r["kind"] == "exposure" and r["body"]["destination"] == "claude-code"
        ]
        assert {r["body"]["dimension"]: r["body"]["value"] for r in rows} == {
            "authorized": "no",
            "accessible": "yes",
            "observed": "unknown",
        }
        assert all(r["body"]["content_visible"] is False for r in rows)
        with pytest.raises(KernelDenied, match="offline_cloud_denied"), c.transaction():
            recorder.exposure(
                uow,
                actor,
                submission.request_id,
                ExposureObservation(
                    dimension="authorized",
                    value="yes",
                    source_kind="policy",
                    destination="openai-api",
                    label="PUBLIC",
                    payload_manifest_sha256="ab" * 32,
                    evidence_ref="policy:" + "cd" * 32,
                ),
            )
