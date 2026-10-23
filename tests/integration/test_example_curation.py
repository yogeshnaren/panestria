"""Real isolated PG/CLI/files and synthetic owner evidence; no provider or trainer."""

import hashlib
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest
from test_aos_002_migration import _schema_fingerprint
from test_ask_kernel import initialize
from typer.testing import CliRunner

from panestria.cli.main import app
from panestria.contracts.curation import CuratedExample
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.repositories.policy import current_policy, insert_revision
from panestria.kernel.uow import UnitOfWork
from panestria.learning.curation import ExampleCuration


def private(path, body):
    path.write_text(json.dumps(body))
    path.chmod(0o600)
    return path


@pytest.fixture
def curation(r1_migration_task, tmp_path, monkeypatch):
    task = r1_migration_task  # Every case owns its DB; cannot contaminate legacy downgrade/restore audits.
    actor, _ = initialize(task, tmp_path / "certificates")
    with psycopg.connect(task["dsn"]) as c:
        uow = UnitOfWork(c)
        old = current_policy(uow, actor)
        actions = dict(old.autonomy.actions) | {"edit": "act-and-report"}
        # Explicit synthetic permission fixture, not a live policy/certificate qualification.
        insert_revision(
            uow,
            old.model_copy(
                update={"version": 2, "autonomy": old.autonomy.model_copy(update={"version": 2, "actions": actions})}
            ),
        )
    monkeypatch.setenv("PANESTRIA_DATABASE_URL", task["dsn"])
    config = private(
        tmp_path / "curation.json", {"schema_version": 1, "owner_id": actor.owner_id, "project_id": actor.project_id}
    )
    return SimpleNamespace(
        actor=actor, service=ExampleCuration(actor, task["dsn"]), config=config, directory=tmp_path, dsn=task["dsn"]
    )


def files(
    f, *, origin="OWNER_AUTHORED", question="How many sides does a triangle have?", answer="Three.", decision="ALLOWED"
):
    example = CuratedExample(schema_version=1, privacy_class="PUBLIC", origin=origin, input=question, response=answer)
    candidate = private(f.directory / f"candidate-{uuid4().hex}.json", example.model_dump(mode="json"))
    evidence = tuple(
        private(
            f.directory / f"proof-{uuid4().hex}.json",
            {
                "schema_version": 1,
                "role": role,
                "privacy_class": "PUBLIC",
                "subject_sha256": example.sha256(),
                "assessment": decision,
                "basis": "SYNTHETIC OWNER EVIDENCE: "
                + {
                    "ORIGIN": "Original owner fixture, no model/provider inputs or provider agreement.",
                    "DATA_RIGHTS": "Owner controls this synthetic original and permits this local preparation purpose.",
                    "VALIDATION": "Owner checked the triangle definition; not a model benchmark.",
                }[role],
                "valid_until": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
                "assessment_source": "OWNER_ATTESTED",
                "provider_basis": "NO_PROVIDER_OR_MODEL_INPUTS" if role == "ORIGIN" else None,
                "permitted_purpose": "LOCAL_TRAINING_DATA_PREPARATION" if role == "DATA_RIGHTS" else None,
                "validation_method": "OWNER_REVIEWED" if role == "VALIDATION" else None,
            },
        )
        for role in ("ORIGIN", "DATA_RIGHTS", "VALIDATION")
    )
    return candidate, evidence


def cli(f, *args, expected=0):
    result = CliRunner().invoke(app, ["examples", *args, "--config", str(f.config)])
    assert result.exit_code == expected, result.output
    return json.loads(result.stdout if expected == 0 else result.output)


def accepted(f, candidate, proofs, days=7):
    review = f.service.prepare(candidate, proofs, days)
    f.service.record(
        candidate,
        proofs,
        review["review_sha256"],
        days=days,
        confirm_owner_review=True,
        accept_training_data_purpose=True,
    )
    return review["review_sha256"]


def test_exact_separate_consent_concurrent_replay_and_offline_export_restore_cli(curation):
    f = curation
    candidate, proofs = files(f)
    assert f.service.prepare(candidate, ())["preview"]["proposed_eligibility"] == "UNKNOWN"
    args = [str(candidate)]
    for path in proofs:
        args += ["--evidence", str(path)]
    review = cli(f, "prepare", *args)
    digest = review["review_sha256"]
    assert review["preview"]["training_export"] == "DENIED_UNTIL_SEPARATE_OWNER_CONFIRMATION"
    origin = json.loads(proofs[0].read_bytes())
    missing_basis = origin.copy()
    missing_basis.pop("provider_basis")
    private(proofs[0], missing_basis)
    assert f.service.prepare(candidate, proofs)["preview"]["proposed_eligibility"] == "UNKNOWN"
    private(proofs[0], origin)
    rights = json.loads(proofs[1].read_bytes())
    unclassified = rights.copy()
    unclassified.pop("privacy_class")
    private(proofs[1], unclassified)
    cli(f, "prepare", *args, expected=1)
    private(proofs[1], rights)
    cli(f, "record", str(candidate), digest, expected=1)
    record_args = [str(candidate), digest, *args[1:], "--confirm-owner-review"]
    cli(f, "record", *record_args, expected=1)  # Ordinary owner review is not training-purpose consent.
    with pytest.raises(KernelDenied, match="exact_review"):
        f.service.record(candidate, proofs, "ff" * 32, confirm_owner_review=True, accept_training_data_purpose=True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: f.service.record(
                    candidate, proofs, digest, confirm_owner_review=True, accept_training_data_purpose=True
                ),
                range(2),
            )
        )
    assert sorted(r["replayed"] for r in results) == [False, True]
    assert all(r["current"] and r["eligibility"] == "ALLOWED" for r in results)
    with f.service.connect() as c:
        saved = c.execute("SELECT expires_at,seq FROM panestria.curated_example_review").fetchall()
        assert len(saved) == 1
    cli(f, "record", *record_args, "--accept-training-data-purpose")
    with f.service.connect() as c:
        assert c.execute("SELECT expires_at,seq FROM panestria.curated_example_review").fetchall() == saved
    output = f.directory / "examples.json"
    assert cli(f, "export", "--review", digest, str(output))["examples"] == 1
    original = output.read_bytes()
    assert output.stat().st_mode & 0o777 == 0o600
    copy = f.directory / "restored.json"
    copy.write_bytes(original)
    copy.chmod(0o600)
    assert cli(f, "validate-export", str(copy))["status"] == "CURRENT_ELIGIBILITY_CONFIRMED"
    assert json.loads(original)["entries"][0]["example"]["response"] == "Three."
    cli(f, "export", "--review", digest, str(output), expected=1)
    assert output.read_bytes() == original
    tampered = json.loads(original)
    e = tampered["entries"][0]
    e["fold"] = "development" if e["fold"] == "holdout" else "holdout"
    private(copy, tampered)
    cli(f, "validate-export", str(copy), expected=1)
    with pytest.raises(KernelDenied, match="not_found"):
        ExampleCuration(Actor(f.actor.owner_id, str(uuid4())), f.dsn).withdraw(digest, confirm=True)
    # Isolate withdrawal itself while policy and the positive review still permit use.
    assert f.service.validate_export(output)["status"] == "CURRENT_ELIGIBILITY_CONFIRMED"
    f.service.withdraw(digest, confirm=True)
    with pytest.raises(KernelDenied, match="current_eligibility"):
        f.service.validate_export(output)
    assert output.read_bytes() == original


def test_new_denial_old_replay_and_canonical_withdrawal_cannot_be_overridden_by_copied_packet(curation):
    f = curation
    candidate, proofs = files(f)
    old = accepted(f, candidate, proofs)
    output = f.directory / "allowed.json"
    f.service.export((old,), output)
    original = output.read_bytes()
    proof = json.loads(proofs[1].read_bytes())
    proof["assessment"] = "DENIED"
    private(proofs[1], proof)
    denied = f.service.prepare(candidate, proofs)
    f.service.record(candidate, proofs, denied["review_sha256"], confirm_owner_review=True)
    with pytest.raises(KernelDenied, match="current_eligibility"):
        f.service.validate_export(output)
    proof["assessment"] = "ALLOWED"
    private(proofs[1], proof)
    replay = f.service.record(candidate, proofs, old, confirm_owner_review=True, accept_training_data_purpose=True)
    assert replay["replayed"] is True and replay["current"] is False
    with f.service.connect() as c:
        with pytest.raises(psycopg.Error, match="immutable"), c.transaction():
            c.execute("UPDATE panestria.curated_example_review SET eligibility='ALLOWED'")
        policy = current_policy(UnitOfWork(c), f.actor)
        insert_revision(
            UnitOfWork(c),
            policy.model_copy(
                update={
                    "version": policy.version + 1,
                    "autonomy": policy.autonomy.model_copy(
                        update={
                            "version": policy.autonomy.version + 1,
                            "actions": dict(policy.autonomy.actions) | {"edit": "observe"},
                        }
                    ),
                }
            ),
        )
    # Withdrawal remains possible after read/edit policy revocation, using an original scoped review.
    assert cli(f, "withdraw", old, "--confirm-withdrawal")["history_deleted"] is False
    assert output.read_bytes() == original
    with pytest.raises(KernelDenied):
        f.service.validate_export(output)
    with f.service.connect() as c:
        assert c.execute("SELECT count(*) FROM panestria.curated_example_withdrawal").fetchone() == (1,)
        assert c.execute("SELECT count(*) FROM panestria.curated_example_review").fetchone() == (2,)


def test_known_model_lineage_duplicate_inputs_and_expiry_stay_ineligible(curation, monkeypatch):
    f = curation
    unknown, unknown_proofs = files(f, origin="UNKNOWN", question="Original synthetic example?")
    pending = f.service.prepare(unknown, unknown_proofs)
    assert pending["preview"]["proposed_eligibility"] == "UNKNOWN"
    f.service.record(unknown, unknown_proofs, pending["review_sha256"], confirm_owner_review=True)
    corrected, corrected_proofs = files(f, question="Original synthetic example?")
    assert f.service.prepare(corrected, corrected_proofs)["preview"]["proposed_eligibility"] == "ALLOWED"
    candidate, proofs = files(f, origin="PROVIDER_OUTPUT")
    review = f.service.prepare(candidate, proofs)
    assert review["preview"]["proposed_eligibility"] == "DENIED"
    f.service.record(candidate, proofs, review["review_sha256"], confirm_owner_review=True)
    own, own_proofs = files(f)  # Same content relabeled as owner original cannot erase known provenance.
    assert f.service.prepare(own, own_proofs)["preview"]["proposed_eligibility"] == "DENIED"
    a, ap = files(f, question="Synthetic count?", answer="One.")
    b, bp = files(f, question="Synthetic count?", answer="Two.")
    first, second = accepted(f, a, ap, days=1), accepted(f, b, bp)
    with pytest.raises(KernelDenied, match="duplicate_or_conflicting_input"):
        f.service.export((first, second), f.directory / "conflict.json")
    f.service.export((first,), f.directory / "current.json")
    real_now = f.service._now
    # Consent expired, but the original two-day evidence period remains valid.
    monkeypatch.setattr(f.service, "_now", lambda c: real_now(c) + timedelta(hours=36))
    replay = f.service.record(a, ap, first, days=1, confirm_owner_review=True, accept_training_data_purpose=True)
    assert replay["replayed"] is True and replay["current"] is False
    with pytest.raises(KernelDenied, match="current_eligibility"):
        f.service.validate_export(f.directory / "current.json")
    assert not (f.directory / "conflict.json").exists()


def test_new_schema_empty_roundtrip_fingerprint_and_audit_prevents_downgrade(curation, record_property):
    f = curation
    root = Path(__file__).resolve().parents[2]

    def migration(target):
        return subprocess.run(
            [
                "uv",
                "run",
                "--frozen",
                "alembic",
                "-c",
                "migrations/alembic.ini",
                "upgrade" if target == "head" else "downgrade",
                target,
            ],
            cwd=root,
            env={**os.environ, "PANESTRIA_DATABASE_URL": f.dsn},
            capture_output=True,
            timeout=60,
        )

    with f.service.connect() as c:
        before = _schema_fingerprint(c)
    assert migration("0038_fetch_connection_grants").returncode == 0
    assert migration("head").returncode == 0
    with f.service.connect() as c:
        assert _schema_fingerprint(c) == before
    path = os.environ.get("PANESTRIA_TEST_SCHEMA_OUTPUT")
    if path:
        with Path(path).open("x") as stream:
            stream.write(before)  # Explicit scoped output; no overwrite or authority claim.
        record_property("observed_schema_sha256", hashlib.sha256(before.encode()).hexdigest())
    candidate, proofs = files(f)
    accepted(f, candidate, proofs)
    assert migration("0038_fetch_connection_grants").returncode != 0
    with f.service.connect() as c:
        assert _schema_fingerprint(c) == before
        assert c.execute("SELECT count(*) FROM panestria.curated_example_review").fetchone() == (1,)
