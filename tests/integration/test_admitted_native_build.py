"""Actual PG/Docker/Git; explicitly labeled certificate and native transport fixtures.

Fixture certificates exist only in disposable test roots. They are not production
runtime qualification, gate evidence or approval to use an owner repository.
"""

import hashlib
import json
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest
from test_registered_check_authority import git, rows
from test_scoped_bash import build as build
from test_scoped_bash import configured as configured
from test_scoped_bash import required_registry

from panestria.brokers.harness.claude_build import PROFILE, ClaudeScopedBashAdapter
from panestria.brokers.harness.claude_check import CheckProfileObservation
from panestria.brokers.harness.claude_proposal import PINNED_BINARY_SHA256
from panestria.brokers.harness.cli_profile import BinaryPin
from panestria.brokers.harness.process_runner import ProcessReceipt
from panestria.contracts.goal import contract_sha256, load_contract
from panestria.execution.native_build import AdmittedNativeBuild, runtime_versions
from panestria.execution.scoped_bash import ScopedBashController
from panestria.kernel.build import BuildEvidenceStore
from panestria.kernel.errors import KernelDenied
from panestria.kernel.policy import PolicyService
from panestria.kernel.uow import UnitOfWork
from panestria.policy.profiles import CertificateStore


@pytest.fixture
def admitted(build, request):
    task, args, _cid, _policy = build
    args = list(args)
    dsn, actor, scope, old, _session, snapshot, _workspace, _certs, _reports = args
    versions = runtime_versions()
    root = snapshot.directory.parents[1] / "admission-certificates"
    blobs = BuildEvidenceStore(root)
    cases = []
    for case in ("AOS-008-TC03", "AOS-010-TC03"):
        report = blobs.write_report(json.dumps({"scope": "TEST_FIXTURE_NOT_LIVE", "case": case}).encode())
        cases.append({"case_id": case, "verdict": "PASS", "execution_mode": "OS_BOUNDARY", "report_sha256": report})
    digest = blobs.write_report(
        json.dumps(
            {
                "schema_version": 1,
                "profile": "PERSONAL_SANDBOX",
                "verdict": "PASS",
                "runtime_versions": versions,
                "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                "candidate_commit": "ab" * 20,
                "allowed_actions": ["read", "edit", "external-send", "merge"],
                "cases": cases,
                "scope": "TEST_FIXTURE_NOT_LIVE",
            }
        ).encode()
    )
    certificates = CertificateStore(root, versions)
    setting = getattr(request, "param", "public")
    with psycopg.connect(dsn) as connection:
        service = PolicyService(certificates)
        policy = service.get(UnitOfWork(connection), actor)
        actions = dict(policy.autonomy.actions)
        actions["external-send"] = "approve-first" if setting == "approval-needed" else "act-and-report"
        proposed = policy.model_copy(
            update={
                "version": policy.version + 1,
                "trust": policy.trust.model_copy(
                    update={
                        "version": policy.trust.version + 1,
                        "profile": "PERSONAL_SANDBOX",
                        "allowed_actions": sorted(["read", "edit", "external-send", "merge"]),
                        "runtime_certificate_sha256": digest,
                    }
                ),
                "privacy": policy.privacy.model_copy(
                    update={"version": policy.privacy.version + 1, "cloud_destinations": ["claude-subscription"]}
                ),
                "autonomy": policy.autonomy.model_copy(
                    update={
                        "version": policy.autonomy.version + int(actions != policy.autonomy.actions),
                        "actions": actions,
                    }
                ),
            }
        )
        review = service.propose(UnitOfWork(connection), actor, task["task"], proposed)
        service.decide(UnitOfWork(connection), actor, review.review_id, review.effect_digest, "approve")
        policy = service.apply(UnitOfWork(connection), actor, review.review_id, review.effect_digest)
        doc = old.model_dump(mode="json")
        doc.update(
            contract_version=4,
            trust_profile_id="PERSONAL_SANDBOX",
            autonomy_profile_ref=f"project-policy:{policy.version}:{policy.sha256()}",
            intent="Set calculator.py to exactly 'value = 43\\n' and create notes/build.txt with exactly "
            "'bounded Bash build\\n'. Change no other files.",
            privacy_class="RESTRICTED" if setting == "restricted" else "PUBLIC",
        )
        doc["constraints"]["cloud_egress"] = "deny" if setting in {"no-egress", "restricted"} else "allow"
        contract = load_contract(doc)
        cid = str(uuid4())
        connection.execute(
            "INSERT INTO panestria.goal_contract(id,goal_id,version,body,sha256) VALUES (%s,%s,4,%s::jsonb,%s)",
            (cid, task["goal"], contract.model_dump_json(), contract_sha256(contract)),
        )
        connection.execute("UPDATE panestria.task SET contract_id=%s WHERE id=%s", (cid, task["task"]))
        for check in contract.acceptance:
            connection.execute(
                "INSERT INTO panestria.acceptance_check"
                "(id,contract_id,check_key,description,required,verifier_type,verifier_spec)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)",
                (
                    str(uuid4()),
                    cid,
                    check.id,
                    check.description,
                    check.required,
                    check.verifier.type,
                    json.dumps(check.verifier.model_dump(mode="json")),
                ),
            )
    args[2] = scope.model_copy(
        update={"policy_ref": contract.autonomy_profile_ref, "contract_sha256": contract_sha256(contract)}
    )
    args[3], args[7] = contract, certificates
    return task, ScopedBashController(*args)


class NativeTransportFixture(ClaudeScopedBashAdapter):
    def __init__(self, root, controller):
        config = root / "private-auth-fixture"
        config.mkdir(mode=0o700)
        self.native = SimpleNamespace(config=config, pin=BinaryPin(root / "not-a-live-cli", PINNED_BINARY_SHA256))
        self.controller, self.launches, self.contexts = controller, 0, []
        self.before, self.block, self.started, self.unavailable = None, False, threading.Event(), False

    def build_public(self, session, *, public_context, cancel=None, startup_only=False, before_launch=None):
        if self.before:
            self.before()
        assert before_launch is not None
        before_launch()
        self.launches += 1
        self.contexts.append(public_context)
        self.started.set()
        if self.block:
            assert cancel is not None and cancel.wait(5)
        elif not self.unavailable:
            for body in (
                {
                    "jsonrpc": "2.0",
                    "id": "init",
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "transport-fixture", "version": "1"},
                    },
                },
                {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
                {
                    "jsonrpc": "2.0",
                    "id": "edit",
                    "method": "tools/call",
                    "params": {
                        "name": "run_scoped_bash",
                        "arguments": {
                            "job_ref": session.references[1],
                            "script": "set -eu; printf 'value = 43\\n' > calculator.py; "
                            "mkdir notes; printf 'bounded Bash build\\n' > notes/build.txt",
                        },
                    },
                },
            ):
                response = session.handle(json.dumps(body).encode())
            assert json.loads(response)["result"]["isError"] is False
        status = "UNAVAILABLE" if self.unavailable else "CANDIDATE"
        return CheckProfileObservation(
            ProcessReceipt(
                status,
                True,
                0,
                "quota_unavailable" if self.unavailable else "TEST_FIXTURE_NOT_LIVE",
                "ab" * 32,
                "cd" * 32,
                None,
            ),
            True,
            True,
            "ef" * 32,
            profile=PROFILE,
        )


def run(task, controller, adapter, **kwargs):
    bare = Path(task["bare"])
    registry = getattr(adapter, "_test_registry", None)
    if registry is None:
        registry = required_registry(bare.parent, "value = 43\n", notes=True)
        adapter._test_registry = registry
    return AdmittedNativeBuild(controller, ("calculator.py",)).run(
        adapter,
        Path(task["protected"]),
        bare,
        git(bare, "rev-parse", "HEAD"),
        bare.parent / "frozen",
        registry,
        **kwargs,
    )


def test_admitted_build_has_one_committed_launch_selected_context_and_exact_review(admitted):
    task, controller = admitted
    adapter = NativeTransportFixture(controller.workspace.parent.parent, controller)
    original = adapter.build_public

    def inspect_intent(*args, **kwargs):
        assert [row[0] for row in rows(task)] == ["CLAIMED"]
        return original(*args, **kwargs)

    adapter.build_public = inspect_intent
    outcome = run(task, controller, adapter)
    assert outcome.status == "WAITING_APPROVAL" and outcome.review.passed and adapter.launches == 1
    context = json.loads(adapter.contexts[0])
    assert context["files"] == [
        {"path": "calculator.py", "sha256": hashlib.sha256(b"value = 42\n").hexdigest(), "content": "value = 42\n"}
    ]
    assert outcome.context_sha256 == hashlib.sha256(adapter.contexts[0].encode()).hexdigest()
    assert sorted(row[0] for row in rows(task)) == ["RETURNED", "RETURNED"]
    with controller.connect() as connection:
        event = connection.execute(
            "SELECT payload FROM panestria.task_event WHERE task_id=%s AND kind='native_build.context_disclosure'",
            (task["task"],),
        ).fetchone()[0]
        assert event["authorized"]["value"] == "yes" and event["observed"]["value"] == "unknown"
        assert "value = 42" not in json.dumps(event)
    assert run(task, controller, adapter).status == "UNAVAILABLE" and adapter.launches == 1


@pytest.mark.parametrize("admitted", ["restricted", "no-egress"], indirect=True)
def test_nonpublic_or_offline_context_is_never_compiled_for_export(admitted):
    _task, controller = admitted
    with pytest.raises(KernelDenied, match="native_build_not_eligible"):
        AdmittedNativeBuild(controller, ("calculator.py",))


@pytest.mark.parametrize("admitted", ["approval-needed"], indirect=True)
def test_missing_export_approval_never_prepares_or_launches(admitted):
    task, controller = admitted
    adapter = NativeTransportFixture(controller.workspace.parent.parent, controller)
    assert run(task, controller, adapter).status == "UNAVAILABLE"
    assert adapter.launches == 0 and rows(task) == []


def test_policy_revoked_at_launch_point_sends_no_context(admitted):
    task, controller = admitted
    adapter = NativeTransportFixture(controller.workspace.parent.parent, controller)

    def revoke():
        with controller.connect() as connection:
            connection.execute(
                "UPDATE panestria.project SET policy_version=policy_version+1 WHERE id=%s", (task["project"],)
            )

    adapter.before = revoke
    assert run(task, controller, adapter).status == "UNAVAILABLE" and adapter.launches == 0
    assert rows(task) == [("UNKNOWN", None)]


def test_cancellation_stops_current_native_call_and_never_replays(admitted):
    from concurrent.futures import ThreadPoolExecutor

    task, controller = admitted
    adapter = NativeTransportFixture(controller.workspace.parent.parent, controller)
    adapter.block = True
    cancel = threading.Event()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(run, task, controller, adapter, cancel=cancel)
        assert adapter.started.wait(5)
        cancel.set()
        outcome = future.result(timeout=6)
    assert outcome.status == "CANCELLED" and rows(task) == [("UNKNOWN", None)]
    assert run(task, controller, adapter).status == "UNAVAILABLE" and adapter.launches == 1


def test_quota_unavailable_finishes_attempt_without_retry_storm(admitted):
    task, controller = admitted
    adapter = NativeTransportFixture(controller.workspace.parent.parent, controller)
    adapter.unavailable = True
    outcome = run(task, controller, adapter)
    assert outcome.status == "UNAVAILABLE" and outcome.reason == "quota_unavailable"
    with controller.connect() as connection:
        assert connection.execute(
            "SELECT state,retry_at FROM panestria.task WHERE id=%s", (task["task"],)
        ).fetchone() == ("FAILED", None)
    assert run(task, controller, adapter).status == "UNAVAILABLE" and adapter.launches == 1


@pytest.mark.parametrize("paths", [("notes/absent.txt",), (".env",), ("calculator.py", "calculator.py")])
def test_only_explicit_protected_scoped_source_can_enter_context(admitted, paths):
    task, controller = admitted
    with pytest.raises(KernelDenied):
        AdmittedNativeBuild(controller, paths)
    assert rows(task) == []


def test_cancelled_verification_cannot_publish_pass_or_request_approval(admitted, monkeypatch):
    import panestria.execution.scoped_bash as module

    task, controller = admitted
    adapter = NativeTransportFixture(controller.workspace.parent.parent, controller)
    cancel = threading.Event()
    original = module.verify_build

    def cancelled(*args, **kwargs):
        verified = original(*args, **kwargs)
        assert verified.bundle.passed()
        cancel.set()
        return verified

    monkeypatch.setattr(module, "verify_build", cancelled)
    outcome = run(task, controller, adapter, cancel=cancel)
    assert outcome.status == "CANCELLED" and outcome.review is None
    with controller.connect() as connection:
        assert connection.execute(
            "SELECT count(*) FROM panestria.build_evidence WHERE task_id=%s", (task["task"],)
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT count(*) FROM panestria.approval_request WHERE task_id=%s", (task["task"],)
        ).fetchone() == (0,)


@pytest.mark.live
def test_actual_native_uses_admitted_context_and_durable_launch(admitted, record_property):
    from panestria.brokers.harness.claude_proposal import ClaudeProposalAdapter

    task, controller = admitted
    native = ClaudeProposalAdapter(
        BinaryPin(Path("/home/yogesh/.local/share/claude/versions/2.1.273"), PINNED_BINARY_SHA256),
        Path.home() / ".panestria-native-claude",
        Path(__file__).resolve().parents[2] / "docs/specification/attachments/agentos-skills-v0.1.0.zip",
    )
    outcome = run(task, controller, ClaudeScopedBashAdapter(native))
    record_property(
        "scope",
        "Actual PUBLIC subscription/PG/Docker/Git flow with TEST_FIXTURE_NOT_LIVE certificate; "
        "does not qualify or install a production runtime certificate",
    )
    record_property("certificate_source", "TEST_FIXTURE_NOT_LIVE")
    record_property("native_actual_cash", "UNKNOWN_SUBSCRIPTION_NO_DIRECT_SDK_CALL")
    record_property(
        "outcome",
        json.dumps(
            {
                "status": outcome.status,
                "reason": outcome.reason,
                "context_sha256": outcome.context_sha256,
                "native_report_sha256": outcome.native_report_sha256,
            }
        ),
    )
    assert outcome.status == "WAITING_APPROVAL" and outcome.review.passed, outcome
    assert len(rows(task)) == 2 and all(row[0] == "RETURNED" for row in rows(task))
