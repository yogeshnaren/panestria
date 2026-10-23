"""Real PG/Docker/Bash/Git; provider-free by default, separately scoped native live run."""

import base64
import hashlib
import json
import threading
import time
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from test_registered_check_authority import configured as configured
from test_registered_check_authority import git, rows

from panestria.contracts.goal import contract_sha256, load_contract
from panestria.execution.build_merge import VerifiedGitTarget, prepare_merge
from panestria.execution.outbox import EffectExecutor
from panestria.execution.scoped_bash import ScopedBashController, ScopedBashUnavailable
from panestria.kernel.approvals import ApprovalService
from panestria.kernel.build import BuildEvidenceService
from panestria.kernel.errors import KernelDenied
from panestria.kernel.leases import LeaseService
from panestria.kernel.policy import PolicyService
from panestria.kernel.uow import UnitOfWork
from panestria.verification.candidate import capture_candidate
from panestria.verification.git_snapshot import SnapshotRejected
from panestria.verification.registry import CommandRegistry, RegisteredCommand


@pytest.fixture
def build(configured):
    task, args = configured
    dsn, actor, scope, old, session, snapshot, _command, certificates, reports = args
    with psycopg.connect(dsn) as connection:
        service = PolicyService(certificates)
        policy = service.get(UnitOfWork(connection), actor)
        actions = dict(policy.autonomy.actions)
        actions["edit"] = "act-and-report"
        proposed = policy.model_copy(
            update={
                "version": policy.version + 1,
                "autonomy": policy.autonomy.model_copy(
                    update={"version": policy.autonomy.version + 1, "actions": actions}
                ),
            }
        )
        review = service.propose(UnitOfWork(connection), actor, task["task"], proposed)
        service.decide(UnitOfWork(connection), actor, review.review_id, review.effect_digest, "approve")
        policy = service.apply(UnitOfWork(connection), actor, review.review_id, review.effect_digest)
        doc = old.model_dump(mode="json")
        doc.update(contract_version=3, autonomy_profile_ref=f"project-policy:{policy.version}:{policy.sha256()}")
        doc["constraints"]["permitted_capabilities"] = ["scoped-bash"]
        doc["constraints"]["allowed_paths"] = ["calculator.py", "notes/**"]
        doc["acceptance"] += [
            {
                "id": "paths",
                "description": "Scoped paths only",
                "required": True,
                "evidence": {"required": True, "kind": "git-diff-path-check-report"},
                "verifier": {
                    "type": "git-diff-path-check",
                    "allowed_paths": ["calculator.py", "notes/**"],
                    "forbidden_paths": [".git"],
                },
            },
            {
                "id": "merge",
                "description": "Exact owner approval",
                "required": True,
                "evidence": {"required": True, "kind": "policy-decision-report"},
                "verifier": {"type": "policy-decision", "action": "protected-merge", "expected": "approval-required"},
            },
        ]
        contract = load_contract(doc)
        cid = str(uuid4())
        connection.execute(
            "INSERT INTO panestria.goal_contract(id,goal_id,version,body,sha256) VALUES (%s,%s,3,%s::jsonb,%s)",
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
    scope = scope.model_copy(
        update={"contract_sha256": contract_sha256(contract), "policy_ref": contract.autonomy_profile_ref}
    )
    protected = snapshot.directory.parents[1] / "protected"
    scoped = protected / actor.owner_id / actor.project_id
    scoped.mkdir(parents=True, mode=0o700)
    bare = scoped / "destination.git"
    (snapshot.directory.parents[1] / "protected.git").rename(bare)
    task.update(bare=str(bare), protected=str(protected))
    parent = snapshot.directory.parents[1] / "attempts"
    parent.mkdir(mode=0o700)
    args = (dsn, actor, scope, contract, session, snapshot, parent / str(scope.attempt_id), certificates, reports)
    return task, args, cid, policy


def execute(controller, script, cancel=None):
    return controller.execute(script, controller.job_ref, cancel or threading.Event())


def required_registry(root, expected, *, notes=False):
    reviewed = root / "independent"
    reviewed.mkdir(mode=0o700)
    script = reviewed / "required_check.py"
    source = "from pathlib import Path\nassert Path('/workspace/calculator.py').read_text() == " + repr(expected) + "\n"
    if notes:
        source += "assert Path('/workspace/notes/build.txt').read_text() == 'bounded Bash build\\n'\n"
    script.write_text(source)
    script.chmod(0o400)
    return CommandRegistry(
        reviewed,
        "/reviewed/python",
        (
            RegisteredCommand(
                "unit-check", ("/reviewed/python", str(script)), True, hashlib.sha256(script.read_bytes()).hexdigest()
            ),
        ),
    )


def test_real_bash_edits_are_separate_from_independent_acceptance_and_never_replay(build):
    task, args, cid, policy = build
    controller = ScopedBashController(*args)
    receipt = execute(controller, "printf 'value = 43\\n' > calculator.py; printf WORKER_TESTS_PASS")
    assert receipt.outcome == "COMPLETED" and receipt.exit_code == 0
    report = json.loads(controller.reports.read_blob(receipt.report_sha256))
    assert report["kind"] == "scoped-bash" and report["independent_verification"] is False
    assert base64.b64decode(report["output_base64"]) == b"WORKER_TESTS_PASS"
    assert rows(task) == [("RETURNED", receipt.report_sha256)]
    assert execute(ScopedBashController(*args), "printf replay > calculator.py").outcome == "UNKNOWN"
    assert (controller.workspace / "calculator.py").read_text() == "value = 43\n"
    bare = Path(task["bare"])
    base = git(bare, "rev-parse", "HEAD")
    assert git(bare, "rev-parse", "HEAD") == base
    assert git(bare, "show", base + ":calculator.py") == "value = 42"
    registry = required_registry(bare.parent, "value = 42\n")
    review = controller.verify_for_review(Path(task["protected"]), bare, base, bare.parent / "frozen", registry)
    assert not review.passed and review.approval is None
    bundle = controller.reports.read(review.evidence_sha256)
    assert next(check for check in bundle.checks if check.check_key == "required-check").verdict == "FAIL"
    with controller.connect() as connection:
        assert connection.execute("SELECT state FROM panestria.task WHERE id=%s", (task["task"],)).fetchone() == (
            "FAILED",
        )
        assert connection.execute(
            "SELECT count(*) FROM panestria.approval_request WHERE task_id=%s", (task["task"],)
        ).fetchone() == (0,)


def test_bash_exec_inherits_os_network_mount_and_secret_limits(build):
    _task, args, _cid, _policy = build
    controller = ScopedBashController(*args)
    receipt = execute(
        controller,
        """set -eu
test ! -e /var/run/docker.sock
test ! -e /workspace/.git
test ! -e /root/.claude
test -z "${ANTHROPIC_API_KEY-unset}" || test "${ANTHROPIC_API_KEY-unset}" = unset
python - <<'PY'
import os, socket
from pathlib import Path
assert set(os.environ) <= {'PATH','HOME','LANG','TMPDIR','PWD','SHLVL','_','LC_CTYPE'}
for family in (socket.AF_INET, socket.AF_INET6):
    try: socket.socket(family, socket.SOCK_STREAM)
    except OSError: pass
    else: raise AssertionError('network socket allowed')
try: Path('/etc/host-effect').write_text('denied')
except OSError: pass
else: raise AssertionError('root writable')
Path('/workspace/calculator.py').write_text('value = 44\\n')
print('OS_LIMITS_OBSERVED')
PY
""",
    )
    assert receipt.outcome == "COMPLETED" and receipt.exit_code == 0
    assert (controller.workspace / "calculator.py").read_text() == "value = 44\n"


def test_independent_check_uses_remaining_wall_budget_before_publication(build):
    task, args, _cid, _policy = build
    controller = ScopedBashController(*args)
    assert execute(controller, "printf 'value = 43\\n' > calculator.py").outcome == "COMPLETED"
    bare = Path(task["bare"])
    reviewed = bare.parent / "deadline-check"
    reviewed.mkdir(mode=0o700)
    script = reviewed / "required.py"
    script.write_text("import time\ntime.sleep(10)\n")
    script.chmod(0o400)
    registry = CommandRegistry(
        reviewed,
        "/reviewed/python",
        (
            RegisteredCommand(
                "unit-check", ("/reviewed/python", str(script)), True, hashlib.sha256(script.read_bytes()).hexdigest()
            ),
        ),
    )
    started = time.monotonic()
    with pytest.raises(ScopedBashUnavailable, match="cancelled_or_deadline"):
        controller.verify_for_review(
            Path(task["protected"]),
            bare,
            git(bare, "rev-parse", "HEAD"),
            bare.parent / "deadline-frozen",
            registry,
            deadline=started + 0.4,
        )
    assert time.monotonic() - started < 4
    with controller.connect() as c:
        assert c.execute(
            "SELECT count(*) FROM panestria.approval_request WHERE task_id=%s", (task["task"],)
        ).fetchone() == (0,)


@pytest.mark.parametrize("revoke", ["lease", "policy", "cancel"])
def test_revocation_after_report_cannot_publish_success_or_replay(build, monkeypatch, revoke):
    task, args, _cid, _policy = build
    controller = ScopedBashController(*args)
    original = controller.reports.write_report
    cancel = threading.Event()

    def write(raw):
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
                    connection.execute(
                        "UPDATE panestria.project SET policy_version=policy_version+1 WHERE id=%s", (task["project"],)
                    )
        return digest

    monkeypatch.setattr(controller.reports, "write_report", write)
    assert execute(controller, "printf 'value = 45\\n' > calculator.py", cancel).outcome in {"CANCELLED", "UNKNOWN"}
    assert rows(task) == [("UNKNOWN", None)]
    assert execute(ScopedBashController(*args), "true").outcome == "UNKNOWN"


@pytest.mark.parametrize("entry", [".git", ".env", "symlink", "hardlink", "fifo"])
def test_candidate_import_refuses_worker_git_secrets_and_special_files(build, entry):
    task, args, _cid, _policy = build
    controller = ScopedBashController(*args)
    commands = {
        ".git": "mkdir .git; printf HOST_HOOK > .git/config",
        ".env": "printf PRIVATE_SENTINEL > .env",
        "symlink": "ln -s /etc/passwd link",
        "hardlink": "ln calculator.py hardlink",
        "fifo": "mkfifo pipe",
    }
    assert execute(controller, commands[entry]).outcome == "COMPLETED"
    bare = Path(task["bare"])
    base = git(bare, "rev-parse", "HEAD")
    with pytest.raises(SnapshotRejected):
        capture_candidate(bare, base, controller.workspace)
    assert git(bare, "rev-parse", "HEAD") == base


def complete_review(task, controller):
    bare = Path(task["bare"])
    base = git(bare, "rev-parse", "HEAD")
    registry = required_registry(bare.parent, "value = 43\n", notes=True)
    review = controller.verify_for_review(Path(task["protected"]), bare, base, bare.parent / "frozen", registry)
    assert review.passed and review.approval is not None
    assert git(bare, "rev-parse", "HEAD") == base
    approval = review.approval
    with controller.connect() as connection:
        assert connection.execute("SELECT state FROM panestria.task WHERE id=%s", (task["task"],)).fetchone() == (
            "WAITING_APPROVAL",
        )
        with pytest.raises(KernelDenied, match="digest_mismatch"), connection.transaction():
            ApprovalService().decide(
                UnitOfWork(connection),
                controller.actor,
                approval.approval_id,
                "ff" * 32,
                approval.expected_version,
                "approve",
                str(uuid4()),
            )
    assert git(bare, "rev-parse", "HEAD") == base
    with controller.connect() as connection:
        ApprovalService().decide(
            UnitOfWork(connection),
            controller.actor,
            approval.approval_id,
            approval.effect_digest,
            approval.expected_version,
            "approve",
            str(uuid4()),
        )
    with controller.connect() as connection:
        effect = prepare_merge(UnitOfWork(connection), controller.actor, approval.approval_id)
    evidence = BuildEvidenceService(controller.reports)
    target = VerifiedGitTarget(
        Path(task["protected"]), bare, controller.connect, controller.actor, evidence, registry, controller.certificates
    )
    EffectExecutor(controller.connect, target).dispatch(controller.actor, effect.effect_id)
    with controller.connect() as connection:
        evidence.complete_confirmed(
            UnitOfWork(connection), controller.actor, task["task"], review.evidence_sha256, effect.effect_id
        )
        assert connection.execute("SELECT state FROM panestria.task WHERE id=%s", (task["task"],)).fetchone() == (
            "COMPLETED",
        )
    assert git(bare, "rev-parse", "HEAD") == review.candidate_commit
    assert execute(controller, "printf replay > calculator.py").outcome == "UNKNOWN"
    assert git(bare, "rev-parse", "HEAD") == review.candidate_commit
    return review


def test_real_bash_build_freezes_verifies_and_requires_exact_approval_before_merge(build):
    task, args, _cid, _policy = build
    controller = ScopedBashController(*args)
    result = execute(
        controller,
        "set -eu; printf 'value = 43\\n' > calculator.py; "
        "mkdir notes; printf 'bounded Bash build\\n' > notes/build.txt",
    )
    assert result.outcome == "COMPLETED" and result.exit_code == 0
    complete_review(task, controller)


@pytest.mark.live
def test_actual_claude_subscription_bash_build_and_exact_review(build, record_property):
    import os
    from dataclasses import asdict

    from panestria.brokers.harness.claude_build import ClaudeScopedBashAdapter
    from panestria.brokers.harness.claude_proposal import PINNED_BINARY_SHA256, ClaudeProposalAdapter
    from panestria.brokers.harness.cli_profile import BinaryPin
    from panestria.contracts.native_model import validate_native_model

    task, args, _cid, _policy = build
    controller = ScopedBashController(*args)
    native = ClaudeProposalAdapter(
        BinaryPin(Path("/home/yogesh/.local/share/claude/versions/2.1.273"), PINNED_BINARY_SHA256),
        Path.home() / ".panestria-native-claude",
        Path(__file__).resolve().parents[2] / "docs/specification/attachments/agentos-skills-v0.1.0.zip",
    )
    context = (
        "PUBLIC synthetic fixture. calculator.py contains exactly 'value = 42\\n'. "
        "Change it to exactly 'value = 43\\n'. Also create notes/build.txt with exactly "
        "'bounded Bash build\\n'. Do not create other files. No repository access or package installation is needed."
    )
    model = validate_native_model(os.environ.get("PANESTRIA_QUALIFICATION_NATIVE_MODEL"))
    observation = ClaudeScopedBashAdapter(native, native_model=model).build_public(
        controller.session(), public_context=context
    )
    record_property("native_observation", json.dumps(asdict(observation), sort_keys=True))
    assert observation.process is not None and observation.process.status == "CANDIDATE", asdict(observation)
    assert observation.hostile_configuration_ignored and observation.startup_observed
    if model is not None:
        assert observation.requested_model == model
        assert observation.process.result is not None and observation.process.result.reported_init_model == model
    assert len(rows(task)) == 1 and rows(task)[0][0] == "RETURNED"
    review = complete_review(task, controller)
    record_property(
        "build_review",
        json.dumps(
            {
                "candidate_commit": review.candidate_commit,
                "evidence_sha256": review.evidence_sha256,
                "passed": review.passed,
            }
        ),
    )
    record_property(
        "scope",
        "Actual bounded PUBLIC synthetic subscription conformance; scripted test-owner approval, "
        "not human signoff or a generic cloud project launcher",
    )
    record_property("native_actual_cash", "UNKNOWN_SUBSCRIPTION_ESTIMATE_ONLY_NO_DIRECT_SDK_CALL")
