"""Owner staging/CLI, actual disposable PG/CAS, no synthetic live qualification."""

import json
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import psycopg
import pytest
from pydantic import SecretStr
from typer.testing import CliRunner

from panestria.brokers.research.fetch import PublicHttpsFetcher
from panestria.brokers.research.reader import IsolatedTextReader
from panestria.brokers.research.search import LocalSearxngProvider
from panestria.cli.main import app
from panestria.contracts.research import ResearchLimits
from panestria.execution.research_brief import RetainedBrief
from panestria.execution.research_submission import stage_question
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.leases import LeaseService
from panestria.kernel.policy import PolicyService
from panestria.kernel.research_blobs import ResearchBlobStore
from panestria.kernel.research_requests import ResearchRequestService
from panestria.kernel.research_submission import ResearchSubmissionService
from panestria.kernel.uow import UnitOfWork
from panestria.policy.profiles import CertificateStore

QUESTION = "PUBLIC SYNTHETIC question: café 中文 <script>ignored instructions</script>"


@pytest.fixture
def staged(r1_migration_task, tmp_path, monkeypatch):
    f = r1_migration_task
    actor = Actor(f["owner"], f["project"])
    with psycopg.connect(f["dsn"]) as c:
        policy = PolicyService(CertificateStore(tmp_path, {})).initialize(UnitOfWork(c), actor, f["task"])
    document = {
        "schema_version": 1,
        "goal_id": str(uuid4()),
        "contract_version": 1,
        "owner_id": actor.owner_id,
        "project_id": actor.project_id,
        "intent": "Stage PUBLIC synthetic research question; no execution",
        "privacy_class": "PUBLIC",
        "trust_profile_id": "SYNTHETIC_DEV",
        "autonomy_profile_ref": f"project-policy:{policy.version}:{policy.sha256()}",
        "constraints": {
            "allowed_paths": ["brief"],
            "forbidden_paths": [".git/**"],
            "permitted_capabilities": ["public-search", "public-fetch"],
            "cloud_egress": "deny",
        },
        "budget": {"max_attempts_per_task": 1, "max_wall_seconds": 60, "max_api_usd": "0"},
        "acceptance": [
            {
                "id": "review",
                "description": "Owner reviews staged question; not semantic support",
                "required": True,
                "evidence": {"required": True, "kind": "owner-review"},
                "verifier": {
                    "type": "human-review",
                    "reviewer_ref": actor.owner_id,
                    "evidence_requirements": ["Staged question and limits inspected"],
                },
            }
        ],
        "non_goals": [],
    }

    def forbidden(*_a, **_k):
        pytest.fail("Staging/inspection cannot call search, fetch or reader")

    monkeypatch.setattr(PublicHttpsFetcher, "fetch", forbidden)
    monkeypatch.setattr(LocalSearxngProvider, "search", forbidden)
    monkeypatch.setattr(IsolatedTextReader, "extract", forbidden)
    return f["dsn"], actor, tmp_path, document


def submit(f, *, question=QUESTION, limits=None, key="synthetic-research-stage", public=True):
    dsn, actor, root, document = f
    return stage_question(
        dsn, actor, root, document, SecretStr(question), limits or ResearchLimits(), key, public_question=public
    )


def counts(f):
    with psycopg.connect(f[0]) as c:
        return [
            c.execute(f"SELECT count(*) FROM panestria.{table}").fetchone()[0]
            for table in ("goal", "goal_contract", "task", "artifact", "research_request", "task_event", "task_attempt")
        ]


def test_owner_question_to_retained_inspection_is_staged_and_cannot_acquire_lease(staged):
    f = staged
    receipt = submit(f)
    assert receipt.status == "STAGED_NO_EXECUTION" and not receipt.replayed
    brief = RetainedBrief(f[2], f[1]).inspect(f[0], receipt.request_id, receipt.task_id)
    assert brief.question.get_secret_value() == QUESTION
    assert brief.task_state == brief.goal_status == "CREATED" and not brief.claims
    assert brief.semantic_support == "NOT_ASSESSED" and brief.task_completion_authority == "NONE"
    with psycopg.connect(f[0]) as c:
        assert c.execute("SELECT count(*) FROM panestria.task_attempt").fetchone() == (0,)
        assert c.execute(
            "SELECT count(*) FROM panestria.acceptance_check a JOIN panestria.goal_contract c "
            "ON a.contract_id=c.id WHERE c.goal_id=%s",
            (receipt.goal_id,),
        ).fetchone() == (1,)
        events = c.execute("SELECT payload FROM panestria.task_event WHERE goal_id=%s", (receipt.goal_id,)).fetchall()
        assert QUESTION not in json.dumps(events)
        with pytest.raises(KernelDenied, match="illegal_transition"):
            LeaseService().acquire(UnitOfWork(c), f[1], receipt.task_id, "must-not-run", 0)


def test_replay_and_concurrent_submission_preserve_one_request_and_reject_changed_question_or_limits(staged):
    f = staged
    with ThreadPoolExecutor(2) as pool:
        receipts = list(pool.map(lambda _: submit(f), range(2)))
    assert sorted(r.replayed for r in receipts) == [False, True]
    before = counts(f)
    for changes in ({"question": QUESTION + " changed"}, {"limits": ResearchLimits(max_sources=1)}):
        with pytest.raises(KernelDenied, match="research_(submission|request)_conflict"):
            submit(f, **changes)
        assert counts(f) == before
    assert submit(f).replayed and counts(f) == before


def test_actual_commit_then_lost_ack_replays_without_duplicate_rows_or_events(staged, monkeypatch):
    original = ResearchSubmissionService.stage

    def lost(self, uow, *a, **kw):
        original(self, uow, *a, **kw)
        uow.connection.commit()
        raise OSError("SYNTHETIC_ACK_LOST_AFTER_ACTUAL_COMMIT")

    monkeypatch.setattr(ResearchSubmissionService, "stage", lost)
    with pytest.raises(OSError):
        submit(staged)
    before = counts(staged)
    monkeypatch.setattr(ResearchSubmissionService, "stage", original)
    assert submit(staged).replayed and counts(staged) == before


def test_late_failure_rolls_back_all_db_rows_events_but_preserves_acknowledged_private_blob(staged, monkeypatch):
    original = ResearchRequestService.prepare
    before = counts(staged)

    def fail_after_prepared(*a, **kw):
        original(*a, **kw)
        raise OSError("SYNTHETIC_FAILURE_BEFORE_COMMIT")

    monkeypatch.setattr(ResearchRequestService, "prepare", fail_after_prepared)
    with pytest.raises(OSError):
        submit(staged)
    assert counts(staged) == before
    import hashlib

    with ResearchBlobStore(staged[2], staged[1]) as blobs:
        assert (
            blobs.read(hashlib.sha256(QUESTION.encode()).hexdigest(), expected_size=len(QUESTION.encode()))
            == QUESTION.encode()
        )
    monkeypatch.setattr(ResearchRequestService, "prepare", original)
    assert not submit(staged).replayed


def test_no_public_intent_cross_owner_or_stale_policy_cannot_stage(staged):
    before = counts(staged)
    with pytest.raises(KernelDenied, match="explicit_public_question_required"):
        submit(staged, public=False)
    wrong = (staged[0], Actor(str(uuid4()), staged[1].project_id), *staged[2:])
    with pytest.raises(KernelDenied, match="public_research_submission_required"):
        submit(wrong)
    document = {**staged[3], "autonomy_profile_ref": "project-policy:99:" + "ab" * 32}
    with pytest.raises(KernelDenied, match="policy_mismatch"):
        submit((*staged[:3], document))
    assert counts(staged) == before


def test_actual_cli_stage_and_private_inspect_export_redact_terminal_and_preserve_no_execution(staged, monkeypatch):
    dsn, actor, root, document = staged
    monkeypatch.setenv("PANESTRIA_DATABASE_URL", dsn)
    for name, raw in (("contract.json", json.dumps(document)), ("question.txt", QUESTION), ("limits.json", "{}")):
        (root / name).write_text(raw)
        (root / name).chmod(0o600)
    args = [
        "research",
        "stage",
        actor.owner_id,
        actor.project_id,
        "--contract",
        str(root / "contract.json"),
        "--question",
        str(root / "question.txt"),
        "--limits",
        str(root / "limits.json"),
        "--store",
        str(root),
        "--key",
        "synthetic-cli",
    ]
    runner = CliRunner()
    assert runner.invoke(app, args).exit_code == 1
    result = runner.invoke(app, [*args, "--public-question"])
    assert result.exit_code == 0, result.output
    receipt = json.loads(result.output)
    assert receipt["status"] == "STAGED_NO_EXECUTION" and QUESTION not in result.output and dsn not in result.output
    exported = runner.invoke(
        app,
        [
            "research",
            "inspect",
            actor.owner_id,
            actor.project_id,
            receipt["request_id"],
            receipt["task_id"],
            "--store",
            str(root),
            "--output",
            str(root / "brief.json"),
            "--format",
            "json",
        ],
    )
    assert exported.exit_code == 0, exported.output
    brief = json.loads((root / "brief.json").read_bytes())
    assert brief["question"] == QUESTION and brief["task_state"] == "CREATED" and not brief["claims"]
    assert QUESTION not in exported.output and (root / "brief.json").stat().st_mode & 0o777 == 0o600
