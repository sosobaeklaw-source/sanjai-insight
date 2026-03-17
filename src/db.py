"""
sanjai-insight Database Layer
SQLite + aiosqlite with WAL mode for concurrent access
"""

import json
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import aiosqlite

from .models import (
    CostLog,
    CrawledData,
    IndexedDocument,
    Insight,
    MarketingContent,
    Proposal,
    PromptVersion,
    SystemMetrics,
    TrendSnapshot,
    WatchLog,
)


class Database:
    """SQLite database manager with async support"""

    def __init__(self, db_path: str = "data/insight.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    async def init_db(self, schema_path: str = "schema.sql"):
        """Initialize database with schema"""
        # Read schema
        schema = Path(schema_path).read_text(encoding="utf-8")

        # Execute schema
        async with aiosqlite.connect(self.db_path) as db:
            # Enable WAL mode for concurrent access
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("PRAGMA foreign_keys=ON")

            # Execute schema
            await db.executescript(schema)
            await db.commit()

    @asynccontextmanager
    async def connect(self):
        """Get database connection context manager"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            yield db

    # ========== Helper Methods ==========

    def _serialize_datetime(self, dt: Optional[datetime]) -> Optional[str]:
        """Convert datetime to ISO string"""
        return dt.isoformat() if dt else None

    def _deserialize_datetime(self, s: Optional[str]) -> Optional[datetime]:
        """Convert ISO string to datetime"""
        return datetime.fromisoformat(s) if s else None

    def _serialize_json(self, obj: Any) -> str:
        """Convert object to JSON string"""
        if isinstance(obj, (dict, list)):
            return json.dumps(obj, ensure_ascii=False)
        return json.dumps(obj)

    def _deserialize_json(self, s: Optional[str]) -> Any:
        """Convert JSON string to object"""
        return json.loads(s) if s else None

    # ========== CrawledData CRUD ==========

    async def create_crawled_data(self, data: CrawledData) -> str:
        """Create new crawled data record"""
        async with self.connect() as db:
            await db.execute(
                """
                INSERT INTO crawled_data
                (id, source, crawled_at, data_type, raw_content, metadata, status, crawled_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data.id,
                    data.source.value,
                    self._serialize_datetime(data.crawled_at),
                    data.data_type.value,
                    data.raw_content,
                    self._serialize_json(data.metadata),
                    data.status.value,
                    data.crawled_by.value,
                ),
            )
            await db.commit()
            return data.id

    async def get_crawled_data(self, data_id: str) -> Optional[CrawledData]:
        """Get crawled data by ID"""
        async with self.connect() as db:
            cursor = await db.execute(
                "SELECT * FROM crawled_data WHERE id = ?", (data_id,)
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return self._row_to_crawled_data(row)

    async def list_crawled_data(
        self, status: Optional[str] = None, limit: int = 100
    ) -> list[CrawledData]:
        """List crawled data with optional status filter"""
        async with self.connect() as db:
            if status:
                cursor = await db.execute(
                    "SELECT * FROM crawled_data WHERE status = ? ORDER BY crawled_at DESC LIMIT ?",
                    (status, limit),
                )
            else:
                cursor = await db.execute(
                    "SELECT * FROM crawled_data ORDER BY crawled_at DESC LIMIT ?",
                    (limit,),
                )
            rows = await cursor.fetchall()
            return [self._row_to_crawled_data(row) for row in rows]

    async def update_crawled_data_status(self, data_id: str, status: str):
        """Update crawled data status"""
        async with self.connect() as db:
            await db.execute(
                "UPDATE crawled_data SET status = ? WHERE id = ?", (status, data_id)
            )
            await db.commit()

    def _row_to_crawled_data(self, row: aiosqlite.Row) -> CrawledData:
        """Convert database row to CrawledData model"""
        return CrawledData(
            id=row["id"],
            source=row["source"],
            crawled_at=self._deserialize_datetime(row["crawled_at"]),
            data_type=row["data_type"],
            raw_content=row["raw_content"],
            metadata=self._deserialize_json(row["metadata"]) or {},
            status=row["status"],
            crawled_by=row["crawled_by"],
            created_at=self._deserialize_datetime(row["created_at"]),
        )

    # ========== Insight CRUD ==========

    async def create_insight(self, insight: Insight) -> str:
        """Create new insight"""
        async with self.connect() as db:
            await db.execute(
                """
                INSERT INTO insights
                (id, type, trigger_data_ids, title, body, confidence, urgency,
                suggested_actions, affected_cases, status, model_used, tokens_used)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    insight.id,
                    insight.type.value,
                    self._serialize_json(insight.trigger_data_ids),
                    insight.title,
                    self._serialize_json(insight.body),
                    insight.confidence,
                    insight.urgency.value,
                    self._serialize_json(insight.suggested_actions),
                    self._serialize_json(insight.affected_cases),
                    insight.status.value,
                    insight.model_used,
                    insight.tokens_used,
                ),
            )
            await db.commit()
            return insight.id

    async def get_insight(self, insight_id: str) -> Optional[Insight]:
        """Get insight by ID"""
        async with self.connect() as db:
            cursor = await db.execute(
                "SELECT * FROM insights WHERE id = ?", (insight_id,)
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return self._row_to_insight(row)

    async def list_insights(
        self,
        status: Optional[str] = None,
        min_confidence: float = 0.0,
        limit: int = 100,
    ) -> list[Insight]:
        """List insights with optional filters"""
        async with self.connect() as db:
            query = "SELECT * FROM insights WHERE confidence >= ?"
            params = [min_confidence]

            if status:
                query += " AND status = ?"
                params.append(status)

            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)

            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
            return [self._row_to_insight(row) for row in rows]

    async def update_insight_status(self, insight_id: str, status: str):
        """Update insight status"""
        async with self.connect() as db:
            await db.execute(
                "UPDATE insights SET status = ? WHERE id = ?", (status, insight_id)
            )
            await db.commit()

    def _row_to_insight(self, row: aiosqlite.Row) -> Insight:
        """Convert database row to Insight model"""
        return Insight(
            id=row["id"],
            type=row["type"],
            trigger_data_ids=self._deserialize_json(row["trigger_data_ids"]) or [],
            title=row["title"],
            body=self._deserialize_json(row["body"]) or {},
            confidence=row["confidence"],
            urgency=row["urgency"],
            suggested_actions=self._deserialize_json(row["suggested_actions"]) or [],
            affected_cases=self._deserialize_json(row["affected_cases"]) or [],
            created_at=self._deserialize_datetime(row["created_at"]),
            status=row["status"],
            model_used=row["model_used"],
            tokens_used=row["tokens_used"] or 0,
        )

    # ========== Proposal CRUD ==========

    async def create_proposal(self, proposal: Proposal) -> str:
        """Create new proposal"""
        async with self.connect() as db:
            await db.execute(
                """
                INSERT INTO proposals
                (id, insight_id, message_text, response, response_latency_sec)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    proposal.id,
                    proposal.insight_id,
                    proposal.message_text,
                    proposal.response.value,
                    proposal.response_latency_sec,
                ),
            )
            await db.commit()
            return proposal.id

    async def update_proposal_response(
        self,
        proposal_id: str,
        response: str,
        response_detail: Optional[str] = None,
        feedback: Optional[str] = None,
    ):
        """Update proposal response"""
        async with self.connect() as db:
            # Calculate response latency
            cursor = await db.execute(
                "SELECT proposed_at FROM proposals WHERE id = ?", (proposal_id,)
            )
            row = await cursor.fetchone()
            if row:
                proposed_at = self._deserialize_datetime(row["proposed_at"])
                latency_sec = int((datetime.now() - proposed_at).total_seconds())
            else:
                latency_sec = None

            await db.execute(
                """
                UPDATE proposals
                SET response = ?, response_at = ?, response_detail = ?,
                    feedback = ?, response_latency_sec = ?
                WHERE id = ?
                """,
                (
                    response,
                    self._serialize_datetime(datetime.now()),
                    response_detail,
                    feedback,
                    latency_sec,
                    proposal_id,
                ),
            )
            await db.commit()

    async def get_proposal(self, proposal_id: str) -> Optional[Proposal]:
        """Get proposal by ID"""
        async with self.connect() as db:
            cursor = await db.execute(
                "SELECT * FROM proposals WHERE id = ?", (proposal_id,)
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return self._row_to_proposal(row)

    def _row_to_proposal(self, row: aiosqlite.Row) -> Proposal:
        """Convert database row to Proposal model"""
        return Proposal(
            id=row["id"],
            insight_id=row["insight_id"],
            message_text=row["message_text"],
            proposed_at=self._deserialize_datetime(row["proposed_at"]),
            response=row["response"],
            response_at=self._deserialize_datetime(row["response_at"]),
            response_detail=row["response_detail"],
            executed_action=row["executed_action"],
            feedback=row["feedback"],
            response_latency_sec=row["response_latency_sec"],
        )

    # ========== CostLog CRUD ==========

    async def log_cost(self, cost_log: CostLog):
        """Log API cost"""
        async with self.connect() as db:
            await db.execute(
                """
                INSERT INTO cost_log
                (id, module, model, input_tokens, output_tokens, cost_krw, insight_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cost_log.id,
                    cost_log.module,
                    cost_log.model,
                    cost_log.input_tokens,
                    cost_log.output_tokens,
                    cost_log.cost_krw,
                    cost_log.insight_id,
                ),
            )
            await db.commit()

    async def get_monthly_cost(self, year: int, month: int) -> float:
        """Get total cost for a specific month"""
        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT SUM(cost_krw) as total
                FROM cost_log
                WHERE strftime('%Y', timestamp) = ? AND strftime('%m', timestamp) = ?
                """,
                (str(year), f"{month:02d}"),
            )
            row = await cursor.fetchone()
            return row["total"] or 0.0

    async def get_cost_breakdown(
        self, year: int, month: int
    ) -> dict[str, dict[str, float]]:
        """Get cost breakdown by module and model"""
        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT module, model, SUM(cost_krw) as total
                FROM cost_log
                WHERE strftime('%Y', timestamp) = ? AND strftime('%m', timestamp) = ?
                GROUP BY module, model
                """,
                (str(year), f"{month:02d}"),
            )
            rows = await cursor.fetchall()

            breakdown = {}
            for row in rows:
                module = row["module"]
                if module not in breakdown:
                    breakdown[module] = {}
                breakdown[module][row["model"]] = row["total"]

            return breakdown

    # ========== MarketingContent CRUD ==========

    async def create_marketing_content(self, content: MarketingContent) -> str:
        """Create new marketing content"""
        async with self.connect() as db:
            await db.execute(
                """
                INSERT INTO marketing_content
                (id, insight_id, content_type, title, target_keyword, seo_meta,
                draft, legal_review, status, published_url, performance, total_cost)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    content.id,
                    content.insight_id,
                    content.content_type.value,
                    content.title,
                    content.target_keyword,
                    self._serialize_json(content.seo_meta),
                    content.draft,
                    self._serialize_json(content.legal_review),
                    content.status.value,
                    content.published_url,
                    self._serialize_json(content.performance),
                    content.total_cost,
                ),
            )
            await db.commit()
            return content.id

    async def get_marketing_content(
        self, content_id: str
    ) -> Optional[MarketingContent]:
        """Get marketing content by ID"""
        async with self.connect() as db:
            cursor = await db.execute(
                "SELECT * FROM marketing_content WHERE id = ?", (content_id,)
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return self._row_to_marketing_content(row)

    async def list_marketing_content(
        self, status: Optional[str] = None, limit: int = 100
    ) -> list[MarketingContent]:
        """List marketing content with optional status filter"""
        async with self.connect() as db:
            if status:
                cursor = await db.execute(
                    "SELECT * FROM marketing_content WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                    (status, limit),
                )
            else:
                cursor = await db.execute(
                    "SELECT * FROM marketing_content ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                )
            rows = await cursor.fetchall()
            return [self._row_to_marketing_content(row) for row in rows]

    async def update_marketing_content_status(self, content_id: str, status: str):
        """Update marketing content status"""
        async with self.connect() as db:
            await db.execute(
                "UPDATE marketing_content SET status = ? WHERE id = ?",
                (status, content_id),
            )
            await db.commit()

    def _row_to_marketing_content(self, row: aiosqlite.Row) -> MarketingContent:
        """Convert database row to MarketingContent model"""
        return MarketingContent(
            id=row["id"],
            insight_id=row["insight_id"],
            content_type=row["content_type"],
            title=row["title"],
            target_keyword=row["target_keyword"],
            seo_meta=self._deserialize_json(row["seo_meta"]) or {},
            draft=row["draft"],
            legal_review=self._deserialize_json(row["legal_review"]) or {},
            status=row["status"],
            published_url=row["published_url"],
            performance=self._deserialize_json(row["performance"]) or {},
            total_cost=row["total_cost"] or 0.0,
            created_at=self._deserialize_datetime(row["created_at"]),
        )

    # ========== WatchLog CRUD ==========

    async def create_watch_log(self, log: WatchLog) -> str:
        """Create watch log"""
        async with self.connect() as db:
            await db.execute(
                """
                INSERT INTO watch_logs
                (id, source, started_at, ended_at, status, items_collected, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    log.id,
                    log.source.value,
                    self._serialize_datetime(log.started_at),
                    self._serialize_datetime(log.ended_at),
                    log.status.value,
                    log.items_collected,
                    log.error_message,
                ),
            )
            await db.commit()
            return log.id

    async def get_crawler_uptime(self, days: int = 7) -> float:
        """Calculate crawler uptime ratio for last N days"""
        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT
                    COUNT(CASE WHEN status = 'SUCCESS' THEN 1 END) as success_count,
                    COUNT(*) as total_count
                FROM watch_logs
                WHERE started_at >= datetime('now', '-' || ? || ' days')
                """,
                (days,),
            )
            row = await cursor.fetchone()
            if row["total_count"] == 0:
                return 0.0
            return row["success_count"] / row["total_count"]

    # ========== SystemMetrics CRUD ==========

    async def save_system_metrics(self, metrics: SystemMetrics):
        """Save or update system metrics for a date"""
        async with self.connect() as db:
            await db.execute(
                """
                INSERT INTO system_metrics
                (id, date, total_insights, high_confidence_ratio, acceptance_rate,
                avg_response_latency_sec, total_cost_krw, crawler_uptime_ratio, top_rejection_reasons)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(date) DO UPDATE SET
                    total_insights = excluded.total_insights,
                    high_confidence_ratio = excluded.high_confidence_ratio,
                    acceptance_rate = excluded.acceptance_rate,
                    avg_response_latency_sec = excluded.avg_response_latency_sec,
                    total_cost_krw = excluded.total_cost_krw,
                    crawler_uptime_ratio = excluded.crawler_uptime_ratio,
                    top_rejection_reasons = excluded.top_rejection_reasons
                """,
                (
                    metrics.id,
                    metrics.date,
                    metrics.total_insights,
                    metrics.high_confidence_ratio,
                    metrics.acceptance_rate,
                    metrics.avg_response_latency_sec,
                    metrics.total_cost_krw,
                    metrics.crawler_uptime_ratio,
                    self._serialize_json(metrics.top_rejection_reasons),
                ),
            )
            await db.commit()


# ========== Global Instance ==========

db = Database()
