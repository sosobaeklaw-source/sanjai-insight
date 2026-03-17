"""
Status Endpoint
GET /status?correlation_id=xxx
Returns detailed execution status
"""

import json
from datetime import datetime
from typing import Optional

import aiosqlite

from ..models import StatusResponse


async def get_status(db_path: str, correlation_id: str) -> Optional[StatusResponse]:
    """
    Get execution status by correlation_id
    Returns: StatusResponse or None
    """
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        # Get runlog
        cursor = await db.execute(
            """
            SELECT * FROM runlogs
            WHERE correlation_id = ?
            ORDER BY started_at DESC
            LIMIT 1
            """,
            (correlation_id,),
        )
        runlog = await cursor.fetchone()

        if not runlog:
            return None

        # Get checkpoint
        cursor = await db.execute(
            "SELECT last_stage FROM checkpoints WHERE correlation_id = ?",
            (correlation_id,),
        )
        checkpoint = await cursor.fetchone()
        last_stage = checkpoint["last_stage"] if checkpoint else None

        # Count events
        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM events WHERE correlation_id = ?",
            (correlation_id,),
        )
        row = await cursor.fetchone()
        event_count = row["cnt"] if row else 0

        # Count insights
        cursor = await db.execute(
            """
            SELECT COUNT(DISTINCT JSON_EXTRACT(payload_json, '$.insight_id')) as cnt
            FROM events
            WHERE correlation_id = ? AND type = 'INSIGHT_CREATED'
            """,
            (correlation_id,),
        )
        row = await cursor.fetchone()
        insights_count = row["cnt"] if row else 0

        # Count items collected
        cursor = await db.execute(
            """
            SELECT COUNT(DISTINCT JSON_EXTRACT(payload_json, '$.item_id')) as cnt
            FROM events
            WHERE correlation_id = ? AND type = 'ITEM_COLLECTED'
            """,
            (correlation_id,),
        )
        row = await cursor.fetchone()
        items_collected = row["cnt"] if row else 0

        # Get errors
        cursor = await db.execute(
            """
            SELECT payload_json FROM events
            WHERE correlation_id = ? AND type = 'ERROR'
            ORDER BY ts DESC
            LIMIT 10
            """,
            (correlation_id,),
        )
        error_rows = await cursor.fetchall()
        errors = [
            json.loads(row["payload_json"]).get("error", "Unknown error")
            for row in error_rows
        ]

        return StatusResponse(
            correlation_id=correlation_id,
            run_id=runlog["run_id"],
            status=runlog["status"],
            started_at=datetime.fromisoformat(runlog["started_at"]),
            ended_at=datetime.fromisoformat(runlog["ended_at"]) if runlog["ended_at"] else None,
            last_stage=last_stage,
            event_count=event_count,
            insights_count=insights_count,
            items_collected=items_collected,
            total_cost_usd=runlog["total_cost_usd"],
            errors=errors,
        )
