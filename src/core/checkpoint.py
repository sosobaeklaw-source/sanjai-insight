"""
Checkpoint Manager for Resume Capability
Fail-safe checkpoint save/load with validation
"""

import json
from datetime import datetime
from typing import Any, Optional

import aiosqlite

from ..models import Checkpoint


class CheckpointManager:
    """Manages checkpoints for resumable execution"""

    def __init__(self, db_path: str):
        self.db_path = db_path

    async def save(self, correlation_id: str, last_stage: str, ctx: dict[str, Any]) -> None:
        """
        Save checkpoint (upsert)
        Fail-closed: validation errors = abort save
        """
        # Validate ctx is JSON-serializable
        try:
            ctx_json = json.dumps(ctx, ensure_ascii=False)
        except (TypeError, ValueError) as e:
            raise ValueError(f"Checkpoint context not JSON-serializable: {e}") from e

        # Validate required fields
        if not correlation_id or not last_stage:
            raise ValueError("correlation_id and last_stage are required")

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO checkpoints (correlation_id, last_stage, ctx_json, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(correlation_id) DO UPDATE SET
                    last_stage = excluded.last_stage,
                    ctx_json = excluded.ctx_json,
                    updated_at = excluded.updated_at
                """,
                (correlation_id, last_stage, ctx_json, datetime.now().isoformat()),
            )
            await db.commit()

    async def load(self, correlation_id: str) -> Optional[Checkpoint]:
        """Load checkpoint by correlation_id"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM checkpoints WHERE correlation_id = ?",
                (correlation_id,),
            )
            row = await cursor.fetchone()

            if not row:
                return None

            return Checkpoint(
                correlation_id=row["correlation_id"],
                last_stage=row["last_stage"],
                ctx_json=json.loads(row["ctx_json"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )

    async def delete(self, correlation_id: str) -> None:
        """Delete checkpoint (after successful completion)"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM checkpoints WHERE correlation_id = ?",
                (correlation_id,),
            )
            await db.commit()

    async def exists(self, correlation_id: str) -> bool:
        """Check if checkpoint exists"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT 1 FROM checkpoints WHERE correlation_id = ? LIMIT 1",
                (correlation_id,),
            )
            row = await cursor.fetchone()
            return row is not None
