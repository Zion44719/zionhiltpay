from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import verify_pin
from app.models.user import User
from app.models.account import Account, AccountType
from app.models.transaction import Transaction, TransactionType, TransactionStatus
from app.models.config import PlatformConfig
from app.schemas.wallet import (
    WalletBalanceOut, DepositRequest, TransferRequest, WithdrawRequest,
    TransactionOut, TransactionListOut,
)
from app.services.ledger import LedgerService, get_or_create_account, InsufficientFundsError, LedgerImbalanceError, q2
from app.services.rewards import compute_fee_split
from app.services.fraud import evaluate_transaction, persist_flags
from app.services.payment_gateway import payment_gateway
from app.services.audit import log_action
from app.api.deps import get_current_user, get_client_ip
from app.core import identity as idt
from app.core.config import settings
from app.core.limiter import limiter
from app.services.directory import find_user

router = APIRouter(prefix="/api/wallet", tags=["wallet"])


async def _get_config(db: AsyncSession) -> PlatformConfig:
    result = await db.execute(select(PlatformConfig).where(PlatformConfig.id == 1))
    cfg = result.scalar_one_or_none()
    if cfg is None:
        cfg = PlatformConfig()
        db.add(cfg)
        await db.flush()
    return cfg


def _require_pin_ok(user: User, pin: str):
    if not user.pin_set or not user.pin_hash:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Please set a transaction PIN before performing this action")
    if not verify_pin(pin, user.pin_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Incorrect transaction PIN")


def _view_for(txn: Transaction, viewer: User) -> TransactionOut:
    """Fee, cashback and insurance accrual belong to the initiator. A counterparty
    paid no fee and earned nothing, so they must not see the sender's figures."""
    out = TransactionOut.model_validate(txn)
    if txn.initiator_user_id != viewer.id:
        out = out.model_copy(update={"fee_amount": 0.0, "reward_amount": 0.0, "insurance_contribution": 0.0})
    return out


@router.get("/resolve-recipient")
@limiter.limit(settings.RATE_LIMIT_LOOKUP)
async def resolve_recipient(request: Request, identifier: str, db: AsyncSession = Depends(get_db),
                            user: User = Depends(get_current_user)):
    """Name enquiry: lets the sender confirm WHO they are paying before entering a PIN.
    Deliberately shows only first name + last initial, never email or phone."""
    kind, target = await find_user(db, identifier)
    if kind == "unknown":
        return {"found": False, "reason": "That isn't a valid account number, username, email or phone number"}
    if target is None or not target.is_active or target.is_frozen:
        return {"found": False, "reason": "No active account matches that"}
    return {
        "found": True,
        "is_self": target.id == user.id,
        "name": idt.mask_name(target.full_name),
        "username": target.username,
        "account_number": target.account_number,
        "matched_by": kind,
    }


@router.get("/balance", response_model=WalletBalanceOut)
async def get_balance(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    wallet = await get_or_create_account(db, AccountType.user_wallet, user.id)
    reward = await get_or_create_account(db, AccountType.user_reward, user.id)
    insurance = await get_or_create_account(db, AccountType.user_insurance, user.id)
    await db.commit()
    return WalletBalanceOut(
        account_number=user.account_number,
        wallet_balance=float(wallet.balance),
        reward_balance=float(reward.balance),
        insurance_balance=float(insurance.balance),
    )


@router.post("/deposit", response_model=TransactionOut, status_code=status.HTTP_201_CREATED)
async def deposit(request: Request, payload: DepositRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Simulates funding the wallet from an external bank/card via the mock gateway.
    No PIN required (inbound funds), mirroring most real fintech UX."""
    amount = q2(payload.amount)

    gw_result = await payment_gateway.initiate_deposit(float(amount), user_reference=str(user.id))

    ledger = LedgerService(db)
    txn = await ledger.start_transaction(
        type=TransactionType.deposit,
        initiator_user_id=user.id,
        amount=amount,
        currency="NGN",
        narration=payload.narration or "Wallet funding",
        gateway_reference=gw_result.gateway_reference,
        ip_address=get_client_ip(request),
        metadata={"gateway_message": gw_result.message},
    )

    if not gw_result.success:
        await ledger.fail(txn, reason=gw_result.message)
        await log_action(db, "DEPOSIT_FAILED", actor_user_id=str(user.id), actor_role=user.role,
                          entity_type="transaction", entity_id=str(txn.id), ip_address=get_client_ip(request))
        await db.commit()
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, gw_result.message)

    external = await get_or_create_account(db, AccountType.external_gateway)
    wallet = await get_or_create_account(db, AccountType.user_wallet, user.id)

    await ledger.post(txn, external, "D", amount)
    await ledger.post(txn, wallet, "C", amount)
    await ledger.finalize(txn)

    await log_action(db, "DEPOSIT_COMPLETED", actor_user_id=str(user.id), actor_role=user.role,
                      entity_type="transaction", entity_id=str(txn.id), ip_address=get_client_ip(request),
                      details={"amount": float(amount)})
    await db.commit()
    return txn


@router.post("/transfer", response_model=TransactionOut, status_code=status.HTTP_201_CREATED)
async def transfer(request: Request, payload: TransferRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Wallet-to-wallet transfer. Every transfer:
      1. Deducts amount + fee from sender's wallet
      2. Credits amount to recipient's wallet
      3. Splits the fee: reward -> sender's reward wallet, insurance -> sender's
         device-insurance pool, remainder -> platform revenue.
    """
    _require_pin_ok(user, payload.pin)
    amount = q2(payload.amount)

    kind, recipient = await find_user(db, payload.recipient_identifier)
    if kind == "unknown":
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Enter a valid account number, username, email or phone number")
    if recipient is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recipient not found")
    if recipient.id == user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot transfer to your own account")
    if recipient.is_frozen or not recipient.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Recipient account cannot receive funds")

    cfg = await _get_config(db)
    split = compute_fee_split(
        amount=amount,
        fee_rate=Decimal(str(cfg.transaction_fee_rate)),
        reward_rate=Decimal(str(cfg.reward_rate)),
        insurance_rate=Decimal(str(cfg.insurance_contribution_rate)),
    )
    total_debit = q2(amount + split.fee_amount)

    # --- Fraud check (advisory unless high/critical) ---
    fraud_result = await evaluate_transaction(db, user, amount, "transfer")

    sender_wallet = await get_or_create_account(db, AccountType.user_wallet, user.id)
    if Decimal(str(sender_wallet.balance)) < total_debit:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Insufficient wallet balance to cover amount + fee")

    ledger = LedgerService(db)
    txn = await ledger.start_transaction(
        type=TransactionType.transfer,
        initiator_user_id=user.id,
        counterparty_user_id=recipient.id,
        amount=amount,
        fee_amount=split.fee_amount,
        reward_amount=split.reward_amount,
        insurance_contribution=split.insurance_contribution,
        narration=payload.narration or f"Transfer to {recipient.full_name}",
        ip_address=get_client_ip(request),
    )

    if fraud_result.blocking:
        await persist_flags(db, user.id, txn.id, fraud_result)
        txn.status = TransactionStatus.flagged
        await log_action(db, "TRANSACTION_BLOCKED_FRAUD", actor_user_id=str(user.id), actor_role=user.role,
                          entity_type="transaction", entity_id=str(txn.id), ip_address=get_client_ip(request),
                          details={"rules": [f[0] for f in fraud_result.flags]})
        await db.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Transaction blocked pending fraud review. Contact support.")
    elif fraud_result.has_flags:
        await persist_flags(db, user.id, txn.id, fraud_result)

    recipient_wallet = await get_or_create_account(db, AccountType.user_wallet, recipient.id)
    sender_reward = await get_or_create_account(db, AccountType.user_reward, user.id)
    sender_insurance = await get_or_create_account(db, AccountType.user_insurance, user.id)
    reward_pool = await get_or_create_account(db, AccountType.platform_reward_pool)
    insurance_pool = await get_or_create_account(db, AccountType.platform_insurance_pool)
    platform_revenue = await get_or_create_account(db, AccountType.platform_revenue)

    try:
        # Sender pays amount + fee out of wallet
        await ledger.post(txn, sender_wallet, "D", total_debit)
        # Recipient receives the transfer amount
        await ledger.post(txn, recipient_wallet, "C", amount)
        # The fee portion collected from the sender (total_debit - amount) is
        # credited into the pools/revenue account it funds, so the ledger
        # balances: reward_pool + insurance_pool + platform_revenue == fee_amount.
        if split.reward_amount > 0:
            await ledger.post(txn, reward_pool, "C", split.reward_amount)
        if split.insurance_contribution > 0:
            await ledger.post(txn, insurance_pool, "C", split.insurance_contribution)
        if split.platform_net > 0:
            await ledger.post(txn, platform_revenue, "C", split.platform_net)
        # Pools immediately disburse to the sender's reward/insurance wallets.
        if split.reward_amount > 0:
            await ledger.post(txn, reward_pool, "D", split.reward_amount)
            await ledger.post(txn, sender_reward, "C", split.reward_amount)
        if split.insurance_contribution > 0:
            await ledger.post(txn, insurance_pool, "D", split.insurance_contribution)
            await ledger.post(txn, sender_insurance, "C", split.insurance_contribution)
    except InsufficientFundsError as e:
        await ledger.fail(txn, reason=str(e))
        await db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))

    try:
        await ledger.finalize(txn)
    except LedgerImbalanceError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Ledger integrity check failed: {e}")

    await log_action(db, "TRANSFER_COMPLETED", actor_user_id=str(user.id), actor_role=user.role,
                      entity_type="transaction", entity_id=str(txn.id), ip_address=get_client_ip(request),
                      details={"amount": float(amount), "recipient_id": str(recipient.id)})
    await db.commit()
    return txn


@router.post("/withdraw", response_model=TransactionOut, status_code=status.HTTP_201_CREATED)
async def withdraw(request: Request, payload: WithdrawRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Withdraw from wallet to an external bank account via the mock gateway."""
    _require_pin_ok(user, payload.pin)
    amount = q2(payload.amount)

    cfg = await _get_config(db)
    split = compute_fee_split(
        amount=amount,
        fee_rate=Decimal("0"),  # withdrawals use a flat fee, not percentage
        reward_rate=Decimal(str(cfg.reward_rate)) / 2,  # smaller reward on withdrawals
        insurance_rate=Decimal(str(cfg.insurance_contribution_rate)),
        flat_fee=Decimal(str(cfg.withdrawal_fee_flat)),
    )
    total_debit = q2(amount + split.fee_amount)

    fraud_result = await evaluate_transaction(db, user, amount, "withdrawal")

    wallet = await get_or_create_account(db, AccountType.user_wallet, user.id)
    if Decimal(str(wallet.balance)) < total_debit:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Insufficient wallet balance to cover amount + fee")

    ledger = LedgerService(db)
    txn = await ledger.start_transaction(
        type=TransactionType.withdrawal,
        initiator_user_id=user.id,
        amount=amount,
        fee_amount=split.fee_amount,
        reward_amount=split.reward_amount,
        insurance_contribution=split.insurance_contribution,
        narration=payload.narration or "Withdrawal to bank account",
        ip_address=get_client_ip(request),
        metadata={"bank_account_number_last4": payload.bank_account_number[-4:], "bank_code": payload.bank_code},
    )

    if fraud_result.blocking:
        await persist_flags(db, user.id, txn.id, fraud_result)
        txn.status = TransactionStatus.flagged
        await log_action(db, "TRANSACTION_BLOCKED_FRAUD", actor_user_id=str(user.id), actor_role=user.role,
                          entity_type="transaction", entity_id=str(txn.id), ip_address=get_client_ip(request))
        await db.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Transaction blocked pending fraud review. Contact support.")
    elif fraud_result.has_flags:
        await persist_flags(db, user.id, txn.id, fraud_result)

    gw_result = await payment_gateway.initiate_withdrawal(
        float(amount), payload.bank_account_number, payload.bank_code, user_reference=str(user.id)
    )
    txn.gateway_reference = gw_result.gateway_reference

    if not gw_result.success:
        await ledger.fail(txn, reason=gw_result.message)
        await log_action(db, "WITHDRAWAL_FAILED", actor_user_id=str(user.id), actor_role=user.role,
                          entity_type="transaction", entity_id=str(txn.id), ip_address=get_client_ip(request))
        await db.commit()
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, gw_result.message)

    reward_pool = await get_or_create_account(db, AccountType.platform_reward_pool)
    insurance_pool = await get_or_create_account(db, AccountType.platform_insurance_pool)
    platform_revenue = await get_or_create_account(db, AccountType.platform_revenue)
    user_reward = await get_or_create_account(db, AccountType.user_reward, user.id)
    user_insurance = await get_or_create_account(db, AccountType.user_insurance, user.id)
    external = await get_or_create_account(db, AccountType.external_gateway)

    try:
        await ledger.post(txn, wallet, "D", total_debit)
        await ledger.post(txn, external, "C", amount)  # principal leaves the platform to the bank
        # The fee portion (total_debit - amount) stays inside the platform and
        # funds reward_pool + insurance_pool + platform_revenue, which must sum
        # to fee_amount for the ledger to balance.
        if split.reward_amount > 0:
            await ledger.post(txn, reward_pool, "C", split.reward_amount)
        if split.insurance_contribution > 0:
            await ledger.post(txn, insurance_pool, "C", split.insurance_contribution)
        if split.platform_net > 0:
            await ledger.post(txn, platform_revenue, "C", split.platform_net)
        # Pools immediately disburse to the user's reward/insurance wallets.
        if split.reward_amount > 0:
            await ledger.post(txn, reward_pool, "D", split.reward_amount)
            await ledger.post(txn, user_reward, "C", split.reward_amount)
        if split.insurance_contribution > 0:
            await ledger.post(txn, insurance_pool, "D", split.insurance_contribution)
            await ledger.post(txn, user_insurance, "C", split.insurance_contribution)
        await ledger.finalize(txn)
    except (InsufficientFundsError, LedgerImbalanceError) as e:
        await db.rollback()
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Ledger error: {e}")

    await log_action(db, "WITHDRAWAL_COMPLETED", actor_user_id=str(user.id), actor_role=user.role,
                      entity_type="transaction", entity_id=str(txn.id), ip_address=get_client_ip(request),
                      details={"amount": float(amount)})
    await db.commit()
    return txn


@router.get("/transactions", response_model=TransactionListOut)
async def list_transactions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    base_stmt = select(Transaction).where(
        or_(Transaction.initiator_user_id == user.id, Transaction.counterparty_user_id == user.id)
    ).order_by(Transaction.created_at.desc())

    count_stmt = select(func.count()).select_from(base_stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = base_stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    items = result.scalars().all()

    return TransactionListOut(items=[_view_for(t, user) for t in items], total=total, page=page, page_size=page_size)


@router.get("/transactions/{transaction_id}", response_model=TransactionOut)
async def get_transaction(transaction_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    result = await db.execute(select(Transaction).where(Transaction.id == transaction_id))
    txn = result.scalar_one_or_none()
    if txn is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transaction not found")
    if str(txn.initiator_user_id) != str(user.id) and str(txn.counterparty_user_id) != str(user.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized to view this transaction")
    return _view_for(txn, user)
