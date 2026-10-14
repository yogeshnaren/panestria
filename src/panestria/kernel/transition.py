"""Bind one task transition to the current policy and a correlation id."""

from __future__ import annotations

import re

from panestria.kernel.errors import KernelDenied

_POLICY_LIMIT = 128
_CORRELATION = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


def require_correlation(correlation_id: str) -> str:
    if not isinstance(correlation_id, str) or _CORRELATION.fullmatch(correlation_id) is None:
        raise KernelDenied("invalid_correlation")
    return correlation_id


def require_policy(policy_version: str) -> str:
    if (
        not isinstance(policy_version, str)
        or not 1 <= len(policy_version) <= _POLICY_LIMIT
        or policy_version != policy_version.strip()
        or "\x00" in policy_version
    ):
        raise KernelDenied("invalid_policy")
    return policy_version


def transition_payload(
    previous: str,
    target: str,
    cause: str,
    policy_version: str,
    correlation_id: str,
) -> dict[str, str]:
    """Return the event body. Invalid context raises before the caller writes."""
    policy = require_policy(policy_version)
    correlation = require_correlation(correlation_id)
    return {
        "cause": cause,
        "correlation_id": correlation,
        "from": previous,
        "policy_version": policy,
        "to": target,
    }
