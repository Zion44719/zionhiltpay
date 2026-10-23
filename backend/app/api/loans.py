"""
Loans. A deliberately simple, transparent product: a flat fee (interest) fixed at the moment you accept, one active
loan at a time, repay any amount early. Money moves through the same balanced ledger as everything else:
  disbursement:  platform_loan_pool (D)  ->  your wallet (C)
  repayment:     your wallet (D)         ->  platform_loan_pool (C, principal part) + platform_revenue (C, interest part)
Lending is regulated (CBN / FCCPC digital-lending rules). This is software, not a licence: do not offer real loans
without proper registration and advice.
"""
import math
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_client_ip, get_current_user
from app.api.wallet import _require_pin_ok
from app.core.config import settings
from app.core.database import get_db
from app.core.security import generate_reference
from app.models.account import AccountType
from app.models.loan import Loan
from app.models.transaction import TransactionType
from app.models.user import User
from app.services.audit import log_action
from app.services.ledger import InsufficientFundsError, LedgerImbalanceError, LedgerService, get_or_create_account, q2
from app.services.limits import naira, tier_limit

router = APIRouter(prefix="/api/loans", tags=["loans"])


def _cap(tier: int) -> Decimal:
    if tier >= 3:
        return Decimal(str(settings.LOAN_TIER3_MAX))
    if tier == 2:
        return Decimal(str(settings.LOAN_TIER2_MAX))
    return Decimal("0")


def make_quote(principal: Decimal, days: int) -> dict:
    rate = Decimal(str(settings.LOAN_INTEREST_RATE_30D))
    interest = q2(principal * rate * Decimal(days) / Decimal(30))
    return {"principal": float(principal), "interest": float(interest), "total_due": float(principal + interest),
            "tenor_days": days, "rate_30d": float(rate),
            "due_at": datetime.now(timezone.utc) + timedelta(days=days)}


def loan_out(loan: Loan) -> dict:
    repaid = Decimal(str(loan.principal_repaid)) + Decimal(str(loan.interest_repaid))
    outstanding = Decimal(str(loan.total_due)) - repaid
    due = loan.due_at if loan.due_at.tzinfo else loan.due_at.replace(tzinfo=timezone.utc)
    return {
        "id": str(loan.id), "reference": loan.reference, "principal": float(loan.principal), "interest": float(loan.interest),
        "total_due": float(loan.total_due), "repaid": float(repaid), "outstanding": float(outstanding),
        "status": loan.status, "is_overdue": loan.status == "active" and due < datetime.now(timezone.utc),
        "tenor_days": loan.tenor_days, "interest_rate_30d": float(loan.interest_rate_30d),
        "disbursed_at": loan.disbursed_at, "due_at": loan.due_at, "closed_at": loan.closed_at,
    }


async def _active_loan(db: AsyncSession, user_id):
    return (await db.execute(select(Loan).where(Loan.user_id == user_id, Loan.status == "active"))).scalar_one_or_none()


async def _offer(db: AsyncSession, user: User, balance: Decimal) -> dict:
    reasons = []
    if not settings.LOANS_ENABLED:
        reasons.append("Loans are not available right now.")
    cap = _cap(user.account_tier)
    if cap <= 0:
        reasons.append("Upgrade to Tier 2 to access loans.")
    active = await _active_loan(db, user.id)
    if active:
        reasons.append("Repay your current loan before borrowing again.")
    lim = tier_limit(user.account_tier)
    room = (lim.max_balance - balance) if lim.max_balance is not None else None
    max_amount = cap if room is None else min(cap, room)
    max_amount = Decimal(math.floor(max(max_amount, Decimal("0"))))
    min_amount = Decimal(str(settings.LOAN_MIN_AMOUNT))
    if cap > 0 and max_amount < min_amount and not active:
        reasons.append("Your wallet balance is too close to your tier's limit to receive a loan right now.")
    return {
        "enabled": settings.LOANS_ENABLED, "eligible": not reasons, "reasons": reasons, "tier": user.account_tier,
        "min_amount": float(min_amount), "max_amount": float(max_amount) if not reasons else 0.0,
        "tenors": [{"days": d, "interest_percent": round(float(settings.LOAN_INTEREST_RATE_30D) * d / 30 * 100, 2)} for d in settings.LOAN_TENORS_DAYS],
        "rate_30d_percent": round(float(settings.LOAN_INTEREST_RATE_30D) * 100, 2),
        "active_loan": loan_out(active) if active else None,
    }


class QuoteRequest(BaseModel):
    amount: float
    tenor_days: int

    @field_validator("amount")
    @classmethod
    def _a(cls, v):
        if v <= 0:
            raise ValueError("Amount must be greater than zero")
        return round(v, 2)


class ApplyRequest(QuoteRequest):
    pin: str
    accept_terms: bool


class RepayRequest(BaseModel):
    amount: float
    pin: str

    @field_validator("amount")
    @classmethod
    def _a(cls, v):
        if v <= 0:
            raise ValueError("Amount must be greater than zero")
        return round(v, 2)


def _check_request(offer: dict, amount: Decimal, days: int) -> None:
    if not offer["eligible"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, offer["reasons"][0])
    if days not in settings.LOAN_TENORS_DAYS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose one of the available repayment periods")
    if amount < Decimal(str(offer["min_amount"])):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"The minimum loan is {naira(offer['min_amount'])}")
    if amount > Decimal(str(offer["max_amount"])):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"You can borrow up to {naira(offer['max_amount'])} right now")


@router.get("/offer")
async def loan_offer(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    wallet = await get_or_create_account(db, AccountType.user_wallet, user.id)
    return await _offer(db, user, Decimal(str(wallet.balance)))


@router.post("/quote")
async def loan_quote(payload: QuoteRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    wallet = await get_or_create_account(db, AccountType.user_wallet, user.id)
    offer = await _offer(db, user, Decimal(str(wallet.balance)))
    amount = q2(Decimal(str(payload.amount)))
    _check_request(offer, amount, payload.tenor_days)
    return make_quote(amount, payload.tenor_days)


@router.get("")
async def my_loans(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    rows = (await db.execute(select(Loan).where(Loan.user_id == user.id).order_by(Loan.disbursed_at.desc()))).scalars().all()
    return [loan_out(r) for r in rows]


@router.post("/apply", status_code=status.HTTP_201_CREATED)
async def apply_for_loan(request: Request, payload: ApplyRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    _require_pin_ok(user, payload.pin)
    if not payload.accept_terms:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Please confirm that you accept the loan terms")
    amount = q2(Decimal(str(payload.amount)))

    wallet = await get_or_create_account(db, AccountType.user_wallet, user.id)
    pool = await get_or_create_account(db, AccountType.platform_loan_pool)
    ledger = LedgerService(db)
    await ledger.lock(wallet)
    await db.refresh(wallet)
    offer = await _offer(db, user, Decimal(str(wallet.balance)))      # re-checked on fresh, locked data
    _check_request(offer, amount, payload.tenor_days)

    quote = make_quote(amount, payload.tenor_days)
    interest = q2(Decimal(str(quote["interest"])))
    loan = Loan(
        reference=generate_reference("LN"), user_id=user.id, principal=amount, interest=interest,
        total_due=amount + interest, tenor_days=payload.tenor_days,
        interest_rate_30d=Decimal(str(settings.LOAN_INTEREST_RATE_30D)), due_at=quote["due_at"],
    )
    db.add(loan)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "You already have an active loan")

    txn = await ledger.start_transaction(
        type=TransactionType.loan_disbursement, initiator_user_id=user.id, amount=amount,
        narration=f"Loan {loan.reference}", ip_address=get_client_ip(request),
        metadata={"loan_reference": loan.reference, "interest": float(interest), "tenor_days": payload.tenor_days},
    )
    await ledger.lock(pool)
    try:
        await ledger.post(txn, pool, "D", amount)
        await ledger.post(txn, wallet, "C", amount)
        await ledger.finalize(txn)
    except (InsufficientFundsError, LedgerImbalanceError) as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Ledger error: {exc}")
    await log_action(db, "LOAN_DISBURSED", actor_user_id=str(user.id), actor_role=user.role, entity_type="loan",
                      entity_id=str(loan.id), ip_address=get_client_ip(request),
                      details={"principal": float(amount), "interest": float(interest), "tenor_days": payload.tenor_days})
    await db.commit()
    return {**loan_out(loan), "transaction_reference": txn.reference}


@router.post("/{loan_id}/repay")
async def repay_loan(loan_id: str, request: Request, payload: RepayRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    _require_pin_ok(user, payload.pin)
    wallet = await get_or_create_account(db, AccountType.user_wallet, user.id)
    pool = await get_or_create_account(db, AccountType.platform_loan_pool)
    revenue = await get_or_create_account(db, AccountType.platform_revenue)
    ledger = LedgerService(db)
    await ledger.lock(wallet)
    await db.refresh(wallet)

    try:
        loan = (await db.execute(select(Loan).where(Loan.id == loan_id, Loan.user_id == user.id).with_for_update())).scalar_one_or_none()
    except Exception:  # an id that isn't a UUID
        loan = None
    if loan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Loan not found")
    if loan.status != "active":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This loan has already been repaid")

    amount = q2(Decimal(str(payload.amount)))
    outstanding = Decimal(str(loan.total_due)) - Decimal(str(loan.principal_repaid)) - Decimal(str(loan.interest_repaid))
    if amount > outstanding:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"You only owe {naira(outstanding)}")
    if Decimal(str(wallet.balance)) < amount:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Insufficient wallet balance")

    interest_left = Decimal(str(loan.interest)) - Decimal(str(loan.interest_repaid))
    interest_part = min(amount, interest_left)          # interest is paid off first
    principal_part = amount - interest_part

    txn = await ledger.start_transaction(
        type=TransactionType.loan_repayment, initiator_user_id=user.id, amount=amount,
        narration=f"Repayment for loan {loan.reference}", ip_address=get_client_ip(request),
        metadata={"loan_reference": loan.reference, "interest_part": float(interest_part), "principal_part": float(principal_part)},
    )
    await ledger.lock(pool, revenue)
    try:
        await ledger.post(txn, wallet, "D", amount)
        if principal_part > 0:
            await ledger.post(txn, pool, "C", principal_part)
        if interest_part > 0:
            await ledger.post(txn, revenue, "C", interest_part)
        await ledger.finalize(txn)
    except InsufficientFundsError:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Insufficient wallet balance")
    except LedgerImbalanceError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Ledger error: {exc}")

    loan.interest_repaid = Decimal(str(loan.interest_repaid)) + interest_part
    loan.principal_repaid = Decimal(str(loan.principal_repaid)) + principal_part
    if outstanding - amount == 0:
        loan.status, loan.closed_at = "repaid", datetime.now(timezone.utc)
    await log_action(db, "LOAN_REPAYMENT", actor_user_id=str(user.id), actor_role=user.role, entity_type="loan",
                      entity_id=str(loan.id), ip_address=get_client_ip(request),
                      details={"amount": float(amount), "closed": loan.status == "repaid"})
    await db.commit()
    return {**loan_out(loan), "transaction_reference": txn.reference}
