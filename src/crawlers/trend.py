"""
Trend Crawler - 네이버 데이터랩 검색량 트렌드
PRD §6.5

API:
- 네이버 데이터랩 API: https://developers.naver.com/docs/serviceapi/datalab/search/search.md
- 무료 한도: 일 25,000건 (A-2 미검증 가정)
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Optional

import yaml

from ..models import CrawledData, DataType, SourceType, TrendSnapshot
from .base import BaseCrawler

logger = logging.getLogger(__name__)


class TrendCrawler(BaseCrawler):
    """네이버 검색량 트렌드 크롤러"""

    def __init__(self):
        super().__init__(SourceType.NAVER_TREND)
        self.keywords = self._load_keywords()
        self.api_url = "https://openapi.naver.com/v1/datalab/search"
        self.client_id = os.getenv("NAVER_CLIENT_ID")
        self.client_secret = os.getenv("NAVER_CLIENT_SECRET")

    def _load_keywords(self) -> list[str]:
        """키워드 로드"""
        try:
            with open("config/keywords.yaml", "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            return config.get("trend_keywords", [])
        except Exception as e:
            logger.warning(f"Failed to load keywords: {e}")
            return ["산재 신청", "산재 승인"]

    async def _crawl(self) -> list[CrawledData]:
        """
        트렌드 데이터 수집

        기간: 최근 30일 vs 그 전 30일 비교
        """
        items = []

        if not self.client_id or not self.client_secret:
            logger.error("Naver API credentials not configured")
            return items

        # 키워드를 5개씩 묶어서 요청 (API 제한)
        batch_size = 5
        for i in range(0, len(self.keywords), batch_size):
            batch = self.keywords[i : i + batch_size]
            try:
                data = await self._fetch_trend_data(batch)
                if data:
                    items.append(data)
                    logger.info(f"Collected trend data for {len(batch)} keywords")
            except Exception as e:
                logger.error(f"Failed to fetch trend for batch {batch}: {e}")
                continue

        # DB 저장
        await self.save_crawled_data(items)

        return items

    async def _fetch_trend_data(self, keywords: list[str]) -> Optional[CrawledData]:
        """
        특정 키워드 배치에 대한 트렌드 데이터 수집
        """
        # 기간 설정: 최근 30일 vs 이전 30일
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=30)
        prev_end_date = start_date - timedelta(days=1)
        prev_start_date = prev_end_date - timedelta(days=30)

        # API 요청 body
        body = {
            "startDate": start_date.strftime("%Y-%m-%d"),
            "endDate": end_date.strftime("%Y-%m-%d"),
            "timeUnit": "week",
            "keywordGroups": [
                {"groupName": keyword, "keywords": [keyword]} for keyword in keywords
            ],
        }

        headers = {
            "X-Naver-Client-Id": self.client_id,
            "X-Naver-Client-Secret": self.client_secret,
            "Content-Type": "application/json",
        }

        try:
            # API 호출
            import httpx

            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    self.api_url, json=body, headers=headers
                )
                response.raise_for_status()
                result = response.json()

            # CrawledData 생성
            item = CrawledData(
                source=self.source,
                crawled_at=datetime.now(),
                data_type=DataType.TREND,
                raw_content=str(result),
                metadata={
                    "keywords": keywords,
                    "period": f"{start_date} ~ {end_date}",
                    "time_unit": "week",
                    "result": result,
                },
            )

            # 변화율 계산 및 저장
            await self._save_trend_snapshots(result, keywords)

            return item

        except Exception as e:
            logger.error(f"Failed to fetch trend data: {e}")
            return None

    async def _save_trend_snapshots(self, result: dict, keywords: list[str]):
        """
        TrendSnapshot 레코드 생성

        변화율 계산:
        - 최근 주 평균 vs 전체 평균 비교
        """
        from ..db import db

        try:
            results = result.get("results", [])

            for item in results:
                keyword = item.get("title")
                data_points = item.get("data", [])

                if not data_points:
                    continue

                # 최근 주 데이터
                recent_week = data_points[-1]
                recent_volume = recent_week.get("ratio", 0)

                # 전체 평균
                total_avg = sum(d.get("ratio", 0) for d in data_points) / len(
                    data_points
                )

                # 변화율 계산
                change_percent = (
                    ((recent_volume - total_avg) / total_avg * 100)
                    if total_avg > 0
                    else 0
                )

                # 관련 키워드 (TODO: 실제 API에서 제공하는지 확인)
                related = []

                # TrendSnapshot 생성
                snapshot = TrendSnapshot(
                    keyword=keyword,
                    period=recent_week.get("period"),
                    search_volume=int(recent_volume),
                    change_percent=round(change_percent, 2),
                    related_keywords=related,
                )

                # DB 저장 (간단 구현)
                async with db.connect() as conn:
                    await conn.execute(
                        """
                        INSERT INTO trend_snapshots
                        (id, keyword, period, search_volume, change_percent, related_keywords)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            snapshot.id,
                            snapshot.keyword,
                            snapshot.period,
                            snapshot.search_volume,
                            snapshot.change_percent,
                            str(snapshot.related_keywords),
                        ),
                    )
                    await conn.commit()

                logger.info(
                    f"Saved trend snapshot: {keyword} "
                    f"({change_percent:+.1f}%)"
                )

        except Exception as e:
            logger.error(f"Failed to save trend snapshots: {e}")

    def calculate_opportunity_score(
        self, keyword: str, change_percent: float, competition_level: float = 0.5
    ) -> float:
        """
        Opportunity Score 계산 (PRD §6.5)

        Score = 0.4 × 검색량변화 + 0.3 × (1 - 경쟁강도) + 0.3 × 키워드적합도

        Args:
            keyword: 키워드
            change_percent: 검색량 변화율 (%)
            competition_level: 경쟁 강도 (0~1)

        Returns:
            Opportunity score (0~1)
        """
        # 검색량 변화 정규화 (0~1)
        # 100% 증가를 1.0으로 가정
        search_change_norm = min(max(change_percent / 100, 0), 1.0)

        # 경쟁 강도 역수
        competition_score = 1 - competition_level

        # 키워드 적합도 (TODO: 실제 로직 구현)
        # 현재는 단순히 1.0으로 가정
        relevance_score = 1.0

        # 가중 평균
        score = (
            0.4 * search_change_norm + 0.3 * competition_score + 0.3 * relevance_score
        )

        return round(score, 3)
