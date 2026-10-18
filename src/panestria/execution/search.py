"""Admit/count/commit before configured search, fence results after cancellation.

This is trusted controller code, not a worker callback or an HTTP endpoint. The
loopback service is operator configured; results remain untrusted and unfetched.
"""

import threading
from typing import Any

import psycopg

from panestria.brokers.research.search import LocalSearxngProvider, SearchUnavailable
from panestria.contracts.search import LocalSearchSettings, SearchDisclosure, SearchQuery, SearchResults
from panestria.contracts.search_admission import SearchPlan
from panestria.execution.research_runtime import research_runtime_versions
from panestria.execution.research_runtime import search_runtime_versions as search_runtime_versions
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.search import SearchAdmissionService, SearchDispatch
from panestria.kernel.uow import UnitOfWork
from panestria.policy.research import RESEARCH_PROFILE
from panestria.policy.search import PublicSearchCertificateStore


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
        self.combined = certificates.runtime_versions.get("profile") == RESEARCH_PROFILE
        self.versions = self._runtime_versions()
        self.service = SearchAdmissionService(certificates)
        if (
            certificates.runtime_versions != self.versions
            or self.versions["search_configuration_sha256" if self.combined else "configuration_sha256"]
            != plan.configuration_sha256
        ):
            raise KernelDenied("public_search_runtime_mismatch")

    def _runtime_versions(self) -> dict[str, str]:
        return research_runtime_versions(self.settings) if self.combined else search_runtime_versions(self.settings)

    def connect(self) -> psycopg.Connection[Any]:
        return psycopg.connect(self.dsn, connect_timeout=2, options="-c statement_timeout=2000 -c lock_timeout=1000")

    def _current(self, connection: psycopg.Connection[Any]) -> float:
        if self._runtime_versions() != self.versions or self.service.certificates.runtime_versions != self.versions:
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
