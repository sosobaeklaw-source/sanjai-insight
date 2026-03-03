"""
Error Handling Tests
Tests for defensive error handling in engines
"""

import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import aiosqlite

from src.engines.watch import WatchEngine
from src.engines.think import ThinkEngine
from src.engines.propose import ProposeEngine
from src.core.events import EventLogger
from src.core.checkpoint import CheckpointManager
from src.core.termination import TerminationChecker
from src.db import Database


@pytest.fixture
async def test_db():
    """Create test database"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        db = Database(db_path)
        await db.init_db("schema_v2_operational.sql")
        yield db_path


@pytest.fixture
def mock_termination_checker():
    """Mock termination checker"""
    checker = MagicMock(spec=TerminationChecker)
    checker.check.return_value = (False, None)
    checker.add_cost = MagicMock()
    return checker


@pytest.fixture
async def mock_checkpoint_manager(test_db):
    """Mock checkpoint manager"""
    return CheckpointManager(test_db)


@pytest.fixture
async def mock_event_logger(test_db):
    """Mock event logger"""
    return EventLogger(test_db)


# ========== WatchEngine Error Handling Tests ==========


@pytest.mark.asyncio
async def test_watch_handles_crawler_failure(
    test_db, mock_termination_checker, mock_checkpoint_manager, mock_event_logger
):
    """Test WatchEngine handles crawler exceptions gracefully"""
    engine = WatchEngine(test_db)

    # Mock crawler that raises exception
    mock_crawler = MagicMock()
    mock_crawler.crawl = AsyncMock(side_effect=Exception("Crawler failed"))
    engine.crawlers["TEST_SOURCE"] = mock_crawler

    payload = {"sources": ["TEST_SOURCE"], "since_days": 7}
    ctx = {}

    # Should not raise, returns empty results
    result = await engine.run(
        correlation_id="test-123",
        payload=payload,
        ctx=ctx,
        checker=mock_termination_checker,
        checkpoint_manager=mock_checkpoint_manager,
        event_logger=mock_event_logger,
    )

    assert result["items_collected"] == 0
    assert result["evidence_created"] == 0


@pytest.mark.asyncio
async def test_watch_handles_db_timeout(
    test_db, mock_termination_checker, mock_checkpoint_manager, mock_event_logger
):
    """Test WatchEngine handles database timeout"""
    engine = WatchEngine(test_db)

    # Mock crawler that returns data
    mock_crawler = MagicMock()
    mock_crawler.crawl = AsyncMock(return_value=[{"id": "test-1", "title": "Test"}])
    engine.crawlers["TEST_SOURCE"] = mock_crawler

    # Close DB to simulate timeout
    os.remove(test_db)

    payload = {"sources": ["TEST_SOURCE"], "since_days": 7}
    ctx = {}

    # Should handle gracefully
    result = await engine.run(
        correlation_id="test-123",
        payload=payload,
        ctx=ctx,
        checker=mock_termination_checker,
        checkpoint_manager=mock_checkpoint_manager,
        event_logger=mock_event_logger,
    )

    # Should return 0 due to DB error
    assert result["items_collected"] == 0


@pytest.mark.asyncio
async def test_watch_handles_invalid_evidence(
    test_db, mock_termination_checker, mock_checkpoint_manager, mock_event_logger
):
    """Test WatchEngine handles invalid evidence data"""
    engine = WatchEngine(test_db)

    # Mock crawler with malformed data
    mock_crawler = MagicMock()
    mock_crawler.crawl = AsyncMock(
        return_value=[
            {"id": None, "title": None},  # Invalid data
            {},  # Empty data
        ]
    )
    engine.crawlers["TEST_SOURCE"] = mock_crawler

    payload = {"sources": ["TEST_SOURCE"], "since_days": 7}
    ctx = {}

    result = await engine.run(
        correlation_id="test-123",
        payload=payload,
        ctx=ctx,
        checker=mock_termination_checker,
        checkpoint_manager=mock_checkpoint_manager,
        event_logger=mock_event_logger,
    )

    # Should handle gracefully
    assert result is not None


# ========== ThinkEngine Error Handling Tests ==========


@pytest.mark.asyncio
async def test_think_handles_no_evidence(
    test_db, mock_termination_checker, mock_checkpoint_manager, mock_event_logger
):
    """Test ThinkEngine handles missing evidence gracefully"""
    engine = ThinkEngine(test_db)

    payload = {"frames": ["CASE_IMPACT"]}
    ctx = {}

    result = await engine.run(
        correlation_id="test-123",
        payload=payload,
        ctx=ctx,
        checker=mock_termination_checker,
        checkpoint_manager=mock_checkpoint_manager,
        event_logger=mock_event_logger,
    )

    assert result["insights_generated"] == 0
    assert result["insights_passed"] == 0


@pytest.mark.asyncio
async def test_think_handles_llm_failure(
    test_db, mock_termination_checker, mock_checkpoint_manager, mock_event_logger
):
    """Test ThinkEngine handles LLM API failures"""
    engine = ThinkEngine(test_db)

    # Add test evidence
    async with aiosqlite.connect(test_db) as db:
        await db.execute(
            """
            INSERT INTO evidence (evidence_id, correlation_id, source_type, locator_json, snippet)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("ev-1", "test-123", "SOURCE_ITEM", "{}", "Test evidence")
        )
        await db.commit()

    # Mock LLM to fail
    with patch.object(engine.llm_client, "call", side_effect=Exception("LLM API failed")):
        payload = {"frames": ["CASE_IMPACT"]}
        ctx = {}

        result = await engine.run(
            correlation_id="test-123",
            payload=payload,
            ctx=ctx,
            checker=mock_termination_checker,
            checkpoint_manager=mock_checkpoint_manager,
            event_logger=mock_event_logger,
        )

        # Should handle gracefully
        assert result["insights_generated"] == 0


@pytest.mark.asyncio
async def test_think_handles_invalid_json(
    test_db, mock_termination_checker, mock_checkpoint_manager, mock_event_logger
):
    """Test ThinkEngine handles invalid JSON from LLM"""
    engine = ThinkEngine(test_db)

    # Add test evidence
    async with aiosqlite.connect(test_db) as db:
        await db.execute(
            """
            INSERT INTO evidence (evidence_id, correlation_id, source_type, locator_json, snippet)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("ev-1", "test-123", "SOURCE_ITEM", "{}", "Test evidence")
        )
        await db.commit()

    # Mock LLM to return invalid JSON
    mock_meta = {
        "model": "test",
        "tokens_in": 100,
        "tokens_out": 50,
        "latency_ms": 100,
        "cost_usd": 0.001,
    }
    with patch.object(
        engine.llm_client,
        "call",
        return_value=("Invalid JSON response", mock_meta),
    ):
        payload = {"frames": ["CASE_IMPACT"]}
        ctx = {}

        result = await engine.run(
            correlation_id="test-123",
            payload=payload,
            ctx=ctx,
            checker=mock_termination_checker,
            checkpoint_manager=mock_checkpoint_manager,
            event_logger=mock_event_logger,
        )

        assert result["insights_generated"] == 0


# ========== ProposeEngine Error Handling Tests ==========


@pytest.mark.asyncio
async def test_propose_handles_no_insights(
    test_db, mock_termination_checker, mock_checkpoint_manager, mock_event_logger
):
    """Test ProposeEngine handles no insights gracefully"""
    engine = ProposeEngine(test_db)

    payload = {"min_confidence": 0.7}
    ctx = {}

    result = await engine.run(
        correlation_id="test-123",
        payload=payload,
        ctx=ctx,
        checker=mock_termination_checker,
        checkpoint_manager=mock_checkpoint_manager,
        event_logger=mock_event_logger,
    )

    assert result["proposals_created"] == 0
    assert result["proposals_sent"] == 0


@pytest.mark.asyncio
async def test_propose_handles_telegram_failure(
    test_db, mock_termination_checker, mock_checkpoint_manager, mock_event_logger
):
    """Test ProposeEngine handles Telegram send failures"""
    engine = ProposeEngine(test_db)

    # Add test insight
    async with aiosqlite.connect(test_db) as db:
        await db.execute(
            """
            INSERT INTO insights (id, type, title, body, confidence, urgency, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("insight-1", "CASE_IMPACT", "Test", "{}", 0.8, "HIGH", "NEW")
        )
        await db.commit()

    # Mock telegram bot that fails
    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock(side_effect=Exception("Telegram API failed"))

    payload = {
        "min_confidence": 0.7,
        "telegram_bot": mock_bot,
        "chat_id": 12345,
    }
    ctx = {}

    result = await engine.run(
        correlation_id="test-123",
        payload=payload,
        ctx=ctx,
        checker=mock_termination_checker,
        checkpoint_manager=mock_checkpoint_manager,
        event_logger=mock_event_logger,
    )

    # Proposal created but not sent
    assert result["proposals_created"] == 1
    assert result["proposals_sent"] == 0


@pytest.mark.asyncio
async def test_propose_handles_db_timeout(
    test_db, mock_termination_checker, mock_checkpoint_manager, mock_event_logger
):
    """Test ProposeEngine handles database timeout"""
    engine = ProposeEngine(test_db)

    # Remove DB to simulate failure
    os.remove(test_db)

    payload = {"min_confidence": 0.7}
    ctx = {}

    # Should handle gracefully
    result = await engine.run(
        correlation_id="test-123",
        payload=payload,
        ctx=ctx,
        checker=mock_termination_checker,
        checkpoint_manager=mock_checkpoint_manager,
        event_logger=mock_event_logger,
    )

    assert result["proposals_created"] == 0
