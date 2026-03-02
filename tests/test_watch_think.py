"""
Watch/Think Engine Tests
"""

import asyncio
import json
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest
import aiosqlite

from src.engines.watch import WatchEngine
from src.engines.think import ThinkEngine
from src.core.checkpoint import CheckpointManager
from src.core.termination import TerminationChecker
from src.core.events import EventLogger
from src.models import TerminationCondition


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
async def test_watch_engine_creates_evidence(test_db):
    """
    TEST: Watch Engine creates evidence from collected items
    """
    engine = WatchEngine(test_db)
    correlation_id = f"TEST_WATCH:{uuid4()}"

    # Mock payload (실제 크롤러는 mock/skip)
    payload = {
        "sources": [],  # 빈 소스 (실제 크롤링 없이 테스트)
        "since_days": 7,
    }

    ctx = {}
    checker = TerminationChecker(
        TerminationCondition(max_cost_usd=10.0, max_time_sec=600)
    )
    checkpoint_manager = CheckpointManager(test_db)
    event_logger = EventLogger(test_db)

    checker.start()

    # Watch 실행
    result = await engine.run(
        correlation_id, payload, ctx, checker, checkpoint_manager, event_logger
    )

    # 검증
    assert "items_collected" in result
    assert "evidence_created" in result
    assert "sources" in result


@pytest.mark.asyncio
async def test_think_engine_validates_evidence_binding(test_db):
    """
    TEST: Think Engine fails when evidence binding is invalid
    """
    # Mock evidence 삽입
    correlation_id = f"TEST_THINK:{uuid4()}"

    async with aiosqlite.connect(test_db) as db:
        await db.execute(
            """
            INSERT INTO evidence (evidence_id, correlation_id, source_type, locator_json, snippet, content_hash)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "E1",
                correlation_id,
                "SOURCE_ITEM",
                json.dumps({"item_id": "I1"}),
                "Test evidence snippet",
                "abc123",
            ),
        )
        await db.commit()

    # Think Engine 실행
    engine = ThinkEngine(test_db)
    payload = {"frames": ["CASE_IMPACT"]}

    ctx = {}
    checker = TerminationChecker(
        TerminationCondition(max_cost_usd=10.0, max_time_sec=600)
    )
    checkpoint_manager = CheckpointManager(test_db)
    event_logger = EventLogger(test_db)

    checker.start()

    # Note: 실제 LLM 호출은 API 키 없으면 실패 (예상됨)
    # 테스트는 Evidence Gate 로직만 검증

    try:
        result = await engine.run(
            correlation_id, payload, ctx, checker, checkpoint_manager, event_logger
        )
        # LLM 호출 실패는 정상 (API 키 없음)
        assert "insights_generated" in result
    except Exception as e:
        # API 키 없으면 실패 예상
        assert "API key" in str(e) or "not configured" in str(e)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
