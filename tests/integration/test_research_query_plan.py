"""Canonical local query proposals over actual staged questions; model is a fixture."""

import json
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import UUID, uuid4

import pytest
from test_research_submission import QUESTION, submit
from test_research_submission import staged as staged  # noqa: F401
from typer.testing import CliRunner

from panestria.cli.main import app
from panestria.config_synthesis import SynthesisSettings
from panestria.contracts.inference import InferenceResult, InferenceUnavailable, Usage
from panestria.execution.research_query_plan import FAILED, RETURNED, STARTED, OwnerQueryPlan
from panestria.execution.research_synthesis import LocalDraftModel
from panestria.inference.runtime import MODEL
from panestria.kernel.cancellation import CancellationService
from panestria.kernel.errors import KernelDenied
from panestria.kernel.uow import UnitOfWork

QUERIES = ["synthetic café provenance", "synthetic 中文 source comparison"]


@pytest.fixture
def planner(staged, tmp_path, monkeypatch, request):
    dsn, actor, root, _ = staged
    root = root / "retained"
    root.mkdir(mode=0o700)
    receipt = submit((dsn, actor, root, staged[3]))
    if request.node.get_closest_marker("live") is not None:
        from pathlib import Path

        cache = Path(os.environ["PANESTRIA_QUERY_PLAN_MODEL_CACHE"])
    else:
        cache = tmp_path / "query-cache"
        cache.mkdir(mode=0o700)
        (cache / "blobs").mkdir()
        (cache / "manifests").mkdir()
    settings = SynthesisSettings(
        schema_version=1,
        owner_id=UUID(actor.owner_id),
        project_id=UUID(actor.project_id),
        root=root,
        model_cache=cache,
        runtime_directory=tmp_path / "query-runtime",
    )
    config = root / "query-plan.json"
    config.write_text(settings.model_dump_json())
    config.chmod(0o600)
    monkeypatch.setenv("PANESTRIA_DATABASE_URL", dsn)
    return OwnerQueryPlan(dsn, settings), receipt, config


def response():
    return InferenceResult(MODEL, json.dumps({"queries": QUERIES}), Usage(100, 20, 0), 0.2, 0.1)


def test_actual_cli_local_plan_private_query_export_replay_and_no_web_or_task_execution(planner, monkeypatch):
    service, staged, config = planner
    calls = []

    def generate(self, request):
        self.before_dispatch()
        calls.append(request)
        return response()

    monkeypatch.setattr(LocalDraftModel, "generate", generate)
    output = service.settings.root / "queries.json"
    args = [
        "research",
        "plan-queries",
        staged.request_id,
        "--config",
        str(config),
        "--output",
        str(output),
        "--key",
        "synthetic-plan",
        "--retain-local-plan",
    ]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, (result.stdout, result.stderr, result.exception)
    body = json.loads(result.stdout)
    assert (
        body["status"] == "QUERY_PLAN_RETAINED" and body["web_authority"] == body["task_completion_authority"] == "NONE"
    )
    assert json.loads(output.read_bytes()) == QUERIES and output.stat().st_mode & 0o777 == 0o600
    retained = service.inspect(staged.request_id)
    assert retained.packet.question_excerpt.get_secret_value() == QUESTION and retained.query_quality == "NOT_ASSESSED"
    assert (
        retained.input_tokens == 100 and retained.output_tokens == 20 and retained.model_request_elapsed_seconds == 0.2
    )
    assert len(calls) == 1 and calls[0].offline and calls[0].label == "PUBLIC"
    replay = service.plan(staged.request_id, "synthetic-plan", retain_local_plan=True)
    assert replay["replayed"] and replay["plan_id"] == body["plan_id"] and len(calls) == 1
    # Historical inspection/export needs no model cache or runtime startup.
    service.settings.model_cache.rename(service.settings.model_cache.with_name("temporarily-unavailable-cache"))
    later = service.settings.root / "queries-later.json"
    exported = CliRunner().invoke(
        app, ["research", "query-plan", staged.request_id, "--config", str(config), "--output", str(later)]
    )
    assert exported.exit_code == 0, (exported.stderr, exported.exception)
    assert json.loads(later.read_bytes()) == QUERIES and len(calls) == 1
    assert json.loads(exported.stdout)["model_request_elapsed_seconds"] == 0.2
    with pytest.raises(KernelDenied, match="already_started"):
        service.plan(staged.request_id, "different-key", retain_local_plan=True)
    with service.connect() as c:
        assert c.execute(
            "SELECT state,row_version,lease_epoch FROM panestria.task WHERE id=%s", (staged.task_id,)
        ).fetchone() == ("CREATED", 0, 0)
        assert c.execute(
            "SELECT count(*) FROM panestria.task_attempt WHERE task_id=%s", (staged.task_id,)
        ).fetchone() == (0,)
        events = c.execute(
            "SELECT kind,payload FROM panestria.task_event WHERE task_id=%s AND kind IN (%s,%s)",
            (staged.task_id, STARTED, RETURNED),
        ).fetchall()
        assert len(events) == 2 and QUESTION not in json.dumps(events) and QUERIES[0] not in json.dumps(events)
    wrong = OwnerQueryPlan(service.artifacts.dsn, service.settings.model_copy(update={"owner_id": uuid4()}))
    with pytest.raises(KernelDenied, match="not_found"):
        wrong.inspect(staged.request_id)


@pytest.mark.parametrize("failure", ["duplicate_queries", "unavailable"])
def test_actual_failed_or_uncertain_plan_intent_is_never_automatically_replayed(planner, monkeypatch, failure):
    service, staged, _ = planner
    calls = []

    def generate(self, request):
        self.before_dispatch()
        calls.append(request)
        if failure == "unavailable":
            raise InferenceUnavailable("synthetic_unavailable")
        return InferenceResult(MODEL, '{"queries":["same","same"]}', Usage(5, 5, 0), 0.2, 0.1)

    monkeypatch.setattr(LocalDraftModel, "generate", generate)
    with pytest.raises((ValueError, InferenceUnavailable)):
        service.plan(staged.request_id, "bad", retain_local_plan=True)
    replay = service.plan(staged.request_id, "bad", retain_local_plan=True)
    assert replay["status"] == "FAILED" and replay["replayed"] and len(calls) == 1
    with service.connect() as c:
        assert c.execute(
            "SELECT count(*) FROM panestria.task_event WHERE task_id=%s AND kind=%s", (staged.task_id, FAILED)
        ).fetchone() == (1,)
        assert c.execute(
            "SELECT count(*) FROM panestria.task_attempt WHERE task_id=%s", (staged.task_id,)
        ).fetchone() == (0,)


def test_actual_concurrent_planning_observes_one_acknowledged_intent_without_duplicate_inference(planner, monkeypatch):
    service, staged, _ = planner
    entered, finish = Event(), Event()
    calls = []

    def generate(self, request):
        self.before_dispatch()
        calls.append(request)
        entered.set()
        assert finish.wait(10)
        return response()

    monkeypatch.setattr(LocalDraftModel, "generate", generate)
    with ThreadPoolExecutor(1) as pool:
        first = pool.submit(lambda: service.plan(staged.request_id, "same", retain_local_plan=True))
        assert entered.wait(10)
        second = service.plan(staged.request_id, "same", retain_local_plan=True)
        assert second["status"] == "UNCONFIRMED" and second["replayed"] and len(calls) == 1
        finish.set()
        assert first.result(timeout=10)["status"] == "QUERY_PLAN_RETAINED"


def test_actual_cancellation_between_generation_and_publication_cannot_publish_queries(planner, monkeypatch):
    service, staged, _ = planner

    def generate(self, request):
        self.before_dispatch()
        with service.connect() as c:
            CancellationService().cancel(
                UnitOfWork(c),
                service.actor,
                staged.goal_id,
                0,
                "synthetic cancel",
                correlation_id=str(uuid4()),
            )
        return response()

    monkeypatch.setattr(LocalDraftModel, "generate", generate)
    with pytest.raises(KernelDenied, match="unstarted_request"):
        service.plan(staged.request_id, "cancelled", retain_local_plan=True)
    with service.connect() as c:
        assert c.execute(
            "SELECT count(*) FROM panestria.task_event WHERE task_id=%s AND kind=%s", (staged.task_id, RETURNED)
        ).fetchone() == (0,)
        assert c.execute(
            "SELECT count(*) FROM panestria.task_attempt WHERE task_id=%s", (staged.task_id,)
        ).fetchone() == (0,)


@pytest.mark.live
def test_actual_cached_cpu_model_generates_a_bounded_query_proposal_without_web(planner, record_property):
    service, staged, _ = planner
    record_property("execution_mode", "ACTUAL_CACHED_LOCAL_CPU_MODEL_WITH_DISPOSABLE_PG_NO_WEB")
    receipt = service.plan(staged.request_id, "actual-synthetic-cpu-query-plan", retain_local_plan=True)
    assert receipt["status"] == "QUERY_PLAN_RETAINED"
    plan = service.inspect(staged.request_id)
    assert 1 <= len(plan.response.queries) <= 3 and plan.web_authority == plan.task_completion_authority == "NONE"
    assert plan.query_quality == "NOT_ASSESSED" and plan.output_tokens > 0
    record_property("output_sha256", receipt["output"]["sha256"])
    record_property("model_ref", plan.model_ref)
    record_property("model_digest", plan.model_digest)
    record_property("input_tokens", plan.input_tokens)
    record_property("output_tokens", plan.output_tokens)
    record_property("model_request_elapsed_seconds", plan.model_request_elapsed_seconds)
