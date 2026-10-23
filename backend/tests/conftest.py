"""
Shared test setup.

When TEST_DATABASE_URL is set, make sure that database has the application's tables, columns and
integrity guards before any test runs. This is the same preparation the backend does at startup, so
the database tests also work against a completely empty database. It is idempotent.
Without TEST_DATABASE_URL nothing happens (the database tests skip themselves).
"""
import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(scope="session", autouse=True)
def _prepare_test_database():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        return

    async def prepare():
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy.pool import NullPool
        import app.models  # noqa: F401  (registers every table on Base.metadata)
        from app.core.database import Base
        from app.core.db_guards import install_db_guards
        from app.core.migrations import upgrade_schema, seed_platform_accounts

        engine = create_async_engine(url, poolclass=NullPool)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
                await upgrade_schema(conn)
                await install_db_guards(conn)
            async with engine.begin() as conn:
                await seed_platform_accounts(conn)
        finally:
            await engine.dispose()

    asyncio.run(prepare())
