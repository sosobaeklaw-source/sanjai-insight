"""
Database Initialization Script
Applies schema.sql + schema_v2_operational.sql
"""

import asyncio
import sys
from pathlib import Path

import aiosqlite


async def init_database(db_path: str = "data/insight.db"):
    """Initialize database with schema"""
    db_file = Path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)

    # Read schemas
    base_schema_path = Path(__file__).parent.parent / "schema.sql"
    operational_schema_path = Path(__file__).parent.parent / "schema_v2_operational.sql"

    if not base_schema_path.exists():
        print(f"ERROR: Base schema not found: {base_schema_path}")
        sys.exit(1)

    if not operational_schema_path.exists():
        print(f"ERROR: Operational schema not found: {operational_schema_path}")
        sys.exit(1)

    base_schema = base_schema_path.read_text(encoding="utf-8")
    operational_schema = operational_schema_path.read_text(encoding="utf-8")

    print(f"Initializing database: {db_path}")

    async with aiosqlite.connect(db_path) as db:
        # Enable WAL mode
        print("Enabling WAL mode...")
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")

        # Apply base schema
        print("Applying base schema...")
        await db.executescript(base_schema)

        # Apply operational schema
        print("Applying operational schema...")
        await db.executescript(operational_schema)

        await db.commit()

        # Verify tables
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = await cursor.fetchall()

        print(f"\nCreated {len(tables)} tables:")
        for table in tables:
            print(f"  - {table[0]}")

        # Verify FTS5
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='vault_fts'"
        )
        fts_table = await cursor.fetchone()
        if fts_table:
            print("\n✓ FTS5 table created: vault_fts")
        else:
            print("\n✗ FTS5 table NOT created")

        # Check WAL mode
        cursor = await db.execute("PRAGMA journal_mode")
        mode = await cursor.fetchone()
        if mode and mode[0] == "wal":
            print("✓ WAL mode enabled")
        else:
            print("✗ WAL mode NOT enabled")

    print("\nDatabase initialization complete!")


if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else "data/insight.db"
    asyncio.run(init_database(db_path))
