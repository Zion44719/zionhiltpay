"""
The append-only ledger/audit guarantee must hold no matter how the tables were created
(db/schema.sql, or SQLAlchemy's create_all on an empty database).
Skipped unless TEST_DATABASE_URL points at a Postgres (empty or schema.sql-loaded).
"""
import os
import sys
import uuid

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEST_DB = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DB, reason="set TEST_DATABASE_URL to run DB tests")


@pytest.mark.asyncio
async def test_guards_install_idempotently_and_block_tampering():
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from sqlalchemy.pool import NullPool
    from app.core.database import Base
    from app.core.db_guards import install_db_guards
    from app.models.user import User
    from app.models.account import Account, AccountType
    from app.models.transaction import Transaction, TransactionType, LedgerEntry

    engine = create_async_engine(TEST_DB, poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await install_db_guards(conn)
            await install_db_guards(conn)  # running twice must not error

        async with engine.begin() as conn:
            rules = {r[0] for r in (await conn.execute(text(
                "select rulename from pg_rules where tablename in ('ledger_entries','audit_logs')"))).all()}
            assert {"ledger_entries_no_update", "ledger_entries_no_delete",
                    "audit_logs_no_update", "audit_logs_no_delete"} <= rules
            trig = {r[0] for r in (await conn.execute(text(
                "select tgname from pg_trigger where not tgisinternal"))).all()}
            assert {"trg_users_updated_at", "trg_accounts_updated_at", "trg_devices_updated_at"} <= trig

        # Behavioural proof via the ORM, so it works whichever way the tables were created.
        Session = async_sessionmaker(engine, expire_on_commit=False)
        async with Session() as s:
            u = User(full_name="guard", email=f"g{uuid.uuid4().hex}@example.com",
                     phone_number="+23480" + str(uuid.uuid4().int)[:8], password_hash="x")
            s.add(u)
            await s.flush()
            acct = Account(user_id=u.id, account_type=AccountType.user_wallet, balance=100)   # consistent with the ledger entry below
            txn = Transaction(reference=f"GUARD-{uuid.uuid4().hex[:12]}",
                              type=TransactionType.deposit, amount=100)
            s.add_all([acct, txn])
            await s.flush()
            counter = Account(user_id=u.id, account_type=AccountType.user_reward, balance=-100)
            s.add(counter)
            await s.flush()
            le = LedgerEntry(transaction_id=txn.id, account_id=acct.id,
                             direction="C", amount=100, balance_after=100)
            s.add(le)
            s.add(LedgerEntry(transaction_id=txn.id, account_id=counter.id,       # the matching debit: a balanced pair
                              direction="D", amount=100, balance_after=-100))
            await s.flush()
            le_id = le.id
            await s.commit()

        async with engine.begin() as conn:
            await conn.execute(text("update ledger_entries set amount = 999999 where id = :i"), {"i": le_id})
            await conn.execute(text("delete from ledger_entries where id = :i"), {"i": le_id})
            row = (await conn.execute(text("select amount from ledger_entries where id = :i"), {"i": le_id})).first()
            assert row is not None, "ledger entry was DELETED - append-only guard is not working"
            assert float(row[0]) == 100.0, "ledger entry was ALTERED - append-only guard is not working"
    finally:
        await engine.dispose()
