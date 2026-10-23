"""
Account levels and the documents needed to move up.

A customer has at most ONE open upgrade request at a time. It starts as a DRAFT that they can fill in over several
visits, becomes PENDING when they submit it, and stays editable while it is under review (each edit is recorded and
flagged to the reviewer). They can aim for Tier 2, or go straight from Tier 1 to Tier 3 by supplying everything
Tier 3 needs. Sensitive values are encrypted (BVN) or stored privately (document photo), and never appear in the
audit trail.
"""
import re
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
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

OPEN = ("draft", "pending")
TIER_NEEDS = {
    2: ["Your ID number (our team verifies it)", "A profile photo", "Your 11-digit BVN"],
    3: ["Everything Tier 2 needs", "Your residential address", "A photo of a utility bill or other proof of address"],
}


async def _lock_customer(db: AsyncSession, user_id) -> None:
    """Queue this customer's upgrade actions one after another (two fast taps must not create two drafts)."""
    await db.execute(select(User.id).where(User.id == user_id).with_for_update())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _missing(user: User, row: TierRequest, documents_only: bool = False) -> list[dict]:
    """What is still needed before this request can be submitted (or must remain in place while it is reviewed)."""
    items = []
    if not row.bvn_enc:
        items.append({"key": "bvn", "label": "Your 11-digit BVN"})
    if row.target_tier == 3:
        if not row.address:
            items.append({"key": "address", "label": "Your residential address"})
        if not row.document_file:
            items.append({"key": "document", "label": "A photo of a utility bill or other proof of address"})
    if not documents_only:
        if user.kyc_status not in ("submitted", "verified"):
            items.insert(0, {"key": "identity", "label": "Your ID number"})
        if not user.has_photo:
            items.insert(0, {"key": "photo", "label": "A profile photo"})
    return items


def _view(user: User, row: TierRequest) -> dict:
    return {
        "id": str(row.id), "target_tier": row.target_tier, "status": row.status, "can_edit": row.status in OPEN,
        "bvn_last4": row.bvn_last4, "address": row.address, "has_document": bool(row.document_file),
        "submitted_at": row.submitted_at, "updated_at": row.updated_at, "edit_count": row.edit_count,
        "review_note": row.review_note, "reviewed_at": row.reviewed_at,
        "missing": _missing(user, row) if row.status in OPEN else [],
    }


async def _open_request(db: AsyncSession, user_id, lock: bool = False) -> TierRequest | None:
    stmt = select(TierRequest).where(TierRequest.user_id == user_id, TierRequest.status.in_(OPEN))
    return (await db.execute(stmt.with_for_update() if lock else stmt)).scalar_one_or_none()


async def _latest_decided(db: AsyncSession, user_id) -> TierRequest | None:
    stmt = (select(TierRequest).where(TierRequest.user_id == user_id, TierRequest.status.in_(("approved", "rejected")))
            .order_by(TierRequest.created_at.desc()).limit(1))
    return (await db.execute(stmt)).scalar_one_or_none()


def _check_target(user: User, target: int) -> None:
    if user.account_tier >= 3:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You are already on the highest tier")
    if target not in (2, 3) or target <= user.account_tier:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Choose Tier {user.account_tier + 1} or higher")


async def _apply_bvn(db: AsyncSession, user: User, row: TierRequest, raw: str) -> None:
    digits = re.sub(r"\s", "", raw or "")
    if not re.fullmatch(r"\d{11}", digits) or len(set(digits)) == 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "BVN must be exactly 11 digits")
    fp = id_fingerprint("bvn", digits)
    other = (await db.execute(select(TierRequest).where(
        TierRequest.bvn_hash == fp, TierRequest.status.in_(["pending", "approved"]), TierRequest.id != row.id))).scalars().first()
    if other is not None and other.user_id != user.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "This BVN is already linked to an account")
    row.bvn_enc, row.bvn_last4 = encrypt_id(digits), digits[-4:]
    # the fingerprint only enforces "one BVN, one customer". If this customer's own earlier request already holds it, don't duplicate it.
    row.bvn_hash = None if other is not None else fp


async def _new_draft(db: AsyncSession, user: User, target: int) -> TierRequest:
    """A new draft starts with whatever the customer already gave us in an earlier request, so nothing is re-typed."""
    row = TierRequest(user_id=user.id, target_tier=target, status="draft", updated_at=_now())
    prev = await _latest_decided(db, user.id)
    if prev is not None:
        row.bvn_enc, row.bvn_last4, row.address = prev.bvn_enc, prev.bvn_last4, prev.address
        row.document_file = uploads.copy_file("documents", prev.document_file)
    db.add(row)
    await db.flush()
    return row


@router.get("")
async def tier_overview(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    wallet = await get_or_create_account(db, AccountType.user_wallet, user.id)
    usage = await limits.overview(db, user, Decimal(str(wallet.balance)))
    open_row = await _open_request(db, user.id)
    last = None if open_row else await _latest_decided(db, user.id)
    tiers = []
    for t in (1, 2, 3):
        lim = limits.tier_limit(t)
        tiers.append({
            "tier": t,
            "daily_limit": float(lim.daily_limit) if lim.daily_limit is not None else None,
            "max_balance": float(lim.max_balance) if lim.max_balance is not None else None,
            "status": "current" if t == user.account_tier else ("done" if t < user.account_tier else "locked"),
            "needs": TIER_NEEDS.get(t, []),
        })
    return {
        "current_tier": user.account_tier,
        "next_tier": user.account_tier + 1 if user.account_tier < 3 else None,
        "targets": [t for t in (2, 3) if t > user.account_tier],
        "usage": usage, "tiers": tiers,
        "identity": {"kyc_status": user.kyc_status, "id_type": user.id_type, "id_number_last4": user.id_number_last4},
        "has_photo": user.has_photo,
        "request": _view(user, open_row) if open_row else None,
        "last_rejection": ({"target_tier": last.target_tier, "review_note": last.review_note, "reviewed_at": last.reviewed_at}
                           if last is not None and last.status == "rejected" else None),
    }


@router.put("/documents")
@limiter.limit("120/hour")
async def save_documents(
    request: Request,
    target_tier: int | None = Form(None),
    bvn: str | None = Form(None),
    address: str | None = Form(None),
    document: UploadFile | None = File(None),
    remove_document: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Save any part of the request. Creates a draft on first use; edits a draft or a request under review in place.
    Omitted fields are left alone. Send an empty `address` to clear it."""
    if user.account_tier >= 3:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You are already on the highest tier")
    await _lock_customer(db, user.id)
    row = await _open_request(db, user.id, lock=True)
    if row is None:
        if target_tier is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose the account level you want to upgrade to")
        _check_target(user, target_tier)
        row = await _new_draft(db, user, target_tier)
    elif target_tier is not None and target_tier != row.target_tier:
        _check_target(user, target_tier)
        row.target_tier = target_tier

    changed, old_doc = [], None
    if bvn is not None and bvn.strip():
        await _apply_bvn(db, user, row, bvn); changed.append("bvn")
    if address is not None:
        addr = " ".join(address.split())
        if addr and not 15 <= len(addr) <= 300:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Enter your full residential address (street, area, city, state)")
        row.address = addr or None; changed.append("address")
    new_doc = None
    if document is not None and document.filename:
        raw = await uploads.read_limited(document, settings.MAX_DOCUMENT_BYTES)
        new_doc = uploads.save_file("documents", await uploads.make_document(raw))
        old_doc, row.document_file = row.document_file, new_doc; changed.append("document")
    elif remove_document and row.document_file:
        old_doc, row.document_file = row.document_file, None; changed.append("document")

    if row.status == "pending":
        # a submission under review must stay complete: people may change things, not remove them
        if _missing(user, row, documents_only=True):
            uploads.delete_file("documents", new_doc)
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Your request is under review, so it must stay complete. Replace items instead of removing them.")
        if changed:
            row.edit_count += 1

    row.updated_at = _now()
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        uploads.delete_file("documents", new_doc)
        raise HTTPException(status.HTTP_409_CONFLICT, "This BVN is already linked to an account")
    await log_action(db, "TIER_REQUEST_EDITED" if row.status == "pending" else "TIER_DRAFT_SAVED", actor_user_id=str(user.id),
                     actor_role=user.role, entity_type="tier_request", entity_id=str(row.id), ip_address=get_client_ip(request),
                     details={"target_tier": row.target_tier, "fields": changed})        # field NAMES only, never the values
    await db.commit()
    uploads.delete_file("documents", old_doc)
    return _view(user, row)


@router.post("/submit")
@limiter.limit("30/hour")
async def submit_request(request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await _lock_customer(db, user.id)
    row = await _open_request(db, user.id, lock=True)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There is nothing to submit yet. Add your documents first.")
    if row.status == "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, "Your request is already submitted and under review")
    _check_target(user, row.target_tier)
    missing = _missing(user, row)
    if missing:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Still needed: " + "; ".join(m["label"] for m in missing))
    row.status, row.submitted_at, row.updated_at = "pending", _now(), _now()
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "This BVN is already linked to an account")
    await log_action(db, "TIER_UPGRADE_REQUESTED", actor_user_id=str(user.id), actor_role=user.role, entity_type="tier_request",
                     entity_id=str(row.id), ip_address=get_client_ip(request), details={"target_tier": row.target_tier})
    await db.commit()
    return _view(user, row)


@router.delete("/documents")
async def withdraw_request(request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Throw away the draft, or withdraw a request that is still under review. Removes the stored document."""
    await _lock_customer(db, user.id)
    row = await _open_request(db, user.id, lock=True)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "You have no open request")
    old_doc, was = row.document_file, row.status
    await db.delete(row)
    await log_action(db, "TIER_REQUEST_WITHDRAWN", actor_user_id=str(user.id), actor_role=user.role, entity_type="tier_request",
                     entity_id=str(row.id), ip_address=get_client_ip(request), details={"was": was})
    await db.commit()
    uploads.delete_file("documents", old_doc)
    return {"withdrawn": True}


@router.get("/documents/file")
async def my_document(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Your own proof-of-address photo, so you can check what you uploaded."""
    row = await _open_request(db, user.id)
    if row is None or not row.document_file:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No document")
    path = uploads.file_path("documents", row.document_file)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No document")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, no-store"})
