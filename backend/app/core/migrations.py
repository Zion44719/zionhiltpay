"""
Idempotent schema upgrade, run at startup right after create_all.

create_all only creates MISSING tables; it never adds columns, enum values or indexes to an existing one.
This brings a database created by an older version (or by db/schema.sql) up to date and gives every
existing user an account number. Safe to run any number of times, and safe with several workers starting
at once (advisory lock). Index creation that could fail on unusual legacy data logs a warning instead of
stopping the app from starting.
"""
import logging

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.identity import generate_account_number

logger = logging.getLogger("zionhiltpay.migrations")

USER_COLUMNS = [
    # identity (v1.1)
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
    # tiers + profile photo (v1.2)
    "account_tier SMALLINT NOT NULL DEFAULT 1",
    "profile_photo VARCHAR(64)",
]
IDENTITY_COLUMNS = USER_COLUMNS  # kept for older imports

USER_INDEXES = [
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_username ON users (username)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_account_number ON users (account_number)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_id_hash ON users (id_type, id_number_hash)",
]
INDEXES = USER_INDEXES

# table -> statements. Only run if the table exists (older/minimal databases may not have it yet).
TABLE_INDEXES = {
    "accounts": [
        # exactly one platform account per type (a UNIQUE over a NULL user_id would not stop duplicates)
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_platform_account_type ON accounts (account_type, currency) WHERE user_id IS NULL",
    ],
    "tier_requests": [
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_tier_requests_one_pending ON tier_requests (user_id) WHERE status = 'pending'",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_tier_requests_bvn ON tier_requests (bvn_hash) WHERE status IN ('pending','approved') AND bvn_hash IS NOT NULL",
    ],
    "loans": [
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_loans_one_active ON loans (user_id) WHERE status = 'active'",
    ],
    "transactions": [
        # makes a payout safe to retry: the same client_reference from the same user can only exist once
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_txn_client_reference ON transactions (initiator_user_id, ((metadata ->> 'client_reference'))) WHERE (metadata ->> 'client_reference') IS NOT NULL",
    ],
}

ENUM_VALUES = [
    ("transaction_type", "loan_disbursement"),
    ("transaction_type", "loan_repayment"),
    ("account_type", "platform_loan_pool"),
]

PLATFORM_ACCOUNT_TYPES = [
    "platform_revenue", "platform_reward_pool", "platform_insurance_pool", "external_gateway", "platform_loan_pool",
]

_LOCK_KEY = 727_001


async def _table_exists(conn: AsyncConnection, name: str) -> bool:
    return (await conn.execute(text("SELECT to_regclass(:n) IS NOT NULL"), {"n": name})).scalar_one()


async def upgrade_schema(conn: AsyncConnection) -> int:
    """Returns how many existing users were given an account number."""
    await conn.execute(text(f"SELECT pg_advisory_xact_lock({_LOCK_KEY})"))
    for col in USER_COLUMNS:
        await conn.execute(text(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col}"))
    for stmt in USER_INDEXES:
        await conn.execute(text(stmt))

    # New enum values (a value added in this transaction cannot be USED until it commits: see seed_platform_accounts)
    for typ, val in ENUM_VALUES:
        await conn.execute(text(
            f"DO $$ BEGIN IF to_regtype('{typ}') IS NOT NULL THEN ALTER TYPE {typ} ADD VALUE IF NOT EXISTS '{val}'; END IF; END $$"
        ))

    for table, statements in TABLE_INDEXES.items():
        if not await _table_exists(conn, table):
            continue
        for stmt in statements:
            try:
                async with conn.begin_nested():
                    await conn.execute(text(stmt))
            except Exception as exc:  # noqa: BLE001 - never block startup on a legacy-data index problem
                logger.warning("Could not create index (%s): %s", stmt.split(" ON ")[0].split()[-1], str(exc).splitlines()[0])
    return await backfill_account_numbers(conn)


async def seed_platform_accounts(conn: AsyncConnection) -> int:
    """Make sure each platform-level ledger account exists exactly once. Run in its OWN transaction after
    upgrade_schema has committed, because a freshly added enum value cannot be used in the same transaction."""
    if not await _table_exists(conn, "accounts"):
        return 0
    await conn.execute(text(f"SELECT pg_advisory_xact_lock({_LOCK_KEY})"))
    created = 0
    for t in PLATFORM_ACCOUNT_TYPES:
        res = await conn.execute(text(
            "INSERT INTO accounts (id, account_type, currency, balance, is_platform_account) "
            "SELECT gen_random_uuid(), CAST(:t AS account_type), 'NGN', 0, TRUE "
            "WHERE NOT EXISTS (SELECT 1 FROM accounts WHERE user_id IS NULL AND account_type = CAST(:t AS account_type))"
        ), {"t": t})
        created += res.rowcount or 0
    return created


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
