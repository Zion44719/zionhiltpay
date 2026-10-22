"""
Bootstrap a super_admin account for ZionhiltPay.

Usage (inside the backend container or venv):
    python -m scripts.create_admin --email admin@yourdomain.com --username zadmin --password "StrongPass123" --name "Zionhilt Admin" --phone +2348000000000 --super

This is the ONLY supported way to create the first admin — there is no
public registration path to the admin role, by design.
"""
import argparse
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from app.core.database import AsyncSessionLocal, engine, Base
from app.core.security import hash_password
from app.models.user import User, UserRole, OTPChannel
from app.models.account import AccountType
from app.services.ledger import get_or_create_account
from app.core import identity as idt
from app.core.migrations import upgrade_schema


async def main(email: str, password: str, name: str, phone: str, username: str, super_admin: bool):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await upgrade_schema(conn)

    async with AsyncSessionLocal() as db:
        existing = await db.execute(select(User).where(User.email == email.strip().lower()))
        if existing.scalar_one_or_none():
            print(f"A user with email {email} already exists. Aborting.")
            return

        norm_phone = idt.normalize_phone(phone)
        if norm_phone is None:
            print(f"Invalid phone number: {phone}"); return
        uname = username.strip().lower()
        if not idt.USERNAME_RE.fullmatch(uname):
            print("Username must be 3-20 characters, start with a letter, letters/digits/underscore only."); return
        if (await db.execute(select(User).where(User.username == uname))).scalar_one_or_none():
            print(f"Username {uname} is already taken. Aborting."); return

        user = User(
            full_name=name,
            username=uname,
            account_number=idt.generate_account_number(),
            kyc_status="verified",
            kyc_level=2,
            email=email.strip().lower(),
            phone_number=norm_phone,
            password_hash=hash_password(password),
            role=UserRole.super_admin if super_admin else UserRole.admin,
            email_verified=True,
            phone_verified=True,
        )
        db.add(user)
        await db.flush()

        await get_or_create_account(db, AccountType.user_wallet, user.id)
        await get_or_create_account(db, AccountType.user_reward, user.id)
        await get_or_create_account(db, AccountType.user_insurance, user.id)

        await db.commit()
        print(f"Created {'super_admin' if super_admin else 'admin'} account: {user.email} (id={user.id})")
        print(f"  Log in with any of: username '{uname}', email '{user.email}', phone '{norm_phone}', account number '{user.account_number}'")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bootstrap a ZionhiltPay admin account")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--phone", required=True)
    parser.add_argument("--username", required=True, help="3-20 chars, starts with a letter (letters, digits, _)")
    parser.add_argument("--super", action="store_true", dest="super_admin", help="Create a super_admin instead of admin")
    args = parser.parse_args()

    asyncio.run(main(args.email, args.password, args.name, args.phone, args.username, args.super_admin))
