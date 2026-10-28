"""MVP-X11 reset pacing (ADR 0014): background work yields to projected regular use.

Fixed, documented bounds rather than new policy fields, so existing reviewed
background policies keep their digests. None of these grants dispatch.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

# An observation older than this cannot make background work eligible, however
# long its own freshness window is.
BACKGROUND_MAX_OBSERVATION_AGE = timedelta(hours=6)
# Within this window before a reported reset, unused quota would be lost, so
# projected regular use no longer holds work back. The static reserve still does.
URGENCY_WINDOW_SECONDS = 3600
# Reports closer together than this say too little about a usage rate.
MIN_RATE_INTERVAL = timedelta(minutes=10)


def usage_rate(earlier: tuple[datetime, Decimal], later: tuple[datetime, Decimal]) -> Decimal | None:
    """Units consumed per second between two reports in one lane and reset period.

    A rise (top-up or reset), or reports less than ``MIN_RATE_INTERVAL`` apart,
    give no rate evidence.
    """
    (first_at, first), (second_at, second) = earlier, later
    if second_at - first_at < MIN_RATE_INTERVAL or second > first:
        return None
    seconds = Decimal(str((second_at - first_at).total_seconds()))
    return (first - second) / seconds


def paced_out(remaining: Decimal, reserve: Decimal, rate: Decimal | None, seconds_to_reset: int | None) -> bool:
    """True when the reserve plus projected regular use until the reset exceed what remains.

    Without rate evidence or a reset time there is nothing to project; the
    caller's static reserve and unknown-quota rules still apply.
    """
    if rate is None or seconds_to_reset is None or seconds_to_reset <= URGENCY_WINDOW_SECONDS:
        return False
    return remaining - reserve < rate * seconds_to_reset
