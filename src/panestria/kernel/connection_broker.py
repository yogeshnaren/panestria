"""Intersect the initial anonymous PUBLIC-fetch capability with exact owner declarations.

This is not a standalone runtime permit: FetchAdmissionService must first run
the existing current certificate/policy/contract/lease checks. No secret, root,
account enrollment, transport or write/delete/spend capability is introduced.
"""

import math
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from panestria.contracts.connections import ConnectionManifest
from panestria.contracts.fetch_connection import (
    FETCH_CONFIGURATION_SHA256,
    FETCH_CONNECTOR,
    FETCH_CONNECTOR_VERSION,
    HTTP_HOP_RESERVED_BYTES,
    FetchConnectionBinding,
    anonymous_fetch_account,
)
from panestria.contracts.research_admission import FetchPlan
from panestria.kernel.connections import ConnectionReviewService
from panestria.kernel.errors import KernelDenied
from panestria.kernel.goals import Actor
from panestria.kernel.repositories.policy import current_policy, lock_project
from panestria.kernel.uow import UnitOfWork


@dataclass(frozen=True)
class FetchGrant:
    binding: FetchConnectionBinding
    manifest: ConnectionManifest = field(repr=False)
    remaining_seconds: float


@dataclass(frozen=True)
class FetchCapacity:
    body_cap: int
    hops: int
    application_bytes: int


class GrantBroker:
    def authorize(self, uow: UnitOfWork, actor: Actor, plan: FetchPlan) -> FetchGrant:
        """Declaration intersection only; called inside certified research admission."""
        ConnectionReviewService._transaction(uow)
        if (plan.scope.owner_id, plan.scope.project_id) != (actor.owner_id, actor.project_id):
            raise KernelDenied("not_found")
        lock_project(uow, actor)  # Same lock as review/revoke; no entity lock after event append.
        binding = plan.connection
        if binding is None:
            raise KernelDenied("fetch_connection_required")
        policy = current_policy(uow, actor)
        declaration = ConnectionReviewService().current(uow, actor, binding.grant_id)
        manifest = declaration.manifest
        if (
            declaration.version != binding.version
            or declaration.state != "DECLARED_ACTIVE"
            or declaration.policy_status != "CURRENT"
            or policy.sha256() != plan.policy_sha256
        ):
            raise KernelDenied("fetch_connection_not_current")
        if (
            manifest.connector_ref != FETCH_CONNECTOR
            or manifest.connector_version != FETCH_CONNECTOR_VERSION
            or manifest.configuration_sha256 != plan.configuration_sha256
            or plan.configuration_sha256 != FETCH_CONFIGURATION_SHA256
            or manifest.account_ref
            != anonymous_fetch_account(actor.owner_id, actor.project_id, plan.configuration_sha256)
            or manifest.conformance_sha256 != policy.trust.runtime_certificate_sha256
            or manifest.root_refs
            or manifest.budget.max_cash_microusd != 0
        ):
            raise KernelDenied("fetch_connection_capability_mismatch")
        if not {"read", "send"}.issubset(manifest.actions) or "PUBLIC" not in manifest.data_classes:
            raise KernelDenied("fetch_connection_action_or_class_denied")
        row = uow.execute(
            "SELECT clock_timestamp(),min(created_at) FROM panestria.fetch_plan "
            "WHERE connection_grant_id=%s AND connection_grant_version=%s",
            (binding.grant_id, binding.version),
        ).fetchone()
        assert row is not None
        elapsed = (row[0] - row[1]).total_seconds() if row[1] is not None else 0.0
        if not math.isfinite(elapsed) or elapsed < 0:
            raise KernelDenied("fetch_connection_budget_unconfirmed")
        remaining = min(
            manifest.budget.max_wall_seconds - elapsed,
            (manifest.expires_at - row[0]).total_seconds(),
        )
        if remaining <= 0:
            raise KernelDenied("fetch_connection_deadline")
        return FetchGrant(binding, manifest, remaining)

    def capacity(
        self,
        uow: UnitOfWork,
        actor: Actor,
        plan: FetchPlan,
        body_cap: int,
        hops: int,
        *,
        url: str,
        host: str,
    ) -> FetchCapacity:
        grant = self.authorize(uow, actor, plan)
        self._origin(grant, url, host)  # Reject an ungranted first target before reserving any capacity.
        calls_left, bytes_left = self._remaining(uow, grant)
        count = min(hops, calls_left, (bytes_left - 2) // HTTP_HOP_RESERVED_BYTES)
        cap = min(body_cap, bytes_left - count * HTTP_HOP_RESERVED_BYTES - 1)
        if count < 1 or cap < 1:
            raise KernelDenied("fetch_connection_budget_exhausted")
        return FetchCapacity(cap, count, cap + 1 + count * HTTP_HOP_RESERVED_BYTES)

    def available(self, uow: UnitOfWork, actor: Actor, plan: FetchPlan) -> None:
        """Metadata-only preflight: don't search when even one minimum fetch cannot fit."""
        calls, size = self._remaining(uow, self.authorize(uow, actor, plan))
        if calls < 1 or size < HTTP_HOP_RESERVED_BYTES + 2:
            raise KernelDenied("fetch_connection_budget_exhausted")

    @staticmethod
    def _remaining(uow: UnitOfWork, grant: FetchGrant) -> tuple[int, int]:
        # No missing/uncertain reservation becomes free capacity, including
        # commit-ack loss. All possible redirects are reserved before any I/O.
        row = uow.execute(
            "SELECT count(*) FILTER(WHERE r.dispatch_id IS NULL "
            "OR r.reserved_bytes!=d.reserved_body_bytes+r.reserved_hops*%s),"
            "coalesce(sum(r.reserved_hops),0),coalesce(sum(r.reserved_bytes),0) "
            "FROM panestria.fetch_plan p JOIN panestria.fetch_dispatch d ON d.task_id=p.task_id "
            "LEFT JOIN panestria.connection_fetch_reservation r ON r.dispatch_id=d.id "
            "WHERE p.connection_grant_id=%s AND p.connection_grant_version=%s",
            (HTTP_HOP_RESERVED_BYTES, grant.binding.grant_id, grant.binding.version),
        ).fetchone()
        assert row is not None
        if row[0]:
            raise KernelDenied("fetch_connection_budget_unconfirmed")
        calls_left = grant.manifest.budget.max_calls - int(row[1])
        bytes_left = grant.manifest.budget.max_bytes - int(row[2])
        return calls_left, bytes_left

    def reserve(
        self,
        uow: UnitOfWork,
        actor: Actor,
        plan: FetchPlan,
        dispatch_id: str,
        capacity: FetchCapacity,
    ) -> None:
        # Caller has inserted the one-use dispatch under the same project lock
        # and transaction. This row and the dispatch/event commit together.
        assert plan.connection is not None
        uow.execute(
            "INSERT INTO panestria.connection_fetch_reservation(dispatch_id,task_id,request_id,grant_id,"
            "grant_version,reserved_hops,reserved_bytes) VALUES(%s,%s,%s,%s,%s,%s,%s)",
            (
                dispatch_id,
                plan.scope.task_id,
                plan.request_id,
                plan.connection.grant_id,
                plan.connection.version,
                capacity.hops,
                capacity.application_bytes,
            ),
        )

    def hop(
        self,
        uow: UnitOfWork,
        actor: Actor,
        plan: FetchPlan,
        dispatch_id: str,
        ordinal: int,
        url: str,
        host: str,
    ) -> None:
        grant = self.authorize(uow, actor, plan)
        self._origin(grant, url, host)
        row = uow.execute(
            "SELECT r.reserved_hops,r.reserved_bytes,d.reserved_body_bytes "
            "FROM panestria.connection_fetch_reservation r "
            "JOIN panestria.fetch_dispatch d ON d.id=r.dispatch_id WHERE r.dispatch_id=%s AND r.task_id=%s "
            "AND r.request_id=%s AND r.grant_id=%s AND r.grant_version=%s",
            (dispatch_id, plan.scope.task_id, plan.request_id, grant.binding.grant_id, grant.binding.version),
        ).fetchone()
        if row is None or row[1] != row[2] + row[0] * HTTP_HOP_RESERVED_BYTES or not 0 <= ordinal < row[0]:
            raise KernelDenied("fetch_connection_reservation_unconfirmed")

    @staticmethod
    def _origin(grant: FetchGrant, url: str, host: str) -> None:
        try:
            if (
                type(url) is not str
                or not 1 <= len(url.encode()) <= 2048
                or any(ord(c) <= 32 or ord(c) == 127 or c == "\\" for c in url)
            ):
                raise ValueError
            parts = urlsplit(url)
            if (
                parts.scheme != "https"
                or parts.username is not None
                or parts.password is not None
                or parts.fragment
                or parts.port not in (None, 443)
                or parts.hostname is None
                or parts.hostname.encode("idna").decode("ascii").lower() != host
                or "https://" + host not in grant.manifest.origins
            ):
                raise ValueError
        except (ValueError, UnicodeError):
            raise KernelDenied("fetch_connection_origin_denied") from None
