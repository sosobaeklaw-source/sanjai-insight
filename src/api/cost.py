"""
Cost Endpoint
GET /cost?correlation_id=xxx
Returns cost breakdown by stage and model
"""

from typing import Optional

import aiosqlite

from ..models import CostBreakdown


async def get_cost(db_path: str, correlation_id: str) -> Optional[CostBreakdown]:
    """
    Get cost breakdown by correlation_id
    Returns: CostBreakdown or None
    """
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        # Check if correlation exists
        cursor = await db.execute(
            "SELECT 1 FROM runlogs WHERE correlation_id = ? LIMIT 1",
            (correlation_id,),
        )
        if not await cursor.fetchone():
            return None

        # Total cost
        cursor = await db.execute(
            """
            SELECT
                SUM(cost_usd) as total_cost,
                SUM(tokens_in) as total_tokens_in,
                SUM(tokens_out) as total_tokens_out,
                COUNT(*) as call_count,
                AVG(latency_ms) as avg_latency_ms
            FROM llm_calls
            WHERE correlation_id = ?
            """,
            (correlation_id,),
        )
        row = await cursor.fetchone()

        total_cost_usd = row["total_cost"] if row and row["total_cost"] else 0.0
        total_tokens_in = row["total_tokens_in"] if row else 0
        total_tokens_out = row["total_tokens_out"] if row else 0
        call_count = row["call_count"] if row else 0
        avg_latency_ms = row["avg_latency_ms"] if row and row["avg_latency_ms"] else 0.0

        # By stage
        cursor = await db.execute(
            """
            SELECT stage, SUM(cost_usd) as cost
            FROM llm_calls
            WHERE correlation_id = ?
            GROUP BY stage
            """,
            (correlation_id,),
        )
        by_stage = {row["stage"]: row["cost"] for row in await cursor.fetchall()}

        # By model
        cursor = await db.execute(
            """
            SELECT model, SUM(cost_usd) as cost
            FROM llm_calls
            WHERE correlation_id = ?
            GROUP BY model
            """,
            (correlation_id,),
        )
        by_model = {row["model"]: row["cost"] for row in await cursor.fetchall()}

        return CostBreakdown(
            correlation_id=correlation_id,
            total_cost_usd=total_cost_usd,
            by_stage=by_stage,
            by_model=by_model,
            total_tokens_in=total_tokens_in,
            total_tokens_out=total_tokens_out,
            call_count=call_count,
            avg_latency_ms=avg_latency_ms,
        )
