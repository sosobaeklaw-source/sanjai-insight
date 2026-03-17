"""
Base Crawler with Circuit Breaker and Safety Harness
PRD §6.3, §8.4
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any, Optional

import httpx
import yaml
from bs4 import BeautifulSoup

from ..db import db
from ..models import CrawledData, SourceType, WatchLog, WatchLogStatus

logger = logging.getLogger(__name__)


class CircuitBreaker:
    """Circuit breaker for crawler safety"""

    def __init__(self, threshold: int = 3, timeout_sec: int = 300):
        self.threshold = threshold
        self.timeout_sec = timeout_sec
        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.is_open = False

    def record_success(self):
        """Record successful operation"""
        self.failure_count = 0
        self.is_open = False

    def record_failure(self):
        """Record failed operation"""
        self.failure_count += 1
        self.last_failure_time = datetime.now()

        if self.failure_count >= self.threshold:
            self.is_open = True
            logger.error(
                f"Circuit breaker opened after {self.failure_count} failures"
            )

    def can_proceed(self) -> bool:
        """Check if operation can proceed"""
        if not self.is_open:
            return True

        # Check if timeout has passed
        if self.last_failure_time:
            elapsed = (datetime.now() - self.last_failure_time).total_seconds()
            if elapsed > self.timeout_sec:
                logger.info("Circuit breaker attempting reset")
                self.is_open = False
                self.failure_count = 0
                return True

        return False


class RateLimiter:
    """Rate limiter for crawler requests"""

    def __init__(self, min_interval_sec: float = 2.0):
        self.min_interval_sec = min_interval_sec
        self.last_request_time: Optional[datetime] = None

    async def wait(self):
        """Wait if necessary to respect rate limit"""
        if self.last_request_time:
            elapsed = (datetime.now() - self.last_request_time).total_seconds()
            if elapsed < self.min_interval_sec:
                wait_time = self.min_interval_sec - elapsed
                logger.debug(f"Rate limiting: waiting {wait_time:.2f}s")
                await asyncio.sleep(wait_time)

        self.last_request_time = datetime.now()


class BaseCrawler(ABC):
    """
    Base crawler with safety harness

    Safety features:
    - Circuit breaker (3 consecutive failures → disable)
    - Rate limiter (2 sec minimum between requests)
    - Timeout (configurable per crawler)
    - Retry with exponential backoff (3 attempts)
    - Error logging
    """

    def __init__(self, source: SourceType):
        self.source = source
        self.circuit_breaker = CircuitBreaker()
        self.rate_limiter = RateLimiter()
        self.config = self._load_config()
        self.timeout = self.config.get("timeout_sec", 600)
        self.max_retries = self.config.get("retry_max", 3)
        self.backoff_base = self.config.get("backoff_base_sec", 2)

    def _load_config(self) -> dict[str, Any]:
        """Load crawler configuration"""
        try:
            with open("config/schedule.yaml", "r", encoding="utf-8") as f:
                schedule_config = yaml.safe_load(f)
            with open("config/thresholds.yaml", "r", encoding="utf-8") as f:
                threshold_config = yaml.safe_load(f)

            return {
                **schedule_config.get("retry", {}),
                **threshold_config.get("crawler", {}),
            }
        except Exception as e:
            logger.warning(f"Failed to load config: {e}. Using defaults.")
            return {}

    async def run(self) -> WatchLog:
        """
        Run crawler with safety harness

        Returns:
            WatchLog with execution results
        """
        # Check circuit breaker
        if not self.circuit_breaker.can_proceed():
            logger.error(f"{self.source.value} crawler: Circuit breaker is open")
            return WatchLog(
                source=self.source,
                started_at=datetime.now(),
                ended_at=datetime.now(),
                status=WatchLogStatus.FAILED,
                items_collected=0,
                error_message="Circuit breaker is open",
            )

        log = WatchLog(
            source=self.source,
            started_at=datetime.now(),
            status=WatchLogStatus.SUCCESS,
        )

        try:
            # Execute crawl with timeout
            items = await asyncio.wait_for(
                self._crawl_with_retry(),
                timeout=self.timeout
            )

            log.items_collected = len(items)
            log.status = WatchLogStatus.SUCCESS if items else WatchLogStatus.PARTIAL
            self.circuit_breaker.record_success()

            logger.info(
                f"{self.source.value} crawler: Collected {len(items)} items"
            )

        except asyncio.TimeoutError:
            log.status = WatchLogStatus.FAILED
            log.error_message = f"Timeout after {self.timeout}s"
            self.circuit_breaker.record_failure()
            logger.error(f"{self.source.value} crawler: {log.error_message}")

        except Exception as e:
            log.status = WatchLogStatus.FAILED
            log.error_message = str(e)
            self.circuit_breaker.record_failure()
            logger.exception(f"{self.source.value} crawler failed")

        finally:
            log.ended_at = datetime.now()

        # Save log to database
        try:
            await db.create_watch_log(log)
        except Exception as e:
            logger.error(f"Failed to save watch log: {e}")

        return log

    async def _crawl_with_retry(self) -> list[CrawledData]:
        """Crawl with retry logic"""
        last_exception = None

        for attempt in range(1, self.max_retries + 1):
            try:
                # Rate limiting
                await self.rate_limiter.wait()

                # Actual crawling
                items = await self._crawl()
                return items

            except Exception as e:
                last_exception = e
                logger.warning(
                    f"{self.source.value} crawler attempt {attempt}/{self.max_retries} failed: {e}"
                )

                if attempt < self.max_retries:
                    # Exponential backoff
                    wait_time = self.backoff_base ** attempt
                    logger.info(f"Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)

        # All retries failed
        raise last_exception or Exception("All retry attempts failed")

    @abstractmethod
    async def _crawl(self) -> list[CrawledData]:
        """
        Implement actual crawling logic

        Returns:
            List of CrawledData objects
        """
        pass

    async def fetch_html(
        self, url: str, timeout: int = 30
    ) -> Optional[BeautifulSoup]:
        """
        Fetch HTML and parse with BeautifulSoup

        Args:
            url: URL to fetch
            timeout: Request timeout in seconds

        Returns:
            BeautifulSoup object or None if failed
        """
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url)
                response.raise_for_status()
                return BeautifulSoup(response.text, "lxml")
        except Exception as e:
            logger.error(f"Failed to fetch {url}: {e}")
            return None

    async def fetch_json(
        self, url: str, timeout: int = 30, **kwargs
    ) -> Optional[dict]:
        """
        Fetch JSON response

        Args:
            url: URL to fetch
            timeout: Request timeout in seconds
            **kwargs: Additional httpx request parameters

        Returns:
            JSON response as dict or None if failed
        """
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url, **kwargs)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Failed to fetch JSON from {url}: {e}")
            return None

    async def save_crawled_data(self, items: list[CrawledData]) -> int:
        """
        Save crawled data to database

        Args:
            items: List of CrawledData objects

        Returns:
            Number of items saved
        """
        saved_count = 0
        for item in items:
            try:
                await db.create_crawled_data(item)
                saved_count += 1
            except Exception as e:
                logger.error(f"Failed to save item {item.id}: {e}")

        return saved_count
