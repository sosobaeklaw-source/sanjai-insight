"""
Initialize database with schema
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db import db


async def main():
    """Initialize database"""
    print("Initializing database...")

    try:
        await db.init_db("schema.sql")
        print("[OK] Database initialized successfully")
        print(f"  Location: {db.db_path}")

        # Test connection
        async with db.connect() as conn:
            cursor = await conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = await cursor.fetchall()
            print(f"\n[OK] Created {len(tables)} tables:")
            for table in tables:
                print(f"  - {table['name']}")

    except Exception as e:
        print(f"[ERROR] Failed to initialize database: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
