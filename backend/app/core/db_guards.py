"""
Database-level integrity guards, installed idempotently at startup.

db/schema.sql already defines these, but if the tables were created by
SQLAlchemy's create_all instead (e.g. a local run against an empty database),
they would be missing and the ledger / audit trail would silently be editable.
Every statement here is safe to run repeatedly and on a schema.sql database.
"""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

APPEND_ONLY_TABLES = ("ledger_entries", "audit_logs")
UPDATED_AT_TABLES = ("users", "accounts", "devices")

_SET_UPDATED_AT_FN = """
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


async def install_db_guards(conn: AsyncConnection) -> None:
    # Append-only: UPDATE/DELETE on the ledger and audit trail silently do nothing.
    for table in APPEND_ONLY_TABLES:
        for op in ("update", "delete"):
            await conn.execute(text(
                f"CREATE OR REPLACE RULE {table}_no_{op} AS ON {op.upper()} TO {table} DO INSTEAD NOTHING"
            ))
    # Keep updated_at honest even though the ORM columns have no onupdate.
    await conn.execute(text(_SET_UPDATED_AT_FN))
    for table in UPDATED_AT_TABLES:
        await conn.execute(text(f"DROP TRIGGER IF EXISTS trg_{table}_updated_at ON {table}"))
        await conn.execute(text(
            f"CREATE TRIGGER trg_{table}_updated_at BEFORE UPDATE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
        ))
