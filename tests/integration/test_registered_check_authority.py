"""Actual PostgreSQL and Docker with public synthetic data, no provider calls."""

import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
from dataclasses import replace
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest

from panestria.brokers.harness.command_transport import RegisteredCheckSocket
from panestria.contracts.goal import contract_sha256, load_contract
from panestria.contracts.native_tools import ToolScope
from panestria.execution.registered_checks import RegisteredCheckController, RegisteredCheckUnavailable
from panestria.kernel.build import BuildEvidenceStore
from panestria.kernel.goals import Actor
from panestria.kernel.leases import LeaseService
from panestria.kernel.policy import PolicyService
from panestria.kernel.uow import UnitOfWork
from panestria.policy.profiles import CertificateStore
from panestria.sandbox.native_tool_gateway import ReviewedCommand
from panestria.verification.git_snapshot import materialize


def git(path, *args):
    return subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", "-C", str(path), *args],
        capture_output=True,
        text=True,
        check=True,
        env={
            "PATH": "/usr/bin:/bin",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
            "GIT_ALLOW_PROTOCOL": "file",
            "GIT_TERMINAL_PROMPT": "0",
        },
    ).stdout.strip()


@pytest.fixture
def configured(r1_task, tmp_path, request):
    actor = Actor(r1_task["owner"], r1_task["project"])
    certificates = CertificateStore(tmp_path / "certificates", {})
    with psycopg.connect(r1_task["dsn"]) as connection:
        policy = PolicyService(certificates).initialize(UnitOfWork(connection), actor, r1_task["task"])
    setting = getattr(request, "param", "permit")
    if setting in {"observe", "approve-first", "trust-deny"}:
        if setting == "trust-deny":
            changes = {"trust": policy.trust.model_copy(update={"version": 2, "allowed_actions": ["edit", "merge"]})}
        else:
            actions = dict(policy.autonomy.actions)
            actions["read"] = setting
            changes = {"autonomy": policy.autonomy.model_copy(update={"version": 2, "actions": actions})}
        proposed = policy.model_copy(update={"version": 2, **changes})
        with psycopg.connect(r1_task["dsn"]) as connection:
            service = PolicyService(certificates)
            review = service.propose(UnitOfWork(connection), actor, r1_task["task"], proposed)
            service.decide(UnitOfWork(connection), actor, review.review_id, review.effect_digest, "approve")
            policy = service.apply(UnitOfWork(connection), actor, review.review_id, review.effect_digest)
    contract = load_contract(
        {
            "schema_version": 1,
            "goal_id": r1_task["goal"],
            "owner_id": actor.owner_id,
            "project_id": actor.project_id,
            "contract_version": 2,
            "intent": "Read public synthetic calculator",
            "privacy_class": "RESTRICTED" if setting == "restricted" else "PUBLIC",
            "trust_profile_id": "SYNTHETIC_DEV",
            "autonomy_profile_ref": f"project-policy:{policy.version}:{policy.sha256()}",
            "constraints": {
                "allowed_paths": ["calculator.py"],
                "forbidden_paths": [".git"],
                "permitted_capabilities": ["read"],
                "cloud_egress": "deny",
            },
            "budget": {"max_attempts_per_task": 3, "max_wall_seconds": 30, "max_api_usd": "0"},
            "acceptance": [
                {
                    "id": "required-check",
                    "description": "Reviewed read check",
                    "required": True,
                    "evidence": {"required": True, "kind": "registered-check-report"},
                    "verifier": {
                        "type": "trusted-command-ref",
                        "command_ref": "unit-check",
                        "expected_exit_code": 0,
                        "timeout_seconds": 10,
                    },
                }
            ],
            "non_goals": [],
        }
    )
    with psycopg.connect(r1_task["dsn"]) as connection:
        cid = str(uuid4())
        connection.execute(
            "INSERT INTO panestria.goal_contract(id,goal_id,version,body,sha256) VALUES (%s,%s,2,%s::jsonb,%s)",
            (cid, r1_task["goal"], contract.model_dump_json(), contract_sha256(contract)),
        )
        connection.execute("UPDATE panestria.task SET contract_id=%s WHERE id=%s", (cid, r1_task["task"]))
        lease = LeaseService().acquire(
            UnitOfWork(connection), actor, r1_task["task"], "registered-check-fixture", 0, ttl_seconds=120
        )
    scope = ToolScope(
        owner_id=UUID(actor.owner_id),
        project_id=UUID(actor.project_id),
        task_id=UUID(r1_task["task"]),
        attempt_id=UUID(lease.attempt_id),
        lease_epoch=lease.epoch,
        contract_sha256=contract_sha256(contract),
        policy_ref=contract.autonomy_profile_ref,
    )
    work = tmp_path / "git-work"
    work.mkdir()
    git(work, "init", "-b", "main")
    git(work, "config", "user.name", "Synthetic test fixture")
    git(work, "config", "user.email", "fixture@panestria.invalid")
    (work / "calculator.py").write_text("value = 42\n")
    git(work, "add", "calculator.py")
    git(work, "commit", "-m", "public synthetic candidate")
    candidate = git(work, "rev-parse", "HEAD")
    bare = tmp_path / "protected.git"
    git(work, "clone", "--bare", ".", str(bare))
    snapshot = materialize(bare, candidate, candidate, tmp_path / "snapshots" / "candidate")
    script = tmp_path / "reviewed.py"
    script.write_text(
        "from pathlib import Path\n"
        "assert Path('/workspace/calculator.py').read_text() == 'value = 42\\n'\n"
        "print('reviewed public check')\n"
    )
    script.chmod(0o600)
    command = ReviewedCommand("unit-check", script, hashlib.sha256(script.read_bytes()).hexdigest(), "read")
    reports = BuildEvidenceStore(tmp_path / "reports")
    args = (r1_task["dsn"], actor, scope, contract, uuid4(), snapshot, command, certificates, reports)
    return r1_task, args


def run(controller, cancel=None):
    return controller.execute(controller.command.ref, controller.candidate_ref, cancel or threading.Event())


def rows(task):
    with psycopg.connect(task["dsn"]) as connection:
        return connection.execute(
            "SELECT state,receipt_sha256 FROM panestria.worker_invocation WHERE task_id=%s", (task["task"],)
        ).fetchall()


def test_actual_read_check_publishes_verified_report_and_restart_never_reruns(configured):
    task, args = configured
    controller = RegisteredCheckController(*args)
    receipt = run(controller)
    assert receipt.outcome == "COMPLETED" and receipt.exit_code == 0
    report = json.loads(controller.reports.read_blob(receipt.report_sha256))
    assert base64.b64decode(report["output_base64"]) == b"reviewed public check\n"
    assert report["candidate_ref"] == controller.candidate_ref and report["independent_verification"] is False
    assert report["scope_sha256"] == controller.scope.sha256()
    assert rows(task) == [("RETURNED", receipt.report_sha256)]
    assert run(RegisteredCheckController(*args)).outcome == "UNKNOWN"
    with controller.connect() as connection:
        assert connection.execute(
            "SELECT count(*) FROM panestria.task_event WHERE task_id=%s AND kind='invocation.claimed'", (task["task"],)
        ).fetchone() == (1,)
        assert connection.execute("SELECT state FROM panestria.task WHERE id=%s", (task["task"],)).fetchone() == (
            "RUNNING",
        )
        assert connection.execute(
            "SELECT count(*) FROM panestria.approval_request WHERE task_id=%s", (task["task"],)
        ).fetchone() == (0,)


@pytest.mark.parametrize("change", ["edit", "unregistered", "not-required", "scope", "contract"])
def test_constructor_refuses_unreviewed_binding(configured, change):
    _task, args = configured
    values = list(args)
    if change == "edit":
        values[6] = replace(values[6], access="edit")
    elif change == "unregistered":
        values[6] = replace(values[6], ref="other")
    elif change == "not-required":
        values[3] = values[3].model_copy(
            update={"acceptance": [values[3].acceptance[0].model_copy(update={"required": False})]}
        )
    elif change == "scope":
        values[2] = values[2].model_copy(update={"project_id": uuid4()})
    else:
        values[3] = values[3].model_copy(update={"intent": "changed"})
    with pytest.raises(RegisteredCheckUnavailable, match="^invalid_registered_check_binding$"):
        RegisteredCheckController(*values)


@pytest.mark.parametrize("change", ["lease", "policy", "candidate", "script", "cancel"])
def test_drift_before_dispatch_has_no_claim_or_effect(configured, change):
    task, args = configured
    controller = RegisteredCheckController(*args)
    cancel = threading.Event()
    if change == "lease":
        with controller.connect() as connection:
            LeaseService().release(
                UnitOfWork(connection), controller.actor, str(controller.scope.attempt_id), controller.scope.lease_epoch
            )
    elif change == "policy":
        with controller.connect() as connection:
            connection.execute("UPDATE panestria.project SET policy_version=2 WHERE id=%s", (task["project"],))
    elif change == "candidate":
        (controller.snapshot.directory / "calculator.py").chmod(0o600)
        (controller.snapshot.directory / "calculator.py").write_text("changed")
    elif change == "script":
        controller.command.script.write_text("raise RuntimeError('PRIVATE_SENTINEL')")
    else:
        cancel.set()
    assert run(controller, cancel).outcome in {"DENIED", "UNKNOWN"}
    assert all(state == "PREPARED" for state, _ in rows(task))
    with controller.connect() as connection:
        assert connection.execute(
            "SELECT count(*) FROM panestria.task_event WHERE task_id=%s AND kind='invocation.claimed'", (task["task"],)
        ).fetchone() == (0,)


def test_nonzero_exit_is_completed_execution_and_failed_check(configured):
    task, args = configured
    script = args[6].script
    script.write_text("print('failed public check')\nraise SystemExit(3)\n")
    values = list(args)
    values[6] = replace(args[6], sha256=hashlib.sha256(script.read_bytes()).hexdigest())
    controller = RegisteredCheckController(*values)
    receipt = run(controller)
    assert receipt.outcome == "COMPLETED" and receipt.exit_code == 3
    assert rows(task) == [("RETURNED", receipt.report_sha256)]


def test_readonly_container_cannot_edit_candidate_or_use_network(configured):
    _task, args = configured
    script = args[6].script
    script.write_text(
        "from pathlib import Path\nimport socket\n"
        "try:\n Path('/workspace/calculator.py').write_text('changed')\n"
        "except OSError:\n pass\nelse:\n raise RuntimeError('writable candidate')\n"
        "try:\n socket.socket().connect(('1.1.1.1',443))\n"
        "except (OSError,PermissionError):\n pass\nelse:\n raise RuntimeError('network available')\n"
        "print('isolation observed')\n"
    )
    values = list(args)
    values[6] = replace(args[6], sha256=hashlib.sha256(script.read_bytes()).hexdigest())
    controller = RegisteredCheckController(*values)
    assert run(controller).outcome == "COMPLETED"
    assert (controller.snapshot.directory / "calculator.py").read_text() == "value = 42\n"


@pytest.mark.parametrize("failure", ["missing", "corrupt"])
def test_missing_or_corrupt_final_report_is_never_a_completion(configured, monkeypatch, failure):
    task, args = configured
    controller = RegisteredCheckController(*args)
    original = controller.reports.write_report

    def broken(raw):
        digest = original(raw)
        path = controller.reports.root / digest
        if failure == "missing":
            path.unlink()
        else:
            path.chmod(0o600)
            path.write_text("corrupt")
        return digest

    monkeypatch.setattr(controller.reports, "write_report", broken)
    assert run(controller).outcome == "UNKNOWN"
    assert rows(task) == [("UNKNOWN", None)]
    assert run(RegisteredCheckController(*args)).outcome == "UNKNOWN"


def test_actual_private_stdio_to_postgres_docker_protected_report(configured):
    task, args = configured
    controller = RegisteredCheckController(*args)

    def frame(method, identity=None, **params):
        body = {"jsonrpc": "2.0", "method": method, "params": params}
        if identity is not None:
            body["id"] = identity
        return json.dumps(body).encode() + b"\n"

    with tempfile.TemporaryDirectory(prefix="pns-check-", dir="/tmp") as root:
        with RegisteredCheckSocket(Path(root) / "attempt", controller.session()) as server:
            child = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "panestria.brokers.harness.command_stdio",
                    "--endpoint",
                    str(server.path),
                    "--device",
                    str(server.identity[0]),
                    "--inode",
                    str(server.identity[1]),
                    "--controller-pid",
                    str(os.getpid()),
                    "--lifetime-seconds",
                    "10",
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(Path(__file__).resolve().parents[2] / "src")},
            )
            try:
                child.stdin.write(
                    frame(
                        "initialize",
                        "init",
                        protocolVersion="2025-06-18",
                        capabilities={},
                        clientInfo={"name": "synthetic", "version": "1"},
                    )
                )
                child.stdin.flush()
                assert json.loads(child.stdout.readline())["id"] == "init"
                child.stdin.write(
                    frame("notifications/initialized")
                    + frame(
                        "tools/call",
                        "check",
                        name="run_registered_check",
                        arguments={"command_ref": "unit-check", "candidate_ref": controller.candidate_ref},
                    )
                )
                child.stdin.flush()
                response = json.loads(child.stdout.readline())["result"]
                assert response["isError"] is False and response["structuredContent"]["outcome"] == "COMPLETED"
                digest = response["structuredContent"]["report_sha256"]
                assert rows(task) == [("RETURNED", digest)] and controller.reports.read_blob(digest)
                child.stdin.close()
                child.wait(timeout=3)
                assert child.returncode == 0 and child.stderr.read() == b""
            finally:
                if child.poll() is None:
                    child.kill()
                child.wait(timeout=3)
                for pipe in (child.stdin, child.stdout, child.stderr):
                    pipe.close()


@pytest.mark.parametrize("configured", ["observe", "approve-first", "trust-deny"], indirect=True)
def test_current_read_policy_denial_or_missing_approval_never_prepares(configured):
    task, args = configured
    controller = RegisteredCheckController(*args)
    assert run(controller).outcome == "UNKNOWN" and rows(task) == []


@pytest.mark.parametrize("configured", ["restricted"], indirect=True)
def test_restricted_local_check_keeps_output_in_protected_report(configured):
    _task, args = configured
    controller = RegisteredCheckController(*args)
    receipt = run(controller)
    assert receipt.outcome == "COMPLETED"
    report = json.loads(controller.reports.read_blob(receipt.report_sha256))
    assert report["privacy_class"] == "RESTRICTED"
    assert "output" not in receipt.model_dump() and "reviewed public check" not in receipt.model_dump_json()
    assert (controller.reports.root / receipt.report_sha256).stat().st_mode & 0o777 == 0o400


@pytest.mark.parametrize("revoke", ["lease", "policy", "cancel"])
def test_authority_loss_after_report_storage_never_publishes_completion(configured, monkeypatch, revoke):
    task, args = configured
    controller = RegisteredCheckController(*args)
    original = controller.reports.write_report
    cancel = threading.Event()

    def revoke_after_write(raw):
        digest = original(raw)
        if revoke == "cancel":
            cancel.set()
        else:
            with controller.connect() as connection:
                if revoke == "lease":
                    LeaseService().release(
                        UnitOfWork(connection),
                        controller.actor,
                        str(controller.scope.attempt_id),
                        controller.scope.lease_epoch,
                    )
                else:
                    connection.execute("UPDATE panestria.project SET policy_version=2 WHERE id=%s", (task["project"],))
        return digest

    monkeypatch.setattr(controller.reports, "write_report", revoke_after_write)
    assert run(controller, cancel).outcome == ("CANCELLED" if revoke == "cancel" else "UNKNOWN")
    assert rows(task) == [("UNKNOWN", None)]


def test_two_reconstructed_controllers_have_one_actual_dispatch(configured):
    from concurrent.futures import ThreadPoolExecutor

    task, args = configured
    with ThreadPoolExecutor(max_workers=2) as pool:
        receipts = list(pool.map(lambda _: run(RegisteredCheckController(*args)), range(2)))
    assert sorted(receipt.outcome for receipt in receipts) == ["COMPLETED", "UNKNOWN"]
    assert len(rows(task)) == 1 and rows(task)[0][0] == "RETURNED"
    with psycopg.connect(task["dsn"]) as connection:
        assert connection.execute(
            "SELECT count(*) FROM panestria.task_event WHERE task_id=%s AND kind='invocation.claimed'", (task["task"],)
        ).fetchone() == (1,)


def test_actual_output_limit_cannot_complete(configured):
    task, args = configured
    script = args[6].script
    script.write_text("print('x' * 20000)\n")
    values = list(args)
    values[6] = replace(args[6], sha256=hashlib.sha256(script.read_bytes()).hexdigest())
    controller = RegisteredCheckController(*values)
    assert run(controller).outcome == "UNKNOWN" and rows(task) == [("UNKNOWN", None)]


@pytest.mark.parametrize("revoke", ["lease", "cancel"])
def test_actual_running_container_stops_after_authority_loss(configured, monkeypatch, revoke):
    import time

    from panestria.sandbox.runner import DockerSandbox

    task, args = configured
    script = args[6].script
    script.write_text("import time\ntime.sleep(8)\n")
    values = list(args)
    values[6] = replace(args[6], sha256=hashlib.sha256(script.read_bytes()).hexdigest())
    controller = RegisteredCheckController(*values)
    original = DockerSandbox.run
    runtime_id = str(uuid4())

    def exact_identity(self, workspace, argv, profile, **kwargs):
        return original(self, workspace, argv, profile, **{**kwargs, "attempt_id": runtime_id})

    # Only supply a deterministic test identity; the real supervisor still starts,
    # inspects, cancels, reaps and removes its actual Docker container.
    monkeypatch.setattr(DockerSandbox, "run", exact_identity)
    results, cancel = [], threading.Event()
    worker = threading.Thread(target=lambda: results.append(run(controller, cancel)))
    worker.start()
    try:
        deadline = time.monotonic() + 5
        while True:
            running = subprocess.run(
                ["docker", "ps", "--filter", "label=panestria.attempt=" + runtime_id, "-q"],
                capture_output=True,
                text=True,
                check=True,
            )
            if running.stdout.strip():
                break
            assert worker.is_alive() and time.monotonic() < deadline
            time.sleep(0.05)
        if revoke == "lease":
            with controller.connect() as connection:
                LeaseService().release(
                    UnitOfWork(connection),
                    controller.actor,
                    str(controller.scope.attempt_id),
                    controller.scope.lease_epoch,
                )
        else:
            cancel.set()
        worker.join(timeout=5)
        assert not worker.is_alive()
        assert results[0].outcome == ("CANCELLED" if revoke == "cancel" else "UNKNOWN")
        assert rows(task) == [("UNKNOWN", None)]
        remaining = subprocess.run(
            ["docker", "ps", "-a", "--filter", "label=panestria.attempt=" + runtime_id, "-q"],
            capture_output=True,
            text=True,
            check=True,
        )
        assert remaining.stdout.strip() == ""
    finally:
        cancel.set()
        worker.join(timeout=5)
