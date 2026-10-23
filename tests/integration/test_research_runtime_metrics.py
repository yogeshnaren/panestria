"""Actual PG/CAS/reader/CLI metrics; explicit model/transport and dispatch metadata fixtures."""

import fcntl
import json
import stat
from uuid import UUID, uuid4

import test_research_synthesis as synthesis_support
from test_research_requests import research as research  # noqa: F401
from test_research_source_provenance import observations as observations  # noqa: F401
from test_research_synthesis import model_fixture as model_fixture  # noqa: F401
from test_research_synthesis import synthesis_context as synthesis_context  # noqa: F401
from typer.testing import CliRunner

from panestria.cli.main import app
from panestria.contracts.research_review import review_json
from panestria.execution.research_review import OwnerResearchReview
from panestria.execution.research_synthesis import RETURNED, STARTED
from panestria.telemetry.performance import latest_snapshot


def client(synthesis, request, directory, monkeypatch):
    monkeypatch.setenv("PANESTRIA_DATABASE_URL", synthesis.dsn)
    config = synthesis.settings.root / "metrics-config.json"
    # Capture needs no installed model/cache. No model/runtime initialization is allowed.
    config.write_text(
        synthesis.settings.model_copy(
            update={
                "model_cache": directory.parent / "not-installed-models",
            }
        ).model_dump_json()
    )
    config.chmod(0o600)

    def capture(expected=0):
        result = CliRunner().invoke(
            app,
            [
                "metrics",
                "capture-research",
                "--config",
                str(config),
                "--request-id",
                request.request_id,
                "--directory",
                str(directory),
            ],
        )
        assert result.exit_code == expected, result.output
        assert synthesis.dsn not in result.output and "PRIVATE_OWNER_NOTE" not in result.output
        return json.loads(result.output)

    return config, capture


def test_actual_capture_deduplicates_original_observation_and_separates_owner_judgments(
    synthesis_context,
    model_fixture,
    monkeypatch,
    tmp_path,
):
    synthesis, request = synthesis_context
    monkeypatch.setattr(
        synthesis_support,
        "RESPONSE",
        {
            "claims": [
                {"text": "PRIVATE_DRAFT_ONE", "kind": "FACT", "citations": ["p1"]},
                {"text": "PRIVATE_DRAFT_TWO", "kind": "INTERPRETATION", "citations": ["p1"]},
            ]
        },
    )
    synthesis.synthesize(request.request_id, "measured-draft", retain_local_draft=True)
    directory = tmp_path / "metrics"
    _, capture = client(synthesis, request, directory, monkeypatch)
    with synthesis.connect() as c:
        before = c.execute("SELECT count(*) FROM panestria.task_event").fetchone()
    first = capture()
    snapshot = latest_snapshot(directory)
    values = {m.metric: m for m in snapshot.observations}
    assert values["usage.research_input_tokens"].value == 123
    assert values["usage.research_output_tokens"].value == 42
    assert values["review.owner_supported_fraction"].value is None
    assert values["review.owner_supported_fraction"].reason == "UNMEASURED"
    assert values["research.fetch_retained_receipt_fraction"].value is None
    assert values["quality.correct_fraction"].value is values["cost.actual"].value is None
    assert all(m.source_commit is None and m.samples <= 1 for m in snapshot.observations)
    source = json.loads((directory / "sources" / first["source_sha256"]).read_bytes())
    with synthesis.connect() as c:
        assert c.execute("SELECT count(*) FROM panestria.task_event").fetchone() == before
        times = c.execute(
            "SELECT occurred_at FROM panestria.task_event WHERE task_id=%s AND kind IN (%s,%s) ORDER BY seq",
            (request.scope.task_id, STARTED, RETURNED),
        ).fetchall()
    exact = (times[1][0] - times[0][0]).total_seconds()
    assert source["intent_to_return_seconds"] == exact
    assert values["latency.research_synthesis_lifecycle"].value == exact
    second = capture()
    assert first["source_sha256"] == second["source_sha256"] and first["snapshot"] != second["snapshot"]
    assert len(list((directory / "sources").iterdir())) == 1

    reviewer = OwnerResearchReview(synthesis.dsn, synthesis.settings)
    body = json.loads(review_json(reviewer.prepare_review(request.request_id)))
    for verdict, row in zip(("SUPPORTED", "CONTRADICTED"), body["claims"], strict=True):
        row.update(verdict=verdict, citations=["p1"], rationale="PRIVATE_OWNER_NOTE")

    def record():
        raw = json.dumps(body).encode()
        digest = reviewer.check_review(request.request_id, raw)
        reviewer.record_review(request.request_id, raw, digest, accept_owner_review=True)

    record()
    third = capture()
    values = {m.metric: m for m in latest_snapshot(directory).observations}
    assert values["review.owner_supported_fraction"].value == values["review.owner_contradicted_fraction"].value == 0.5
    assert values["review.owner_supported_fraction"].samples == 2
    assert values["quality.correct_fraction"].value is None
    assert third["source_sha256"] != first["source_sha256"]
    for row in body["claims"]:
        row.update(verdict="NOT_FACTUAL", citations=[], rationale="PRIVATE_OWNER_NOTE nonfactual")
    record()
    capture()
    values = {m.metric: m for m in latest_snapshot(directory).observations}
    assert values["review.owner_supported_fraction"].value is None
    assert values["review.owner_supported_fraction"].reason == "UNDEFINED_DENOMINATOR"
    for path in directory.rglob("*"):
        if path.is_file():
            raw = path.read_bytes()
            for private in (
                "PRIVATE_OWNER_NOTE",
                "PRIVATE_DRAFT_ONE",
                "PRIVATE_DRAFT_TWO",
                synthesis_support.QUESTION,
                "example.org",
                synthesis.dsn,
            ):
                assert private.encode() not in raw
            assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert len(model_fixture) == 1 and not (tmp_path / "not-installed-models").exists()
    with synthesis.connect() as c:
        assert c.execute("SELECT state FROM panestria.task WHERE id=%s", (request.scope.task_id,)).fetchone() == (
            "VERIFYING",
        )


def test_unknown_dispatches_scope_storage_pressure_and_cancellation_never_add_authority(
    synthesis_context,
    model_fixture,
    monkeypatch,
    tmp_path,
):
    synthesis, request = synthesis_context
    synthesis.synthesize(request.request_id, "bounded-metrics", retain_local_draft=True)
    directory = tmp_path / "metrics"
    config, capture = client(synthesis, request, directory, monkeypatch)
    # Explicit metadata fixtures exercise receipt accounting, not network or runtime qualification.
    with synthesis.connect() as c:
        task = request.scope.task_id
        c.execute(
            "INSERT INTO panestria.fetch_plan(task_id,request_id,request_sha256,contract_sha256,policy_sha256,"
            "configuration_sha256,plan_sha256) VALUES(%s,%s,repeat('ab',32),repeat('ab',32),repeat('ab',32),"
            "repeat('ab',32),repeat('ab',32))",
            (task, request.request_id),
        )
        attempt = str(uuid4())
        c.execute(
            "INSERT INTO panestria.task_attempt(id,task_id,attempt_number,status,lease_epoch,lease_expires_at,adapter) "
            "VALUES(%s,%s,1,'LOST',1,clock_timestamp()-interval '1 second','synthetic-metrics')",
            (attempt, task),
        )
        ids = [str(uuid4()), str(uuid4())]
        for ordinal, identity in enumerate(ids, 1):
            c.execute(
                "INSERT INTO panestria.fetch_dispatch(id,task_id,request_id,attempt_id,lease_epoch,ordinal,"
                "url_sha256,reserved_body_bytes) VALUES(%s,%s,%s,%s,1,%s,%s,100)",
                (identity, task, request.request_id, attempt, ordinal, f"{ordinal:064x}"),
            )
        c.execute(
            "INSERT INTO panestria.fetch_outcome(dispatch_id,task_id,request_id,status,diagnostic) "
            "VALUES(%s,%s,%s,'FETCH_ERROR','fetch_timeout')",
            (ids[0], task, request.request_id),
        )
        before = c.execute("SELECT count(*) FROM panestria.task_event").fetchone()
    result = capture()
    source = json.loads((directory / "sources" / result["source_sha256"]).read_bytes())
    values = {m.metric: m for m in latest_snapshot(directory).observations}
    assert source["fetch_receipts"] == {"FETCH_ERROR": 1, "UNKNOWN": 1}
    assert values["research.fetch_retained_receipt_fraction"].value == 0.0
    assert values["research.fetch_retained_receipt_fraction"].samples == 2
    assert values["research.reserved_body_bytes"].value == 200
    assert source["reserved_body_bytes"] == 200 and values["cost.actual"].value is None
    with (directory / "capture.lock").open("wb") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert capture(expected=1)["reason"] == "metrics_capture_busy"
    with (directory / "full-fixture.bin").open("wb") as stream:
        stream.truncate(16 * 1024 * 1024)
    assert capture(expected=1)["reason"] == "research_metrics_history_budget_reached"
    assert len(list(directory.glob("*.json"))) == len(list((directory / "sources").iterdir())) == 1
    original = config.read_bytes()
    settings = synthesis.settings.model_copy(update={"owner_id": UUID(str(uuid4()))})
    config.write_text(settings.model_dump_json())
    assert capture(expected=1)["status"] == "UNAVAILABLE"
    config.write_bytes(original)
    with synthesis.connect() as c:
        assert c.execute("SELECT count(*) FROM panestria.task_event").fetchone() == before
        c.execute("UPDATE panestria.task SET state='CANCELLING',row_version=row_version+1 WHERE id=%s", (task,))
    assert capture(expected=1)["status"] == "UNAVAILABLE"
    assert len(model_fixture) == 1 and len(list(directory.glob("*.json"))) == 1
