"""
Watch Engine - 크롤러 통합 및 Evidence 생성
기존 크롤러를 Worker 핸들러로 통합
"""

import logging
from datetime import datetime
from typing import Any, Dict, List
from uuid import uuid4

import aiosqlite

from ..crawlers.precedent import PrecedentCrawler
from ..crawlers.trend import TrendCrawler
from ..crawlers.policy import MoelCrawler
from ..crawlers.competitor import CompetitorCrawler
from ..models import EventType
from ..core.events import EventLogger
from ..core.checkpoint import CheckpointManager
from ..core.termination import TerminationChecker

logger = logging.getLogger(__name__)


class WatchEngine:
    """Watch Engine - 외부 데이터 수집 및 Evidence 생성"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.event_logger = EventLogger(db_path)

        # 크롤러 초기화
        self.crawlers = {
            "SUPREME_COURT": PrecedentCrawler(),
            "NAVER_TREND": TrendCrawler(),
            "MOEL": MoelCrawler(),
            "COMPETITOR": CompetitorCrawler(),
        }

    async def run(
        self,
        correlation_id: str,
        payload: Dict[str, Any],
        ctx: Dict[str, Any],
        checker: TerminationChecker,
        checkpoint_manager: CheckpointManager,
        event_logger: EventLogger,
    ) -> Dict[str, Any]:
        """
        Watch 실행 (Worker 핸들러)

        Args:
            correlation_id: 실행 추적 ID
            payload: {sources: ["SUPREME_COURT", "NAVER_TREND"], since_days: 7}
            ctx: 체크포인트 컨텍스트
            checker: 종료 조건 체크
            checkpoint_manager: 체크포인트 관리
            event_logger: 이벤트 로거

        Returns:
            {items_collected: int, evidence_created: int, sources: [...]}
        """
        sources = payload.get("sources", list(self.crawlers.keys()))
        since_days = payload.get("since_days", 7)

        # 시작 이벤트
        await event_logger.log(
            EventType.WATCH_START,
            correlation_id,
            {"sources": sources, "since_days": since_days},
        )

        total_items = 0
        total_evidence = 0
        source_results = []

        for source in sources:
            # 종료 조건 체크
            should_terminate, reason = checker.check()
            if should_terminate:
                logger.warning(f"[Watch] Termination: {reason}")
                await event_logger.log(
                    EventType.TERMINATION,
                    correlation_id,
                    {"reason": reason, "stage": "WATCH"},
                )
                break

            # 크롤러 실행
            crawler = self.crawlers.get(source)
            if not crawler:
                logger.warning(f"[Watch] Unknown source: {source}")
                continue

            try:
                logger.info(f"[Watch] Crawling {source}...")

                # 크롤링 실행
                items = await self._crawl_source(
                    source=source,
                    crawler=crawler,
                    since_days=since_days,
                    correlation_id=correlation_id,
                )

                # Evidence 생성
                evidence_count = await self._create_evidence_from_items(
                    items=items,
                    source=source,
                    correlation_id=correlation_id,
                )

                total_items += len(items)
                total_evidence += evidence_count

                source_results.append(
                    {
                        "source": source,
                        "items": len(items),
                        "evidence": evidence_count,
                    }
                )

                # 아이템 수집 이벤트
                for item in items:
                    await event_logger.log(
                        EventType.ITEM_COLLECTED,
                        correlation_id,
                        {"source": source, "item_id": item.get("id")},
                    )

                # 체크포인트 저장
                ctx["watch_progress"] = {
                    "completed_sources": [r["source"] for r in source_results],
                    "total_items": total_items,
                    "total_evidence": total_evidence,
                }
                await checkpoint_manager.save(correlation_id, "WATCH", ctx)

            except Exception as e:
                logger.error(f"[Watch] Error crawling {source}: {e}")
                await event_logger.log(
                    EventType.ERROR,
                    correlation_id,
                    {"error": str(e), "source": source, "stage": "WATCH"},
                )
                continue

        # 완료 이벤트
        await event_logger.log(
            EventType.WATCH_END,
            correlation_id,
            {
                "total_items": total_items,
                "total_evidence": total_evidence,
                "sources": source_results,
            },
        )

        return {
            "items_collected": total_items,
            "evidence_created": total_evidence,
            "sources": source_results,
        }

    async def _crawl_source(
        self,
        source: str,
        crawler: Any,
        since_days: int,
        correlation_id: str,
    ) -> List[Dict[str, Any]]:
        """
        단일 소스 크롤링

        Returns:
            수집된 아이템 목록
        """
        try:
            # 크롤러 실행 (기존 크롤러 인터페이스 사용)
            try:
                items = await crawler.crawl(days=since_days)
            except AttributeError as e:
                logger.error(f"[Watch] Crawler {source} missing crawl method: {e}")
                return []
            except TypeError as e:
                logger.error(f"[Watch] Crawler {source} invalid parameters: {e}")
                return []

            # source_items 테이블에 저장 (증분 멱등)
            async with aiosqlite.connect(self.db_path, timeout=10.0) as db:
                for item in items:
                    try:
                        item_id = str(uuid4())
                        external_key = self._make_external_key(source, item)

                        await db.execute(
                            """
                            INSERT INTO source_items
                            (item_id, source_id, external_key, fetched_at, payload_json, content_hash)
                            VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (
                                item_id,
                                source,
                                external_key,
                                datetime.now().isoformat(),
                                str(item),  # JSON serialize
                                self._hash_content(item),
                            ),
                        )
                        item["item_id"] = item_id  # 추가
                    except aiosqlite.IntegrityError:
                        # external_key 중복 (이미 수집됨) - 스킵
                        logger.debug(f"[Watch] Duplicate item: {external_key}")
                        continue
                    except Exception as e:
                        logger.error(f"[Watch] Failed to save item: {e}")
                        continue

                await db.commit()

            return items
        except TimeoutError:
            logger.error(f"[Watch] Database timeout for source {source}")
            return []
        except Exception as e:
            logger.error(f"[Watch] Crawler failed for {source}: {e}")
            return []

    async def _create_evidence_from_items(
        self,
        items: List[Dict[str, Any]],
        source: str,
        correlation_id: str,
    ) -> int:
        """
        수집된 아이템에서 Evidence 생성

        Returns:
            생성된 evidence 개수
        """
        evidence_count = 0

        try:
            async with aiosqlite.connect(self.db_path, timeout=10.0) as db:
                for item in items:
                    try:
                        evidence_id = str(uuid4())

                        # Locator 생성 (source_type=SOURCE_ITEM)
                        locator = {
                            "item_id": item.get("item_id"),
                            "source": source,
                            "url": item.get("url"),
                            "date": item.get("date"),
                        }

                        # Snippet 추출 (최대 500자)
                        snippet = self._extract_snippet(item)

                        await db.execute(
                            """
                            INSERT INTO evidence
                            (evidence_id, correlation_id, source_type, locator_json, snippet, content_hash)
                            VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (
                                evidence_id,
                                correlation_id,
                                "SOURCE_ITEM",
                                str(locator),  # JSON serialize
                                snippet,
                                self._hash_content(item),
                            ),
                        )

                        evidence_count += 1
                    except Exception as e:
                        logger.error(f"[Watch] Failed to create evidence: {e}")
                        continue

                await db.commit()
        except TimeoutError:
            logger.error(f"[Watch] Database timeout creating evidence")
        except Exception as e:
            logger.error(f"[Watch] Failed to create evidence batch: {e}")

        return evidence_count

    def _make_external_key(self, source: str, item: Dict[str, Any]) -> str:
        """외부 키 생성 (멱등성)"""
        # 판례: 사건번호
        if source == "SUPREME_COURT":
            return f"{source}:{item.get('case_number', item.get('id'))}"

        # 트렌드: 키워드+날짜
        if source == "NAVER_TREND":
            return f"{source}:{item.get('keyword')}:{item.get('date')}"

        # 정책: URL 또는 제목
        if source == "MOEL":
            return f"{source}:{item.get('url', item.get('title'))}"

        # 경쟁사: URL
        if source == "COMPETITOR":
            return f"{source}:{item.get('url')}"

        # 기본: ID
        return f"{source}:{item.get('id', str(uuid4()))}"

    def _hash_content(self, item: Dict[str, Any]) -> str:
        """컨텐츠 해시 (중복 감지)"""
        import hashlib
        import json

        content = json.dumps(item, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _extract_snippet(self, item: Dict[str, Any]) -> str:
        """스니펫 추출 (최대 500자)"""
        # 우선순위: summary > content > title
        snippet = (
            item.get("summary")
            or item.get("content")
            or item.get("title")
            or str(item)
        )
        return snippet[:500]
