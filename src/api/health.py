"""
Health Check Endpoints
/healthz - Simple liveness check (200/non-200)
/health - Detailed health status
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiosqlite

from ..models import HealthStatus


async def get_healthz(db_path: str) -> tuple[int, str]:
    """
    Simple liveness check
    Returns: (status_code, message)
    """
    try:
        # Check DB connection
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute("SELECT 1")
            await cursor.fetchone()

        # Check if tables exist
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'"
            )
            row = await cursor.fetchone()
            if not row:
                return (503, "Tables not initialized")

        return (200, "OK")

    except Exception as e:
        return (503, f"Unhealthy: {str(e)}")


async def get_health(db_path: str, telegram_token: Optional[str] = None) -> HealthStatus:
    """
    Detailed health check
    Returns: HealthStatus model
    """
    # DB connection
    db_connected = False
    db_wal_enabled = False
    try:
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute("SELECT 1")
            await cursor.fetchone()
            db_connected = True

            # Check WAL mode
            cursor = await db.execute("PRAGMA journal_mode")
            row = await cursor.fetchone()
            if row and row[0] == "wal":
                db_wal_enabled = True
    except Exception:
        pass

    # Telegram configured
    telegram_configured = bool(telegram_token)

    # Vault accessible
    vault_path = os.getenv("VAULT_PATH", "/data/vault")
    vault_accessible = Path(vault_path).exists() if vault_path else False

    # Get operational metrics
    last_success_run = None
    pending_jobs = 0
    running_jobs = 0
    active_runs = 0
    insights_24h = 0
    pending_proposals = 0
    cost_24h_usd = 0.0

    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row

            # Last success run
            cursor = await db.execute(
                """
                SELECT MAX(started_at) as last_run
                FROM runlogs
                WHERE status = 'COMPLETED'
                """
            )
            row = await cursor.fetchone()
            if row and row["last_run"]:
                last_success_run = datetime.fromisoformat(row["last_run"])

            # Pending/Running jobs
            cursor = await db.execute(
                "SELECT COUNT(*) as cnt FROM jobs WHERE status = 'PENDING'"
            )
            row = await cursor.fetchone()
            pending_jobs = row["cnt"] if row else 0

            cursor = await db.execute(
                "SELECT COUNT(*) as cnt FROM jobs WHERE status = 'RUNNING'"
            )
            row = await cursor.fetchone()
            running_jobs = row["cnt"] if row else 0

            # Active runs
            cursor = await db.execute(
                "SELECT COUNT(*) as cnt FROM runlogs WHERE status = 'RUNNING'"
            )
            row = await cursor.fetchone()
            active_runs = row["cnt"] if row else 0

            # Insights 24h
            cursor = await db.execute(
                """
                SELECT COUNT(*) as cnt FROM insights
                WHERE created_at >= datetime('now', '-24 hours')
                """
            )
            row = await cursor.fetchone()
            insights_24h = row["cnt"] if row else 0

            # Pending proposals
            cursor = await db.execute(
                "SELECT COUNT(*) as cnt FROM proposals WHERE response = 'PENDING'"
            )
            row = await cursor.fetchone()
            pending_proposals = row["cnt"] if row else 0

            # Cost 24h
            cursor = await db.execute(
                """
                SELECT SUM(cost_usd) as total FROM llm_calls
                WHERE created_at >= datetime('now', '-24 hours')
                """
            )
            row = await cursor.fetchone()
            cost_24h_usd = row["total"] if row and row["total"] else 0.0

    except Exception:
        pass

    return HealthStatus(
        db_connected=db_connected,
        db_wal_enabled=db_wal_enabled,
        telegram_configured=telegram_configured,
        vault_accessible=vault_accessible,
        last_success_run=last_success_run,
        pending_jobs=pending_jobs,
        running_jobs=running_jobs,
        active_runs=active_runs,
        insights_24h=insights_24h,
        pending_proposals=pending_proposals,
        cost_24h_usd=cost_24h_usd,
    )
