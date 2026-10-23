"""My profile: details and profile picture."""
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_client_ip, get_current_user
from datetime import datetime, timezone

from app.core import identity as idt
from app.core.config import settings
from app.core.crypto import encrypt_id, id_fingerprint
from app.core.database import get_db
from app.core.limiter import limiter
from app.models.user import User
from app.services import uploads
from app.services.audit import log_action

router = APIRouter(prefix="/api/profile", tags=["profile"])
_PHOTO_HEADERS = {"Cache-Control": "private, max-age=60"}


@router.get("")
async def my_profile(user: User = Depends(get_current_user)):
    return {
        "full_name": user.full_name, "username": user.username, "account_number": user.account_number,
        "email": user.email, "phone_number": user.phone_number, "account_tier": user.account_tier,
        "kyc_status": user.kyc_status, "has_photo": user.has_photo, "member_since": user.created_at,
    }


@router.post("/photo")
@limiter.limit("10/minute")
async def upload_photo(request: Request, file: UploadFile = File(...), db: AsyncSession = Depends(get_db),
                       user: User = Depends(get_current_user)):
    data = await uploads.read_limited(file, settings.MAX_PHOTO_BYTES)
    processed = await uploads.make_avatar(data)               # validates, crops square, re-encodes, strips metadata
    old = user.profile_photo
    user.profile_photo = uploads.save_file("avatars", processed)
    await log_action(db, "PROFILE_PHOTO_UPDATED", actor_user_id=str(user.id), actor_role=user.role,
                      entity_type="user", entity_id=str(user.id), ip_address=get_client_ip(request))
    await db.commit()
    uploads.delete_file("avatars", old)
    return {"has_photo": True}


@router.get("/photo")
async def my_photo(user: User = Depends(get_current_user)):
    if not user.profile_photo:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No profile photo")
    path = uploads.file_path("avatars", user.profile_photo)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No profile photo")
    return FileResponse(path, media_type="image/jpeg", headers=_PHOTO_HEADERS)


@router.delete("/photo")
async def delete_photo(request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    old = user.profile_photo
    user.profile_photo = None
    await log_action(db, "PROFILE_PHOTO_REMOVED", actor_user_id=str(user.id), actor_role=user.role,
                      entity_type="user", entity_id=str(user.id), ip_address=get_client_ip(request))
    await db.commit()
    uploads.delete_file("avatars", old)
    return {"has_photo": False}


class IdentityUpdate(BaseModel):
    id_type: Literal["national_id", "drivers_license"]
    id_number: str
    consent_id_processing: bool

    @model_validator(mode="after")
    def _check(self):
        if self.consent_id_processing is not True:
            raise ValueError("You must consent to ZionhiltPay processing your ID for identity verification")
        self.id_number = idt.normalize_id_number(self.id_type, self.id_number)
        return self


@router.put("/identity")
@limiter.limit("10/hour")
async def update_identity(request: Request, payload: IdentityUpdate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Correct or add your ID number (for example after a rejection, or if you registered before IDs were collected).
    It goes back into the review queue. A verified ID can only be changed by contacting support."""
    if user.kyc_status == "verified":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Your ID is already verified. Contact support if it needs to change.")
    fp = id_fingerprint(payload.id_type, payload.id_number)
    clash = (await db.execute(select(User.id).where(User.id_type == payload.id_type, User.id_number_hash == fp, User.id != user.id))).first()
    if clash:
        raise HTTPException(status.HTTP_409_CONFLICT, "This ID number is already linked to an account")
    user.id_type, user.id_number_enc, user.id_number_hash = payload.id_type, encrypt_id(payload.id_number), fp
    user.id_number_last4 = payload.id_number[-4:]
    user.id_submitted_at, user.kyc_status = datetime.now(timezone.utc), "submitted"
    user.kyc_note, user.kyc_reviewed_by, user.kyc_reviewed_at = None, None, None
    await log_action(db, "ID_RESUBMITTED", actor_user_id=str(user.id), actor_role=user.role, entity_type="user",
                     entity_id=str(user.id), ip_address=get_client_ip(request), details={"id_type": payload.id_type})   # never the number
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "This ID number is already linked to an account")
    return {"kyc_status": user.kyc_status, "id_type": user.id_type, "id_number_last4": user.id_number_last4}
