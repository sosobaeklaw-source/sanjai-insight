"""
Tests for BaseCrawler
"""

import pytest

from src.crawlers.base import BaseCrawler, CircuitBreaker, RateLimiter
from src.models import CrawledData, DataType, SourceType


class DummyCrawler(BaseCrawler):
    """Dummy crawler for testing"""

    def __init__(self):
        super().__init__(SourceType.SUPREME_COURT)
        self.call_count = 0

    async def _crawl(self) -> list[CrawledData]:
        self.call_count += 1
        return []


@pytest.mark.asyncio
async def test_circuit_breaker():
    """Test circuit breaker opens after threshold"""
    cb = CircuitBreaker(threshold=3, timeout_sec=1)

    assert cb.can_proceed() is True
    assert cb.is_open is False

    # Record failures
    cb.record_failure()
    assert cb.failure_count == 1
    assert cb.can_proceed() is True

    cb.record_failure()
    assert cb.failure_count == 2
    assert cb.can_proceed() is True

    cb.record_failure()
    assert cb.failure_count == 3
    assert cb.is_open is True
    assert cb.can_proceed() is False

    # Test success reset
    cb.record_success()
    assert cb.failure_count == 0
    assert cb.is_open is False
    assert cb.can_proceed() is True


@pytest.mark.asyncio
async def test_rate_limiter():
    """Test rate limiter enforces delay"""
    limiter = RateLimiter(min_interval_sec=0.1)

    import time

    start = time.time()
    await limiter.wait()
    await limiter.wait()
    elapsed = time.time() - start

    # Should take at least 0.1 seconds
    assert elapsed >= 0.1


@pytest.mark.asyncio
async def test_crawler_run_success(test_db):
    """Test successful crawler run"""
    crawler = DummyCrawler()
    log = await crawler.run()

    # Empty result is PARTIAL, not SUCCESS
    assert log.status.value == "PARTIAL"
    assert log.items_collected == 0
    assert log.error_message is None
    assert crawler.call_count == 1


@pytest.mark.asyncio
async def test_crawler_circuit_breaker_opens(test_db):
    """Test circuit breaker prevents execution"""

    class FailingCrawler(DummyCrawler):
        async def _crawl(self):
            raise Exception("Test failure")

    crawler = FailingCrawler()

    # First 3 runs should fail
    for _ in range(3):
        log = await crawler.run()
        assert log.status.value == "FAILED"

    # 4th run should be blocked by circuit breaker
    log = await crawler.run()
    assert log.status.value == "FAILED"
    assert "Circuit breaker is open" in log.error_message
