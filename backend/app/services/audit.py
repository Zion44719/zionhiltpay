"""
Audit service — writes an immutable trail for every sensitive action.
Called from auth, wallet, device, and admin routers.
"""
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.user import UserRole


async def log_action(
    db: AsyncSession,
    action: str,
    actor_user_id: Optional[str] = None,
    actor_role: Optional[UserRole] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    details: Optional[dict] = None,
) -> AuditLog:
    entry = AuditLog(
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        ip_address=ip_address,
        user_agent=user_agent,
        details=details or {},
    )
    db.add(entry)
    await db.flush()
    return entry
