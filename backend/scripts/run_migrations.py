#!/usr/bin/env python3
"""
Run idempotent SQL migrations from migrations/ in order.
Uses DB_* env (or Vault-injected env). Safe to re-run.
"""
import asyncio
import os
import sys
from pathlib import Path

# Add app to path so we can load settings
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.chdir(Path(__file__).resolve().parent.parent)

from app.config import settings


def _db_url_for_asyncpg() -> str:
    """Convert SQLAlchemy async URL to asyncpg URL."""
    url = settings.get_database_url()
    # postgresql+asyncpg://... -> postgresql://...
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql://", 1)
    if url.startswith("postgresql://"):
        return url
    return url


async def main() -> int:
    import asyncpg
    migrations_dir = Path(__file__).resolve().parent.parent / "migrations"
    if not migrations_dir.is_dir():
        print(f"Migrations dir not found: {migrations_dir}", file=sys.stderr)
        return 1
    sql_files = sorted(migrations_dir.glob("*.sql"))
    if not sql_files:
        print("No migration files found.", file=sys.stderr)
        return 0
    conn = await asyncpg.connect(_db_url_for_asyncpg())
    try:
        for path in sql_files:
            print(f"Running {path.name}...")
            sql = path.read_text()
            await conn.execute(sql)
            print(f"  OK {path.name}")
    finally:
        await conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
