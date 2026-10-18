"""Explicit bounded collection, retained excerpts and a canonical verification wait."""

import hashlib
import threading
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import psycopg
from pydantic import SecretStr

from panestria.brokers.research.search import SearchUnavailable
from panestria.config_research import ResearchSettings, validate_research_settings
from panestria.contracts.research import ClaimDraft, PassageRef
from panestria.contracts.research_admission import FetchPlan
from panestria.contracts.research_claims import ClaimEvidenceDraft, QuotedPassage
from panestria.contracts.search import SearchQuery
from panestria.contracts.search_admission import SearchPlan
from panestria.execution.research_brief import RetainedBrief
from panestria.execution.research_claims import ClaimStore
from panestria.execution.research_fetch import AdmittedFetch
from panestria.execution.research_runtime import research_runtime_versions
from panestria.execution.search import AdmittedSearch
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.leases import AttemptLease
from panestria.kernel.research_collection import CollectionBinding, CollectionLifecycle, CollectionStop
from panestria.kernel.research_sources import SourceRecordService
from panestria.kernel.uow import UnitOfWork
from panestria.policy.research_fetch import PublicFetchCertificateStore
from panestria.policy.search import PublicSearchCertificateStore


@dataclass(frozen=True)
class CollectionReceipt:
    request_id: str
    task_id: str
    stop_reason: CollectionStop
    status: str = "COLLECTION_STOPPED_AWAITING_SYNTHESIS_AND_SUPPORT"
    semantic_support: str = "NOT_ASSESSED"
    task_completion_authority: str = "NONE"


class OwnerCollection:
    def __init__(self, dsn: str, settings: ResearchSettings) -> None:
        self.dsn, self.settings = dsn, validate_research_settings(settings)
        self.actor = Actor(str(settings.owner_id), str(settings.project_id))
        versions = research_runtime_versions(self.settings.search)
        self.lifecycle = CollectionLifecycle(
            PublicSearchCertificateStore(self.settings.certificates, versions),
            PublicFetchCertificateStore(self.settings.certificates, versions),
            self.settings.certificate_sha256,
        )

    def connect(self) -> psycopg.Connection[Any]:
        return psycopg.connect(self.dsn, connect_timeout=2, options="-c statement_timeout=5000 -c lock_timeout=1000")

    def collect(self, request_id: str, queries: tuple[SecretStr, ...], *, public_web: bool) -> CollectionReceipt:
        if public_web is not True or type(queries) is not tuple or not 1 <= len(queries) <= 16:
            raise KernelDenied("explicit_bounded_public_collection_required")
        if str(UUID(request_id)) != request_id or any(type(query) is not SecretStr for query in queries):
            raise KernelDenied("bounded_public_queries_required")
        with self.connect() as c:
            initial = self.lifecycle.load(UnitOfWork(c), self.actor, request_id)
        # Check acknowledged question bytes/current request binding without egress.
        brief = RetainedBrief(self.settings.root, self.actor).inspect(
            self.dsn, request_id, initial.request.scope.task_id
        )
        if brief.request_sha256 != initial.request_sha256 or brief.claims:
            raise KernelDenied("research_collection_existing_or_unconfirmed_evidence")
        planned = tuple(
            SearchQuery(request_id=UUID(request_id), scope=initial.request.scope, query=query, privacy_class="PUBLIC")
            for query in queries
        )
        if len({q.query.get_secret_value() for q in planned}) != len(planned):
            raise KernelDenied("duplicate_public_query")
        # Each canonical phase has its state+event in one acknowledged transaction.
        # A crash between phases is visible and refuses automatic restart. This
        # avoids writing entity rows after taking the global event-counter lock.
        with self.connect() as c:
            binding = self.lifecycle.load(UnitOfWork(c), self.actor, request_id)
            self.lifecycle.begin(UnitOfWork(c), self.actor, binding)
        with self.connect() as c:
            binding = self.lifecycle.load(UnitOfWork(c), self.actor, request_id)
            self.lifecycle.ready(UnitOfWork(c), self.actor, binding)
        lease: AttemptLease | None = None
        cancel = threading.Event()
        try:
            with self.connect() as c:
                binding = self.lifecycle.load(UnitOfWork(c), self.actor, request_id)
                lease = self.lifecycle.lease(UnitOfWork(c), self.actor, binding)
            common: dict[str, Any] = dict(
                scope=binding.request.scope,
                request_id=request_id,
                request_sha256=binding.request_sha256,
                contract_sha256=binding.contract_sha256,
                policy_sha256=binding.contract.autonomy_profile_ref.rsplit(":", 1)[1],
            )
            versions = self.lifecycle.search.runtime_versions
            search = AdmittedSearch(
                self.dsn,
                self.actor,
                SearchPlan(
                    **common, configuration_sha256=versions["search_configuration_sha256"], max_queries=len(planned)
                ),
                lease.attempt_id,
                lease.epoch,
                self.settings.search,
                self.lifecycle.search,
            )
            fetch = AdmittedFetch(
                self.dsn,
                self.actor,
                FetchPlan(**common, configuration_sha256=versions["fetch_configuration_sha256"]),
                lease.attempt_id,
                lease.epoch,
                self.lifecycle.fetch,
                self.settings.root,
                search_settings=self.settings.search,
            )
            search.prepare()
            fetch.prepare()
            reason: CollectionStop = "queries_exhausted"
            seen: set[str] = set()
            for query in planned:
                try:
                    result = search.search(query, cancel=cancel)
                except SearchUnavailable:
                    reason = "search_unavailable"
                    break  # One unavailable search stops; no provider retry/fallback storm.
                for candidate in result.candidates:
                    digest = hashlib.sha256(candidate.url.get_secret_value().encode()).hexdigest()
                    if digest in seen:
                        continue
                    seen.add(digest)
                    try:
                        collected = fetch.collect(candidate.url, cancel=cancel)
                    except KernelDenied as error:
                        if error.code == "fetch_budget_exhausted":
                            reason = self._capacity_stop(binding) or "body_limit"
                            break
                        raise
                    if collected.snapshot_id is not None:
                        self._excerpt(binding, fetch, collected.snapshot_id)
                    exhausted = self._capacity_stop(binding)
                    if exhausted is not None:
                        reason = exhausted
                        break  # Do not send more queries when no source/body capacity remains.
                if reason in {"source_limit", "body_limit"}:
                    break
            with self.connect() as c:
                fetch._current(c)  # Same locked policy/lease transaction as known adapter termination.
                self.lifecycle.finish(UnitOfWork(c), self.actor, binding, lease, reason=reason, known=True)
            return CollectionReceipt(request_id, binding.request.scope.task_id, reason)
        except BaseException:
            cancel.set()
            if lease is not None:
                try:
                    with self.connect() as c:
                        self.lifecycle.finish(
                            UnitOfWork(c), self.actor, binding, lease, reason="interrupted", known=False
                        )
                except Exception:
                    pass  # Never overwrite a replaced/cancelled/completed epoch or hide the original error.
            raise

    def _capacity_stop(self, binding: CollectionBinding) -> CollectionStop | None:
        with self.connect() as c:
            consumed = c.execute(
                "SELECT count(*),coalesce(sum(reserved_body_bytes),0) FROM panestria.fetch_dispatch WHERE task_id=%s",
                (binding.request.scope.task_id,),
            ).fetchone()
        assert consumed is not None
        if consumed[0] >= binding.request.limits.max_sources:
            return "source_limit"
        return "body_limit" if binding.request.limits.max_total_bytes - int(consumed[1]) < 2 else None

    def _excerpt(self, binding: CollectionBinding, fetch: AdmittedFetch, snapshot_id: str) -> None:
        with self.connect() as c:
            fetch._current(c)
            task_id, request_id = binding.request.scope.task_id, binding.request.request_id
            source = SourceRecordService().read(
                UnitOfWork(c), self.actor, snapshot_id, request_id=request_id, task_id=task_id
            )
            text = SourceRecordService().read_bytes(
                UnitOfWork(c),
                self.actor,
                snapshot_id,
                request_id=request_id,
                task_id=task_id,
                root=self.settings.root,
                role="text",
            )
            # Exact prefix, ending at a UTF-8 boundary, with explicit byte offsets.
            # Dropping a partial trailing code point never changes retained bytes.
            prefix = text.data[:8192]
            try:
                excerpt = prefix.decode("utf-8")
            except UnicodeDecodeError as error:
                if error.reason != "unexpected end of data" or error.end != len(prefix):
                    raise KernelDenied("research_excerpt_invalid_text") from None
                excerpt = prefix[: error.start].decode("utf-8")
            if not excerpt:
                return
            if source.evidence.snapshot.text is None:
                raise KernelDenied("research_excerpt_text_unavailable")
            ref = PassageRef(
                snapshot_id=snapshot_id,
                request_id=request_id,
                text_sha256=source.evidence.snapshot.text.sha256,
                start=0,
                end=len(excerpt.encode()),
            )
            checked = ClaimStore(self.settings.root, self.actor).record(
                UnitOfWork(c),
                request_id=request_id,
                task_id=task_id,
                draft=ClaimEvidenceDraft(
                    claim=ClaimDraft(
                        text=SecretStr("Retained source excerpt; not an assessed answer."),
                        kind="INTERPRETATION",
                        passages=(ref,),
                    ),
                    quotes=(QuotedPassage(reference=ref, quote=SecretStr(excerpt)),),
                ),
                input_label="PUBLIC",
            )
            if checked.verdict != "EVIDENCE_PRESENT":
                raise KernelDenied("research_excerpt_unconfirmed")
