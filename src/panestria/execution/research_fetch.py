"""Trusted PUBLIC fetch/read/retain controller, fenced by canonical authority."""

import hashlib
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import psycopg
from pydantic import SecretStr

from panestria.brokers.research.fetch import PublicHttpsFetcher, https_target
from panestria.brokers.research.reader import IsolatedTextReader
from panestria.contracts.research import ResearchLimits
from panestria.contracts.research_admission import FetchDiagnostic, FetchPlan
from panestria.contracts.search import LocalSearchSettings
from panestria.execution.research_runtime import fetch_runtime_versions as fetch_runtime_versions
from panestria.execution.research_runtime import research_runtime_versions
from panestria.execution.research_sources import SourceStore
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.research_fetch import FetchAdmissionService
from panestria.kernel.uow import UnitOfWork
from panestria.policy.research import RESEARCH_PROFILE
from panestria.policy.research_fetch import PublicFetchCertificateStore

_FETCHER = PublicHttpsFetcher()  # Shared bounded fetch/DNS slots, not one new pool per task.


@dataclass(frozen=True)
class CollectedSource:
    dispatch_id: str
    status: Literal["RETAINED", "FETCH_ERROR", "READER_ERROR"]
    diagnostic: FetchDiagnostic
    snapshot_id: str | None = None


class AdmittedFetch:
    def __init__(
        self,
        dsn: str,
        actor: Actor,
        plan: FetchPlan,
        attempt_id: str,
        epoch: int,
        certificates: PublicFetchCertificateStore,
        root: Path,
        *,
        search_settings: LocalSearchSettings | None = None,
    ) -> None:
        self.dsn, self.actor, self.root = dsn, actor, root
        self.plan = FetchPlan.model_validate_json(plan.model_dump_json())
        self.attempt_id, self.epoch = attempt_id, epoch
        self.combined = certificates.runtime_versions.get("profile") == RESEARCH_PROFILE
        if self.combined != (search_settings is not None):
            raise KernelDenied("public_fetch_search_settings_mismatch")
        self.search_settings = (
            LocalSearchSettings.model_validate_json(search_settings.model_dump_json())
            if search_settings is not None
            else None
        )
        self.versions = self._runtime_versions()
        self.service = FetchAdmissionService(certificates)
        if (
            certificates.runtime_versions != self.versions
            or plan.configuration_sha256
            != self.versions["fetch_configuration_sha256" if self.combined else "configuration_sha256"]
        ):
            raise KernelDenied("public_fetch_runtime_mismatch")

    def _runtime_versions(self) -> dict[str, str]:
        if self.search_settings is not None:
            return research_runtime_versions(self.search_settings)
        return fetch_runtime_versions()

    def connect(self) -> psycopg.Connection[Any]:
        return psycopg.connect(self.dsn, connect_timeout=2, options="-c statement_timeout=2000 -c lock_timeout=1000")

    def _current(self, connection: psycopg.Connection[Any]) -> float:
        if self._runtime_versions() != self.versions or self.service.certificates.runtime_versions != self.versions:
            raise KernelDenied("public_fetch_runtime_changed")
        return self.service.current(UnitOfWork(connection), self.actor, self.plan, self.attempt_id, self.epoch)

    def collect(self, url: SecretStr, *, cancel: threading.Event | None = None) -> CollectedSource:
        if type(url) is not SecretStr:
            raise KernelDenied("explicit_public_url_required")
        target_url = url.get_secret_value()
        https_target(target_url)  # Syntax before reservation; DNS only after the committed hop.
        stopped, done = threading.Event(), threading.Event()

        def check() -> float:
            if stopped.is_set() or (cancel is not None and cancel.is_set()):
                raise KernelDenied("fetch_cancelled")
            with self.connect() as connection:
                return self._current(connection)

        check()
        with self.connect() as connection:
            self.service.prepare(UnitOfWork(connection), self.actor, self.plan, self.attempt_id, self.epoch)
        with self.connect() as connection:
            dispatch = self.service.claim(
                UnitOfWork(connection),
                self.actor,
                self.plan,
                self.attempt_id,
                self.epoch,
                hashlib.sha256(target_url.encode()).hexdigest(),
            )
        # The acknowledged reservation is permanently consumed, even if setup/cancel/lost ACK stops all I/O.
        result: CollectedSource | None = None

        def monitor() -> None:
            while not done.wait(0.1):
                try:
                    check()
                except Exception:
                    stopped.set()
                    return

        def before_hop(current_url: str, host: str, ordinal: int) -> None:
            check()
            with self.connect() as connection:
                self.service.hop(
                    UnitOfWork(connection),
                    self.actor,
                    self.plan,
                    self.attempt_id,
                    self.epoch,
                    dispatch.dispatch_id,
                    ordinal,
                    current_url,
                    host,
                )
            check()  # Exit/COMMIT acknowledged before the broker can resolve a hostname.

        watchdog = threading.Thread(target=monitor, daemon=True, name="panestria-fetch-authority")
        watchdog.start()
        try:
            remaining = check()
            if remaining < 1:
                raise KernelDenied("fetch_deadline")  # Never round a nearly expired task up to a fresh second.
            fetched = _FETCHER.fetch(
                target_url,
                ResearchLimits(
                    max_sources=1,
                    max_source_bytes=dispatch.body_cap,
                    max_total_bytes=dispatch.body_cap,
                    max_redirects=dispatch.max_redirects,
                    deadline_seconds=min(300.0, remaining),
                ),
                cancel=stopped,
                before_hop=before_hop,
            )
            check()
            if fetched.outcome != "COMPLETE":
                diagnostic: FetchDiagnostic = (
                    "fetch_size_limit"
                    if fetched.outcome == "TRUNCATED" or fetched.reason == "declared_body_limit"
                    else "fetch_timeout"
                    if fetched.reason == "fetch_deadline"
                    else "fetch_http_error"
                    if fetched.reason == "http_error"
                    else "fetch_denied_or_unavailable"
                )
                result = CollectedSource(dispatch.dispatch_id, "FETCH_ERROR", diagnostic)
            else:
                extracted = IsolatedTextReader().extract(
                    fetched.body,
                    expected_sha256=fetched.retained_sha256,
                    content_type=fetched.content_type or "application/octet-stream",
                    cancel=stopped,
                )
                check()
                if extracted.outcome != "COMPLETE":
                    result = CollectedSource(
                        dispatch.dispatch_id,
                        "READER_ERROR",
                        "reader_truncated"
                        if extracted.outcome == "TRUNCATED"
                        else "reader_unsupported"
                        if extracted.outcome == "UNSUPPORTED"
                        else "reader_unavailable",
                    )
                else:
                    with self.connect() as connection:
                        self._current(connection)
                        retained = SourceStore(self.root, self.actor).commit_fetch(
                            UnitOfWork(connection),
                            request_id=self.plan.request_id,
                            task_id=self.plan.scope.task_id,
                            fetched=fetched,
                            extracted=extracted,
                            source_label="PUBLIC",
                        )
                    result = CollectedSource(dispatch.dispatch_id, "RETAINED", "retained", retained.snapshot_id)
            check()
        finally:
            done.set()
            watchdog.join(timeout=3)
            # Separate historical receipt. A crash between source commit and this receipt stays UNKNOWN;
            # valid retained bytes survive, but the URL/reservation cannot be silently repeated.
            with self.connect() as connection:
                self.service.finish(
                    UnitOfWork(connection),
                    self.actor,
                    self.plan.scope.task_id,
                    dispatch.dispatch_id,
                    result.status if result is not None else "UNKNOWN",
                    result.snapshot_id if result is not None else None,
                    result.diagnostic if result is not None else "unconfirmed",
                )
        check()  # Receipt commit/cleanup cannot revive a cancelled task or return a late result.
        assert result is not None
        return result
