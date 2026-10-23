"""
Account tiers: daily outgoing limit and maximum wallet balance.

Enforcement happens AFTER the sender's wallet row is locked, so two simultaneous requests cannot both
squeeze under the same limit. Limits come from settings (see config.py; defaults follow the CBN's 2017
mobile-money KYC circular and MUST be confirmed against your licence). 0 means unlimited.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.transaction import Transaction, TransactionType, TransactionStatus

WAT = timezone(timedelta(hours=1))  # Nigeria has no daylight saving, so a fixed offset is exact
OUTGOING_TYPES = (TransactionType.transfer, TransactionType.withdrawal)


def naira(x) -> str:
    return f"₦{Decimal(str(x)):,.2f}"


@dataclass(frozen=True)
class TierLimit:
    tier: int
    daily_limit: Optional[Decimal]
    max_balance: Optional[Decimal]


def tier_limit(tier: int) -> TierLimit:
    tier = tier if tier in (1, 2, 3) else 1
    daily = getattr(settings, f"TIER{tier}_DAILY_LIMIT")
    bal = getattr(settings, f"TIER{tier}_MAX_BALANCE")
    return TierLimit(tier, Decimal(str(daily)) if daily > 0 else None, Decimal(str(bal)) if bal > 0 else None)


def day_start_utc(now: Optional[datetime] = None) -> datetime:
    """Midnight at the start of today in Nigeria (WAT), as a UTC timestamp."""
    now = now or datetime.now(timezone.utc)
    local = now.astimezone(WAT)
    return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


async def spent_today(db: AsyncSession, user_id) -> Decimal:
    stmt = select(func.coalesce(func.sum(Transaction.amount), 0)).where(
        Transaction.initiator_user_id == user_id,
        Transaction.type.in_(OUTGOING_TYPES),
        Transaction.status.in_([TransactionStatus.completed, TransactionStatus.processing]),
        Transaction.created_at >= day_start_utc(),
    )
    return Decimal(str((await db.execute(stmt)).scalar_one()))


async def enforce_outgoing(db: AsyncSession, user, amount: Decimal) -> None:
    lim = tier_limit(user.account_tier)
    if lim.daily_limit is None:
        return
    spent = await spent_today(db, user.id)
    if spent + amount > lim.daily_limit:
        left = max(lim.daily_limit - spent, Decimal("0"))
        hint = " Upgrade your account level to raise it." if lim.tier < 3 else ""
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"This would go over your Tier {lim.tier} daily limit of {naira(lim.daily_limit)} "
            f"({naira(left)} left today).{hint}",
        )


def room_for(tier: int, balance: Decimal, incoming: Decimal) -> bool:
    lim = tier_limit(tier)
    return lim.max_balance is None or balance + incoming <= lim.max_balance


def enforce_own_balance_room(tier: int, balance: Decimal, incoming: Decimal) -> None:
    if not room_for(tier, balance, incoming):
        lim = tier_limit(tier)
        hint = " Upgrade your account level to hold more." if lim.tier < 3 else ""
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Your wallet can hold at most {naira(lim.max_balance)} on Tier {lim.tier}.{hint}",
        )


async def overview(db: AsyncSession, user, balance: Decimal) -> dict:
    lim = tier_limit(user.account_tier)
    spent = await spent_today(db, user.id)
    return {
        "tier": lim.tier,
        "daily_limit": float(lim.daily_limit) if lim.daily_limit is not None else None,
        "max_balance": float(lim.max_balance) if lim.max_balance is not None else None,
        "spent_today": float(spent),
        "remaining_today": float(max(lim.daily_limit - spent, Decimal("0"))) if lim.daily_limit is not None else None,
        "balance": float(balance),
    }
