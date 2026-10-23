"""
Partner logos for the landing page.

Public (no login needed, because the landing page is public):  list active partners, fetch a logo image.
Admin only:  create, edit, reorder, hide and delete partners, and upload their logos.

Only show companies you genuinely work with, and only logos you have permission to display.
"""
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_client_ip, get_current_admin
from app.core.config import settings
from app.core.database import get_db
from app.core.limiter import limiter
from app.models.partner import Partner
from app.models.user import User
from app.services import uploads
from app.services.audit import log_action

public = APIRouter(prefix="/api/partners", tags=["partners"])
admin = APIRouter(prefix="/api/admin/partners", tags=["admin"])


def _clean_name(raw: str | None) -> str:
    name = " ".join((raw or "").split())
    if not 2 <= len(name) <= 80:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Partner name must be 2 to 80 characters")
    return name


def _clean_website(raw: str | None) -> str | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    if len(raw) > 300:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That website address is too long")
    u = urlparse(raw)
    if u.scheme not in ("http", "https") or not u.netloc or " " in raw:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Website must be a full http:// or https:// address")
    return raw


def _view(p: Partner, full: bool = False) -> dict:
    out = {
        "id": str(p.id), "name": p.name, "website": p.website, "has_logo": bool(p.logo_file),
        "version": int(p.updated_at.timestamp()) if p.updated_at else 0,        # changes when the logo does: busts caches
    }
    if full:
        out.update({"sort_order": p.sort_order, "is_active": p.is_active})
    return out


# ---------------------------------------------------------------- public
@public.get("")
@limiter.limit("120/minute")
async def list_partners(request: Request, db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Partner).where(Partner.is_active.is_(True)).order_by(Partner.sort_order, Partner.created_at))).scalars().all()
    return [_view(p) for p in rows]


@public.get("/{partner_id}/logo")
@limiter.limit("600/minute")
async def partner_logo(request: Request, partner_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    p = (await db.execute(select(Partner).where(Partner.id == partner_id, Partner.is_active.is_(True)))).scalar_one_or_none()
    if p is None or not p.logo_file:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No logo")
    path = uploads.file_path("logos", p.logo_file)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No logo")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "public, max-age=3600"})


# ---------------------------------------------------------------- admin
@admin.get("")
async def admin_list(db: AsyncSession = Depends(get_db), who: User = Depends(get_current_admin)):
    rows = (await db.execute(select(Partner).order_by(Partner.sort_order, Partner.created_at))).scalars().all()
    return [_view(p, full=True) for p in rows]


@admin.get("/{partner_id}/logo")
async def admin_logo(partner_id: uuid.UUID, db: AsyncSession = Depends(get_db), who: User = Depends(get_current_admin)):
    """Preview for the admin screen: works for hidden partners too (the public endpoint refuses those)."""
    p = (await db.execute(select(Partner).where(Partner.id == partner_id))).scalar_one_or_none()
    if p is None or not p.logo_file:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No logo")
    path = uploads.file_path("logos", p.logo_file)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No logo")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "private, max-age=60"})


async def _process_logo(logo: UploadFile | None) -> str | None:
    if logo is None or not logo.filename:
        return None
    raw = await uploads.read_limited(logo, settings.MAX_LOGO_BYTES)
    return uploads.save_file("logos", await uploads.make_logo(raw), "png")


@admin.post("", status_code=status.HTTP_201_CREATED)
async def create_partner(
    request: Request,
    name: str = Form(...), website: str | None = Form(None), sort_order: int = Form(0), is_active: bool = Form(True),
    logo: UploadFile | None = File(None),
    db: AsyncSession = Depends(get_db), who: User = Depends(get_current_admin),
):
    if not 0 <= sort_order <= 999:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Order must be between 0 and 999")
    row = Partner(name=_clean_name(name), website=_clean_website(website), sort_order=sort_order, is_active=is_active,
                  updated_at=datetime.now(timezone.utc))
    row.logo_file = await _process_logo(logo)
    db.add(row)
    await db.flush()
    await log_action(db, "PARTNER_CREATED", actor_user_id=str(who.id), actor_role=who.role, entity_type="partner",
                      entity_id=str(row.id), ip_address=get_client_ip(request), details={"name": row.name})
    await db.commit()
    return _view(row, full=True)


@admin.patch("/{partner_id}")
async def update_partner(
    request: Request, partner_id: uuid.UUID,
    name: str | None = Form(None), website: str | None = Form(None), sort_order: int | None = Form(None),
    is_active: bool | None = Form(None), remove_logo: bool = Form(False), logo: UploadFile | None = File(None),
    db: AsyncSession = Depends(get_db), who: User = Depends(get_current_admin),
):
    row = (await db.execute(select(Partner).where(Partner.id == partner_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Partner not found")
    if name is not None:
        row.name = _clean_name(name)
    if website is not None:
        row.website = _clean_website(website)
    if sort_order is not None:
        if not 0 <= sort_order <= 999:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Order must be between 0 and 999")
        row.sort_order = sort_order
    if is_active is not None:
        row.is_active = is_active
    old = row.logo_file
    new = await _process_logo(logo)
    if new:
        row.logo_file = new
    elif remove_logo:
        row.logo_file = None
    row.updated_at = datetime.now(timezone.utc)
    await log_action(db, "PARTNER_UPDATED", actor_user_id=str(who.id), actor_role=who.role, entity_type="partner",
                      entity_id=str(row.id), ip_address=get_client_ip(request), details={"name": row.name, "active": row.is_active})
    await db.commit()
    if old and old != row.logo_file:
        uploads.delete_file("logos", old)
    return _view(row, full=True)


@admin.delete("/{partner_id}")
async def delete_partner(request: Request, partner_id: uuid.UUID, db: AsyncSession = Depends(get_db), who: User = Depends(get_current_admin)):
    row = (await db.execute(select(Partner).where(Partner.id == partner_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Partner not found")
    old, name = row.logo_file, row.name
    await db.delete(row)
    await log_action(db, "PARTNER_DELETED", actor_user_id=str(who.id), actor_role=who.role, entity_type="partner",
                      entity_id=str(partner_id), ip_address=get_client_ip(request), details={"name": name})
    await db.commit()
    uploads.delete_file("logos", old)
    return {"deleted": True}
