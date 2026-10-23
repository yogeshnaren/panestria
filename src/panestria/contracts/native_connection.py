"""Explicit account/context authority, separate from physical network accounting."""

from pydantic import Field, StrictInt

from panestria.contracts.build import canonical_sha256
from panestria.contracts.connections import ConnectionContract, ConnectionId, Digest
from panestria.contracts.native_account import NativeAccountObservation
from panestria.contracts.native_tools import ToolScope


class NativeConnectionSelection(ConnectionContract):
    grant_id: ConnectionId
    version: StrictInt = Field(ge=1, le=1_000_001)
    account_observation_sha256: Digest


class NativeConnectionReservation(ConnectionContract):
    selection: NativeConnectionSelection
    scope: ToolScope
    configuration_sha256: Digest
    context_sha256: Digest
    context_bytes: StrictInt = Field(ge=1, le=16 * 1024)

    def sha256(self) -> str:
        return canonical_sha256(self.model_dump(mode="json"))


def native_configuration(observation: NativeAccountObservation, runtime: dict[str, str], model: str) -> str:
    # The reviewed account/profile identity is stable; observation time and
    # compatibility probe receipt deliberately do not renew or change consent.
    return canonical_sha256(
        {
            "connector": "claude-public-bash",
            "version": "account-context-v1",
            "route": "claude-subscription",
            "budget_scope": "SELECTED_PUBLIC_CONTEXT_AND_NATIVE_LAUNCHES",
            "account_ref": observation.account_ref,
            "identity_sha256": observation.identity_sha256,
            "identity_basis": observation.identity_basis,
            "profile_sha256": observation.profile_sha256,
            "binary_sha256": observation.binary_sha256,
            "subscription_type": observation.subscription_type,
            "runtime": runtime,
            "requested_model": model,
        }
    )
