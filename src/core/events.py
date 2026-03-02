"""
Event Logger for Append-Only Audit Trail
All operational events with correlation_id for traceability
"""

import json
from datetime import datetime
from typing import Any
from uuid import uuid4

import aiosqlite

from ..models import Event, EventType


class EventLogger:
    """Logs events to append-only audit trail"""

    def __init__(self, db_path: str):
        self.db_path = db_path

    async def log(
        self,
        event_type: EventType,
        correlation_id: str,
        payload: dict[str, Any],
    ) -> str:
        """
        Log event (append-only)
        Returns: event_id
        """
        event_id = str(uuid4())
        ts = datetime.now()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO events (id, ts, type, correlation_id, payload_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    ts.isoformat(),
                    event_type.value,
                    correlation_id,
                    json.dumps(payload, ensure_ascii=False),
                ),
            )
            await db.commit()

        return event_id

    async def get_events(
        self,
        correlation_id: str,
        event_type: Optional[EventType] = None,
        limit: int = 100,
    ) -> list[Event]:
        """Get events by correlation_id (with optional type filter)"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            if event_type:
                cursor = await db.execute(
                    """
                    SELECT * FROM events
                    WHERE correlation_id = ? AND type = ?
                    ORDER BY ts DESC
                    LIMIT ?
                    """,
                    (correlation_id, event_type.value, limit),
                )
            else:
                cursor = await db.execute(
                    """
                    SELECT * FROM events
                    WHERE correlation_id = ?
                    ORDER BY ts DESC
                    LIMIT ?
                    """,
                    (correlation_id, limit),
                )

            rows = await cursor.fetchall()
            return [self._row_to_event(row) for row in rows]

    async def count_events(
        self,
        correlation_id: str,
        event_type: Optional[EventType] = None,
    ) -> int:
        """Count events by correlation_id"""
        async with aiosqlite.connect(self.db_path) as db:
            if event_type:
                cursor = await db.execute(
                    "SELECT COUNT(*) as cnt FROM events WHERE correlation_id = ? AND type = ?",
                    (correlation_id, event_type.value),
                )
            else:
                cursor = await db.execute(
                    "SELECT COUNT(*) as cnt FROM events WHERE correlation_id = ?",
                    (correlation_id,),
                )

            row = await cursor.fetchone()
            return row[0] if row else 0

    async def get_latest_event(
        self,
        correlation_id: str,
        event_type: Optional[EventType] = None,
    ) -> Optional[Event]:
        """Get latest event by correlation_id"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            if event_type:
                cursor = await db.execute(
                    """
                    SELECT * FROM events
                    WHERE correlation_id = ? AND type = ?
                    ORDER BY ts DESC
                    LIMIT 1
                    """,
                    (correlation_id, event_type.value),
                )
            else:
                cursor = await db.execute(
                    """
                    SELECT * FROM events
                    WHERE correlation_id = ?
                    ORDER BY ts DESC
                    LIMIT 1
                    """,
                    (correlation_id,),
                )

            row = await cursor.fetchone()
            return self._row_to_event(row) if row else None

    def _row_to_event(self, row: aiosqlite.Row) -> Event:
        """Convert DB row to Event model"""
        return Event(
            id=row["id"],
            ts=datetime.fromisoformat(row["ts"]),
            type=EventType(row["type"]),
            correlation_id=row["correlation_id"],
            payload_json=json.loads(row["payload_json"]),
        )
