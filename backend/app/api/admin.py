from datetime import datetime, timezone, timedelta
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User, UserRole
from app.models.account import Account, AccountType
from app.models.transaction import Transaction, TransactionStatus
from app.models.fraud import FraudFlag
from app.models.device import InsuranceClaim, Device, DeviceStatus
from app.models.config import PlatformConfig
from app.models.audit import AuditLog
from app.schemas.admin import (
    KycDecisionRequest, AdminUserOut, FreezeAccountRequest, ReviewClaimRequest, ResolveFraudFlagRequest,
    PlatformStatsOut, ConfigUpdateRequest,
)
from app.schemas.wallet import TransactionOut
from app.services.ledger import LedgerService, get_or_create_account, q2
from app.services.audit import log_action
from app.api.deps import get_current_admin, get_current_super_admin, get_client_ip
from app.core.crypto import decrypt_id
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Literal
from app.models.tier import TierRequest
from app.models.loan import Loan
from app.services import uploads
from app.core.limiter import limiter
from app.models.transaction import TransactionType

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users", response_model=list[AdminUserOut])
async def list_users(
    q: str | None = Query(None, description="Search by name, username, account number, email, or phone"),
    kyc_status: str | None = Query(None, description="not_submitted | submitted | verified | rejected"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    stmt = select(User)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(User.full_name.ilike(like), User.email.ilike(like), User.phone_number.ilike(like),
                              User.username.ilike(like), User.account_number.ilike(like)))
    if kyc_status:
        stmt = stmt.where(User.kyc_status == kyc_status)
    stmt = stmt.order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/users/{user_id}", response_model=AdminUserOut)
async def get_user(user_id: str, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return target


@router.post("/users/{user_id}/kyc")
async def review_kyc(user_id: uuid.UUID, request: Request, payload: KycDecisionRequest,
                     db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    """Approve or reject a submitted identity document. Approval lifts the user to KYC level 1."""
    target = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if target.id == admin.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot review your own identity document")
    if not target.id_number_enc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This user has not submitted an ID")

    target.kyc_status = "verified" if payload.decision == "verify" else "rejected"
    target.kyc_level = max(target.kyc_level, 1) if payload.decision == "verify" else 0
    target.kyc_reviewed_by = admin.id
    target.kyc_reviewed_at = datetime.now(timezone.utc)
    target.kyc_note = payload.note

    await log_action(db, f"KYC_{payload.decision.upper()}", actor_user_id=str(admin.id), actor_role=admin.role,
                      entity_type="user", entity_id=str(target.id), ip_address=get_client_ip(request),
                      details={"note": payload.note, "id_type": target.id_type})
    await db.commit()
    return {"message": f"KYC {target.kyc_status}", "user_id": str(target.id), "kyc_status": target.kyc_status}


@router.post("/users/{user_id}/kyc/reveal")
@limiter.limit("10/minute")
async def reveal_id_number(user_id: uuid.UUID, request: Request, db: AsyncSession = Depends(get_db),
                           admin: User = Depends(get_current_super_admin)):
    """Decrypt a user's ID number for manual verification. Super-admin only and always audit-logged
    (who looked at whose ID, and when - never the number itself)."""
    target = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if target is None or not target.id_number_enc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No ID on file for that user")
    try:
        number = decrypt_id(target.id_number_enc)
    except ValueError as exc:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(exc))
    await log_action(db, "KYC_ID_REVEALED", actor_user_id=str(admin.id), actor_role=admin.role,
                      entity_type="user", entity_id=str(target.id), ip_address=get_client_ip(request),
                      details={"id_type": target.id_type})
    await db.commit()
    return {"id_type": target.id_type, "id_number": number}


@router.get("/transactions")
async def list_all_transactions(
    q: str | None = Query(None, description="Reference, username, account number, or email"),
    status_filter: str | None = Query(None, alias="status"),
    type_filter: str | None = Query(None, alias="type"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    sender = User.__table__.alias("sender")
    stmt = (
        select(Transaction, sender.c.username, sender.c.account_number, sender.c.full_name)
        .outerjoin(sender, sender.c.id == Transaction.initiator_user_id)
        .order_by(Transaction.created_at.desc())
    )
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Transaction.reference.ilike(like), sender.c.username.ilike(like),
                              sender.c.account_number.ilike(like), sender.c.email.ilike(like)))
    if status_filter:
        stmt = stmt.where(Transaction.status == status_filter)
    if type_filter:
        stmt = stmt.where(Transaction.type == type_filter)
    rows = (await db.execute(stmt.offset((page - 1) * page_size).limit(page_size))).all()
    return [
        {
            "id": str(t.id), "reference": t.reference, "type": t.type.value, "status": t.status.value,
            "amount": float(t.amount), "fee_amount": float(t.fee_amount),
            "from_username": uname, "from_account_number": acct, "from_name": name,
            "narration": t.narration, "created_at": t.created_at.isoformat(),
        }
        for t, uname, acct, name in rows
    ]


@router.post("/users/{user_id}/freeze")
async def freeze_user(user_id: str, request: Request, payload: FreezeAccountRequest, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if target.role in (UserRole.admin, UserRole.super_admin) and admin.role != UserRole.super_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only a super admin can freeze an admin account")

    target.is_frozen = True
    target.freeze_reason = payload.reason

    await log_action(db, "ADMIN_FREEZE_ACCOUNT", actor_user_id=str(admin.id), actor_role=admin.role,
                      entity_type="user", entity_id=str(target.id), ip_address=get_client_ip(request),
                      details={"reason": payload.reason})
    await db.commit()
    return {"message": "Account frozen", "user_id": str(target.id)}


@router.post("/users/{user_id}/unfreeze")
async def unfreeze_user(user_id: str, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    target.is_frozen = False
    target.freeze_reason = None

    await log_action(db, "ADMIN_UNFREEZE_ACCOUNT", actor_user_id=str(admin.id), actor_role=admin.role,
                      entity_type="user", entity_id=str(target.id), ip_address=get_client_ip(request))
    await db.commit()
    return {"message": "Account unfrozen", "user_id": str(target.id)}


@router.get("/fraud-flags")
async def list_fraud_flags(
    resolved: bool | None = None,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    stmt = select(FraudFlag).order_by(FraudFlag.created_at.desc())
    if resolved is not None:
        stmt = stmt.where(FraudFlag.resolved == resolved)
    result = await db.execute(stmt.limit(200))
    flags = result.scalars().all()
    return [
        {
            "id": str(f.id), "user_id": str(f.user_id) if f.user_id else None,
            "transaction_id": str(f.transaction_id) if f.transaction_id else None,
            "rule_code": f.rule_code, "severity": f.severity.value,
            "details": f.details, "resolved": f.resolved, "created_at": f.created_at.isoformat(),
        } for f in flags
    ]


@router.post("/fraud-flags/{flag_id}/resolve")
async def resolve_fraud_flag(flag_id: str, request: Request, payload: ResolveFraudFlagRequest, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    result = await db.execute(select(FraudFlag).where(FraudFlag.id == flag_id))
    flag = result.scalar_one_or_none()
    if flag is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fraud flag not found")

    flag.resolved = True
    flag.resolved_by = admin.id
    flag.resolved_at = datetime.now(timezone.utc)

    await log_action(db, "FRAUD_FLAG_RESOLVED", actor_user_id=str(admin.id), actor_role=admin.role,
                      entity_type="fraud_flag", entity_id=str(flag.id), ip_address=get_client_ip(request),
                      details={"note": payload.resolution_note})
    await db.commit()
    return {"message": "Fraud flag resolved"}


@router.get("/claims")
async def list_claims(status_filter: str | None = Query(None, alias="status"), db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    stmt = select(InsuranceClaim).order_by(InsuranceClaim.created_at.desc())
    if status_filter:
        stmt = stmt.where(InsuranceClaim.status == status_filter)
    result = await db.execute(stmt.limit(200))
    return result.scalars().all()


@router.post("/claims/{claim_id}/review", response_model=TransactionOut)
async def review_claim(claim_id: str, request: Request, payload: ReviewClaimRequest, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    result = await db.execute(select(InsuranceClaim).where(InsuranceClaim.id == claim_id))
    claim = result.scalar_one_or_none()
    if claim is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Claim not found")
    if claim.status not in ("submitted", "under_review"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Claim already {claim.status}")

    claim.reviewed_by = admin.id
    claim.reviewed_at = datetime.now(timezone.utc)

    if not payload.approve:
        claim.status = "rejected"
        await log_action(db, "CLAIM_REJECTED", actor_user_id=str(admin.id), actor_role=admin.role,
                          entity_type="insurance_claim", entity_id=str(claim.id), ip_address=get_client_ip(request),
                          details={"note": payload.review_note})
        await db.commit()
        return {"message": "Claim rejected"}

    approved_amount = q2(payload.approved_amount if payload.approved_amount is not None else claim.requested_amount)
    device_result = await db.execute(select(Device).where(Device.id == claim.device_id))
    device = device_result.scalar_one_or_none()
    user_result = await db.execute(select(User).where(User.id == claim.user_id))
    claim_user = user_result.scalar_one_or_none()

    insurance_pool = await get_or_create_account(db, AccountType.platform_insurance_pool)
    user_insurance = await get_or_create_account(db, AccountType.user_insurance, claim.user_id)
    user_wallet = await get_or_create_account(db, AccountType.user_wallet, claim.user_id)

    if Decimal(str(user_insurance.balance)) < approved_amount:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Approved amount exceeds the user's accrued insurance balance")

    ledger = LedgerService(db)
    txn = await ledger.start_transaction(
        type=TransactionType.insurance_claim_payout,
        initiator_user_id=claim.user_id,
        amount=approved_amount,
        narration=f"Insurance payout for claim {claim.id}",
        ip_address=get_client_ip(request),
        metadata={"claim_id": str(claim.id), "device_id": str(claim.device_id), "approved_by": str(admin.id)},
    )
    await ledger.post(txn, user_insurance, "D", approved_amount)
    await ledger.post(txn, user_wallet, "C", approved_amount)
    await ledger.finalize(txn)

    claim.status = "paid"
    claim.approved_amount = approved_amount
    if device:
        device.status = DeviceStatus.claim_paid

    await log_action(db, "CLAIM_APPROVED_PAID", actor_user_id=str(admin.id), actor_role=admin.role,
                      entity_type="insurance_claim", entity_id=str(claim.id), ip_address=get_client_ip(request),
                      details={"approved_amount": float(approved_amount)})
    await db.commit()
    return txn


@router.get("/stats", response_model=PlatformStatsOut)
async def platform_stats(db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    total_users = (await db.execute(select(func.count(User.id)))).scalar_one()
    active_users = (await db.execute(select(func.count(User.id)).where(User.is_active == True, User.is_frozen == False))).scalar_one()  # noqa: E712
    frozen_users = (await db.execute(select(func.count(User.id)).where(User.is_frozen == True))).scalar_one()  # noqa: E712

    wallet_sum = (await db.execute(select(func.coalesce(func.sum(Account.balance), 0)).where(Account.account_type == AccountType.user_wallet))).scalar_one()
    reward_liability = (await db.execute(select(func.coalesce(func.sum(Account.balance), 0)).where(Account.account_type == AccountType.user_reward))).scalar_one()
    insurance_liability = (await db.execute(select(func.coalesce(func.sum(Account.balance), 0)).where(Account.account_type == AccountType.user_insurance))).scalar_one()
    platform_revenue = (await db.execute(select(func.coalesce(func.sum(Account.balance), 0)).where(Account.account_type == AccountType.platform_revenue))).scalar_one()

    total_txns = (await db.execute(select(func.count(Transaction.id)))).scalar_one()
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    txns_today = (await db.execute(select(func.count(Transaction.id)).where(Transaction.created_at >= today_start))).scalar_one()

    open_flags = (await db.execute(select(func.count(FraudFlag.id)).where(FraudFlag.resolved == False))).scalar_one()  # noqa: E712
    pending_claims = (await db.execute(select(func.count(InsuranceClaim.id)).where(InsuranceClaim.status.in_(["submitted", "under_review"])))).scalar_one()

    pending_tier = (await db.execute(select(func.count(TierRequest.id)).where(TierRequest.status == "pending"))).scalar_one()
    loan_rows = (await db.execute(select(Loan).where(Loan.status == "active"))).scalars().all()
    loans_outstanding = sum(float(l.total_due) - float(l.principal_repaid) - float(l.interest_repaid) for l in loan_rows)
    return PlatformStatsOut(
        pending_tier_requests=pending_tier, loans_outstanding=round(loans_outstanding, 2), active_loans=len(loan_rows),
        total_users=total_users,
        active_users=active_users,
        frozen_users=frozen_users,
        total_wallet_balance=float(wallet_sum),
        total_reward_pool_liability=float(reward_liability),
        total_insurance_pool_liability=float(insurance_liability),
        platform_revenue_balance=float(platform_revenue),
        total_transactions=total_txns,
        transactions_today=txns_today,
        open_fraud_flags=open_flags,
        pending_claims=pending_claims,
    )


@router.get("/audit-logs")
async def list_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    logs = result.scalars().all()
    return [
        {
            "id": str(l.id), "actor_user_id": str(l.actor_user_id) if l.actor_user_id else None,
            "actor_role": l.actor_role.value if l.actor_role else None,
            "action": l.action, "entity_type": l.entity_type,
            "entity_id": str(l.entity_id) if l.entity_id else None,
            "ip_address": l.ip_address, "details": l.details, "created_at": l.created_at.isoformat(),
        } for l in logs
    ]


@router.get("/config")
async def get_config(db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    result = await db.execute(select(PlatformConfig).where(PlatformConfig.id == 1))
    cfg = result.scalar_one_or_none()
    if cfg is None:
        cfg = PlatformConfig()
        db.add(cfg)
        await db.commit()
    return cfg


@router.patch("/config")
async def update_config(request: Request, payload: ConfigUpdateRequest, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_super_admin)):
    """Only super admins may change platform economics/fraud thresholds."""
    result = await db.execute(select(PlatformConfig).where(PlatformConfig.id == 1))
    cfg = result.scalar_one_or_none()
    if cfg is None:
        cfg = PlatformConfig()
        db.add(cfg)
        await db.flush()

    changes = {}
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(cfg, field, value)
            changes[field] = value

    await log_action(db, "PLATFORM_CONFIG_UPDATED", actor_user_id=str(admin.id), actor_role=admin.role,
                      entity_type="platform_config", ip_address=get_client_ip(request), details=changes)
    await db.commit()
    return cfg



# ----------------------------------------------------------------------------
# Tier upgrades, loans, profile photos
# ----------------------------------------------------------------------------
class TierDecision(BaseModel):
    decision: Literal["approve", "reject"]
    note: str | None = None


def _tier_request_view(r: TierRequest, u: User) -> dict:
    return {
        "id": str(r.id), "target_tier": r.target_tier, "status": r.status, "created_at": r.created_at,
        "reviewed_at": r.reviewed_at, "review_note": r.review_note, "bvn_last4": r.bvn_last4, "address": r.address,
        "has_document": bool(r.document_file),
        "user": {"id": str(u.id), "full_name": u.full_name, "username": u.username, "account_number": u.account_number,
                 "current_tier": u.account_tier, "kyc_status": u.kyc_status, "has_photo": u.has_photo},
    }


@router.get("/tier-requests")
async def list_tier_requests(status_filter: str | None = Query("pending", alias="status"), db: AsyncSession = Depends(get_db),
                             admin: User = Depends(get_current_admin)):
    stmt = select(TierRequest, User).join(User, User.id == TierRequest.user_id).order_by(TierRequest.created_at.desc()).limit(200)
    if status_filter:
        stmt = stmt.where(TierRequest.status == status_filter)
    return [_tier_request_view(r, u) for r, u in (await db.execute(stmt)).all()]


@router.post("/tier-requests/{request_id}/decision")
async def decide_tier_request(request_id: uuid.UUID, request: Request, payload: TierDecision,
                              db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    row = (await db.execute(select(TierRequest).where(TierRequest.id == request_id).with_for_update())).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Request not found")
    if row.status != "pending":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"This request was already {row.status}")
    user = (await db.execute(select(User).where(User.id == row.user_id))).scalar_one()
    if user.id == admin.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You cannot review your own upgrade request")
    if payload.decision == "approve":
        if row.target_tier == 2 and user.kyc_status != "verified":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Verify this customer's ID first (Users & KYC)")
        if row.target_tier != user.account_tier + 1:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "The customer's tier changed since this request was made")
        user.account_tier = row.target_tier
        row.status = "approved"
    else:
        row.status = "rejected"
    row.reviewed_by, row.reviewed_at, row.review_note = admin.id, datetime.now(timezone.utc), payload.note
    await log_action(db, f"TIER_{row.status.upper()}", actor_user_id=str(admin.id), actor_role=admin.role,
                      entity_type="tier_request", entity_id=str(row.id), ip_address=get_client_ip(request),
                      details={"target_tier": row.target_tier, "user_id": str(user.id), "note": payload.note})
    await db.commit()
    return {"status": row.status, "user_tier": user.account_tier}


@router.get("/tier-requests/{request_id}/document")
async def tier_request_document(request_id: uuid.UUID, request: Request, db: AsyncSession = Depends(get_db),
                                admin: User = Depends(get_current_admin)):
    row = (await db.execute(select(TierRequest).where(TierRequest.id == request_id))).scalar_one_or_none()
    if row is None or not row.document_file:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No document")
    path = uploads.file_path("documents", row.document_file)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No document")
    await log_action(db, "TIER_DOCUMENT_VIEWED", actor_user_id=str(admin.id), actor_role=admin.role,
                      entity_type="tier_request", entity_id=str(row.id), ip_address=get_client_ip(request))
    await db.commit()
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, no-store"})


@router.post("/tier-requests/{request_id}/reveal-bvn")
@limiter.limit("10/minute")
async def reveal_bvn(request_id: uuid.UUID, request: Request, db: AsyncSession = Depends(get_db),
                     admin: User = Depends(get_current_super_admin)):
    row = (await db.execute(select(TierRequest).where(TierRequest.id == request_id))).scalar_one_or_none()
    if row is None or not row.bvn_enc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No BVN on file for that request")
    try:
        bvn = decrypt_id(row.bvn_enc)
    except ValueError as exc:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(exc))
    await log_action(db, "BVN_REVEALED", actor_user_id=str(admin.id), actor_role=admin.role, entity_type="tier_request",
                      entity_id=str(row.id), ip_address=get_client_ip(request))
    await db.commit()
    return {"bvn": bvn}


@router.get("/loans")
async def list_all_loans(status_filter: str | None = Query(None, alias="status"), page: int = Query(1, ge=1),
                         page_size: int = Query(25, ge=1, le=100), db: AsyncSession = Depends(get_db),
                         admin: User = Depends(get_current_admin)):
    from app.api.loans import loan_out
    stmt = select(Loan, User).join(User, User.id == Loan.user_id).order_by(Loan.disbursed_at.desc())
    if status_filter:
        stmt = stmt.where(Loan.status == status_filter)
    rows = (await db.execute(stmt.offset((page - 1) * page_size).limit(page_size))).all()
    return [{**loan_out(l), "user": {"full_name": u.full_name, "username": u.username, "account_number": u.account_number}} for l, u in rows]


@router.get("/users/{user_id}/photo")
async def user_photo(user_id: uuid.UUID, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    u = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if u is None or not u.profile_photo:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No photo")
    path = uploads.file_path("avatars", u.profile_photo)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No photo")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=60"})
