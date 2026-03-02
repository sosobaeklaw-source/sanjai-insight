"""
Precedent Crawler - 대법원/고등법원 판례 크롤링
PRD §6.4

API:
- 대법원 종합법률정보: https://www.law.go.kr/DRF/lawSearch.do
- NOTE: 실제 API 엔드포인트는 A-1 미검증 가정으로 표기됨
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

import yaml

from ..models import CrawledData, DataType, SourceType
from .base import BaseCrawler

logger = logging.getLogger(__name__)


class PrecedentCrawler(BaseCrawler):
    """대법원 판례 크롤러"""

    def __init__(self):
        super().__init__(SourceType.SUPREME_COURT)
        self.keywords = self._load_keywords()
        self.base_url = "https://www.law.go.kr/DRF/lawSearch.do"
        # TODO: 실제 API 키는 환경변수에서 로드
        self.api_key = None

    def _load_keywords(self) -> list[str]:
        """키워드 로드"""
        try:
            with open("config/keywords.yaml", "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            return config.get("precedent_keywords", [])
        except Exception as e:
            logger.warning(f"Failed to load keywords: {e}")
            return ["산재보험", "업무상재해"]

    async def _crawl(self) -> list[CrawledData]:
        """
        판례 크롤링 로직

        NOTE: A-1 미검증 가정 - 대법원 API가 산재 판례 제공 여부 확인 필요
        실제 구현 시 API 문서 참조하여 수정 필요
        """
        items = []
        lookback_days = 7  # 최근 7일 판례 수집

        for keyword in self.keywords:
            try:
                # 키워드별 판례 검색
                precedents = await self._search_precedents(keyword, lookback_days)
                items.extend(precedents)
                logger.info(
                    f"Collected {len(precedents)} precedents for keyword: {keyword}"
                )
            except Exception as e:
                logger.error(f"Failed to crawl keyword '{keyword}': {e}")
                continue

        # 중복 제거 (판례 번호 기준)
        unique_items = self._deduplicate(items)
        logger.info(
            f"Total {len(items)} → {len(unique_items)} after deduplication"
        )

        # DB 저장
        await self.save_crawled_data(unique_items)

        return unique_items

    async def _search_precedents(
        self, keyword: str, lookback_days: int
    ) -> list[CrawledData]:
        """
        특정 키워드로 판례 검색

        TODO: 실제 API 구조에 맞춰 수정 필요
        """
        items = []
        start_date = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y%m%d")
        end_date = datetime.now().strftime("%Y%m%d")

        # API 파라미터 구성 (예시)
        params = {
            "OC": self.api_key or "DEMO_KEY",
            "target": "prec",  # 판례
            "type": "XML",
            "query": keyword,
            "date_from": start_date,
            "date_to": end_date,
            "display": 100,  # 최대 100건
        }

        # API 호출 (현재는 Mock)
        # TODO: 실제 API 호출로 교체
        logger.warning(
            f"[MOCK] Would call API with params: {params}. "
            "Returning empty list until API verified."
        )

        # Mock response parsing (실제 구현 시 제거)
        # response = await self.fetch_json(self.base_url, params=params)
        # if response:
        #     items = self._parse_precedents(response, keyword)

        return items

    def _parse_precedents(
        self, response: dict, keyword: str
    ) -> list[CrawledData]:
        """
        API 응답 파싱

        TODO: 실제 응답 구조에 맞춰 구현
        """
        items = []

        # 예시 파싱 로직 (실제 API 응답 구조 확인 후 수정)
        precedents = response.get("PrecSearch", {}).get("prec", [])

        for prec in precedents:
            try:
                item = CrawledData(
                    source=self.source,
                    crawled_at=datetime.now(),
                    data_type=DataType.PRECEDENT,
                    raw_content=str(prec),  # 전체 JSON
                    metadata={
                        "case_number": prec.get("판례일련번호"),
                        "case_name": prec.get("사건명"),
                        "court": prec.get("법원명"),
                        "decision_date": prec.get("선고일자"),
                        "case_type": prec.get("사건종류명"),
                        "summary": prec.get("판시사항"),
                        "keyword": keyword,
                        "url": prec.get("판례상세링크"),
                    },
                )
                items.append(item)
            except Exception as e:
                logger.error(f"Failed to parse precedent: {e}")
                continue

        return items

    def _deduplicate(self, items: list[CrawledData]) -> list[CrawledData]:
        """판례 번호 기준 중복 제거"""
        seen = set()
        unique = []

        for item in items:
            case_number = item.metadata.get("case_number")
            if case_number and case_number not in seen:
                seen.add(case_number)
                unique.append(item)

        return unique


class HighCourtCrawler(BaseCrawler):
    """고등법원 판례 크롤러"""

    def __init__(self):
        super().__init__(SourceType.HIGH_COURT)
        self.keywords = self._load_keywords()

    def _load_keywords(self) -> list[str]:
        """키워드 로드"""
        try:
            with open("config/keywords.yaml", "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            return config.get("precedent_keywords", [])
        except Exception as e:
            logger.warning(f"Failed to load keywords: {e}")
            return ["산재보험", "업무상재해"]

    async def _crawl(self) -> list[CrawledData]:
        """
        고등법원 판례 크롤링

        NOTE: 대법원 API와 동일한 엔드포인트 사용 가능성 있음
        실제 API 확인 후 구현
        """
        items = []

        # TODO: 실제 크롤링 로직 구현
        logger.warning(
            "[MOCK] HighCourtCrawler not yet implemented. "
            "Returning empty list until API verified."
        )

        await self.save_crawled_data(items)
        return items
