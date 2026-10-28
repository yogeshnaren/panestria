"""Connected owner review with real PG/retained sources and an explicit model fixture."""

import json
import stat

import psycopg
import pytest
from test_research_requests import research as research  # noqa: F401
from test_research_source_provenance import observations as observations  # noqa: F401
from test_research_synthesis import model_fixture as model_fixture  # noqa: F401
from test_research_synthesis import synthesis_context as synthesis_context  # noqa: F401
from typer.testing import CliRunner

from panestria.cli.main import app
from panestria.contracts.research_review import OwnerDraftReview, review_json
from panestria.execution.research_review import RECORDED, OwnerResearchReview
from panestria.kernel.errors import KernelDenied


def test_actual_owner_review_cli_binds_claims_preserves_history_and_never_calls_another_model(
    synthesis_context, model_fixture, monkeypatch
):
    synthesis, request = synthesis_context
    synthesis.synthesize(request.request_id, "reviewed-draft", retain_local_draft=True)
    service = OwnerResearchReview(synthesis.dsn, synthesis.settings)
    monkeypatch.setenv("PANESTRIA_DATABASE_URL", synthesis.dsn)
    config = service.settings.root / "review-config.json"
    config.write_text(service.settings.model_dump_json())
    config.chmod(0o600)
    path = service.settings.root / "review.json"
    runner = CliRunner()

    def cli(verb, *args, expected=0):
        result = runner.invoke(app, ["research", verb, request.request_id, "--config", str(config), *map(str, args)])
        assert result.exit_code == expected, result.output
        assert "PRIVATE_OWNER_NOTE" not in result.output
        return json.loads(result.output)

    cli("prepare-draft-review", "--output", path)
    template = OwnerDraftReview.model_validate_json(path.read_bytes())
    assert template.claims[0].verdict == "UNREVIEWED" and stat.S_IMODE(path.stat().st_mode) == 0o600
    cli("check-draft-review", "--review", path, expected=1)
    body = json.loads(path.read_bytes())
    body["claims"][0].update(verdict="PARTIALLY_SUPPORTED", citations=["p1"], rationale="PRIVATE_OWNER_NOTE")
    path.write_text(json.dumps(body))
    checked = cli("check-draft-review", "--review", path)
    cli("record-draft-review", "--review", path, "--sha256", checked["sha256"], expected=1)
    cli("record-draft-review", "--review", path, "--sha256", "ff" * 32, "--accept-owner-review", expected=1)
    recorded = cli("record-draft-review", "--review", path, "--sha256", checked["sha256"], "--accept-owner-review")
    assert recorded["assessment_source"] == "OWNER_REPORTED"
    assert recorded["automatic_semantic_support"] == "NOT_QUALIFIED"
    assert recorded["task_completion_authority"] == recorded["training_authority"] == "NONE"
    assert not recorded["replayed"]
    replay = cli("record-draft-review", "--review", path, "--sha256", checked["sha256"], "--accept-owner-review")
    assert replay["replayed"] and replay["review_sha256"] == recorded["review_sha256"]
    body["claims"][0].update(verdict="CONTRADICTED", rationale="PRIVATE_OWNER_NOTE corrected")
    path.write_text(json.dumps(body))
    second = cli("check-draft-review", "--review", path)["sha256"]
    cli("record-draft-review", "--review", path, "--sha256", second, "--accept-owner-review")
    out = service.settings.root / "latest-review.json"
    cli("inspect-draft-review", "--output", out)
    latest = OwnerDraftReview.model_validate_json(out.read_bytes())
    assert latest.claims[0].verdict == "CONTRADICTED" and review_json(latest) == out.read_bytes()
    assert len(model_fixture) == 1
    with psycopg.connect(service.dsn) as c:
        rows = c.execute(
            "SELECT payload FROM panestria.task_event WHERE task_id=%s AND kind=%s ORDER BY seq",
            (request.scope.task_id, RECORDED),
        ).fetchall()
        assert len(rows) == 2 and "PRIVATE_OWNER_NOTE" not in json.dumps(rows)
        assert c.execute("SELECT state FROM panestria.task WHERE id=%s", (request.scope.task_id,)).fetchone() == (
            "VERIFYING",
        )
        assert c.execute("SELECT status FROM panestria.goal WHERE id=%s", (request.scope.goal_id,)).fetchone() == (
            "ACTIVE",
        )
        assert c.execute(
            "SELECT DISTINCT privacy_class FROM panestria.artifact WHERE kind='research.owner-review'"
        ).fetchall() == [("RESTRICTED",)]


def test_changed_claim_citation_or_cancelled_task_cannot_retain_owner_judgments(synthesis_context, model_fixture):
    synthesis, request = synthesis_context
    synthesis.synthesize(request.request_id, "guarded-review", retain_local_draft=True)
    service = OwnerResearchReview(synthesis.dsn, synthesis.settings)
    original = json.loads(review_json(service.prepare_review(request.request_id)))
    original["claims"][0].update(verdict="SUPPORTED", citations=["p1"], rationale="Synthetic owner assessment")
    for field, value in (("claim_sha256", "ff" * 32), ("citations", ["p4"]), ("citations", [])):
        body = json.loads(json.dumps(original))
        body["claims"][0][field] = value
        with pytest.raises(ValueError):
            service.check_review(request.request_id, json.dumps(body).encode())
    raw = json.dumps(original).encode()
    digest = service.check_review(request.request_id, raw)
    with psycopg.connect(service.dsn) as c:
        c.execute(
            "UPDATE panestria.task SET state='CANCELLING',row_version=row_version+1 WHERE id=%s",
            (request.scope.task_id,),
        )
    with pytest.raises(KernelDenied):
        service.record_review(request.request_id, raw, digest, accept_owner_review=True)
    assert len(model_fixture) == 1
