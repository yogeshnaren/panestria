"""Metadata filters and exporter failure do not expose content or alter task truth."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
from starlette.testclient import TestClient

from panestria.api.main import create_app
from panestria.api.tracing import TraceRequests
from panestria.config import Settings
from panestria.telemetry.tracing import MetadataProcessor, Telemetry, trusted_context


def test_metadata_redaction_and_scoped_export(record_property: pytest.RecordProperty) -> None:
    record_property("gate_case_id", "AOS-014-TC03")
    record_property("source_clauses", "AOS-014-F01,AOS-014-AC02,AOS-014-AC03")
    public = []
    processor = MetadataProcessor(public_sink=public.append, max_spans=4)
    telemetry = Telemetry(processor)
    for label in ["PUBLIC", "PRIVATE", "RESTRICTED", "UNKNOWN"]:
        with telemetry.tracer.start_as_current_span("kernel.transaction", record_exception=False) as span:
            span.set_attribute("panestria.privacy_label", label)
            span.set_attribute("panestria.task_id", str(uuid4()))
            span.set_attribute("panestria.owner_id", "SECRET_SENTINEL")
            span.set_attribute("http.request.header.authorization", "SECRET_SENTINEL")
            span.set_attribute("panestria.input_tokens", 12)
            span.set_attribute("prompt", "SECRET_SENTINEL")
            span.add_event("SECRET_SENTINEL", {"data": "SECRET_SENTINEL"})
    assert len(public) == 1 and public[0]["attributes"]["panestria.privacy_label"] == "PUBLIC"
    assert "SECRET_SENTINEL" not in json.dumps(processor.snapshot())
    assert len(processor.snapshot()) == 4
    telemetry.shutdown()


def test_exporter_failure_is_contained(record_property: pytest.RecordProperty) -> None:
    record_property("gate_case_id", "AOS-014-TC04")
    record_property("source_clauses", "AOS-014-F04,AOS-014-AC03")

    def unavailable(record: dict[str, object]) -> None:
        raise RuntimeError("SECRET_SENTINEL")

    processor = MetadataProcessor(public_sink=unavailable)
    telemetry = Telemetry(processor)
    with telemetry.tracer.start_as_current_span("kernel.transaction") as span:
        span.set_attribute("panestria.privacy_label", "PUBLIC")
    assert processor.failures == 1 and len(processor.snapshot()) == 1
    assert "SECRET_SENTINEL" not in json.dumps(processor.snapshot())
    telemetry.shutdown()


def test_http_trace_poisoning_is_not_parent() -> None:
    telemetry = Telemetry()
    app = create_app(
        Settings(database_url="postgresql://synthetic:placeholder-not-a-secret@127.0.0.1:55439/synthetic"),
        lambda _deadline: None,
    )
    app.add_middleware(TraceRequests, telemetry=telemetry)
    client = TestClient(app, base_url="http://127.0.0.1:8765")
    forged = "ab" * 16
    response = client.get("/healthz", headers={"traceparent": f"00-{forged}-{'cd' * 8}-01"})
    assert response.status_code == 200 and response.headers["x-panestria-trace-id"] != forged
    assert telemetry.processor.snapshot()[0]["parent_span_id"] is None
    telemetry.shutdown()
    with pytest.raises(ValueError, match="trace_capsule_invalid"):
        trusted_context("0" * 32, "0" * 16)


def test_real_dbos_persisted_trace_transport(r1_task: dict[str, str], tmp_path: Path) -> None:
    import os
    import subprocess

    import psycopg

    attempt, workflow = str(uuid4()), str(uuid4())
    with psycopg.connect(r1_task["dsn"]) as c:
        c.execute(
            "INSERT INTO panestria.task_attempt(id,task_id,attempt_number,lease_epoch,status,adapter)"
            " VALUES (%s,%s,1,0,'PENDING','mock')",
            (attempt, r1_task["task"]),
        )
    report = tmp_path / "trace-chain.json"
    script = Path(__file__).resolve().parents[1] / "fixtures/r1/trace_dbos.py"
    safe_env = {k: v for k, v in os.environ.items() if not k.startswith(("OTEL_", "DBOS_"))}
    result = subprocess.run(
        ["uv", "run", "--frozen", "python", str(script)],
        capture_output=True,
        text=True,
        timeout=60,
        env={
            **safe_env,
            "PANESTRIA_SYNTHETIC_TRACE_IDS": json.dumps({**r1_task, "attempt": attempt, "workflow": workflow}),
            "PANESTRIA_SYNTHETIC_TRACE_REPORT": str(report),
        },
    )
    assert result.returncode == 0, result.stderr
    observed = json.loads(report.read_text())
    assert len(observed["trace_id"]) == 32 and len(observed["spans"]) >= 6
