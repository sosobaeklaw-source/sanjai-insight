"""
Telegram Update Idempotency Handler
Prevents duplicate processing of Telegram updates
"""

import json
from datetime import datetime
from typing import Optional

import aiosqlite


class TelegramIdempotency:
    """Handles Telegram update_id idempotency"""

    def __init__(self, db_path: str):
        self.db_path = db_path

    async def is_processed(self, update_id: int) -> bool:
        """Check if update_id already processed"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT 1 FROM telegram_updates WHERE update_id = ? LIMIT 1",
                (update_id,),
            )
            row = await cursor.fetchone()
            return row is not None

    async def mark_processed(
        self,
        update_id: int,
        chat_id: int,
        payload: dict,
    ) -> bool:
        """
        Mark update_id as processed (idempotent)
        Returns: True if newly inserted, False if already exists
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    """
                    INSERT INTO telegram_updates (update_id, chat_id, payload_json, processed_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        update_id,
                        chat_id,
                        json.dumps(payload, ensure_ascii=False),
                        datetime.now().isoformat(),
                    ),
                )
                await db.commit()
                return True
        except aiosqlite.IntegrityError:
            # Already processed (update_id is PK)
            return False

    async def get_update(self, update_id: int) -> Optional[dict]:
        """Get processed update by ID"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM telegram_updates WHERE update_id = ?",
                (update_id,),
            )
            row = await cursor.fetchone()

            if not row:
                return None

            return {
                "update_id": row["update_id"],
                "chat_id": row["chat_id"],
                "payload_json": json.loads(row["payload_json"]),
                "processed_at": row["processed_at"],
            }
