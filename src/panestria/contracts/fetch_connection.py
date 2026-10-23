"""The initial connection capability is anonymous PUBLIC HTTPS GET, without credentials."""

import hashlib
import json
from uuid import NAMESPACE_URL, uuid5

from pydantic import Field, StrictInt, TypeAdapter

from panestria.contracts.connections import ConnectionContract, ConnectionId, Digest

FETCH_CONNECTOR = "public-https-fetch"
FETCH_CONNECTOR_VERSION = "anonymous-read-v1"
HTTP_FRAMING_BYTES = 32 * 1024
HTTP_READ_BUFFER_BYTES = 4096
HTTP_REQUEST_BYTES = 8192
# Reserve request/status/headers/chunk framing and conservative buffer read-ahead
# for EVERY possible hop; the terminal body and one-byte overread are separate.
# These are application plaintext bounds, not DNS/TLS/TCP or physical wire usage.
HTTP_HOP_RESERVED_BYTES = HTTP_FRAMING_BYTES + HTTP_REQUEST_BYTES + 2 * HTTP_READ_BUFFER_BYTES + 1
FETCH_CONFIGURATION_SHA256 = hashlib.sha256(
    json.dumps(
        {
            "connector": FETCH_CONNECTOR,
            "version": FETCH_CONNECTOR_VERSION,
            "transport": "public-https443-get-no-auth-cookie-proxy-retry",
            "reader": "fixed-isolated-no-network",
            "http_hop_reserved_bytes": HTTP_HOP_RESERVED_BYTES,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
).hexdigest()


class FetchConnectionBinding(ConnectionContract):
    grant_id: ConnectionId
    version: StrictInt = Field(ge=1, le=1_000_001)


def anonymous_fetch_account(owner_id: str, project_id: str, configuration_sha256: str) -> str:
    """Scoped anonymous service identity, never an authenticated external account."""
    for identity in (owner_id, project_id):
        TypeAdapter(ConnectionId).validate_python(identity)
    TypeAdapter(Digest).validate_python(configuration_sha256)
    return str(
        uuid5(NAMESPACE_URL, f"panestria:{FETCH_CONNECTOR_VERSION}:{owner_id}:{project_id}:{configuration_sha256}")
    )
