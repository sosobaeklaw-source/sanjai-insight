"""
Health Check Tests
Tests for /healthz and /health endpoints
"""

import os
import tempfile
from pathlib import Path

import pytest
import aiosqlite

from src.api.health import get_healthz, get_health
from src.db import Database


@pytest.fixture
async def test_db():
    """Create test database"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        db = Database(db_path)

        # Initialize with schema
        schema_path = "schema_v2_operational.sql"
        if not Path(schema_path).exists():
            schema_path = "schema.sql"

        await db.init_db(schema_path)

        yield db_path


@pytest.mark.asyncio
async def test_healthz_success(test_db):
    """Test /healthz returns 200 for healthy database"""
    status_code, message = await get_healthz(test_db)

    assert status_code == 200
    assert message == "OK"


@pytest.mark.asyncio
async def test_healthz_missing_tables():
    """Test /healthz returns 503 for uninitialized database"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "empty.db")

        # Create empty database (no tables)
        async with aiosqlite.connect(db_path) as db:
            await db.execute("SELECT 1")

        status_code, message = await get_healthz(db_path)

        assert status_code == 503
        assert "not initialized" in message


@pytest.mark.asyncio
async def test_healthz_missing_db():
    """Test /healthz returns 503 for missing database"""
    status_code, message = await get_healthz("/nonexistent/path.db")

    assert status_code == 503
    assert "Unhealthy" in message


@pytest.mark.asyncio
async def test_health_success(test_db):
    """Test /health returns detailed status"""
    health = await get_health(test_db, telegram_token="test-token")

    assert health.db_connected is True
    assert health.db_wal_enabled is True
    assert health.telegram_configured is True
    assert health.pending_jobs == 0
    assert health.running_jobs == 0


@pytest.mark.asyncio
async def test_health_no_telegram(test_db):
    """Test /health with no Telegram token"""
    health = await get_health(test_db, telegram_token=None)

    assert health.db_connected is True
    assert health.telegram_configured is False


@pytest.mark.asyncio
async def test_health_missing_db():
    """Test /health with missing database"""
    health = await get_health("/nonexistent/path.db")

    assert health.db_connected is False
    assert health.db_wal_enabled is False


@pytest.mark.asyncio
async def test_health_with_data(test_db):
    """Test /health with existing data"""
    # Insert test data
    async with aiosqlite.connect(test_db) as db:
        # Add a pending job
        await db.execute(
            """
            INSERT INTO jobs (job_id, handler_name, payload_json, status)
            VALUES (?, ?, ?, ?)
            """,
            ("test-job-1", "WATCH", "{}", "PENDING")
        )

        # Add a running job
        await db.execute(
            """
            INSERT INTO jobs (job_id, handler_name, payload_json, status)
            VALUES (?, ?, ?, ?)
            """,
            ("test-job-2", "THINK", "{}", "RUNNING")
        )

        # Add an insight
        await db.execute(
            """
            INSERT INTO insights (id, type, title, body, confidence, urgency, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("insight-1", "CASE_IMPACT", "Test Insight", "{}", 0.85, "HIGH", "NEW")
        )

        await db.commit()

    health = await get_health(test_db)

    assert health.db_connected is True
    assert health.pending_jobs == 1
    assert health.running_jobs == 1
    assert health.insights_24h == 1


@pytest.mark.asyncio
async def test_health_db_timeout():
    """Test health check handles database timeout gracefully"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "locked.db")

        # Create database
        async with aiosqlite.connect(db_path) as db:
            await db.execute("CREATE TABLE test (id INTEGER)")
            await db.commit()

        # Lock database by opening long transaction
        lock_conn = await aiosqlite.connect(db_path)
        await lock_conn.execute("BEGIN EXCLUSIVE")

        try:
            # Health check should timeout gracefully
            health = await get_health(db_path)

            # Should return partial status
            assert health is not None
        finally:
            await lock_conn.close()
