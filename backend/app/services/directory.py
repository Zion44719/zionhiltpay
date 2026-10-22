"""Find a user by whatever identifier a person typed (account number, username, email, phone)."""
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import identity as idt
from app.models.user import User


async def find_user(db: AsyncSession, raw: str) -> tuple[str, Optional[User]]:
    """Returns (kind, user_or_None). kind == 'unknown' means the text isn't any valid identifier."""
    kind, value = idt.classify_identifier(raw)
    clause = {
        "email": lambda: func.lower(User.email) == value,
        "account_number": lambda: User.account_number == value,
        "phone": lambda: User.phone_number.in_(idt.phone_lookup_variants(value)),
        "username": lambda: User.username == value,
    }.get(kind)
    if clause is None:
        return kind, None
    user = (await db.execute(select(User).where(clause()))).scalar_one_or_none()
    return kind, user
