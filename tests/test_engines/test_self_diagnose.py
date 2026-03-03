"""
Tests for Self-Diagnose Engine
"""

import pytest
import os
from datetime import datetime, timedelta
from uuid import uuid4

from src.engines.self_diagnose import SelfDiagnoseEngine
from src.core.events import EventLogger
from src.core.checkpoint import CheckpointManager
from src.core.termination import TerminationChecker
from src.models import TerminationCondition, EventType


@pytest.mark.asyncio
async def test_health_check_pass(test_db):
    """건강한 시스템 체크"""
    db_path = test_db.db_path
    engine = SelfDiagnoseEngine(db_path)

    # 정상 데이터 설정
    import aiosqlite
    async with aiosqlite.connect(db_path) as db:
        # 최근 성공 실행
        await db.execute(
            """
            INSERT INTO runlogs (run_id, correlation_id, job_id, status, started_at, ended_at)
            VALUES (?, ?, ?, 'COMPLETED', datetime('now', '-1 hour'), datetime('now', '-30 minutes'))
            """,
            (str(uuid4()), str(uuid4()), str(uuid4())),
        )
        await db.commit()

    result = await engine._check_health()

    assert result["status"] == "PASS"
    assert result["metrics"]["db_connected"] is True
    assert "hours_since_last_success" in result["metrics"]
    assert result["metrics"]["hours_since_last_success"] < 24


@pytest.mark.asyncio
async def test_health_check_fail_no_recent_runs(test_db):
    """최근 실행 없음 체크"""
    db_path = test_db.db_path
    engine = SelfDiagnoseEngine(db_path)

    # 오래된 실행만 있음
    import aiosqlite
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT INTO runlogs (run_id, correlation_id, job_id, status, started_at, ended_at)
            VALUES (?, ?, ?, 'COMPLETED', datetime('now', '-72 hours'), datetime('now', '-71 hours'))
            """,
            (str(uuid4()), str(uuid4()), str(uuid4())),
        )
        await db.commit()

    result = await engine._check_health()

    assert result["status"] == "FAIL"
    assert any("No successful run" in issue["message"] for issue in result["issues"])


@pytest.mark.asyncio
async def test_cost_check_within_budget(test_db):
    """비용 체크 - 정상 범위"""
    db_path = test_db.db_path
    engine = SelfDiagnoseEngine(db_path)

    # 24시간 비용 $3
    import aiosqlite
    async with aiosqlite.connect(db_path) as db:
        for i in range(10):
            await db.execute(
                """
                INSERT INTO llm_calls
                (id, correlation_id, stage, model, tokens_in, tokens_out, latency_ms, cost_usd, created_at)
                VALUES (?, ?, 'THINK', 'claude-sonnet-4-5-20250929', 1000, 500, 2000, 0.3, datetime('now', '-' || ? || ' hours'))
                """,
                (str(uuid4()), str(uuid4()), i),
            )
        await db.commit()

    result = await engine._check_cost()

    assert result["status"] == "PASS"
    assert result["metrics"]["cost_24h_usd"] == 3.0


@pytest.mark.asyncio
async def test_cost_check_exceeds_threshold(test_db):
    """비용 체크 - 임계값 초과"""
    db_path = test_db.db_path
    engine = SelfDiagnoseEngine(db_path)

    # 24시간 비용 $15
    import aiosqlite
    async with aiosqlite.connect(db_path) as db:
        for i in range(15):
            await db.execute(
                """
                INSERT INTO llm_calls
                (id, correlation_id, stage, model, tokens_in, tokens_out, latency_ms, cost_usd, created_at)
                VALUES (?, ?, 'THINK', 'claude-sonnet-4-5-20250929', 1000, 500, 2000, 1.0, datetime('now'))
                """,
                (str(uuid4()), str(uuid4())),
            )
        await db.commit()

    result = await engine._check_cost()

    assert result["status"] == "FAIL"
    assert any("exceeds $10 threshold" in issue["message"] for issue in result["issues"])
    assert result["metrics"]["cost_24h_usd"] == 15.0


@pytest.mark.asyncio
async def test_quality_check_low_insights(test_db):
    """품질 체크 - 인사이트 부족"""
    db_path = test_db.db_path
    engine = SelfDiagnoseEngine(db_path)

    # 24시간 내 인사이트 1개만
    import aiosqlite
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT INTO insights
            (id, type, trigger_data_ids, title, body, confidence, urgency, suggested_actions, affected_cases, status)
            VALUES (?, 'CASE_IMPACT', '[]', 'Test Insight', '{}', 0.8, 'MEDIUM', '[]', '[]', 'NEW')
            """,
            (str(uuid4()),),
        )
        await db.commit()

    result = await engine._check_quality()

    assert any("Only" in issue["message"] and "insights" in issue["message"] for issue in result["issues"])
    assert result["metrics"]["insights_24h"] == 1


@pytest.mark.asyncio
async def test_quality_check_high_rejection_rate(test_db):
    """품질 체크 - 높은 거절률"""
    db_path = test_db.db_path
    engine = SelfDiagnoseEngine(db_path)

    # 생성 2개, 거절 5개
    import aiosqlite
    async with aiosqlite.connect(db_path) as db:
        for i in range(2):
            await db.execute(
                """
                INSERT INTO events (id, ts, type, correlation_id, payload_json)
                VALUES (?, datetime('now'), 'INSIGHT_CREATED', ?, '{}')
                """,
                (str(uuid4()), str(uuid4())),
            )
        for i in range(5):
            await db.execute(
                """
                INSERT INTO events (id, ts, type, correlation_id, payload_json)
                VALUES (?, datetime('now'), 'INSIGHT_REJECTED', ?, '{}')
                """,
                (str(uuid4()), str(uuid4())),
            )
        await db.commit()

    result = await engine._check_quality()

    assert any("rejection rate" in issue["message"] for issue in result["issues"])
    assert result["metrics"]["rejection_rate"] > 0.5


@pytest.mark.asyncio
async def test_performance_check(test_db):
    """성능 체크"""
    db_path = test_db.db_path
    engine = SelfDiagnoseEngine(db_path)

    # LLM 호출 시간 데이터
    import aiosqlite
    async with aiosqlite.connect(db_path) as db:
        for i in range(5):
            await db.execute(
                """
                INSERT INTO llm_calls
                (id, correlation_id, stage, model, tokens_in, tokens_out, latency_ms, cost_usd, created_at)
                VALUES (?, ?, 'THINK', 'claude-sonnet-4-5-20250929', 1000, 500, 3000, 0.2, datetime('now'))
                """,
                (str(uuid4()), str(uuid4())),
            )
        await db.commit()

    result = await engine._check_performance()

    assert result["status"] == "PASS"
    assert result["metrics"]["avg_llm_latency_ms"] == 3000.0


@pytest.mark.asyncio
async def test_overall_health_evaluation(test_db):
    """전체 건강도 평가"""
    db_path = test_db.db_path
    engine = SelfDiagnoseEngine(db_path)

    # HEALTHY
    results = {"issues": [{"severity": "LOW"}]}
    assert engine._evaluate_overall_health(results) == "HEALTHY"

    # DEGRADED
    results = {
        "issues": [
            {"severity": "HIGH"},
            {"severity": "HIGH"},
        ]
    }
    assert engine._evaluate_overall_health(results) == "DEGRADED"

    # CRITICAL
    results = {"issues": [{"severity": "CRITICAL"}]}
    assert engine._evaluate_overall_health(results) == "CRITICAL"


@pytest.mark.asyncio
async def test_run_full_diagnose(test_db):
    """전체 진단 실행"""
    db_path = test_db.db_path
    engine = SelfDiagnoseEngine(db_path)

    correlation_id = str(uuid4())
    payload = {"checks": ["health", "cost"]}
    ctx = {}

    checker = TerminationChecker(
        TerminationCondition(
            max_cost_usd=5.0,
            max_time_sec=3600,
            max_retries=3,
            max_rebuilds=3,
        )
    )
    checker.start()
    checkpoint_manager = CheckpointManager(db_path)
    event_logger = EventLogger(db_path)

    # 정상 데이터 설정
    import aiosqlite
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT INTO runlogs (run_id, correlation_id, job_id, status, started_at, ended_at)
            VALUES (?, ?, ?, 'COMPLETED', datetime('now', '-1 hour'), datetime('now'))
            """,
            (str(uuid4()), str(uuid4()), str(uuid4())),
        )
        await db.commit()

    result = await engine.run(
        correlation_id, payload, ctx, checker, checkpoint_manager, event_logger
    )

    assert "overall_health" in result
    assert result["overall_health"] in ["HEALTHY", "DEGRADED", "CRITICAL"]
    assert "checks" in result
    assert "health" in result["checks"]
    assert "cost" in result["checks"]
    assert isinstance(result["issues"], list)
    assert isinstance(result["recommendations"], list)

    # 이벤트 확인
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM events WHERE correlation_id = ? AND type = 'DIAGNOSE_START'",
            (correlation_id,),
        )
        row = await cursor.fetchone()
        assert row is not None


@pytest.mark.asyncio
async def test_auto_fix_stuck_runs(test_db):
    """자동 수정 - 멈춘 실행 종료"""
    db_path = test_db.db_path
    engine = SelfDiagnoseEngine(db_path)
    correlation_id = str(uuid4())
    event_logger = EventLogger(db_path)

    # 2시간 이상 실행 중인 작업 생성
    import aiosqlite
    stuck_correlation_id = str(uuid4())
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT INTO runlogs (run_id, correlation_id, job_id, status, started_at)
            VALUES (?, ?, ?, 'RUNNING', datetime('now', '-3 hours'))
            """,
            (str(uuid4()), stuck_correlation_id, str(uuid4())),
        )
        await db.commit()

    results = {
        "issues": [{"severity": "MEDIUM", "message": "1 runs stuck for >2 hours"}],
        "recommendations": [],
    }

    await engine._apply_auto_fixes(results, correlation_id, event_logger)

    # 종료되었는지 확인
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT status, meta_json FROM runlogs WHERE correlation_id = ?",
            (stuck_correlation_id,),
        )
        row = await cursor.fetchone()
        assert row["status"] == "FAILED"
        import json
        meta = json.loads(row["meta_json"]) if row["meta_json"] else {}
        assert "Auto-terminated" in meta.get("error", "")
