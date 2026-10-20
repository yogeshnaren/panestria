"""Exact local verification/approval/Git flow; native Claude generation remains a separate live case."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from panestria.contracts.build import BuildCheck, BuildEvidenceBundle, canonical_sha256
from panestria.contracts.goal import GoalContract, contract_sha256, load_contract
from panestria.contracts.plan import PlanTaskScope
from panestria.contracts.policy import PolicyContext
from panestria.kernel.build import BuildEvidenceService, BuildEvidenceStore
from panestria.kernel.goals import Actor
from panestria.kernel.leases import LeaseService
from panestria.kernel.policy import PolicyService
from panestria.kernel.uow import UnitOfWork
from panestria.policy.profiles import CertificateStore
from panestria.verification.build import verifier_bundle_digest
from panestria.verification.git_snapshot import GitSnapshot, materialize
from panestria.verification.registry import CommandRegistry

ROOT = Path(__file__).resolve().parents[2]


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), "-c", "core.hooksPath=/dev/null", *args], text=True).strip()


@dataclass
class BuildFixture:
    task: dict[str, str]
    actor: Actor
    contract: GoalContract
    ids: dict[str, str]
    attempt: str
    source: Path
    bare: Path
    protected: Path
    base: str
    candidate: str
    snapshot: GitSnapshot
    registry: CommandRegistry
    service: BuildEvidenceService
    certificates: CertificateStore
    policy: PolicyContext


@pytest.fixture
def build(r1_task: dict[str, str], tmp_path: Path, request: pytest.FixtureRequest) -> BuildFixture:
    actor = Actor(r1_task["owner"], r1_task["project"])
    certificates = CertificateStore(tmp_path / "certificates", {})
    with psycopg.connect(r1_task["dsn"]) as c:
        policy = PolicyService(certificates).initialize(UnitOfWork(c), actor, r1_task["task"])
    document = json.loads((ROOT / "docs/fixtures/synthetic-goal-contract.json").read_text())
    document.update(
        owner_id=actor.owner_id,
        project_id=actor.project_id,
        goal_id=r1_task["goal"],
        contract_version=2,
        autonomy_profile_ref=f"project-policy:1:{policy.sha256()}",
    )
    allowed = list(getattr(request, "param", ("answer.txt",)))
    document["constraints"]["allowed_paths"] = allowed
    document["acceptance"][1]["verifier"]["allowed_paths"] = allowed
    contract = load_contract(document)
    contract_id = str(uuid4())
    ids = {check.id: str(uuid4()) for check in contract.acceptance}
    with psycopg.connect(r1_task["dsn"]) as c:
        c.execute(
            "INSERT INTO panestria.goal_contract(id,goal_id,version,body,sha256) VALUES (%s,%s,2,%s::jsonb,%s)",
            (contract_id, r1_task["goal"], contract.model_dump_json(), contract_sha256(contract)),
        )
        c.execute("UPDATE panestria.task SET contract_id=%s WHERE id=%s", (contract_id, r1_task["task"]))
        for check in contract.acceptance:
            c.execute(
                "INSERT INTO panestria.acceptance_check(id,contract_id,check_key,description,required,"
                "verifier_type,verifier_spec) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)",
                (
                    ids[check.id],
                    contract_id,
                    check.id,
                    check.description,
                    check.required,
                    check.verifier.type,
                    check.verifier.model_dump_json(),
                ),
            )
        lease = LeaseService().acquire(
            UnitOfWork(c), actor, r1_task["task"], "synthetic-controller-fixture", 0, ttl_seconds=120
        )
    task = {**r1_task, "contract": contract_id}
    source = tmp_path / "source"
    source.mkdir()
    _git(source, "init", "-b", "main")
    _git(source, "config", "user.name", "Synthetic fixture")
    _git(source, "config", "user.email", "synthetic@panestria.invalid")
    (source / "answer.txt").write_text("base")
    _git(source, "add", "answer.txt")
    _git(source, "commit", "-m", "synthetic base")
    base = _git(source, "rev-parse", "HEAD")
    (source / "answer.txt").write_text("verified")
    _git(source, "commit", "-am", "synthetic candidate")
    candidate = _git(source, "rev-parse", "HEAD")
    protected = tmp_path / "protected"
    protected.mkdir(mode=0o700)
    repository_scope = protected / actor.owner_id / actor.project_id
    repository_scope.mkdir(parents=True, mode=0o700)
    bare = repository_scope / "destination.git"
    subprocess.run(["git", "clone", "--bare", str(source), str(bare)], check=True, capture_output=True)
    subprocess.run(["git", "--git-dir", str(bare), "update-ref", "refs/heads/main", base], check=True)
    snapshot = materialize(bare, base, candidate, tmp_path / "snapshots" / "one")
    bundle_dir = protected / "check-bundle"
    bundle_dir.mkdir(mode=0o700)
    (bundle_dir / "required_check.py").write_text(
        "import os\nfrom pathlib import Path\n"
        "assert Path(os.environ['PANESTRIA_CANDIDATE'],'answer.txt').read_text()=='verified'\n"
    )
    registry = CommandRegistry.load(bundle_dir, "/synthetic/reviewed-python")
    service = BuildEvidenceService(BuildEvidenceStore(tmp_path / "evidence"))
    return BuildFixture(
        task,
        actor,
        contract,
        ids,
        lease.attempt_id,
        source,
        bare,
        protected,
        base,
        candidate,
        snapshot,
        registry,
        service,
        certificates,
        policy,
    )


def _bundle(
    build: BuildFixture, *, verdict: str = "PASS", plan_scope: PlanTaskScope | None = None
) -> BuildEvidenceBundle:
    # Protected-controller report fixtures exercise DB guards/CAS; they are not
    # claimed as native-worker or OS-verifier evidence. The OS case uses verify_build.
    checks = []
    bundle_digest = verifier_bundle_digest(build.contract, build.registry)
    for check in sorted(build.contract.acceptance, key=lambda c: c.id):
        if plan_scope is not None and check.id not in plan_scope.node.acceptance_keys:
            continue
        spec_digest = canonical_sha256(check.verifier.model_dump(mode="json"))
        report = json.dumps(
            {
                "schema_version": 1,
                "check_key": check.id,
                "verdict": verdict,
                "candidate_commit": build.candidate,
                "candidate_tree": build.snapshot.tree,
                "base_commit": build.base,
                "snapshot_sha256": build.snapshot.manifest_sha256,
                "attempt_id": build.attempt,
                "lease_epoch": 1,
                "contract_sha256": contract_sha256(build.contract),
                "spec_sha256": spec_digest,
                "verifier_bundle_sha256": bundle_digest,
                **({"plan_scope_sha256": plan_scope.sha256()} if plan_scope else {}),
            },
            sort_keys=True,
        ).encode()
        digest = build.service.store.write_report(report)
        checks.append(
            BuildCheck(
                check_id=build.ids[check.id],
                check_key=check.id,
                required=check.required,
                spec_sha256=spec_digest,
                verdict=verdict,
                report_sha256=digest,
            )
        )
    return BuildEvidenceBundle(
        owner_id=build.actor.owner_id,
        project_id=build.actor.project_id,
        task_id=build.task["task"],
        attempt_id=build.attempt,
        lease_epoch=1,
        contract_id=build.task["contract"],
        contract_sha256=contract_sha256(build.contract),
        contract_version=2,
        policy_ref=build.contract.autonomy_profile_ref,
        base_commit=build.base,
        candidate_commit=build.candidate,
        candidate_tree=build.snapshot.tree,
        snapshot_sha256=build.snapshot.manifest_sha256,
        verifier_bundle_sha256=bundle_digest,
        checks=tuple(checks),
    )


def _publish(build: BuildFixture, bundle: BuildEvidenceBundle | None = None) -> str:
    bundle = bundle or _bundle(build)
    with psycopg.connect(build.task["dsn"]) as c:
        return build.service.publish(UnitOfWork(c), build.actor, bundle)
