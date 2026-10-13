"""Browser session scope, single-use pairing and revocation on PostgreSQL."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import psycopg
import pytest

from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.sessions import SessionService
from panestria.kernel.uow import UnitOfWork


def test_pairing_and_secret_redaction(r1_task: dict[str, str], record_property: pytest.RecordProperty) -> None:
    record_property("gate_case_id", "AOS-009-TC02")
    record_property("source_clauses", "AOS-009-F01,AOS-009-F03")
    service, actor = SessionService(b"test-only-key-not-a-real-secret!!"), Actor(r1_task["owner"], r1_task["project"])
    with psycopg.connect(r1_task["dsn"]) as c:
        old = service.issue_pairing_code(UnitOfWork(c), actor)
        c.commit()
        code = service.issue_pairing_code(UnitOfWork(c), actor)
        c.commit()
        with pytest.raises(KernelDenied, match="invalid_pairing_code"), c.transaction():
            service.pair(UnitOfWork(c), actor, old)
        with pytest.raises(KernelDenied, match="invalid_pairing_code"), c.transaction():
            service.pair(UnitOfWork(c), Actor(str(uuid4()), actor.project_id), code)

    def pair() -> object:
        try:
            with psycopg.connect(r1_task["dsn"]) as c:
                return service.pair(UnitOfWork(c), actor, code)
        except KernelDenied as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: pair(), range(2)))
    assert results.count("invalid_pairing_code") == 1
    tokens = next(value for value in results if value != "invalid_pairing_code")
    assert tokens.token not in repr(tokens) and tokens.csrf not in repr(tokens)
    with psycopg.connect(r1_task["dsn"]) as c:
        assert service.authenticate(UnitOfWork(c), actor, tokens.token) == tokens.session_id
        for supplied in [None, "bad", ""]:
            with pytest.raises(KernelDenied, match="csrf_denied"), c.transaction():
                service.authenticate(UnitOfWork(c), actor, tokens.token, csrf=supplied, mutation=True)
        service.authenticate(UnitOfWork(c), actor, tokens.token, csrf=tokens.csrf, mutation=True)
        c.commit()
        persisted = str(
            c.execute(
                "SELECT token_hash,csrf_hash FROM panestria.browser_session WHERE id=%s", (tokens.session_id,)
            ).fetchall()
        )
        persisted += str(
            c.execute(
                "SELECT code_hash FROM panestria.pairing_challenge WHERE project_id=%s", (actor.project_id,)
            ).fetchall()
        )
        assert all(secret not in persisted for secret in [code, old, tokens.token, tokens.csrf])
        service.revoke(UnitOfWork(c), actor, tokens.token, tokens.csrf)
        c.commit()
        with pytest.raises(KernelDenied, match="unauthorized"), c.transaction():
            service.authenticate(UnitOfWork(c), actor, tokens.token)
        with pytest.raises(KernelDenied, match="unauthorized"), c.transaction():
            service.authenticate(UnitOfWork(c), actor, tokens.token, csrf=tokens.csrf, mutation=True)


def test_session_expiry_and_other_project(r1_task: dict[str, str]) -> None:
    service, actor = SessionService(b"test-only-key-not-a-real-secret!!"), Actor(r1_task["owner"], r1_task["project"])
    with psycopg.connect(r1_task["dsn"]) as c:
        code = service.issue_pairing_code(UnitOfWork(c), actor)
        c.commit()
        tokens = service.pair(UnitOfWork(c), actor, code)
        c.commit()
        with pytest.raises(KernelDenied, match="unauthorized"), c.transaction():
            service.authenticate(UnitOfWork(c), Actor(actor.owner_id, str(uuid4())), tokens.token)
        c.execute(
            "UPDATE panestria.browser_session SET expires_at=clock_timestamp()-interval '1 second' WHERE id=%s",
            (tokens.session_id,),
        )
        c.commit()
        with pytest.raises(KernelDenied, match="unauthorized"), c.transaction():
            service.authenticate(UnitOfWork(c), actor, tokens.token)
        code = service.issue_pairing_code(UnitOfWork(c), actor)
        c.commit()
        c.execute(
            "UPDATE panestria.pairing_challenge SET expires_at=clock_timestamp()-interval '1 second'"
            " WHERE owner_id=%s AND project_id=%s",
            (actor.owner_id, actor.project_id),
        )
        c.commit()
        with pytest.raises(KernelDenied, match="invalid_pairing_code"), c.transaction():
            service.pair(UnitOfWork(c), actor, code)
