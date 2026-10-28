"""AI-P2e / ADR 0014: reset pacing is monotone and never invents headroom."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from panestria.kernel.pacing import MIN_RATE_INTERVAL, URGENCY_WINDOW_SECONDS, paced_out, usage_rate

amounts = st.decimals(min_value=0, max_value=10**6, places=2, allow_nan=False, allow_infinity=False)
rates = st.one_of(st.none(), st.decimals(min_value=0, max_value=100, places=4, allow_nan=False, allow_infinity=False))
resets = st.one_of(st.none(), st.integers(min_value=0, max_value=30 * 86400))
T0 = datetime(2026, 10, 28, tzinfo=UTC)


def test_ai_p2e_owner_example_waits_far_from_reset_and_runs_near_it():
    # 40% left, 20% reserve, regular use 1%/hour: 30 h from reset that 30% is
    # needed for regular use, so background waits; 45 min out it may run.
    rate = usage_rate((T0, Decimal(41)), (T0 + timedelta(hours=1), Decimal(40)))
    assert rate == Decimal(1) / 3600
    assert paced_out(Decimal(40), Decimal(20), rate, 30 * 3600)
    assert not paced_out(Decimal(40), Decimal(20), rate, 45 * 60)
    assert not paced_out(Decimal(40), Decimal(20), rate, 10 * 3600)


@given(amounts, amounts, st.integers(min_value=1, max_value=86400))
def test_ai_p2e_rate_needs_a_drop_over_a_meaningful_interval(first, second, gap):
    rate = usage_rate((T0, first), (T0 + timedelta(seconds=gap), second))
    assert (rate is None) == (second > first or gap < MIN_RATE_INTERVAL.total_seconds())
    assert rate is None or rate >= 0


@given(amounts, amounts, rates, resets)
def test_ai_p2e_no_evidence_or_urgency_never_paces_out(remaining, reserve, rate, until_reset):
    if rate is None or until_reset is None or until_reset <= URGENCY_WINDOW_SECONDS:
        assert not paced_out(remaining, reserve, rate, until_reset)


@given(amounts, amounts, amounts, rates, resets)
def test_ai_p2e_more_remaining_never_paces_out_more(low, high, reserve, rate, until_reset):
    low, high = sorted((low, high))
    assert not (paced_out(high, reserve, rate, until_reset) and not paced_out(low, reserve, rate, until_reset))


@given(
    amounts, amounts, rates, st.integers(min_value=0, max_value=30 * 86400), st.integers(min_value=0, max_value=86400)
)
def test_ai_p2e_monotone_beyond_the_urgency_window(remaining, reserve, rate, until_reset, extra):
    # Further from the reset never makes work more eligible (outside the window).
    if until_reset > URGENCY_WINDOW_SECONDS and paced_out(remaining, reserve, rate, until_reset):
        assert paced_out(remaining, reserve, rate, until_reset + extra)
