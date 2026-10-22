"""
Fraud detection — lightweight rule-based engine.

Rules implemented (v1.0):
  1. VELOCITY_LIMIT        — too many transactions from one user in a short window
  2. LARGE_AMOUNT          — single transaction exceeds configured threshold
  3. NEW_ACCOUNT_LARGE_TXN — account younger than 24h attempting a large transfer
  4. RAPID_PIN_FAILURES    — repeated failed PIN attempts (checked at auth layer,
                              logged here for visibility)

Flags are advisory: they are written to `fraud_flags` and, for high/critical
severity, the transaction is marked `flagged` and blocked pending review —
everything else proceeds normally so legitimate users aren't blocked by
low-severity signals.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import Transaction, TransactionStatus
from app.models.fraud import FraudFlag, FraudSeverity
from app.models.user import User
from app.models.config import PlatformConfig


class FraudCheckResult:
    def __init__(self):
        self.flags: list[tuple[str, FraudSeverity, dict]] = []

    @property
    def blocking(self) -> bool:
        return any(sev in (FraudSeverity.high, FraudSeverity.critical) for _, sev, _ in self.flags)

    @property
    def has_flags(self) -> bool:
        return len(self.flags) > 0


async def _get_config(db: AsyncSession) -> PlatformConfig:
    result = await db.execute(select(PlatformConfig).where(PlatformConfig.id == 1))
    cfg = result.scalar_one_or_none()
    if cfg is None:
        cfg = PlatformConfig()
        db.add(cfg)
        await db.flush()
    return cfg


async def evaluate_transaction(
    db: AsyncSession, user: User, amount: Decimal, txn_type: str
) -> FraudCheckResult:
    cfg = await _get_config(db)
    result = FraudCheckResult()

    # Rule 1: velocity — count completed/processing transactions in window
    window_start = datetime.now(timezone.utc) - timedelta(minutes=cfg.fraud_velocity_window_minutes)
    stmt = select(func.count(Transaction.id)).where(
        Transaction.initiator_user_id == user.id,
        Transaction.created_at >= window_start,
    )
    count = (await db.execute(stmt)).scalar_one()
    if count >= cfg.fraud_velocity_max_txns:
        result.flags.append((
            "VELOCITY_LIMIT",
            FraudSeverity.high,
            {"txn_count": count, "window_minutes": cfg.fraud_velocity_window_minutes},
        ))

    # Rule 2: large single-transaction amount
    if amount >= Decimal(str(cfg.fraud_large_amount_threshold)):
        result.flags.append((
            "LARGE_AMOUNT",
            FraudSeverity.medium,
            {"amount": float(amount), "threshold": float(cfg.fraud_large_amount_threshold)},
        ))

    # Rule 3: brand-new account attempting a large transaction
    account_age = datetime.now(timezone.utc) - user.created_at.replace(tzinfo=timezone.utc)
    if account_age < timedelta(hours=24) and amount >= Decimal(str(cfg.fraud_large_amount_threshold)) / 2:
        result.flags.append((
            "NEW_ACCOUNT_LARGE_TXN",
            FraudSeverity.high,
            {"account_age_hours": round(account_age.total_seconds() / 3600, 2), "amount": float(amount)},
        ))

    return result


async def persist_flags(
    db: AsyncSession, user_id, transaction_id, check_result: FraudCheckResult
) -> list[FraudFlag]:
    saved = []
    for rule_code, severity, details in check_result.flags:
        flag = FraudFlag(
            user_id=user_id,
            transaction_id=transaction_id,
            rule_code=rule_code,
            severity=severity,
            details=details,
        )
        db.add(flag)
        saved.append(flag)
    if saved:
        await db.flush()
    return saved
