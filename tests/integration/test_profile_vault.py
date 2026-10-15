"""Real crypto/PG failure matrix; synthetic test keys are not runtime config."""

from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from uuid import uuid4

import psycopg
import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from psycopg.errors import CheckViolation, ForeignKeyViolation, UniqueViolation
from pydantic import SecretBytes, SecretStr, ValidationError

from panestria.contracts.profile import ProfileDocument
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.uow import UnitOfWork
from panestria.memory import vault as vault_module
from panestria.memory.keys import KeyStoreUnavailable, ProfileKeyHandle
from panestria.memory.vault import ProfileVault

SENTINEL = "SYNTHETIC_PRIVATE_PROFILE_SENTINEL_世界"


class TestKeys:
    __test__ = False

    def __init__(self):
        self.values = {}
        self.loads = []

    def provision(self, handle):
        self.values[handle.model_dump_json()] = SecretBytes(AESGCM.generate_key(bit_length=256))

    def load(self, handle):
        self.loads.append(handle)
        try:
            return self.values[handle.model_dump_json()]
        except KeyError:
            raise KeyStoreUnavailable("key_handle_missing") from None


@pytest.fixture
def profile(r1_task):
    actor = Actor(r1_task["owner"], r1_task["project"])
    handle = ProfileKeyHandle(
        owner_id=actor.owner_id, project_id=actor.project_id, profile_id=str(uuid4()), key_id=str(uuid4())
    )
    keys = TestKeys()
    keys.provision(handle)
    return r1_task["dsn"], actor, handle, keys, ProfileVault(keys, enabled=True)


def document(**updates):
    return ProfileDocument(fields={"background": SecretStr(SENTINEL)}, **updates)


def create(profile):
    dsn, actor, handle, keys, vault = profile
    with psycopg.connect(dsn) as c:
        return vault.create(UnitOfWork(c), actor, handle, document(), consent_ref=str(uuid4()))


def test_default_feature_is_off_before_db_or_key_access(profile):
    dsn, actor, handle, keys, _ = profile
    vault = ProfileVault(keys)
    for operation in (
        lambda: vault.create(None, actor, handle, document(), consent_ref=str(uuid4())),
        lambda: vault.read(None, actor, handle.profile_id),
        lambda: vault.revise(None, actor, handle, 0, document(), consent_ref=str(uuid4())),
        lambda: vault.suppress(None, actor, handle.profile_id, 0),
    ):
        with pytest.raises(KernelDenied, match="^profile_disabled$"):
            operation()
    assert keys.loads == []


def test_ciphertext_only_and_masked_results(profile, caplog):
    dsn, actor, handle, keys, vault = profile
    original = create(profile)
    with psycopg.connect(dsn) as c:
        ref, decoded = vault.read(UnitOfWork(c), actor, original.profile_id)
        assert ref == original and decoded.fields["background"].get_secret_value() == SENTINEL
        for table in ("profile", "profile_revision", "profile_event", "memory_source", "context_pack"):
            rows = c.execute(f"SELECT row_to_json(t)::text FROM panestria.{table} t").fetchall()
            assert all(SENTINEL not in row[0] for row in rows)
        stored = c.execute(
            "SELECT nonce,ciphertext,ciphertext_sha256 FROM panestria.profile_revision WHERE id=%s", (ref.revision_id,)
        ).fetchone()
        assert SENTINEL.encode() not in stored[1] and len(stored[0]) == 12
        assert hashlib.sha256(stored[1]).hexdigest() == stored[2]
        assert hashlib.sha256(SENTINEL.encode()).hexdigest() not in repr(stored)
    assert SENTINEL not in repr(decoded) + decoded.model_dump_json() + repr(ref) + caplog.text


@pytest.mark.parametrize("field", ["owner_id", "project_id"])
def test_scope_denies_before_key_access(profile, field):
    dsn, actor, handle, keys, vault = profile
    create(profile)
    actor = Actor(
        str(uuid4()) if field == "owner_id" else actor.owner_id,
        str(uuid4()) if field == "project_id" else actor.project_id,
    )
    keys.loads.clear()
    with psycopg.connect(dsn) as c:
        uow = UnitOfWork(c)
        for operation in (
            lambda: vault.read(uow, actor, handle.profile_id),
            lambda: vault.create(uow, actor, handle, document(), consent_ref=str(uuid4())),
            lambda: vault.revise(uow, actor, handle, 0, document(), consent_ref=str(uuid4())),
            lambda: vault.suppress(uow, actor, handle.profile_id, 0),
        ):
            with pytest.raises(KernelDenied, match="^not_found$"):
                operation()
    assert keys.loads == []


@pytest.mark.parametrize("fault", ["ciphertext", "nonce", "revision_id", "consent_ref", "key_id"])
def test_tampered_restore_denies_with_fixed_error(profile, fault):
    dsn, actor, handle, keys, vault = profile
    ref = create(profile)
    with psycopg.connect(dsn) as c:
        # Corrupt only this synthetic row inside a rolled-back transaction, as
        # though an untrusted backup had supplied a validly shaped envelope.
        c.execute("ALTER TABLE panestria.profile_revision DISABLE TRIGGER immutable_profile_revision")
        if fault == "ciphertext":
            cipher = c.execute(
                "SELECT ciphertext FROM panestria.profile_revision WHERE id=%s", (ref.revision_id,)
            ).fetchone()[0]
            altered = bytes([cipher[0] ^ 1]) + cipher[1:]
            c.execute(
                "UPDATE panestria.profile_revision SET ciphertext=%s,ciphertext_sha256=%s WHERE id=%s",
                (altered, hashlib.sha256(altered).hexdigest(), ref.revision_id),
            )
        elif fault == "nonce":
            c.execute("UPDATE panestria.profile_revision SET nonce=%s WHERE id=%s", (b"x" * 12, ref.revision_id))
        elif fault == "key_id":
            other = handle.model_copy(update={"key_id": str(uuid4())})
            keys.values[other.model_dump_json()] = keys.values[handle.model_dump_json()]
            c.execute("UPDATE panestria.profile_revision SET key_id=%s WHERE id=%s", (other.key_id, ref.revision_id))
        else:
            column = "id" if fault == "revision_id" else "consent_ref"
            c.execute(f"UPDATE panestria.profile_revision SET {column}=%s WHERE id=%s", (str(uuid4()), ref.revision_id))
        with pytest.raises(KernelDenied, match="^profile_integrity_failed$") as caught:
            vault.read(UnitOfWork(c), actor, handle.profile_id)
        assert SENTINEL not in str(caught.value)
        c.rollback()


def test_cross_profile_ciphertext_swap_fails_even_with_reused_key(profile):
    dsn, actor, handle, keys, vault = profile
    first = create(profile)
    other = handle.model_copy(update={"profile_id": str(uuid4()), "key_id": str(uuid4())})
    keys.values[other.model_dump_json()] = keys.values[handle.model_dump_json()]
    with psycopg.connect(dsn) as c:
        second = vault.create(UnitOfWork(c), actor, other, document(), consent_ref=str(uuid4()))
    with psycopg.connect(dsn) as c:
        c.execute("ALTER TABLE panestria.profile_revision DISABLE TRIGGER immutable_profile_revision")
        c.execute(
            "UPDATE panestria.profile_revision SET (nonce,ciphertext,ciphertext_sha256)="
            " (SELECT nonce,ciphertext,ciphertext_sha256 FROM panestria.profile_revision WHERE id=%s) WHERE id=%s",
            (first.revision_id, second.revision_id),
        )
        with pytest.raises(KernelDenied, match="^profile_integrity_failed$"):
            vault.read(UnitOfWork(c), actor, other.profile_id)
        c.rollback()


def test_revision_rotation_suppression_and_missing_keys(profile):
    dsn, actor, handle, keys, vault = profile
    first = create(profile)
    rotated = handle.model_copy(update={"key_id": str(uuid4())})
    keys.provision(rotated)
    with psycopg.connect(dsn) as c:
        uow = UnitOfWork(c)
        changed = vault.revise(uow, actor, rotated, 0, document(), consent_ref=str(uuid4()))
        assert (changed.revision, changed.row_version, changed.key_id) == (2, 1, rotated.key_id)
        assert vault.read(uow, actor, handle.profile_id)[0] == changed
        assert len(keys.values) == 2
        keys.values.pop(rotated.model_dump_json())
        with pytest.raises(KernelDenied, match="^key_handle_missing$"):
            vault.read(uow, actor, handle.profile_id)
        assert vault.suppress(uow, actor, handle.profile_id, 1) == 2
        assert vault.suppress(uow, actor, handle.profile_id, 2) == 2
        with pytest.raises(KernelDenied, match="^profile_suppressed$"):
            vault.read(uow, actor, handle.profile_id)
        with pytest.raises(KernelDenied, match="^version_conflict$"):
            vault.revise(uow, actor, rotated, 1, document(), consent_ref=str(uuid4()))
        events = c.execute(
            "SELECT kind,row_version,current_revision FROM panestria.profile_event"
            " WHERE profile_id=%s ORDER BY row_version",
            (first.profile_id,),
        ).fetchall()
        assert events == [("CREATED", 0, 1), ("REVISED", 1, 2), ("SUPPRESSED", 2, 2)]
        assert c.execute(
            "SELECT count(*) FROM panestria.profile_revision WHERE profile_id=%s", (first.profile_id,)
        ).fetchone() == (2,)


def test_expiry_denies_new_reads(profile):
    dsn, actor, handle, keys, vault = profile
    with psycopg.connect(dsn) as c:
        ref = vault.create(
            UnitOfWork(c),
            actor,
            handle,
            document(valid_until=datetime.now(timezone.utc) - timedelta(seconds=1)),
            consent_ref=str(uuid4()),
        )
        with pytest.raises(KernelDenied, match="^profile_expired$"):
            vault.read(UnitOfWork(c), actor, ref.profile_id)


def test_missing_keys_never_create_rows_or_reprovision(profile):
    dsn, actor, handle, keys, vault = profile
    keys.values.clear()
    with psycopg.connect(dsn) as c:
        with pytest.raises(KernelDenied, match="^key_handle_missing$"):
            vault.create(UnitOfWork(c), actor, handle, document(), consent_ref=str(uuid4()))
        assert c.execute("SELECT count(*) FROM panestria.profile WHERE id=%s", (handle.profile_id,)).fetchone() == (0,)
    assert keys.values == {} and len(keys.loads) == 1


def test_database_rollback_preserves_keys_but_no_partial_profile(profile, monkeypatch):
    dsn, actor, handle, keys, vault = profile
    original = vault._store

    def interrupted(uow, envelope):
        original(uow, envelope)
        raise KernelDenied("synthetic_interruption")

    monkeypatch.setattr(vault, "_store", interrupted)
    with pytest.raises(KernelDenied, match="synthetic_interruption"), psycopg.connect(dsn) as c:
        vault.create(UnitOfWork(c), actor, handle, document(), consent_ref=str(uuid4()))
    with psycopg.connect(dsn) as c:
        for table, column in (("profile", "id"), ("profile_revision", "profile_id"), ("profile_event", "profile_id")):
            assert c.execute(
                f"SELECT count(*) FROM panestria.{table} WHERE {column}=%s", (handle.profile_id,)
            ).fetchone() == (0,)
    assert len(keys.values) == 1


def test_nonce_reuse_and_immutable_revisions_are_rejected(profile, monkeypatch):
    dsn, actor, handle, keys, vault = profile
    monkeypatch.setattr(vault_module.os, "urandom", lambda size: b"x" * size)
    ref = create(profile)
    with psycopg.connect(dsn) as c:
        with pytest.raises(UniqueViolation), c.transaction():
            vault.revise(UnitOfWork(c), actor, handle, 0, document(), consent_ref=str(uuid4()))
        for table in ("profile_revision", "profile_event"):
            with pytest.raises(psycopg.Error, match="immutable"), c.transaction():
                c.execute(f"DELETE FROM panestria.{table} WHERE profile_id=%s", (ref.profile_id,))
        assert vault.read(UnitOfWork(c), actor, ref.profile_id)[0] == ref


def test_concurrent_corrections_have_one_winner(profile):
    dsn, actor, handle, keys, vault = profile
    create(profile)
    start = Barrier(2)

    def correction(index):
        try:
            with psycopg.connect(dsn) as c:
                start.wait(timeout=5)
                vault.revise(UnitOfWork(c), actor, handle, 0, document(), consent_ref=str(uuid4()))
                return "COMMITTED"
        except KernelDenied as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(correction, range(2))) == ["COMMITTED", "version_conflict"]
    with psycopg.connect(dsn) as c:
        assert c.execute(
            "SELECT count(*) FROM panestria.profile_event WHERE profile_id=%s", (handle.profile_id,)
        ).fetchone() == (2,)


@pytest.mark.parametrize(
    "mutation",
    [
        {"approved_for_local_context": ("goals",)},
        {"fields": {"background": SecretStr("x" * 8193)}},
        {"fields": {"arbitrary_claim": SecretStr(SENTINEL)}},
    ],
)
def test_document_bounds_and_approval_are_explicit(mutation):
    with pytest.raises(ValidationError):
        ProfileDocument(**{"fields": {"background": SecretStr(SENTINEL)}, **mutation})


def test_database_enforces_scope_and_no_dangling_pointer(profile):
    dsn, actor, handle, keys, vault = profile
    create(profile)
    with psycopg.connect(dsn) as c:
        with pytest.raises(CheckViolation), c.transaction():
            c.execute("ALTER TABLE panestria.profile_revision DISABLE TRIGGER immutable_profile_revision")
            c.execute(
                "UPDATE panestria.profile_revision SET privacy_label='PUBLIC' WHERE profile_id=%s", (handle.profile_id,)
            )
        with pytest.raises(ForeignKeyViolation), c.transaction():
            c.execute(
                "INSERT INTO panestria.profile(id,owner_id,project_id) VALUES(%s,%s,%s)",
                (str(uuid4()), actor.owner_id, str(uuid4())),
            )
        with pytest.raises(ForeignKeyViolation), c.transaction():
            c.execute(
                "INSERT INTO panestria.profile(id,owner_id,project_id) VALUES(%s,%s,%s)",
                (str(uuid4()), actor.owner_id, actor.project_id),
            )
            c.execute("SET CONSTRAINTS ALL IMMEDIATE")


@pytest.mark.parametrize("version", [True, 1.0, "1", 2])
def test_profile_schema_version_is_exact(version):
    import json

    with pytest.raises(ValidationError):
        ProfileDocument.model_validate_json(json.dumps({"schema_version": version, "fields": {"background": SENTINEL}}))


@pytest.mark.parametrize("change_owner", [True, False])
def test_scope_metadata_in_corrupt_backup_is_authenticated(profile, change_owner):
    dsn, actor, handle, keys, vault = profile
    create(profile)
    new_owner = str(uuid4()) if change_owner else actor.owner_id
    new_project = str(uuid4())
    new_handle = handle.model_copy(update={"owner_id": new_owner, "project_id": new_project})
    keys.values[new_handle.model_dump_json()] = keys.values[handle.model_dump_json()]
    with psycopg.connect(dsn) as c:
        if change_owner:
            c.execute(
                "INSERT INTO panestria.principal(id,display_name) VALUES(%s,'synthetic backup owner')", (new_owner,)
            )
        c.execute("INSERT INTO panestria.project(id,owner_id) VALUES(%s,%s)", (new_project, new_owner))
        c.execute("ALTER TABLE panestria.profile DISABLE TRIGGER profile_lifecycle")
        c.execute("ALTER TABLE panestria.profile_revision DISABLE TRIGGER immutable_profile_revision")
        # Exercise crypto independently of the normally immediate scope FK.
        # This DDL and all corrupt rows are rolled back below.
        c.execute(
            "ALTER TABLE panestria.profile_revision ALTER CONSTRAINT"
            " profile_revision_profile_id_owner_id_project_id_fkey DEFERRABLE INITIALLY DEFERRED"
        )
        c.execute(
            "UPDATE panestria.profile SET owner_id=%s,project_id=%s WHERE id=%s",
            (new_owner, new_project, handle.profile_id),
        )
        c.execute(
            "UPDATE panestria.profile_revision SET owner_id=%s,project_id=%s,consented_by=%s WHERE profile_id=%s",
            (new_owner, new_project, new_owner, handle.profile_id),
        )
        with pytest.raises(KernelDenied, match="^profile_integrity_failed$"):
            vault.read(UnitOfWork(c), Actor(new_owner, new_project), handle.profile_id)
        c.rollback()
