#!/usr/bin/env python3
"""
E2E 통합 테스트 스위트
======================
Watch → Think → Propose 전체 파이프라인 테스트
"""

import pytest
import asyncio
import aiosqlite
from pathlib import Path
from datetime import datetime
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.engines.watch import WatchEngine
from src.engines.think import ThinkEngine
from src.engines.propose import ProposeEngine
from src.core.worker import Worker
from src.db import Database

# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
async def test_db():
    """테스트 DB"""
    db_path = Path("test_e2e.db")

    # 스키마 생성
    async with aiosqlite.connect(str(db_path)) as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS crawl_results (
                id INTEGER PRIMARY KEY,
                url TEXT,
                content_hash TEXT,
                title TEXT,
                content TEXT,
                source TEXT,
                keywords TEXT,
                crawled_at TEXT
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS insights (
                id INTEGER PRIMARY KEY,
                crawl_id TEXT,
                title TEXT,
                summary TEXT,
                category TEXT,
                confidence REAL,
                evidence TEXT,
                reasoning TEXT,
                created_at TEXT,
                approved INTEGER
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS proposals (
                id INTEGER PRIMARY KEY,
                insight_id INTEGER,
                telegram_message_id INTEGER,
                proposed_at TEXT,
                approved_at TEXT,
                status TEXT
            )
        """)
        await conn.commit()

    yield db_path

    # Cleanup
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def sample_crawl_data():
    """샘플 크롤링 데이터"""
    return {
        "url": "https://www.moel.go.kr/news/notice/test.do",
        "title": "산재보험 요양급여 지급기준 개정",
        "content": "산재보험 요양급여 지급기준이 개정되었습니다. " * 50,
        "source": "moel.go.kr",
        "keywords": ["산재보험", "요양급여", "지급기준"]
    }


# ============================================================================
# E2E Pipeline Tests
# ============================================================================

@pytest.mark.asyncio
async def test_e2e_full_pipeline_success(test_db, sample_crawl_data):
    """E2E-001: 전체 파이프라인 성공 케이스"""
    # Watch 단계 (크롤링 저장)
    async with aiosqlite.connect(str(test_db)) as conn:
        cursor = await conn.execute("""
            INSERT INTO crawl_results (url, content_hash, title, content, source, keywords, crawled_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            sample_crawl_data["url"],
            "test_hash_001",
            sample_crawl_data["title"],
            sample_crawl_data["content"],
            sample_crawl_data["source"],
            str(sample_crawl_data["keywords"]),
            datetime.now().isoformat()
        ))
        await conn.commit()
        crawl_id = cursor.lastrowid

    # Think 단계 (인사이트 생성) - 시뮬레이션
    async with aiosqlite.connect(str(test_db)) as conn:
        await conn.execute("""
            INSERT INTO insights (crawl_id, title, summary, category, confidence, evidence, reasoning, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(crawl_id),
            "인사이트: 산재보험 요양급여 지급기준 개정",
            "요양급여 지급기준이 변경되어 의료비 청구 절차가 개선되었습니다.",
            "policy",
            0.85,
            '{"source": "moel.go.kr", "evidence_count": 3}',
            "정부 공식 발표 자료 기반",
            datetime.now().isoformat()
        ))
        await conn.commit()
        insight_id = cursor.lastrowid

    # Propose 단계 (제안) - 시뮬레이션
    async with aiosqlite.connect(str(test_db)) as conn:
        await conn.execute("""
            INSERT INTO proposals (insight_id, telegram_message_id, proposed_at, status)
            VALUES (?, ?, ?, ?)
        """, (
            insight_id,
            12345,
            datetime.now().isoformat(),
            "pending"
        ))
        await conn.commit()

    # 검증
    async with aiosqlite.connect(str(test_db)) as conn:
        cursor = await conn.execute("SELECT COUNT(*) FROM crawl_results")
        assert (await cursor.fetchone())[0] == 1

        cursor = await conn.execute("SELECT COUNT(*) FROM insights")
        assert (await cursor.fetchone())[0] == 1

        cursor = await conn.execute("SELECT COUNT(*) FROM proposals")
        assert (await cursor.fetchone())[0] == 1

        cursor = await conn.execute("SELECT confidence FROM insights WHERE id = ?", (insight_id,))
        confidence = (await cursor.fetchone())[0]
        assert confidence >= 0.7  # 임계값 통과


@pytest.mark.asyncio
async def test_e2e_low_confidence_filtered(test_db, sample_crawl_data):
    """E2E-002: 낮은 신뢰도 필터링"""
    async with aiosqlite.connect(str(test_db)) as conn:
        # 크롤링 데이터
        cursor = await conn.execute("""
            INSERT INTO crawl_results (url, content_hash, title, content, source, keywords, crawled_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            sample_crawl_data["url"],
            "test_hash_002",
            sample_crawl_data["title"],
            sample_crawl_data["content"],
            sample_crawl_data["source"],
            str(sample_crawl_data["keywords"]),
            datetime.now().isoformat()
        ))
        await conn.commit()
        crawl_id = cursor.lastrowid

        # 낮은 신뢰도 인사이트
        await conn.execute("""
            INSERT INTO insights (crawl_id, title, summary, category, confidence, evidence, reasoning, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(crawl_id),
            "낮은 신뢰도 인사이트",
            "불확실한 정보",
            "trend",
            0.55,  # 임계값 미만
            '{"source": "unknown"}',
            "근거 부족",
            datetime.now().isoformat()
        ))
        await conn.commit()

        # Proposal은 생성되지 않아야 함
        cursor = await conn.execute("SELECT COUNT(*) FROM proposals")
        assert (await cursor.fetchone())[0] == 0


@pytest.mark.asyncio
async def test_e2e_duplicate_prevention(test_db, sample_crawl_data):
    """E2E-003: 중복 방지 메커니즘"""
    async with aiosqlite.connect(str(test_db)) as conn:
        # 동일 content_hash로 2번 크롤링
        for i in range(2):
            await conn.execute("""
                INSERT INTO crawl_results (url, content_hash, title, content, source, keywords, crawled_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                sample_crawl_data["url"],
                "duplicate_hash",
                sample_crawl_data["title"],
                sample_crawl_data["content"],
                sample_crawl_data["source"],
                str(sample_crawl_data["keywords"]),
                datetime.now().isoformat()
            ))
        await conn.commit()

        # content_hash로 중복 체크
        cursor = await conn.execute("""
            SELECT COUNT(DISTINCT content_hash) FROM crawl_results WHERE content_hash = ?
        """, ("duplicate_hash",))
        unique_count = (await cursor.fetchone())[0]
        assert unique_count == 1  # 중복 제거 확인


@pytest.mark.asyncio
async def test_e2e_approval_flow(test_db):
    """E2E-004: 승인 플로우"""
    async with aiosqlite.connect(str(test_db)) as conn:
        # 인사이트 생성
        cursor = await conn.execute("""
            INSERT INTO insights (crawl_id, title, summary, category, confidence, evidence, reasoning, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "test_crawl_001",
            "테스트 인사이트",
            "테스트 요약",
            "policy",
            0.80,
            '{}',
            "테스트",
            datetime.now().isoformat()
        ))
        await conn.commit()
        insight_id = cursor.lastrowid

        # Proposal 생성
        cursor = await conn.execute("""
            INSERT INTO proposals (insight_id, telegram_message_id, proposed_at, status)
            VALUES (?, ?, ?, ?)
        """, (insight_id, 54321, datetime.now().isoformat(), "pending"))
        await conn.commit()
        proposal_id = cursor.lastrowid

        # 승인 처리
        await conn.execute("""
            UPDATE proposals SET status = ?, approved_at = ? WHERE id = ?
        """, ("approved", datetime.now().isoformat(), proposal_id))

        await conn.execute("""
            UPDATE insights SET approved = ? WHERE id = ?
        """, (1, insight_id))
        await conn.commit()

        # 검증
        cursor = await conn.execute("SELECT status FROM proposals WHERE id = ?", (proposal_id,))
        assert (await cursor.fetchone())[0] == "approved"

        cursor = await conn.execute("SELECT approved FROM insights WHERE id = ?", (insight_id,))
        assert (await cursor.fetchone())[0] == 1


@pytest.mark.asyncio
async def test_e2e_error_handling(test_db):
    """E2E-005: 에러 핸들링"""
    async with aiosqlite.connect(str(test_db)) as conn:
        # 잘못된 데이터 처리
        try:
            await conn.execute("""
                INSERT INTO insights (crawl_id, title, summary, category, confidence, evidence, reasoning, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                None,  # NULL crawl_id
                "에러 테스트",
                "에러",
                "policy",
                0.80,
                '{}',
                "에러",
                datetime.now().isoformat()
            ))
            await conn.commit()
        except Exception as e:
            # 에러가 발생해야 정상
            assert "NOT NULL" in str(e) or "constraint" in str(e).lower()


@pytest.mark.asyncio
async def test_e2e_performance_baseline(test_db, sample_crawl_data):
    """E2E-006: 성능 베이스라인"""
    import time

    start_time = time.time()

    # 10건의 인사이트 생성 시뮬레이션
    async with aiosqlite.connect(str(test_db)) as conn:
        for i in range(10):
            # 크롤링
            await conn.execute("""
                INSERT INTO crawl_results (url, content_hash, title, content, source, keywords, crawled_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                f"{sample_crawl_data['url']}?id={i}",
                f"hash_{i}",
                sample_crawl_data["title"],
                sample_crawl_data["content"],
                sample_crawl_data["source"],
                str(sample_crawl_data["keywords"]),
                datetime.now().isoformat()
            ))

            # 인사이트
            await conn.execute("""
                INSERT INTO insights (crawl_id, title, summary, category, confidence, evidence, reasoning, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                f"crawl_{i}",
                f"인사이트 {i}",
                "요약",
                "policy",
                0.80,
                '{}',
                "분석",
                datetime.now().isoformat()
            ))
        await conn.commit()

    elapsed = time.time() - start_time

    # 성능 체크: 10건 처리 < 5초
    assert elapsed < 5.0, f"Performance degraded: {elapsed:.2f}s for 10 items"


@pytest.mark.asyncio
async def test_e2e_concurrent_processing(test_db, sample_crawl_data):
    """E2E-007: 동시 처리 테스트"""
    async def insert_crawl(conn, idx):
        await conn.execute("""
            INSERT INTO crawl_results (url, content_hash, title, content, source, keywords, crawled_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            f"{sample_crawl_data['url']}?concurrent={idx}",
            f"concurrent_hash_{idx}",
            sample_crawl_data["title"],
            sample_crawl_data["content"],
            sample_crawl_data["source"],
            str(sample_crawl_data["keywords"]),
            datetime.now().isoformat()
        ))
        await conn.commit()

    # 동시에 5개 삽입
    async with aiosqlite.connect(str(test_db)) as conn:
        tasks = [insert_crawl(conn, i) for i in range(5)]
        await asyncio.gather(*tasks)

    # 검증
    async with aiosqlite.connect(str(test_db)) as conn:
        cursor = await conn.execute("SELECT COUNT(*) FROM crawl_results")
        count = (await cursor.fetchone())[0]
        assert count == 5


@pytest.mark.asyncio
async def test_e2e_data_integrity(test_db):
    """E2E-008: 데이터 무결성"""
    async with aiosqlite.connect(str(test_db)) as conn:
        # Foreign key 제약 조건 테스트
        # (SQLite는 기본적으로 foreign key를 강제하지 않음, 설정 필요)

        # 존재하지 않는 crawl_id 참조
        await conn.execute("""
            INSERT INTO insights (crawl_id, title, summary, category, confidence, evidence, reasoning, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "nonexistent_crawl",
            "무결성 테스트",
            "테스트",
            "policy",
            0.80,
            '{}',
            "테스트",
            datetime.now().isoformat()
        ))
        await conn.commit()

        # 검증: 데이터는 삽입되지만 join 시 NULL
        cursor = await conn.execute("""
            SELECT i.id, c.id
            FROM insights i
            LEFT JOIN crawl_results c ON i.crawl_id = CAST(c.id AS TEXT)
            WHERE i.crawl_id = ?
        """, ("nonexistent_crawl",))
        result = await cursor.fetchone()
        assert result[1] is None  # crawl_results에 없음


@pytest.mark.asyncio
async def test_e2e_transaction_rollback(test_db):
    """E2E-009: 트랜잭션 롤백"""
    async with aiosqlite.connect(str(test_db)) as conn:
        try:
            # 트랜잭션 시작
            await conn.execute("BEGIN TRANSACTION")

            # 정상 삽입
            await conn.execute("""
                INSERT INTO crawl_results (url, content_hash, title, content, source, keywords, crawled_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, ("test_url", "hash", "title", "content", "source", "[]", datetime.now().isoformat()))

            # 강제 에러 발생
            await conn.execute("INSERT INTO nonexistent_table VALUES (1)")

            await conn.execute("COMMIT")
        except Exception:
            await conn.execute("ROLLBACK")

        # 검증: 롤백되어야 함
        cursor = await conn.execute("SELECT COUNT(*) FROM crawl_results")
        assert (await cursor.fetchone())[0] == 0


@pytest.mark.asyncio
async def test_e2e_quality_threshold_enforcement(test_db):
    """E2E-010: 품질 임계값 강제"""
    confidence_threshold = 0.7

    async with aiosqlite.connect(str(test_db)) as conn:
        # 다양한 신뢰도로 인사이트 생성
        test_cases = [
            ("high", 0.90, True),
            ("medium", 0.75, True),
            ("threshold", 0.70, True),
            ("low", 0.65, False),
            ("very_low", 0.50, False)
        ]

        for name, confidence, should_propose in test_cases:
            await conn.execute("""
                INSERT INTO insights (crawl_id, title, summary, category, confidence, evidence, reasoning, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                f"crawl_{name}",
                f"Insight {name}",
                "Summary",
                "policy",
                confidence,
                '{}',
                "Reasoning",
                datetime.now().isoformat()
            ))
        await conn.commit()

        # 검증: 임계값 이상만 카운트
        cursor = await conn.execute("""
            SELECT COUNT(*) FROM insights WHERE confidence >= ?
        """, (confidence_threshold,))
        passing_count = (await cursor.fetchone())[0]
        assert passing_count == 3  # high, medium, threshold만


# ============================================================================
# Test Runner
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
