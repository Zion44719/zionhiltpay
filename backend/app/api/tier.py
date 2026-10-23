"""Account tiers: see your limits and what each level needs, and request an upgrade."""
import re
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_client_ip, get_current_user
from app.core.config import settings
from app.core.crypto import encrypt_id, id_fingerprint
from app.core.database import get_db
from app.core.limiter import limiter
from app.models.account import AccountType
from app.models.tier import TierRequest
from app.models.user import User
from app.services import limits, uploads
from app.services.audit import log_action
from app.services.ledger import get_or_create_account

router = APIRouter(prefix="/api/tier", tags=["tier"])


def _requirements(user: User, target: int) -> list[dict]:
    if target == 2:
        return [
            {"key": "id_verified", "label": "Your ID has been verified by our team", "done": user.kyc_status == "verified",
             "detail": {"submitted": "Under review", "rejected": "Rejected: contact support", "not_submitted": "No ID on file"}.get(user.kyc_status)},
            {"key": "photo", "label": "Add a profile photo", "done": user.has_photo},
            {"key": "bvn", "label": "Provide your 11-digit BVN", "done": False, "at_request": True},
        ]
    return [
        {"key": "tier2", "label": "Reach Tier 2 first", "done": user.account_tier >= 2},
        {"key": "address", "label": "Your residential address", "done": False, "at_request": True},
        {"key": "document", "label": "A clear photo of a utility bill or other proof of address", "done": False, "at_request": True},
    ]


def _request_out(r: TierRequest) -> dict:
    return {"id": str(r.id), "target_tier": r.target_tier, "status": r.status, "review_note": r.review_note,
            "created_at": r.created_at, "reviewed_at": r.reviewed_at}


@router.get("")
async def tier_overview(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    wallet = await get_or_create_account(db, AccountType.user_wallet, user.id)
    usage = await limits.overview(db, user, Decimal(str(wallet.balance)))
    reqs = (await db.execute(select(TierRequest).where(TierRequest.user_id == user.id).order_by(TierRequest.created_at.desc()))).scalars().all()
    pending = next((r for r in reqs if r.status == "pending"), None)
    last_rejected = next((r for r in reqs if r.status == "rejected" and r.target_tier == user.account_tier + 1), None)
    tiers = []
    for t in (1, 2, 3):
        lim = limits.tier_limit(t)
        tiers.append({
            "tier": t,
            "daily_limit": float(lim.daily_limit) if lim.daily_limit is not None else None,
            "max_balance": float(lim.max_balance) if lim.max_balance is not None else None,
            "status": "current" if t == user.account_tier else ("done" if t < user.account_tier else "locked"),
            "requirements": _requirements(user, t) if t > 1 else [],
        })
    next_tier = user.account_tier + 1 if user.account_tier < 3 else None
    return {
        "current_tier": user.account_tier, "next_tier": next_tier, "usage": usage, "tiers": tiers,
        "pending_request": _request_out(pending) if pending else None,
        "last_rejection": _request_out(last_rejected) if last_rejected else None,
    }


@router.post("/upgrade", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/hour")
async def request_upgrade(
    request: Request,
    target_tier: int = Form(...),
    bvn: str | None = Form(None),
    address: str | None = Form(None),
    document: UploadFile | None = File(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.account_tier >= 3:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You are already on the highest tier")
    if target_tier != user.account_tier + 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"You can request Tier {user.account_tier + 1} next")
    if (await db.execute(select(TierRequest.id).where(TierRequest.user_id == user.id, TierRequest.status == "pending"))).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "You already have an upgrade request under review")

    row = TierRequest(user_id=user.id, target_tier=target_tier)
    doc_name = None
    if target_tier == 2:
        if user.kyc_status != "verified":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Your ID must be verified by our team before you can move to Tier 2")
        if not user.has_photo:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Please add a profile photo first")
        digits = re.sub(r"\s", "", bvn or "")
        if not re.fullmatch(r"\d{11}", digits) or len(set(digits)) == 1:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "BVN must be exactly 11 digits")
        fp = id_fingerprint("bvn", digits)
        taken = (await db.execute(select(TierRequest.id).where(TierRequest.bvn_hash == fp, TierRequest.status.in_(["pending", "approved"])))).first()
        if taken:
            raise HTTPException(status.HTTP_409_CONFLICT, "This BVN is already linked to an account")
        row.bvn_enc, row.bvn_hash, row.bvn_last4 = encrypt_id(digits), fp, digits[-4:]
    else:
        addr = " ".join((address or "").split())
        if not 15 <= len(addr) <= 300:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Enter your full residential address (street, area, city, state)")
        if document is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Attach a photo of a utility bill or other proof of address")
        raw = await uploads.read_limited(document, settings.MAX_DOCUMENT_BYTES)
        doc_name = uploads.save_file("documents", await uploads.make_document(raw))
        row.address, row.document_file = addr, doc_name

    db.add(row)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        uploads.delete_file("documents", doc_name)
        raise HTTPException(status.HTTP_409_CONFLICT, "You already have an upgrade request under review, or this BVN is already in use")
    await log_action(db, "TIER_UPGRADE_REQUESTED", actor_user_id=str(user.id), actor_role=user.role,
                      entity_type="tier_request", entity_id=str(row.id), ip_address=get_client_ip(request),
                      details={"target_tier": target_tier})          # never the BVN or the address
    await db.commit()
    return _request_out(row)
