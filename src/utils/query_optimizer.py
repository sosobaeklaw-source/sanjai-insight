"""
Query Optimizer Utilities
Helper functions for optimized database queries.
"""

import sqlite3
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple


class QueryOptimizer:
    """Database query optimization helpers"""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def get_connection(self) -> sqlite3.Connection:
        """Get optimized database connection"""
        conn = sqlite3.connect(self.db_path)

        # Performance optimizations
        conn.execute("PRAGMA journal_mode=WAL")  # Write-Ahead Logging
        conn.execute("PRAGMA synchronous=NORMAL")  # Faster commits
        conn.execute("PRAGMA cache_size=-64000")  # 64MB cache
        conn.execute("PRAGMA temp_store=MEMORY")  # Temp tables in memory
        conn.execute("PRAGMA mmap_size=268435456")  # 256MB memory-mapped I/O
        conn.execute("PRAGMA page_size=4096")  # Optimal page size

        return conn

    def analyze_tables(self):
        """Update SQLite statistics for query planner"""
        with self.get_connection() as conn:
            conn.execute("ANALYZE")
            conn.commit()

    def vacuum_database(self):
        """Vacuum database to reclaim space and defragment"""
        with self.get_connection() as conn:
            conn.execute("VACUUM")

    def get_table_sizes(self) -> List[Dict[str, Any]]:
        """Get size information for all tables"""
        with self.get_connection() as conn:
            cursor = conn.execute("""
                SELECT
                    name,
                    (SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND tbl_name=m.name) as index_count,
                    (SELECT COUNT(*) FROM pragma_table_info(m.name)) as column_count
                FROM sqlite_master m
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
                ORDER BY name
            """)

            tables = []
            for row in cursor.fetchall():
                table_name = row[0]

                # Get row count
                count_cursor = conn.execute(f"SELECT COUNT(*) FROM {table_name}")
                row_count = count_cursor.fetchone()[0]

                tables.append({
                    "name": table_name,
                    "row_count": row_count,
                    "index_count": row[1],
                    "column_count": row[2]
                })

            return tables

    def get_index_usage(self, table_name: str) -> List[Dict[str, Any]]:
        """Get index information for a table"""
        with self.get_connection() as conn:
            cursor = conn.execute(f"""
                SELECT name, sql
                FROM sqlite_master
                WHERE type='index' AND tbl_name=?
                ORDER BY name
            """, (table_name,))

            return [
                {"name": row[0], "sql": row[1]}
                for row in cursor.fetchall()
            ]

    def explain_query(self, query: str, params: tuple = ()) -> str:
        """Get query execution plan"""
        with self.get_connection() as conn:
            cursor = conn.execute(f"EXPLAIN QUERY PLAN {query}", params)
            plan = "\n".join(
                f"{row[0]}: {row[3]}"
                for row in cursor.fetchall()
            )
            return plan

    def get_slow_queries_estimate(self, query: str, params: tuple = ()) -> dict:
        """Estimate if query will be slow based on execution plan"""
        plan = self.explain_query(query, params)

        # Heuristics for slow queries
        is_slow = any([
            "SCAN TABLE" in plan and "USING INDEX" not in plan,  # Full table scan
            "TEMP B-TREE" in plan,  # Temp tables (expensive)
            "USE TEMP B-TREE FOR ORDER BY" in plan  # Sort without index
        ])

        return {
            "query": query,
            "is_potentially_slow": is_slow,
            "execution_plan": plan,
            "recommendations": self._get_query_recommendations(plan)
        }

    def _get_query_recommendations(self, plan: str) -> List[str]:
        """Get optimization recommendations based on execution plan"""
        recommendations = []

        if "SCAN TABLE" in plan and "USING INDEX" not in plan:
            recommendations.append("Add index on queried columns to avoid full table scan")

        if "TEMP B-TREE" in plan:
            recommendations.append("Consider adding covering index to avoid temp tables")

        if "USE TEMP B-TREE FOR ORDER BY" in plan:
            recommendations.append("Add index on ORDER BY columns")

        if not recommendations:
            recommendations.append("Query is well optimized")

        return recommendations


# Optimized query helpers

def get_cost_summary_optimized(
    conn: sqlite3.Connection,
    start_date: str,
    end_date: str
) -> Dict[str, Any]:
    """
    Optimized cost summary query using indexes.

    Uses idx_llm_calls_cost_date and idx_llm_calls_stage_cost.
    """
    cursor = conn.execute("""
        SELECT
            SUM(cost_usd) as total_cost,
            COUNT(*) as total_calls,
            AVG(cost_usd) as avg_cost,
            SUM(tokens_in + tokens_out) as total_tokens
        FROM llm_calls
        WHERE created_at BETWEEN ? AND ?
    """, (start_date, end_date))

    result = cursor.fetchone()

    # Stage breakdown
    stage_cursor = conn.execute("""
        SELECT
            stage,
            SUM(cost_usd) as stage_cost,
            COUNT(*) as stage_calls
        FROM llm_calls
        WHERE created_at BETWEEN ? AND ?
        GROUP BY stage
        ORDER BY stage_cost DESC
    """, (start_date, end_date))

    stages = [
        {"stage": r[0], "cost": r[1], "calls": r[2]}
        for r in stage_cursor.fetchall()
    ]

    return {
        "total_cost": result[0] or 0,
        "total_calls": result[1] or 0,
        "avg_cost": result[2] or 0,
        "total_tokens": result[3] or 0,
        "by_stage": stages
    }


def get_health_check_optimized(conn: sqlite3.Connection) -> Dict[str, Any]:
    """
    Optimized health check query using covering indexes.

    Uses idx_jobs_status_created and idx_runlogs_status_started.
    """
    # Jobs status
    jobs_cursor = conn.execute("""
        SELECT status, COUNT(*) as count
        FROM jobs
        WHERE status IN ('PENDING', 'RUNNING')
        GROUP BY status
    """)
    jobs_status = dict(jobs_cursor.fetchall())

    # Recent runs
    runs_cursor = conn.execute("""
        SELECT
            status,
            COUNT(*) as count,
            MAX(started_at) as latest
        FROM runlogs
        WHERE started_at >= datetime('now', '-24 hours')
        GROUP BY status
    """)
    runs_status = {
        row[0]: {"count": row[1], "latest": row[2]}
        for row in runs_cursor.fetchall()
    }

    # Recent insights
    insights_cursor = conn.execute("""
        SELECT COUNT(*) FROM insights
        WHERE created_at >= datetime('now', '-24 hours')
    """)
    insights_24h = insights_cursor.fetchone()[0]

    return {
        "pending_jobs": jobs_status.get("PENDING", 0),
        "running_jobs": jobs_status.get("RUNNING", 0),
        "runs_24h": runs_status,
        "insights_24h": insights_24h,
        "timestamp": datetime.utcnow().isoformat()
    }


def get_quality_metrics_optimized(
    conn: sqlite3.Connection,
    days: int = 7
) -> Dict[str, Any]:
    """
    Optimized quality metrics query.

    Uses idx_strategy_packs_validation and idx_approvals_decision_date.
    """
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()

    # Validation status
    validation_cursor = conn.execute("""
        SELECT
            validation_status,
            COUNT(*) as count,
            AVG(CAST((SELECT generated_claims FROM strategy_pack_metrics WHERE pack_id = strategy_packs.pack_id) AS FLOAT)) as avg_claims
        FROM strategy_packs
        WHERE created_at >= ?
        GROUP BY validation_status
    """, (since,))

    validation = {
        row[0]: {"count": row[1], "avg_claims": row[2]}
        for row in validation_cursor.fetchall()
    }

    # Approval rate
    approval_cursor = conn.execute("""
        SELECT
            decision,
            COUNT(*) as count
        FROM approvals
        WHERE decided_at >= ?
        GROUP BY decision
    """, (since,))

    approvals = dict(approval_cursor.fetchall())
    total_approvals = sum(approvals.values())
    approval_rate = approvals.get("APPROVE", 0) / total_approvals if total_approvals > 0 else 0

    return {
        "validation": validation,
        "approvals": approvals,
        "approval_rate": approval_rate,
        "days": days
    }


def get_correlation_status_optimized(
    conn: sqlite3.Connection,
    correlation_id: str
) -> Dict[str, Any]:
    """
    Optimized correlation status query.

    Uses idx_runlogs_health_cover and idx_events_type_correlation.
    """
    # Runlog info
    runlog_cursor = conn.execute("""
        SELECT status, started_at, ended_at, total_cost_usd, total_tokens
        FROM runlogs
        WHERE correlation_id = ?
    """, (correlation_id,))

    runlog = runlog_cursor.fetchone()
    if not runlog:
        return {"error": "Correlation ID not found"}

    # Events
    events_cursor = conn.execute("""
        SELECT type, COUNT(*) as count
        FROM events
        WHERE correlation_id = ?
        GROUP BY type
    """, (correlation_id,))

    events = dict(events_cursor.fetchall())

    # LLM calls
    llm_cursor = conn.execute("""
        SELECT
            stage,
            COUNT(*) as calls,
            SUM(cost_usd) as cost,
            SUM(tokens_in + tokens_out) as tokens
        FROM llm_calls
        WHERE correlation_id = ?
        GROUP BY stage
    """, (correlation_id,))

    llm_calls = [
        {"stage": r[0], "calls": r[1], "cost": r[2], "tokens": r[3]}
        for r in llm_cursor.fetchall()
    ]

    return {
        "correlation_id": correlation_id,
        "status": runlog[0],
        "started_at": runlog[1],
        "ended_at": runlog[2],
        "total_cost": runlog[3],
        "total_tokens": runlog[4],
        "events": events,
        "llm_calls": llm_calls
    }


def get_database_stats(conn: sqlite3.Connection) -> Dict[str, Any]:
    """Get comprehensive database statistics"""
    # Page count
    page_cursor = conn.execute("SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()")
    db_size = page_cursor.fetchone()[0]

    # Table stats
    table_cursor = conn.execute("""
        SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'
    """)

    table_stats = []
    for (table_name,) in table_cursor.fetchall():
        count_cursor = conn.execute(f"SELECT COUNT(*) FROM {table_name}")
        row_count = count_cursor.fetchone()[0]
        table_stats.append({"table": table_name, "rows": row_count})

    return {
        "size_bytes": db_size,
        "size_mb": db_size / (1024 * 1024),
        "tables": table_stats
    }
