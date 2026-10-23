"""
One routine for every "money leaves to an external bank account" operation (withdrawal to your own bank, or
a transfer to someone else's bank account). Order of operations matters:

  1. lock the user's wallet row           -> concurrent requests from this user queue up
  2. re-read the balance and check it, the tier daily limit, then fraud rules (all on fresh data)
  3. call the payment gateway             -> while holding ONLY this user's lock, not the shared platform rows
  4. lock the shared platform rows, post the balanced ledger legs, finalise and commit

A repeated `client_reference` from the same user returns the original transaction instead of paying twice.
"""
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import AccountType
from app.models.config import PlatformConfig
from app.models.transaction import Transaction, TransactionStatus, TransactionType
from app.services.audit import log_action
from app.services.fraud import evaluate_transaction, persist_flags
from app.services.ledger import (
    InsufficientFundsError, LedgerImbalanceError, LedgerService, get_or_create_account, q2,
)
from app.services.limits import enforce_outgoing
from app.services.payment_gateway import payment_gateway
from app.services.rewards import compute_fee_split


async def get_config(db: AsyncSession) -> PlatformConfig:
    cfg = (await db.execute(select(PlatformConfig).where(PlatformConfig.id == 1))).scalar_one_or_none()
    if cfg is None:
        cfg = PlatformConfig()
        db.add(cfg)
        await db.flush()
    return cfg


async def perform_bank_payout(
    db: AsyncSession, *, user, amount: Decimal, bank_code: str, account_number: str, narration: str,
    meta: dict, ip: str, audit_name: str = "WITHDRAWAL", client_reference: str | None = None,
) -> tuple[Transaction, bool]:
    """Returns (transaction, replayed). `replayed` is True when client_reference matched an earlier request."""
    amount = q2(amount)
    cfg = await get_config(db)
    wallet = await get_or_create_account(db, AccountType.user_wallet, user.id)
    ledger = LedgerService(db)

    # 1. lock + fresh read
    await ledger.lock(wallet)
    await db.refresh(wallet)

    if client_reference:
        existing = (await db.execute(
            select(Transaction).where(Transaction.initiator_user_id == user.id,
                                      Transaction.meta["client_reference"].astext == client_reference)
        )).scalar_one_or_none()
        if existing is not None:
            return existing, True

    # 2. checks on fresh data
    split = compute_fee_split(
        amount=amount,
        fee_rate=Decimal("0"),                                       # bank payouts use a flat fee
        reward_rate=Decimal(str(cfg.reward_rate)) / 2,
        insurance_rate=Decimal(str(cfg.insurance_contribution_rate)),
        flat_fee=Decimal(str(cfg.withdrawal_fee_flat)),
    )
    total_debit = q2(amount + split.fee_amount)
    if Decimal(str(wallet.balance)) < total_debit:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Insufficient wallet balance to cover amount + fee")
    await enforce_outgoing(db, user, amount)
    fraud_result = await evaluate_transaction(db, user, amount, "withdrawal")

    txn_meta = dict(meta)
    if client_reference:
        txn_meta["client_reference"] = client_reference
    txn = await ledger.start_transaction(
        type=TransactionType.withdrawal, initiator_user_id=user.id, amount=amount,
        fee_amount=split.fee_amount, reward_amount=split.reward_amount,
        insurance_contribution=split.insurance_contribution,
        narration=narration, ip_address=ip, metadata=txn_meta,
    )

    if fraud_result.blocking:
        await persist_flags(db, user.id, txn.id, fraud_result)
        txn.status = TransactionStatus.flagged
        await log_action(db, "TRANSACTION_BLOCKED_FRAUD", actor_user_id=str(user.id), actor_role=user.role,
                         entity_type="transaction", entity_id=str(txn.id), ip_address=ip,
                         details={"rules": [f[0] for f in fraud_result.flags]})
        await db.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Transaction blocked pending fraud review. Contact support.")
    if fraud_result.has_flags:
        await persist_flags(db, user.id, txn.id, fraud_result)

    # 3. external call (only this user's wallet is locked)
    gw = await payment_gateway.initiate_withdrawal(float(amount), account_number, bank_code, user_reference=str(user.id))
    txn.gateway_reference = gw.gateway_reference
    if not gw.success:
        await ledger.fail(txn, reason=gw.message)
        await log_action(db, f"{audit_name}_FAILED", actor_user_id=str(user.id), actor_role=user.role,
                         entity_type="transaction", entity_id=str(txn.id), ip_address=ip)
        await db.commit()
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, gw.message)

    # 4. shared rows, in one short critical section
    reward_pool = await get_or_create_account(db, AccountType.platform_reward_pool)
    insurance_pool = await get_or_create_account(db, AccountType.platform_insurance_pool)
    platform_revenue = await get_or_create_account(db, AccountType.platform_revenue)
    external = await get_or_create_account(db, AccountType.external_gateway)
    user_reward = await get_or_create_account(db, AccountType.user_reward, user.id)
    user_insurance = await get_or_create_account(db, AccountType.user_insurance, user.id)
    await ledger.lock(user_reward, user_insurance, reward_pool, insurance_pool, platform_revenue, external)

    try:
        await ledger.post(txn, wallet, "D", total_debit)
        await ledger.post(txn, external, "C", amount)                  # principal leaves the platform to the bank
        # the fee stays inside: reward_pool + insurance_pool + platform_revenue must sum to fee_amount
        if split.reward_amount > 0:
            await ledger.post(txn, reward_pool, "C", split.reward_amount)
        if split.insurance_contribution > 0:
            await ledger.post(txn, insurance_pool, "C", split.insurance_contribution)
        if split.platform_net > 0:
            await ledger.post(txn, platform_revenue, "C", split.platform_net)
        if split.reward_amount > 0:
            await ledger.post(txn, reward_pool, "D", split.reward_amount)
            await ledger.post(txn, user_reward, "C", split.reward_amount)
        if split.insurance_contribution > 0:
            await ledger.post(txn, insurance_pool, "D", split.insurance_contribution)
            await ledger.post(txn, user_insurance, "C", split.insurance_contribution)
        await ledger.finalize(txn)
    except InsufficientFundsError:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Insufficient wallet balance to cover amount + fee")
    except LedgerImbalanceError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Ledger integrity check failed: {exc}")

    await log_action(db, f"{audit_name}_COMPLETED", actor_user_id=str(user.id), actor_role=user.role,
                     entity_type="transaction", entity_id=str(txn.id), ip_address=ip,
                     details={"amount": float(amount)})
    await db.commit()
    return txn, False
