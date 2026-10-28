"""Synthetic declaration data only, never a conformance or execution certificate."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from panestria.contracts.connections import ConnectionBudget, ConnectionManifest, ConnectionReviewRequest


def manifest(owner, project, **changes):
    body = dict(
        owner_id=owner,
        project_id=project,
        connector_ref="public-web",
        connector_version="fetch-v1",
        configuration_sha256="ab" * 32,
        account_ref="11111111-1111-1111-1111-111111111111",
        actions=("send",),
        data_classes=("PUBLIC",),
        origins=("https://example.com",),
        budget=ConnectionBudget(max_calls=2, max_bytes=4096, max_wall_seconds=30),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        conformance_sha256="de" * 32,
    )
    body.update(changes)
    return ConnectionManifest(**body)


def proposal(policy, body=None, **changes):
    value = dict(proposal_id=str(uuid4()), policy_ref=policy, expected_version=0, operation="REPLACE", manifest=body)
    value.update(changes)
    return ConnectionReviewRequest(**value)
