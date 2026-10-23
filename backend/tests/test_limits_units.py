"""Unit tests for the tier-limit helpers that need no database."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from datetime import datetime, timezone
from decimal import Decimal

from app.services import limits


def test_day_starts_at_midnight_in_lagos_not_utc():
    # 23:30 UTC on the 22nd is already 00:30 on the 23rd in Nigeria (UTC+1): today began at 23:00 UTC
    now = datetime(2026, 10, 22, 23, 30, tzinfo=timezone.utc)
    assert limits.day_start_utc(now) == datetime(2026, 10, 22, 23, 0, tzinfo=timezone.utc)
    # 22:59 UTC is still 23:59 on the 22nd in Nigeria: today began at 23:00 UTC the day before
    now = datetime(2026, 10, 22, 22, 59, tzinfo=timezone.utc)
    assert limits.day_start_utc(now) == datetime(2026, 10, 21, 23, 0, tzinfo=timezone.utc)


def test_default_tier_limits_follow_the_documented_circular():
    t1, t2, t3 = (limits.tier_limit(t) for t in (1, 2, 3))
    assert (t1.daily_limit, t1.max_balance) == (Decimal("50000"), Decimal("300000"))
    assert (t2.daily_limit, t2.max_balance) == (Decimal("200000"), Decimal("500000"))
    assert (t3.daily_limit, t3.max_balance) == (Decimal("5000000"), None)       # unlimited balance
    assert limits.tier_limit(99).tier == 1 and limits.tier_limit(0).tier == 1   # unknown tiers get the strictest limits


def test_limits_are_configurable_and_zero_means_unlimited(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "TIER1_DAILY_LIMIT", 0)
    monkeypatch.setattr(settings, "TIER1_MAX_BALANCE", 1234)
    t1 = limits.tier_limit(1)
    assert t1.daily_limit is None and t1.max_balance == Decimal("1234")


def test_room_for():
    assert limits.room_for(1, Decimal("290000"), Decimal("10000")) is True
    assert limits.room_for(1, Decimal("290000"), Decimal("10000.01")) is False
    assert limits.room_for(3, Decimal("999999999"), Decimal("1")) is True
