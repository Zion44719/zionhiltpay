"""
Idempotent schema upgrade, run at startup right after create_all.

create_all only creates MISSING tables; it never adds columns to an existing one. This brings a
database created by an older version (or by db/schema.sql) up to date, then gives every existing
user an account number. Safe to run any number of times, and safe with several workers starting at
once (advisory lock).
"""
import logging

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.identity import generate_account_number

logger = logging.getLogger("zionhiltpay.migrations")

IDENTITY_COLUMNS = [
    "username VARCHAR(20)",
    "account_number VARCHAR(10)",
    "id_type VARCHAR(20)",
    "id_number_enc TEXT",
    "id_number_hash VARCHAR(64)",
    "id_number_last4 VARCHAR(4)",
    "id_submitted_at TIMESTAMPTZ",
    "kyc_status VARCHAR(20) NOT NULL DEFAULT 'not_submitted'",
    "kyc_reviewed_by UUID",
    "kyc_reviewed_at TIMESTAMPTZ",
    "kyc_note TEXT",
]

INDEXES = [
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_username ON users (username)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_account_number ON users (account_number)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_id_hash ON users (id_type, id_number_hash)",
]

_LOCK_KEY = 727_001


async def upgrade_schema(conn: AsyncConnection) -> int:
    """Returns how many existing users were given an account number."""
    await conn.execute(text(f"SELECT pg_advisory_xact_lock({_LOCK_KEY})"))
    for col in IDENTITY_COLUMNS:
        await conn.execute(text(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col}"))
    for stmt in INDEXES:
        await conn.execute(text(stmt))
    return await backfill_account_numbers(conn)


async def backfill_account_numbers(conn: AsyncConnection) -> int:
    ids = [r[0] for r in (await conn.execute(text("SELECT id FROM users WHERE account_number IS NULL"))).all()]
    for uid in ids:
        for _ in range(20):  # a collision is astronomically unlikely, but the index is the real guarantee
            try:
                async with conn.begin_nested():
                    await conn.execute(
                        text("UPDATE users SET account_number = :n WHERE id = :i AND account_number IS NULL"),
                        {"n": generate_account_number(), "i": uid},
                    )
                break
            except IntegrityError:
                continue
        else:  # pragma: no cover
            raise RuntimeError("Could not allocate a unique account number")
    if ids:
        logger.info("Assigned account numbers to %d existing user(s).", len(ids))
    return len(ids)
