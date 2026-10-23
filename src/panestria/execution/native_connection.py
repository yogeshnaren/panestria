"""Selected connection intersection for existing native controllers, never a launcher."""

import hashlib
from typing import TYPE_CHECKING, Any

import psycopg

from panestria.brokers.harness.claude_check import REQUESTED_MODEL
from panestria.contracts.build import canonical_sha256
from panestria.contracts.native_connection import NativeConnectionReservation, native_configuration
from panestria.contracts.native_tools import ToolScope
from panestria.execution.background_account import account_reports, collect_account
from panestria.execution.native_build import runtime_versions
from panestria.execution.worker_authority import WorkerAuthority
from panestria.kernel.background_account import BackgroundAccountService
from panestria.kernel.connections import ConnectionReviewService
from panestria.kernel.errors import KernelDenied
from panestria.kernel.native_connection import NativeConnectionBroker
from panestria.kernel.uow import UnitOfWork

if TYPE_CHECKING:
    from panestria.execution.owner_build import OwnerBuild


def preflight_connection(owner: "OwnerBuild") -> None:
    selection = owner.settings.native_connection
    model = owner.settings.native_model
    if selection is None:
        if model is not None:
            raise KernelDenied("selected_model_requires_reviewed_native_connection")
        return
    anchor = BackgroundAccountService(account_reports(owner)).observation(selection.account_observation_sha256)
    configuration = native_configuration(anchor, runtime_versions(model), model or REQUESTED_MODEL)
    with owner.connect() as c:
        grant = ConnectionReviewService().current(UnitOfWork(c), owner.actor, selection.grant_id)
        if (
            grant.version != selection.version
            or grant.state != "DECLARED_ACTIVE"
            or grant.policy_status != "CURRENT"
            or grant.manifest.schema_version != (3 if model is not None else 2)
            or grant.manifest.requested_model != model
            or grant.manifest.configuration_sha256 != configuration
        ):
            raise KernelDenied("native_connection_not_current")


def selected_authority(owner: "OwnerBuild", scope: ToolScope, context: str | None) -> WorkerAuthority | None:
    selection = owner.settings.native_connection
    model = owner.settings.native_model
    if selection is None:
        if model is not None:
            raise KernelDenied("selected_model_requires_reviewed_native_connection")
        return None  # Legacy policy-only configurations acquire no connection claim.
    accounts, broker = BackgroundAccountService(account_reports(owner)), NativeConnectionBroker()
    anchor = accounts.observation(selection.account_observation_sha256)
    versions = runtime_versions(model)
    configuration = native_configuration(anchor, versions, model or REQUESTED_MODEL)
    current = accounts.observation(collect_account(owner, anchor.account_ref))
    reservation = (
        None
        if context is None
        else NativeConnectionReservation(
            selection=selection,
            scope=scope,
            configuration_sha256=configuration,
            context_sha256=hashlib.sha256(context.encode()).hexdigest(),
            context_bytes=len(context.encode()),
            requested_model=model,
        )
    )

    def authorize(connection: psycopg.Connection[Any]) -> None:
        if (
            owner.settings.native_model != model
            or owner.settings.native_connection != selection
            or runtime_versions(model) != versions
            or native_configuration(current, versions, model or REQUESTED_MODEL) != configuration
        ):
            raise KernelDenied("native_connection_account_or_configuration_changed")
        if reservation is None:
            broker.authorize(
                UnitOfWork(connection), owner.actor, selection, configuration, current, scope, requested_model=model
            )
        else:
            broker.require_reserved(UnitOfWork(connection), owner.actor, reservation, current)

    def refresh() -> None:
        nonlocal current
        with owner.connect() as c:
            authorize(c)
        fresh = accounts.observation(collect_account(owner, anchor.account_ref))
        if native_configuration(fresh, versions, model or REQUESTED_MODEL) != configuration:
            raise KernelDenied("native_connection_account_or_configuration_changed")
        current = fresh
        with owner.connect() as c:
            authorize(c)

    if native_configuration(current, versions, model or REQUESTED_MODEL) != configuration:
        raise KernelDenied("native_connection_account_or_configuration_changed")
    with owner.connect() as c:
        if reservation is not None:
            broker.reserve(UnitOfWork(c), owner.actor, reservation, current)
        else:
            authorize(c)
    return WorkerAuthority(
        canonical_sha256(
            {
                "selection": selection.model_dump(mode="json"),
                "configuration": configuration,
                "scope": scope.sha256(),
                "reservation": reservation.sha256() if reservation else None,
            }
        ),
        authorize,
        refresh,
    )
