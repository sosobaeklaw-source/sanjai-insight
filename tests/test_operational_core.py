"""
Operational Core Tests (WP-1, WP-2)
Critical regression tests for operational guarantees
"""

import asyncio
import json
import tempfile
from pathlib import Path

import pytest
import aiosqlite

from src.core.checkpoint import CheckpointManager
from src.core.events import EventLogger
from src.core.jobs import JobManager
from src.core.termination import TerminationChecker
from src.models import EventType, TerminationCondition


@pytest.fixture
async def test_db():
    """Create test database"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    # Initialize schema
    schema_base = Path(__file__).parent.parent / "schema.sql"
    schema_operational = Path(__file__).parent.parent / "schema_v2_operational.sql"

    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")

        if schema_base.exists():
            await db.executescript(schema_base.read_text(encoding="utf-8"))

        if schema_operational.exists():
            await db.executescript(schema_operational.read_text(encoding="utf-8"))

        await db.commit()

    yield db_path

    # Cleanup
    Path(db_path).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_job_key_idempotency(test_db):
    """
    TEST: Job key idempotency (중복 방지)
    WP-1 필수 조건
    """
    job_manager = JobManager(test_db)

    # First enqueue
    job_id_1 = await job_manager.enqueue(
        job_key="WATCH_DAILY:2026-03-03",
        job_type="WATCH",
        payload={"source": "SUPREME_COURT"},
    )

    assert job_id_1 is not None

    # Second enqueue (same job_key)
    job_id_2 = await job_manager.enqueue(
        job_key="WATCH_DAILY:2026-03-03",
        job_type="WATCH",
        payload={"source": "SUPREME_COURT"},
    )

    assert job_id_2 is None  # Idempotent: returns None

    # Verify only 1 job exists
    async with aiosqlite.connect(test_db) as db:
        cursor = await db.execute("SELECT COUNT(*) as cnt FROM jobs")
        row = await cursor.fetchone()
        assert row[0] == 1


@pytest.mark.asyncio
async def test_checkpoint_save_load(test_db):
    """
    TEST: Checkpoint save/load
    재기동 시 checkpoint로 재개 가능
    """
    checkpoint_manager = CheckpointManager(test_db)

    correlation_id = "DAILY_WATCH:2026-03-03"
    ctx = {"stage": "THINK", "items_collected": 50, "insights_generated": 3}

    # Save checkpoint
    await checkpoint_manager.save(correlation_id, "THINK", ctx)

    # Load checkpoint
    checkpoint = await checkpoint_manager.load(correlation_id)

    assert checkpoint is not None
    assert checkpoint.correlation_id == correlation_id
    assert checkpoint.last_stage == "THINK"
    assert checkpoint.ctx_json["items_collected"] == 50


@pytest.mark.asyncio
async def test_termination_condition(test_db):
    """
    TEST: Termination condition check
    비용/시간/재시도 제한
    """
    condition = TerminationCondition(
        max_cost_usd=1.0,
        max_time_sec=10,
        max_retries=3,
        max_rebuilds=3,
    )

    checker = TerminationChecker(condition)
    checker.start()

    # Test cost limit
    checker.add_cost(0.5)
    should_terminate, reason = checker.check()
    assert not should_terminate

    checker.add_cost(0.6)  # Total: 1.1
    should_terminate, reason = checker.check()
    assert should_terminate
    assert "Cost limit" in reason


@pytest.mark.asyncio
async def test_event_logging(test_db):
    """
    TEST: Event logging (append-only)
    correlation_id 기반 추적
    """
    event_logger = EventLogger(test_db)

    correlation_id = "DAILY_WATCH:2026-03-03"

    # Log events
    await event_logger.log(
        EventType.WATCH_START,
        correlation_id,
        {"source": "SUPREME_COURT"},
    )

    await event_logger.log(
        EventType.ITEM_COLLECTED,
        correlation_id,
        {"item_id": "I123", "title": "Test case"},
    )

    # Get events
    events = await event_logger.get_events(correlation_id)

    assert len(events) == 2
    assert events[0].type == EventType.ITEM_COLLECTED  # DESC order
    assert events[1].type == EventType.WATCH_START


@pytest.mark.asyncio
async def test_approval_idempotency(test_db):
    """
    TEST: Approval idempotency (중복 클릭 방어)
    WP-6 필수 조건
    """
    from src.bot.approval_handler import ApprovalHandler
    from src.models import ApprovalDecision

    # Create proposal
    proposal_id = "P123"
    async with aiosqlite.connect(test_db) as db:
        await db.execute(
            """
            INSERT INTO insights (id, type, trigger_data_ids, title, body, confidence, urgency)
            VALUES ('I123', 'CASE_IMPACT', '[]', 'Test', '{}', 0.8, 'HIGH')
            """
        )
        await db.execute(
            """
            INSERT INTO proposals (id, insight_id, message_text)
            VALUES (?, 'I123', 'Test proposal')
            """,
            (proposal_id,),
        )
        await db.commit()

    handler = ApprovalHandler(test_db)

    # First approval
    success_1, msg_1 = await handler.process_approval(
        proposal_id, chat_id=123, decision=ApprovalDecision.APPROVE
    )

    assert success_1 is True

    # Second approval (duplicate)
    success_2, msg_2 = await handler.process_approval(
        proposal_id, chat_id=123, decision=ApprovalDecision.APPROVE
    )

    assert success_2 is False
    assert "duplicate" in msg_2.lower()

    # Verify only 1 approval
    async with aiosqlite.connect(test_db) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM approvals WHERE proposal_id = ?",
            (proposal_id,),
        )
        row = await cursor.fetchone()
        assert row[0] == 1


@pytest.mark.asyncio
async def test_telegram_update_idempotency(test_db):
    """
    TEST: Telegram update_id idempotency
    웹훅 중복 방지
    """
    from src.bot.idempotency import TelegramIdempotency

    idempotency = TelegramIdempotency(test_db)

    update_id = 123456
    chat_id = 789
    payload = {"message": "test"}

    # First process
    is_new_1 = await idempotency.mark_processed(update_id, chat_id, payload)
    assert is_new_1 is True

    # Second process (duplicate)
    is_new_2 = await idempotency.mark_processed(update_id, chat_id, payload)
    assert is_new_2 is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
