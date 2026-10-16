"""Synthetic quota metadata; never a provider quota reading or credential."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from panestria.contracts.quota import QuotaObservation


def observation(**changes):
    now = datetime.now(UTC) - timedelta(seconds=1)
    body = {
        "observation_id": str(uuid4()),
        "scope": {"provider": "claude-subscription", "account_ref": str(uuid4()), "window_ref": "session"},
        "source": "OWNER_REPORTED",
        "remaining": "40",
        "unit": "percent",
        "observed_at": now.isoformat(),
        "resets_at": (now + timedelta(days=1)).isoformat(),
    }
    body.update(changes)
    return QuotaObservation.model_validate_json(__import__("json").dumps(body))
