"""My profile: details and profile picture."""
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_client_ip, get_current_user
from app.core.config import settings
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
