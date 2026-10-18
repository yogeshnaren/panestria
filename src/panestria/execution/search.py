"""Admit/count/commit before configured search, fence results after cancellation.

This is trusted controller code, not a worker callback or an HTTP endpoint. The
loopback service is operator configured; results remain untrusted and unfetched.
"""

import hashlib
import threading
from pathlib import Path
from typing import Any

import psycopg

from panestria.brokers.research.search import LocalSearxngProvider, SearchUnavailable
from panestria.contracts.search import LocalSearchSettings, SearchDisclosure, SearchQuery, SearchResults
from panestria.contracts.search_admission import SearchPlan
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.search import SearchAdmissionService, SearchDispatch
from panestria.kernel.uow import UnitOfWork
from panestria.policy.search import SEARCH_PROFILE, PublicSearchCertificateStore


def search_runtime_versions(settings: LocalSearchSettings) -> dict[str, str]:
    source = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for path in sorted(source.rglob("*.py")):
        digest.update(str(path.relative_to(source)).encode() + b"\0" + path.read_bytes())
    return {
        "profile": SEARCH_PROFILE,
        "source_sha256": digest.hexdigest(),
        "configuration_sha256": hashlib.sha256(settings.model_dump_json().encode()).hexdigest(),
    }


class AdmittedSearch:
    def __init__(
        self,
        dsn: str,
        actor: Actor,
        plan: SearchPlan,
        attempt_id: str,
        epoch: int,
        settings: LocalSearchSettings,
        certificates: PublicSearchCertificateStore,
    ) -> None:
        self.dsn, self.actor = dsn, actor
        self.plan = SearchPlan.model_validate_json(plan.model_dump_json())
        self.attempt_id, self.epoch = attempt_id, epoch
        self.settings = LocalSearchSettings.model_validate_json(settings.model_dump_json())
        self.versions = search_runtime_versions(self.settings)
        self.service = SearchAdmissionService(certificates)
        if (
            certificates.runtime_versions != self.versions
            or self.versions["configuration_sha256"] != plan.configuration_sha256
        ):
            raise KernelDenied("public_search_runtime_mismatch")

    def connect(self) -> psycopg.Connection[Any]:
        return psycopg.connect(self.dsn, connect_timeout=2, options="-c statement_timeout=2000 -c lock_timeout=1000")

    def _current(self, connection: psycopg.Connection[Any]) -> float:
        if (
            search_runtime_versions(self.settings) != self.versions
            or self.service.certificates.runtime_versions != self.versions
        ):
            raise KernelDenied("public_search_runtime_changed")
        return self.service.current(UnitOfWork(connection), self.actor, self.plan, self.attempt_id, self.epoch)

    def prepare(self) -> None:
        with self.connect() as connection:
            self._current(connection)
            self.service.prepare(UnitOfWork(connection), self.actor, self.plan, self.attempt_id, self.epoch)

    def search(self, query: SearchQuery, *, cancel: threading.Event | None = None) -> SearchResults:
        query = SearchQuery.model_validate(query)
        if query.scope != self.plan.scope or str(query.request_id) != self.plan.request_id:
            raise KernelDenied("search_scope_mismatch")
        self.prepare()
        stopped, done = threading.Event(), threading.Event()
        claimed: SearchDispatch | None = None
        result: SearchResults | None = None
        unavailable = False

        def check() -> None:
            if stopped.is_set() or (cancel is not None and cancel.is_set()):
                raise KernelDenied("search_cancelled")
            with self.connect() as connection:
                self._current(connection)

        def monitor() -> None:
            while not done.wait(0.1):
                try:
                    check()
                except Exception:
                    stopped.set()
                    return

        def before_send(disclosure: SearchDisclosure) -> None:
            nonlocal claimed
            check()
            with self.connect() as connection:
                self._current(connection)
                claimed = self.service.claim(
                    UnitOfWork(connection), self.actor, self.plan, self.attempt_id, self.epoch, disclosure
                )
            # No socket can be opened until __exit__ has acknowledged COMMIT.
            check()

        watchdog = threading.Thread(target=monitor, daemon=True, name="panestria-search-authority")
        watchdog.start()
        try:
            check()
            result = LocalSearxngProvider(self.settings).search(query, before_send, cancel=stopped)
            check()  # A late result cannot revive expired/revoked/cancelled authority.
        except SearchUnavailable:
            unavailable = True
            raise
        finally:
            done.set()
            watchdog.join(timeout=3)
            if claimed is not None:
                with self.connect() as connection:
                    self.service.finish(
                        UnitOfWork(connection),
                        self.actor,
                        self.plan.scope.task_id,
                        claimed.dispatch_id,
                        "RETURNED" if result is not None else "UNAVAILABLE" if unavailable else "UNKNOWN",
                        result.response_sha256 if result is not None else None,
                        len(result.candidates) if result is not None else None,
                    )
        check()  # Receipt commit/cleanup can itself overlap cancellation.
        assert result is not None
        return result
