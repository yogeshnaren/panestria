"""Real owner CLI/PG/Docker/Git; default transport and certificates are explicit fixtures."""

import hashlib
import json
import os
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest
from test_admitted_native_build import NativeTransportFixture
from test_registered_check_authority import git
from typer.testing import CliRunner

from panestria.brokers.harness.claude_build import ClaudeScopedBashAdapter
from panestria.cli.main import app
from panestria.config_build import load_build_settings
from panestria.config_local import read_private
from panestria.execution.native_build import runtime_versions
from panestria.execution.owner_build import OwnerBuild
from panestria.kernel.build import BuildEvidenceStore


@pytest.fixture
def owner_cli(tmp_path, r1_database, monkeypatch, request):
    root = tmp_path / "build"
    root.mkdir(mode=0o700)
    reviewed = root / "reviewed"
    reviewed.mkdir(mode=0o700)
    check = reviewed / "required.py"
    check.write_text(
        "from pathlib import Path\nassert Path('/workspace/calculator.py').read_text() == 'value = 43\\n'\n"
        "assert Path('/workspace/notes/build.txt').read_text() == 'bounded Bash build\\n'\n"
    )
    check.chmod(0o600)
    actual = request.node.get_closest_marker("live") is not None
    if actual:
        directory = Path(os.environ["PANESTRIA_NATIVE_QUALIFICATION_DIRECTORY"])
        result = json.loads(read_private(directory / "latest.json", 4096))
        assert result["status"] == "PASS" and result["scope"] == "PUBLIC_BASH_RUNTIME_ONLY"
        store = BuildEvidenceStore(directory / "certificates")
        digest = result["certificate_sha256"]
        certificate = json.loads(store.read_blob(digest))
        assert certificate["runtime_versions"] == runtime_versions()
        assert "TEST_FIXTURE_NOT_LIVE" not in json.dumps(certificate)
        auth = Path.home() / ".panestria-native-claude"
    else:
        store = BuildEvidenceStore(tmp_path / "certificate-fixture")
        observation = store.write_report(b'{"scope":"TEST_FIXTURE_NOT_LIVE"}')
        digest = store.write_report(
            json.dumps(
                {
                    "schema_version": 1,
                    "profile": "PERSONAL_SANDBOX",
                    "verdict": "PASS",
                    "runtime_versions": runtime_versions(),
                    "candidate_commit": "ab" * 20,
                    "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                    "allowed_actions": ["read", "edit", "external-send", "merge"],
                    "cases": [
                        {
                            "case_id": case,
                            "verdict": "PASS",
                            "execution_mode": "OS_BOUNDARY",
                            "report_sha256": observation,
                        }
                        for case in ("AOS-008-TC03", "AOS-010-TC03")
                    ],
                    "scope": "TEST_FIXTURE_NOT_LIVE",
                }
            ).encode()
        )
        auth = tmp_path / "auth-fixture"
        auth.mkdir(mode=0o700)
    owner, project = str(uuid4()), str(uuid4())
    cfg = {
        "schema_version": 1,
        "owner_id": owner,
        "project_id": project,
        "root": str(root),
        "certificates": str(store.root),
        "certificate_sha256": digest,
        "native_binary": str(
            Path.home() / ".local/share/claude/versions/2.1.273" if actual else tmp_path / "not-a-live-cli"
        ),
        "native_config": str(auth),
        "skills_archive": str(
            Path(__file__).resolve().parents[2] / "docs/specification/attachments/agentos-skills-v0.1.0.zip"
        ),
        "checks": [
            {"ref": "unit-check", "script": "required.py", "sha256": hashlib.sha256(check.read_bytes()).hexdigest()}
        ],
    }
    config = tmp_path / "build.json"
    config.write_text(json.dumps(cfg))
    config.chmod(0o600)
    source = tmp_path / "source"
    source.mkdir()
    git(source, "init", "-b", "main")
    git(source, "config", "user.name", "Synthetic owner fixture")
    git(source, "config", "user.email", "fixture@panestria.invalid")
    (source / "calculator.py").write_text("value = 42\n")
    git(source, "add", "calculator.py")
    git(source, "commit", "-m", "public synthetic baseline")
    bare = root / "protected" / owner / project / "destination.git"
    bare.parent.mkdir(parents=True, mode=0o700)
    git(source, "clone", "--bare", "--no-hardlinks", ".", str(bare))
    transport = SimpleNamespace(
        before=None, launches=0, contexts=[], started=threading.Event(), block=False, unavailable=False
    )

    def fake_native(_self, *args, **kwargs):
        return NativeTransportFixture.build_public(transport, *args, **kwargs)

    if not actual:
        monkeypatch.setattr(ClaudeScopedBashAdapter, "build_public", fake_native)
    monkeypatch.setenv("PANESTRIA_DATABASE_URL", r1_database)
    return SimpleNamespace(
        actual=actual,
        config=config,
        cfg=cfg,
        root=root,
        source=source,
        bare=bare,
        transport=transport,
        dsn=r1_database,
        base=git(bare, "rev-parse", "HEAD"),
    )


def invoke(fixture, *args, expected=0):
    result = CliRunner().invoke(app, ["build", args[0], "--config", str(fixture.config), *args[1:]])
    assert result.exit_code == expected, (result.stdout, result.exception)
    return json.loads(result.stdout)


def prepare(fixture):
    review = invoke(fixture, "prepare-policy", "--allow-public-native-build")
    assert review["state"] == "PENDING" and fixture.transport.launches == 0
    invoke(fixture, "confirm-policy", review["review_id"], "ff" * 32, expected=1)
    return invoke(fixture, "confirm-policy", review["review_id"], review["effect_digest"])["policy_ref"]


def contract(fixture, ref):
    return {
        "schema_version": 1,
        "goal_id": str(uuid4()),
        "owner_id": fixture.cfg["owner_id"],
        "project_id": fixture.cfg["project_id"],
        "contract_version": 1,
        "intent": "Change calculator.py to exactly 'value = 43\\n' and create notes/build.txt with exactly "
        "'bounded Bash build\\n'. Change no other files.",
        "privacy_class": "PUBLIC",
        "trust_profile_id": "PERSONAL_SANDBOX",
        "autonomy_profile_ref": ref,
        "constraints": {
            "allowed_paths": ["calculator.py", "notes/**"],
            "forbidden_paths": [".git/**", ".env*", "secrets/**"],
            "permitted_capabilities": ["scoped-bash"],
            "cloud_egress": "allow",
        },
        "budget": {"max_attempts_per_task": 1, "max_wall_seconds": 90, "max_api_usd": "0"},
        "acceptance": [
            {
                "id": "tests",
                "description": "Reviewed calculator and note checks",
                "required": True,
                "evidence": {"required": True, "kind": "registered-check-report"},
                "verifier": {
                    "type": "trusted-command-ref",
                    "command_ref": "unit-check",
                    "expected_exit_code": 0,
                    "timeout_seconds": 10,
                },
            },
            {
                "id": "paths",
                "description": "Scoped diff",
                "required": True,
                "evidence": {"required": True, "kind": "git-diff-path-check-report"},
                "verifier": {
                    "type": "git-diff-path-check",
                    "allowed_paths": ["calculator.py", "notes/**"],
                    "forbidden_paths": [".git/**"],
                },
            },
            {
                "id": "merge",
                "description": "Exact owner approval",
                "required": True,
                "evidence": {"required": True, "kind": "policy-decision-report"},
                "verifier": {"type": "policy-decision", "action": "protected-merge", "expected": "approval-required"},
            },
        ],
        "non_goals": [],
    }


def submit(fixture, document, expected=0):
    path = fixture.config.parent / "contract.json"
    path.write_text(json.dumps(document))
    path.chmod(0o600)
    return invoke(
        fixture,
        "submit",
        "--contract",
        str(path),
        "--select",
        "calculator.py",
        "--expected-base",
        fixture.base,
        "--idempotency-key",
        document["goal_id"],
        "--public-subscription-run",
        expected=expected,
    )


def journey(f):
    doc = contract(f, prepare(f))
    result = submit(f, doc)
    assert result["task_state"] == "WAITING_APPROVAL"
    assert f.actual or f.transport.launches == 1
    assert git(f.bare, "rev-parse", "HEAD") == f.base
    view = invoke(f, "status", doc["goal_id"], "--diff")
    assert "+value = 43" in view["diff"] and "+bounded Bash build" in view["diff"]
    assert all(check["verdict"] == "PASS" for check in view["checks"])
    approval = view["approval"]
    args = (approval["approval_id"], approval["effect_digest"], str(approval["expected_version"]), "exact-test-owner")
    invoke(f, "approve", args[0], "ff" * 32, *args[2:], expected=1)
    assert git(f.bare, "rev-parse", "HEAD") == f.base
    merged = invoke(f, "approve", *args)
    assert merged["task_state"] == "COMPLETED"
    assert git(f.bare, "rev-parse", "HEAD") == view["candidate_commit"]
    assert git(f.source, "rev-parse", "HEAD") == f.base
    assert (f.source / "calculator.py").read_text() == "value = 42\n"
    assert submit(f, doc)["replayed"] is True
    assert f.actual or f.transport.launches == 1
    with psycopg.connect(f.dsn) as c:
        assert c.execute("SELECT status FROM panestria.goal WHERE id=%s", (doc["goal_id"],)).fetchone() == (
            "COMPLETED",
        )


def test_owner_cli_submits_inspects_and_merges_only_the_exact_reviewed_candidate(owner_cli, record_property):
    record_property("scope", "TEST_FIXTURE_NOT_LIVE certificate and native transport; actual PG/Docker/Git/CLI")
    journey(owner_cli)


@pytest.mark.live
def test_actual_owner_cli_uses_real_operator_certificate_and_native_subscription(owner_cli, record_property):
    record_property(
        "scope",
        "Actual PUBLIC native transport and real operator-issued certificate; "
        "scripted test-owner approval, no human signoff",
    )
    record_property("runtime_certificate_sha256", owner_cli.cfg["certificate_sha256"])
    journey(owner_cli)


@pytest.mark.parametrize("bad", ["private", "money", "missing-checks", "wrong-owner", "stale-base"])
def test_owner_cli_denies_ineligible_work_without_native_inference(owner_cli, bad):
    f = owner_cli
    doc = contract(f, prepare(f))
    if bad == "private":
        doc["privacy_class"], doc["constraints"]["cloud_egress"] = "RESTRICTED", "deny"
    elif bad == "money":
        doc["budget"]["max_api_usd"] = "1"
    elif bad == "missing-checks":
        doc["acceptance"] = doc["acceptance"][1:]
    elif bad == "wrong-owner":
        doc["owner_id"] = str(uuid4())
    else:
        f.base = "ab" * 20
    assert submit(f, doc, expected=1)["status"] == "UNAVAILABLE" and f.transport.launches == 0
    with psycopg.connect(f.dsn) as c:
        assert c.execute("SELECT count(*) FROM panestria.goal WHERE id=%s", (doc["goal_id"],)).fetchone() == (0,)


def test_owner_cli_cancellation_interrupts_running_submit_without_operation_lock(owner_cli):
    f = owner_cli
    document = contract(f, prepare(f))
    f.transport.block = True
    service = OwnerBuild(load_build_settings(f.config), f.dsn)
    results = []
    worker = threading.Thread(
        target=lambda: results.append(
            service.submit(document, ("calculator.py",), f.base, document["goal_id"], public_subscription_run=True)
        )
    )
    worker.start()
    try:
        assert f.transport.started.wait(5)
        view = service.status(document["goal_id"])
        receipt = invoke(f, "cancel", document["goal_id"], str(view["row_version"]))
        assert receipt["task_state"] == "CANCELLED"
    finally:
        worker.join(timeout=8)
    assert not worker.is_alive() and results[0]["task_state"] == "CANCELLED"
    assert git(f.bare, "rev-parse", "HEAD") == f.base
    assert "approval" not in service.status(document["goal_id"])


def test_failed_independent_check_is_inspectable_and_cannot_create_merge_approval(owner_cli):
    f = owner_cli
    script = f.root / "reviewed/required.py"
    script.write_text("raise AssertionError('independent synthetic failure')\n")
    f.cfg["checks"][0]["sha256"] = hashlib.sha256(script.read_bytes()).hexdigest()
    f.config.write_text(json.dumps(f.cfg))
    document = contract(f, prepare(f))
    result = submit(f, document, expected=1)
    assert result["task_state"] == "FAILED"
    view = invoke(f, "status", document["goal_id"], "--diff")
    assert any(check["verdict"] == "FAIL" for check in view["checks"])
    assert "approval" not in view and git(f.bare, "rev-parse", "HEAD") == f.base
